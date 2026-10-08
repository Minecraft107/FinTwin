from app.services.coach.llm.base import LLMError, LLMProvider, post_json


class OpenAIProvider(LLMProvider):
    name = "openai"
    URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str, timeout: float):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def generate(self, system: str, user: str) -> str:
        body = post_json(
            self.URL,
            {"Authorization": f"Bearer {self.api_key}"},
            {
                "model": self.model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            self.timeout,
        )
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("Unexpected OpenAI response shape") from e


class GeminiProvider(LLMProvider):
    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, timeout: float):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def generate(self, system: str, user: str) -> str:
        body = post_json(
            self.URL.format(model=self.model),
            {"x-goog-api-key": self.api_key},  # header, so the key never appears in a URL
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            },
            self.timeout,
        )
        try:
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError("Unexpected Gemini response shape") from e


def get_provider(config) -> tuple[LLMProvider | None, str | None]:
    """(provider, reason-if-none). None means: use the local deterministic coach."""
    choice = (config.get("LLM_PROVIDER") or "local").lower()
    timeout = float(config.get("LLM_TIMEOUT", 20))
    if choice == "openai":
        if not config.get("OPENAI_API_KEY"):
            return None, "OPENAI_API_KEY is not set"
        return OpenAIProvider(config["OPENAI_API_KEY"], config["OPENAI_MODEL"], timeout), None
    if choice == "gemini":
        if not config.get("GEMINI_API_KEY"):
            return None, "GEMINI_API_KEY is not set"
        return GeminiProvider(config["GEMINI_API_KEY"], config["GEMINI_MODEL"], timeout), None
    return None, None
