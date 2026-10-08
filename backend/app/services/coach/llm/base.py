"""LLM provider abstraction. Providers only turn a prompt into text; they never see the
database and never compute anything. Any failure raises LLMError, and the coach falls back
to the deterministic local answer."""

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class CoachAnswer(BaseModel):
    """The only shape an answer may take: what is fact, calculation, prediction or advice."""

    summary: str = Field(min_length=1, max_length=1500)
    facts: list[str] = Field(default_factory=list, max_length=8)  # the user's own data
    calculations: list[str] = Field(default_factory=list, max_length=8)  # backend results
    predictions: list[str] = Field(default_factory=list, max_length=8)  # forecasts/projections
    recommendations: list[str] = Field(default_factory=list, max_length=8)
    background: list[str] = Field(default_factory=list, max_length=4)  # general knowledge

    def text(self) -> str:
        """All answer text, for the grounding check."""
        return "\n".join(
            [
                self.summary,
                *self.facts,
                *self.calculations,
                *self.predictions,
                *self.recommendations,
                *self.background,
            ]
        )


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, system: str, user: str) -> str:
        """Return the model's raw text reply (expected to be a JSON object)."""


def post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed https URLs)
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        raise LLMError(f"HTTP {e.code} from the LLM provider") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise LLMError(f"LLM request failed: {e.__class__.__name__}") from e
