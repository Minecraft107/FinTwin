# FinTwin — Machine Learning

This document covers what each model does, how it was trained and evaluated, the actual results, and the limitations. All numbers below come from `ml/models/metrics/*.json`, which is written by the pipeline on every run. Re-running it updates them.

```bash
flask ml train            # from backend/  (≈ 90 s on a laptop)
python -m ml.pipeline     # same, from the repository root
```
Docker images run the same pipeline at build time. XGBoost results differ by about 1–2% between operating systems, because multithreaded histogram building sums floats in a different order (a Linux build gave MAE ₹5,387 against ₹5,312 below); the categorizer and anomaly metrics reproduce exactly. The committed metrics come from a Windows run.

Training is separate from inference. `ml/` builds the data, trains, evaluates and saves artifacts to `ml/models/`. The backend only loads those artifacts (`app/services/ml/artifacts.py`). If an artifact is missing or corrupt, every feature falls back to a non-ML method, and `GET /api/ml/status` shows which artifacts are loaded.

Feature engineering lives once, in `backend/app/services/ml/features.py`, and the training code imports it. So training and serving cannot drift apart.

## 1. Data

There is no public dataset of individual Indian household transactions with labels, so models are trained and evaluated on a **synthetic population** (`ml/datasets/population.py`): 300 randomised personas × 30 months ≈ 404,000 transactions. They come from the same generator as the demo user (`app/seed/synthetic.py`). Each persona varies in:
- salary (₹25k–₹4L), raise timing, bonus month
- rent and family-support shares
- spending intensity per category
- festive multiplier, food-delivery "creep"
- SIPs, EMIs
- 0–3 injected anomalies (oversized purchases, hospital bills, duplicate charges, travel-heavy months), with ground-truth labels

> **Main limitation:** evaluating on data from our own generator is partly circular. The patterns the models find (festive seasonality, category scale) are patterns we put there. The evaluation therefore shows that each method works as designed and compares methods fairly; it does not show accuracy on real users. With real, consented data the same pipeline would be re-run unchanged.

## 2. Expense forecasting

**Task:** predict next month's consumption spending per category (EMIs and SIPs are scheduled, not predicted), then sum the categories to a total.

**Models** (`app/services/forecasting/models.py`):

| Model | Idea |
|---|---|
| Naive | next month = this month |
| 3-month moving average | mean of the last 3 months |
| Seasonal naive | same month last year (needs 12 months) |
| Holt damped trend | exponential smoothing with level and damped trend; parameters chosen by in-sample one-step SSE over a small grid (pure NumPy) |
| **XGBoost (global)** | One regressor trained across all synthetic users and categories. Each series is divided by its own recent level, so one model serves a ₹30k and a ₹3L earner alike. Features: lags 1/2/3/6/12, 3- and 6-month means, 3-month std, month-of-year (sin/cos), festive flag, category id. Multi-month forecasts are recursive (each prediction is fed back as a lag) |

**Why a global model?** One user has about 24 monthly points per category, far too few to train XGBoost per user. Pooling many users gives about 100,000 training rows while each user keeps their own scale.

**Evaluation protocol** (`ml/training/forecaster.py`). There is no leakage across users or time:
- Users are split 80/20.
- The model is trained on train users only, excluding their final 3 months.
- Each of the final 3 months of every held-out user is predicted one step ahead, from the true history before it.
- All models are scored on exactly the same targets.
- The shipped artifact is then refit on all data.

**Results** (60 held-out users × 3 months; total monthly spending):

| Strategy | MAE | RMSE | R² |
|---|---|---|---|
| XGBoost (always) | **₹5,312** | ₹8,082 | **0.872** |
| **Production rule** (champion–challenger, below) | ₹5,500 | — | 0.860 |
| Seasonal naive | ₹6,975 | ₹10,483 | 0.784 |
| Holt damped trend | ₹7,973 | ₹10,330 | 0.791 |
| 3-month moving average | ₹8,544 | ₹11,054 | 0.760 |
| Naive | ₹11,674 | ₹15,364 | 0.537 |

At category level (2,700 category-months), XGBoost has an MAE of ₹699 and R² of 0.916, against ₹890 / 0.866 for the best baseline. The most important features are `mean3`, `std3`, `lag1` and `lag2`.

**Engineering findings** (kept here because they shaped the design):
1. **Scale bug.** The first XGBoost run scored R² = −10. A category with no prior spending got scale 1, so a first ₹2,000 purchase became a target of 2,000 instead of a ratio near 1. Rows with an all-zero history are now skipped in training and inference (`features.training_rows`).
2. **Loss function.** Absolute-error loss beat squared error by about 25% in MAE, because targets contain one-off spikes that squared error over-weights.
3. **Model selection.** Picking, per user, whichever model had the lowest error over the last 3 months (MAE ₹6,141) was *worse* than always using XGBoost, because a 3-point backtest is noisy. Tested alternatives on the held-out users:

   | Selection rule | MAE |
   |---|---|
   | lowest backtest MAE, 3 origins | ₹6,141 |
   | lowest backtest MAE, 6 origins | ₹6,158 |
   | XGBoost unless a baseline is ≥ 20% better, 3 origins | ₹5,659 |
   | **XGBoost unless a baseline is ≥ 20% better, 6 origins** (adopted) | ₹5,500 |
   | always XGBoost | ₹5,312 |

   The adopted **champion–challenger** rule costs 3.5% against "always XGBoost" on synthetic data. In return, if the synthetic-trained model clearly fails on a real user's spending, a simple baseline takes over automatically. The evaluation calls the same `select_model` function the API uses.

**Uncertainty.** The likely range is an empirical ~80% band, `forecast ± 1.28·σ·√h`, where σ is the selected model's backtest RMSE on the user's own history and h is the months ahead. σ is floored at 5% of recent monthly spending, because a 3–6 point backtest on a very steady history can show near-zero error, and certainty can't be claimed from so few points. With fewer than 4 complete months no backtest is possible, so a ±20% band is shown and labelled as a rule of thumb.

**Cash flow** = income (median of the last 3 months, so one-off bonuses aren't assumed to repeat) − forecast spending − scheduled EMIs (stopping when each loan's tenure ends) − SIPs. The projected cash balance carries cumulative uncertainty (√Σσ²).

## 3. Anomaly & risk detection

Detection is unsupervised: nothing is trained on labels. The injected labels are used only to score.

**Transaction level** (`app/services/analytics/anomalies.py`):
- **Robust rule:** robust z-score of log(amount) within the transaction's own category (median and MAD), with z ≥ 3.5 *and* the amount at least 3× the category median. Categories with fewer than 8 transactions are not judged.
- **Isolation Forest:** fitted per user on [log amount, category z, weekday, day of month], with contamination 0.02. Only used with at least 60 expense transactions.
- **Severity:** both agree → HIGH (CRITICAL if the amount is ≥ 50% of monthly income); rule only → MEDIUM; forest only (with z ≥ 2.5) → LOW, which is never alerted.
- **Duplicates:** same date, amount and description. Reference numbers are kept, so two different UPI payments are not duplicates.

| Detector (300 users, 323 labelled anomalies) | Precision | Recall | F1 |
|---|---|---|---|
| **Production alerts (MEDIUM+)** | 0.65 | 1.00 | **0.79** |
| Robust rule only (large purchases) | 0.56 | 1.00 | 0.72 |
| Isolation Forest only | 0.15 | 1.00 | 0.27 |
| Rule AND forest (→ HIGH) | 0.62 | 1.00 | 0.77 |
| Duplicate detector | 1.00 | 1.00 | 1.00 |

The forest alone is noisy, but agreement between the forest and the robust rule is more precise than the rule alone. That's why agreement sets the HIGH severity. Some "false positives" are genuinely unusual but unlabelled purchases from the generator's heavy-tailed amounts, so precision is pessimistic. Recall is optimistic, because injected anomalies are pronounced (≥ 3× typical).

**Month level:**
- **Abnormal month:** total spending ≥ 2 sd above the previous 6 months.
- **Seasonal check:** once a year of history exists, the month must also be ≥ 25% above the same month last year.
- **Category drift:** a category's last 3 months vs the 3 before (a sustained trend), or its last month vs the previous 3 (a spike), with at least +25–30% *and* +₹2,000.

| Month-level detection | Precision | Recall | F1 |
|---|---|---|---|
| Without the seasonal check | 0.28 | 0.74 | 0.41 |
| With the seasonal check, all evaluable months | 0.51 | 0.67 | 0.58 |
| **With the seasonal check, months with 12+ months of history** | **0.76** | 0.64 | **0.69** |

The seasonal check was added after the first evaluation showed festive Octobers and annual-premium Junes being reported as anomalies every year.

**Risk rules** (`app/services/analytics/risk_service.py`) are transparent thresholds on the Digital Twin, using the same anchors as the health score:
- savings < 10% (< 0 → HIGH)
- debt-to-income > 36% (> 50% → CRITICAL)
- emergency fund < 3 months (< 1 → HIGH)
- negative cash flow in 2 of the last 3 months
- cash below one month of outgoings

Alerts are persisted with a stable fingerprint: rescans update them, user dismissals persist, and resolved conditions disappear. Transaction anomalies older than 90 days are kept as history, not raised as live risks.

**Health-score link:** HIGH/CRITICAL transaction anomalies in the 30 days before a snapshot feed the "spending behaviour" component (−35 points per anomaly within its 30% anomaly share). For historical snapshots the detector is fitted once on the full history, a small look-ahead that is accepted and noted here.

## 4. Transaction categorization

The cascade (`app/services/ml/categorizer.py`) is: the user's own past corrections → about 140 keyword rules → **ML classifier** (expenses only, used only if its probability ≥ 0.55) → "Other".

**Model:** TF-IDF of character 3–5-grams + word 1–2-grams, then Logistic Regression (balanced classes). Text goes through the same `normalize_description` function at training and inference. Training data is 349 hand-curated real-world Indian merchants across 16 categories (`ml/datasets/categorizer_corpus.csv`): national brands plus typical local names ("Sri Venkateshwara Provisions", "Om Sai Medicals"). Each is expanded into 8 bank-statement formats (`UPI/48213/…`, `POS 4411 … BLR`, `NEFT/…`).

**Evaluation:** GroupKFold(5) **by merchant**, so every score is on merchant names the model never saw. That is exactly the case the ML stage exists for.

| | Coverage | Accuracy |
|---|---|---|
| Keyword rules alone | 58% | 96.6% when matched; 56.5% overall |
| ML alone (all predictions) | 100% | 48.0% (macro-F1 0.50; 16 classes, chance ≈ 6%) |
| ML when confident (≥ 0.55) | 26.6% | 86.4% |
| ML on the rules' misses, when confident | resolves 14% of misses | **92.7%** |
| **Production cascade** | 100% | **61.9%** (macro-F1 0.71), +5.5 points over rules alone |

**Honest reading:** many merchant names are pure brands with no meaningful text ("Zara", "Toni and Guy"), and no text model can categorize those without outside knowledge. The ML stage adds value on descriptive local names ("…Medicals", "…Provisions", "…Tiffins"), and the threshold keeps it from guessing on the rest. Every user correction is remembered and takes precedence, so accuracy improves with use.

## 5. Retrieval for the AI Coach (RAG)

**Knowledge base:** 13 short, original guides in `backend/knowledge_base/*.md`, covering budgeting (50/30/20), emergency funds, debt and EMIs, savings and cash flow, SIPs and compounding, asset allocation, goal planning, insurance, credit scores, inflation, big purchases, spending patterns, and how the health score works.

**Pipeline** (`app/services/coach/rag.py`):
1. Split each guide at its headings into ~120-word chunks with a 30-word overlap (62 chunks).
2. Embed each chunk two ways: TF-IDF (word 1–2-grams), and LSA (TruncatedSVD, up to 64 dimensions) on top of it.
3. Score chunks against the query by hybrid cosine similarity: 0.5 × TF-IDF + 0.5 × LSA.
4. Return the top 3, at most one chunk per guide. A hit must score at least 0.12 *and* at least half the best hit's score.

TF-IDF catches exact terms ("EMI", "SIP"), and LSA catches related wording: "rainy day savings for job loss" → *Emergency funds*. The index is built in memory in ~60 ms and rebuilt automatically when any guide changes. There's no torch or GPU dependency.

**Evaluation** (`tests/test_coach_nlu.py::RETRIEVAL_SET`, 20 labelled questions):

| | hit@1 | hit@3 |
|---|---|---|
| Hybrid TF-IDF + LSA | 19/20 (95%) | 20/20 (100%) |

Off-topic queries ("best cricket team") retrieve nothing. **Caveat:** the questions were written alongside the guides, so this is a regression check rather than an independent benchmark.

**Intent detection** uses transparent weighted keyword rules, not a trained model. There is no real labelled question data to learn from, and deterministic rules can be tested and explained case by case; 20 example questions are covered by tests.

**Grounding check** (`app/services/coach/grounding.py`):
- Every ₹ amount, percentage and decimal in an LLM answer must match, within 1% (or 0.05 for small values), a number in the context, the retrieved knowledge, or the question. Lakh and crore notation is understood.
- Whole counts up to 12 and years are exempt.
- Anything else, such as "₹7,720 × 12 = ₹92,640", rejects the answer, and the deterministic local answer is used instead.

## 6. Limitations & future work

- **Synthetic training data** (see §1). The next step is a consented, anonymised real dataset run through the same pipeline and evaluation.
- **Forecasting:**
  - Income is projected at its recent median; bonuses and raises are not forecast.
  - Category forecasts are independent (no cross-category effects).
  - Prediction intervals assume roughly normal, independent errors.
- **Anomalies:**
  - The 3× and z ≥ 3.5 thresholds were set by design, not tuned on data.
  - The per-user Isolation Forest is refitted on every recalculation (≈ 0.1–0.3 s); it could be cached per data version.
- **Categorizer:** the corpus is small (349 merchants). Possible upgrades: merchant-category codes from card networks, or sentence embeddings.
- **Monitoring:** the metrics files are regenerated on every training run. Real deployments would also track live forecast error against actuals as months close.
