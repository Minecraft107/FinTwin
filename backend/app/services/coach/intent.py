"""Intent detection by transparent keyword scoring.

Each intent has weighted regular expressions; the highest total wins, and below a minimum
score the question is treated as a general concept question (answered from the knowledge
base). Rules were chosen over a trained classifier on purpose: there is no real labelled
question data to learn from, and deterministic rules are easy to test, explain and extend.
"""

import re
from dataclasses import dataclass

# (intent, [(pattern, weight), ...]) — order breaks ties.
RULES: list[tuple[str, list[tuple[str, float]]]] = [
    (
        "out_of_scope",
        [
            (r"\bwhich (stock|share|fund|mutual fund|crypto)", 3),
            (r"\b(best|top|good) (stock|share|fund|mutual fund|crypto|coin)s?\b", 3),
            (r"\b(buy|sell) (shares?|stocks?|crypto|bitcoin)\b", 3),
            (r"\b(bitcoin|crypto|intraday|options trading|f&o)\b", 2),
            (r"\b(stock tips?|multibagger)\b", 3),
        ],
    ),
    (
        "affordability",
        [
            (r"\bcan i (afford|buy|purchase)\b", 3),
            (r"\b(afford|affordable)\b", 2),
            (r"\bshould i (buy|purchase|get)\b", 2),
            (r"\b(buy|purchase|buying)\b", 1),
        ],
    ),
    (
        "what_if",
        [
            (r"\bwhat (happens|would happen|if)\b", 3),
            (r"\bif i\b", 1.5),
            (r"\b(take|taking|get) an? .*\bloan\b", 2),
            (
                r"\b(increase|raise|reduce|decrease|stop|start|cut)s? (my )?"
                r"(sip|salary|income|expenses?|spending)",
                2,
            ),
            (r"\b(salary|income) (cut|drop|decrease|falls?|goes down)", 2),
            (r"\b(lose|lost) my job\b", 3),
            (r"\b(save|spend) .* (more|less) (every|each|per|a) month", 2),
            (r"\bdelay\b", 1.5),
            (r"\bbonus\b", 1),
        ],
    ),
    (
        "score_explanation",
        [
            (r"\b(health )?score\b", 2),
            (r"\bwhy (did|has|is) my\b", 1),
            (r"\b(grade|rating)\b", 1),
        ],
    ),
    (
        "improve_health",
        [
            (r"\bimprove\b", 2),
            (r"\b(better|healthier|stronger)\b", 1),
            (r"\bwhat should i (do|change|focus)\b", 2),
            (r"\b(tips|advice|suggestions?)\b", 1),
        ],
    ),
    (
        "overspending",
        [
            (r"\boverspend", 3),
            (r"\b(where|what) (am i|do i) (spend|spending|wasting)", 3),
            (r"\bspending too much\b", 3),
            (r"\b(cut|reduce) (my )?(expenses|spending|costs)\b", 2),
            (r"\b(biggest|largest|top) (expenses?|spending|categor)", 2),
            (r"\bspend(ing)?\b", 1),
        ],
    ),
    (
        "emergency_fund",
        [
            (r"\bemergency\b", 3),
            (r"\brainy day\b", 2),
        ],
    ),
    (
        "goal_planning",
        [
            (r"\bgoals?\b", 2),
            (r"\bsave (for|up)\b", 2),
            (r"\bhow much (should|do) i (save|put aside)\b", 2),
            (r"\b(target|on track)\b", 1),
        ],
    ),
    (
        "debt",
        [
            (r"\b(loan|emi|emis|debt|prepay|prepayment|credit card)\b", 2),
            (r"\bdebt[- ]to[- ]income\b", 2),
        ],
    ),
    (
        "forecast",
        [
            (r"\b(next|coming) (month|months|quarter)\b", 2),
            (r"\b(forecast|predict|projection|project)\b", 2),
            (r"\bcash ?flow\b", 1),
            (r"\b(future|expected) (expenses|spending)\b", 2),
        ],
    ),
    (
        "risk",
        [
            (r"\b(risks?|alerts?|warnings?|anomal|unusual|suspicious|duplicate)\b", 2),
        ],
    ),
    (
        "greeting",
        [
            (r"^\s*(hi|hello|hey|namaste|good (morning|evening|afternoon))\b", 2),
            (r"\bwhat can you do\b", 3),
        ],
    ),
]
_COMPILED = [(name, [(re.compile(p, re.IGNORECASE), w) for p, w in rules]) for name, rules in RULES]
MIN_SCORE = 1.5
FALLBACK = "concept_question"
INTENTS = [name for name, _ in RULES] + [FALLBACK]


@dataclass(frozen=True)
class Intent:
    name: str
    score: float
    scores: dict[str, float]


def detect(text: str) -> Intent:
    scores = {
        name: sum(weight for pattern, weight in rules if pattern.search(text))
        for name, rules in _COMPILED
    }
    best = max(scores, key=lambda n: scores[n])  # dict order = RULES order breaks ties
    if scores[best] < MIN_SCORE:
        return Intent(FALLBACK, 0.0, scores)
    return Intent(best, scores[best], scores)
