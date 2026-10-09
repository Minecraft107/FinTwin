# FinTwin — Viva Guide

Plain-language answers to the questions examiners are most likely to ask. Each answer is short enough to say aloud, and then points to where it can be shown in the code or the running app.

---

### 1. What is a Digital Twin?
A digital twin is a **virtual model of a real system that is kept in sync with it**, and that can be analysed and experimented on without touching the real thing. The idea comes from engineering: a jet engine's twin, fed by sensor data, predicts wear and tests "what if we fly this route?" safely.

It has three properties:
1. It mirrors the current state from real data.
2. It updates when that data changes.
3. It lets you predict and simulate.

### 2. Why is FinTwin a Digital Twin?
It has all three properties, applied to a person's finances:

| Property | In FinTwin | Where |
|---|---|---|
| Mirrors the real system | `TwinState` is rebuilt from the user's real transactions, profile, investments, loans and goals: flows, balances, ratios, and the source of each figure | `services/digital_twin/builder.py` |
| Stays in sync | Every write (transaction, CSV import, profile, holdings, goals) triggers a rebuild of the twin and its monthly history | `recalculate_after_writes` in `digital_twin/service.py` |
| Predict & simulate | Forecasts run on the twin's history; the What-If engine copies the twin, applies changes, and projects both futures with the same formulas | `forecasting/`, `simulation/` |

It is not a database table. It's a *derived* object, computed fresh, and it is the single input to analysis, prediction and simulation. Show it in the app: **Digital Twin page** → current state → health → predicted state → "try a scenario".

### 3. Why not just build an expense tracker?
An expense tracker records the past. FinTwin answers the questions that drive decisions:
- **How healthy am I, and why did it change?** A 0–100 score with component reasons.
- **Where is my spending heading?** Forecasts with a likely range.
- **Can I afford this, and what does it do to my goals?** The simulation runs before the money is spent.
- **What should I change?** Ranked, concrete options, explained by the coach.

The tracker is only the input layer (manual entry and CSV import).

### 4. How is the Financial Health Score calculated?
It has seven components, each mapped to 0–100 by a **piecewise-linear curve anchored on widely used personal-finance guidelines**. The total is their weighted mean.

| Component (weight) | Measures | Anchor example |
|---|---|---|
| Savings (20) | savings ratio | 20% → 80 points (50/30/20 rule) |
| Emergency fund (20) | months of essentials + EMIs covered | 3 months → 70, 6+ → 100 |
| Debt (20) | EMI ÷ income | 36% → 50 (common lending ceiling) |
| Cash-flow stability (15) | share of positive months + spending variability | — |
| Investments (10) | contribution rate + diversification | 10% → 70 |
| Goals (10) | how much of each goal's required saving the surplus can fund | priority-weighted |
| Spending behaviour (5) | discretionary share + recent high-severity anomalies | ≤ 30% → 100 |

If a component can't be measured (e.g. no goals), it is **dropped and the other weights renormalised**, so missing data is never punished. Grades: A ≥ 85, B ≥ 70, C ≥ 55, D ≥ 40, otherwise E.

"Why did my score change?" compares each component's points now and N months ago, and names the biggest drivers. Show it with `GET /api/health-score/methodology` (the anchors, served from the code itself) and the Digital Twin page's "How it's calculated" table.

### 5. How does forecasting work?
The task is to predict next month's spending per category, sum the categories to a total, and give a likely range.
- **Models:** four simple baselines (naive, 3-month average, same month last year, Holt damped trend) and one **global XGBoost** model.
- **Global, not per-user:** one user has only ~24 monthly points, too few to train on. So XGBoost is trained offline on a synthetic population of 300 users. Each series is divided by the user's own recent level, so one model fits every income level.
- **Features:** lags 1/2/3/6/12, rolling means and std, month (sin/cos), festive flag, category.
- **Champion–challenger:** for each user, XGBoost is used unless a baseline was ≥ 20% better on that user's own last 6 months. A user whose behaviour the model doesn't fit therefore gets a simple, robust model automatically.
- **Range:** forecast ± 1.28 · σ · √h (about 80%), where σ is the backtest error on the user's history, with a floor so we never claim false certainty.

**Result on 60 unseen users:** MAE ₹5,312 and R² 0.87 for XGBoost, against ₹6,975 / 0.78 for the best baseline (`docs/ml.md` §2).

### 6. Why use XGBoost?
- **Tabular data with lag features** is where gradient-boosted trees are strongest. They capture non-linear effects (festive spikes, interactions between category and season) without feature scaling and with little tuning.
- **Small and fast:** training takes seconds, inference microseconds. It needs no GPU, unlike deep sequence models (LSTMs), which would also need far more data.
- **Robust loss:** we use absolute-error loss, which is 25% better than squared error here, because spending has one-off spikes.
- **Explainable:** feature importance shows it relies on recent averages and lags (`mean3`, `std3`, `lag1`), which matches intuition.
- **We proved it rather than assumed it:** it was compared against four baselines on held-out users, and the production rule still falls back to them.

### 7. How does anomaly detection work?
Detection is **unsupervised**: there are no labels in real life, so nothing is trained on them.
- **Robust rule:** within each category, how far a transaction's log-amount is from the median, in MAD units (a robust z-score that outliers can't distort). It flags z ≥ 3.5 *and* ≥ 3× the typical amount.
- **Isolation Forest:** fitted per user on amount, category z, weekday and day of month. Anomalies are points that random splits isolate quickly.
- **Severity:** both agree → HIGH; the rule alone → MEDIUM; the forest alone is ignored, because it's too noisy (F1 0.27 by itself).
- **Plus:**
  - exact duplicate charges;
  - abnormal months (≥ 2 sd above the previous 6, *and* ≥ 25% above the same month last year, so Diwali isn't flagged every October);
  - category drift (sustained increase or a spike);
  - ratio rules (savings < 10%, EMIs > 36% of income, emergency fund < 3 months, …).

**Evaluation:** we planted labelled anomalies in synthetic users. Production alerts reach F1 0.79 (`docs/ml.md` §3).

### 8. How does What-If Simulation work?
It is a **month-by-month cash-flow projection**, run twice: once without the change (the baseline) and once with it.
1. Start from the twin: income, spending, EMIs, SIPs, balances and goals.
2. Apply the scenario's changes. There are 8 types, and they can be combined: big purchase (optionally on EMI), income change, spending change, SIP change, new loan, save more, delay a goal, one-time income.
3. Each month: cash += income − spending − EMIs − SIPs − goal contributions. Investments compound, loans amortise with the standard EMI formula, and if cash goes negative the emergency fund covers it. Anything beyond that is a *shortfall*.
4. Compare the two futures at 12 months: cash, net worth, surplus, health score (computed with the same scoring code), and goal dates.
5. Assign a risk level by rule (any shortfall → CRITICAL, …), and list every assumption.

Live demo: dashboard **Quick what-if** with ₹1,30,000, then ₹4,00,000. The first is LOW risk; the second is CRITICAL, with the month the money runs out.

### 9. Why is simulation deterministic rather than LLM-generated?
- **Correctness:** LLMs are poor at multi-step arithmetic and can produce plausible but wrong numbers. A financial decision tool can't do that.
- **Reproducibility:** the same inputs always give the same output, so results can be tested and audited. Our tests check scenarios against hand calculations (EMI formula, a ₹1.3 lakh purchase, a 20% income cut).
- **Explainability:** every number traces to a formula and a listed assumption.
- **Cost and availability:** it works offline, with no API key.

The LLM's role is to **explain** the engine's output in plain language, never to produce it.

### 10. What is RAG?
**Retrieval-Augmented Generation:** before a language model answers, the system *retrieves* relevant passages from a trusted document collection and gives them to the model as context. The answer is then based on those sources rather than only on what the model memorised. The basic steps:
1. Split the documents into chunks.
2. Turn each chunk into a vector (an embedding).
3. For a question, find the chunks whose vectors are most similar.
4. Pass those chunks to the generator along with the question.

### 11. Why use RAG?
- **Grounded general knowledge:** concepts like the 50/30/20 rule, emergency funds or how SIPs compound come from **our own vetted guides**, not the model's memory, which may be wrong or not suited to India.
- **Citations:** every answer lists the guides it used, so the user can check them.
- **Updatable without retraining:** edit a markdown guide and the index rebuilds automatically.
- **Our implementation:** 13 guides, ~120-word chunks, hybrid TF-IDF + LSA embeddings in a NumPy vector store. TF-IDF matches exact terms like "EMI"; LSA matches meaning, so "rainy day savings" finds *Emergency funds*. It scores hit@3 100% on 20 test questions, with no GPU dependency.

### 12. How does the AI Coach access user data?
It never queries the database freely, and the LLM never sees raw tables.
1. **Intent detection** works out what kind of question it is (affordability, score change, overspending, goals, …).
2. **Entities** are parsed: amounts ("1.3 lakh" → 130000), percentages, months, goal names.
3. The **context builder** calls the same services the app uses (twin, health score, forecast, risks, goal planner) and includes **only the sections that intent needs**.
4. Affordability and what-if questions are turned into a scenario and run through the **simulation engine**.
5. That structured, verified context (plus retrieved guides) is what the provider receives.

All of this is scoped to the logged-in user's id from the JWT, so one user can never see another's data.

### 13. How does the system prevent hallucination?
It uses several layers:
1. **Numbers are computed before the LLM is involved.** The prompt gives verified figures and instructs the model to explain, not calculate.
2. **Grounding check** (`coach/grounding.py`): every ₹ amount, percentage and decimal in the LLM's answer must match a number in the context within 1%. Lakh and crore are understood. One unverifiable number rejects the whole answer.
3. **Fallback:** a rejected, malformed or timed-out answer is replaced by the **deterministic local answer**, built from templates over the same context. It is correct by construction, and it's also the default when no API key is set.
4. **RAG** for general knowledge, with sources shown.
5. **Scope rules:** no specific securities or buy/sell instructions; the disclaimer is always shown.

For example, an answer containing "₹7,720 × 12 = ₹92,640" is rejected, because ₹92,640 isn't in the data.

### 14. What is the difference between prediction and simulation?
| | Prediction (forecasting) | Simulation (What-If) |
|---|---|---|
| Question | What will *probably* happen if I carry on? | What *would* happen if I do X, under stated assumptions? |
| Method | Statistical / ML, learned from history | Deterministic formulas |
| Output | An estimate with an uncertainty range | An exact consequence of the assumptions |
| Same inputs twice | Same model gives the same output, but it's an estimate | Always identical, and checkable by hand |
| In FinTwin | Forecasts page, the predicted state on the twin | Simulator, coach affordability answers |

The simulator deliberately uses trailing averages rather than ML forecasts as its baseline, so that every simulated number stays reproducible.

### 15. What makes this an AI/ML project?
- **Supervised ML:** a global XGBoost spending forecaster, and a TF-IDF + Logistic Regression transaction categorizer. Both are trained offline and evaluated on held-out data against baselines.
- **Unsupervised ML:** Isolation Forest plus robust statistics for anomaly detection, scored on labelled injected anomalies.
- **NLP / IR:** entity extraction for Indian amount formats, and a RAG retrieval system with TF-IDF + LSA embeddings and a measured hit rate.
- **Generative AI:** an LLM coach (OpenAI / Gemini) with grounding verification and a safe fallback.
- **ML engineering:** a training pipeline separate from serving, shared feature code (no train/serve skew), versioned artifacts, metrics files, model-status endpoint, graceful fallbacks, and documented negative results (the first XGBoost run scored R² −10, and we explain why and how it was fixed).

AI is used where it adds value, and deterministic code where correctness matters. That split is a deliberate design decision.

### 16. What are the limitations?
- **Synthetic data:** models are trained and evaluated on generated personas, because no labelled Indian household dataset is public. This shows the methods work as designed, not real-world accuracy.
- **Categorizer:** ~62% on merchants it has never seen; pure brand names can't be categorized from text (user corrections are remembered).
- **Forecasts:** income is held at its recent median; categories are independent; ranges assume normal errors.
- **Simulation:** no taxes, no market volatility, and cash earns nothing.
- **Coach:**
  - Intent detection is rule-based.
  - Live LLM calls are tested only with mocks; the local provider is the default.
- **Security trade-off:** the token is stored in `localStorage`.

### 17. What future improvements can be made?
- Retrain and re-evaluate on consented, anonymised real data; monitor forecast error as months close.
- Import through India's Account Aggregator framework instead of CSV files.
- Monte-Carlo simulation (uncertain income and returns) alongside the deterministic engine.
- Sentence-transformer embeddings or pgvector for retrieval; a trained intent classifier once real questions exist.
- Tax-aware planning, insurance adequacy, retirement planning; household accounts; notifications; a mobile app.

---

## Demo script (5 minutes)
1. **Dashboard** (demo account): the score, KPIs, alerts. *"Every number comes from the API; nothing is hard-coded."*
2. **Digital Twin:** observed vs declared sources → score components and "how it's calculated" → predicted state.
3. **Transactions → Import CSV:** download the sample statement and upload it. Show the per-row status, auto-categories, and a category correction that is remembered.
4. **Forecasts:** the model chosen, its backtest, and the likely range.
5. **Simulator:** a ₹4,00,000 purchase → CRITICAL, the month cash runs out, the goals delayed, the assumptions listed.
6. **Coach:** "Can I afford a laptop for 1.3 lakh?" → the simulation behind the answer, with sources. Then "Which stock should I buy?" → the educational redirect.
7. **Risks:** a planted anomaly with its explanation and recommended action.
