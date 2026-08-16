"""
LLM provider abstraction.

AutoTriage never bundles or charges for LLM usage — the caller supplies
their own API key (env var LLM_API_KEY) for whichever provider they set
via LLM_PROVIDER ("openai" | "anthropic"). Both providers are called with
the same prompt contract and must return the same JSON shape.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings

SYSTEM_PROMPT = """You are a senior backend engineer performing root cause \
analysis on a production error. You will be given a stack trace and one or \
more relevant source files. Identify the root cause, the files that need to \
change, and propose a concrete fix.

Respond with ONLY a JSON object in this exact shape, no prose, no markdown \
fences:

{
  "root_cause": "<one or two sentence explanation>",
  "affected_files": ["<path/to/file.py>", ...],
  "confidence": "<low|medium|high>",
  "suggested_fix": "<description of the fix>",
  "patch_diff": "<a unified diff implementing the fix, or null if not enough context>"
}
"""


class LLMProviderError(RuntimeError):
    """Raised when the configured LLM provider fails or is misconfigured."""


class BaseLLMProvider(ABC):
    @abstractmethod
    def analyze(self, stack_trace: str, source_context: str) -> dict[str, Any]:
        """Return a dict matching the schema documented in SYSTEM_PROMPT."""


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError(
                "openai package not installed. Run: pip install openai"
            ) from exc
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def analyze(self, stack_trace: str, source_context: str) -> dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Stack trace:\n{stack_trace}\n\nSource context:\n{source_context}",
                },
            ],
            temperature=0,
        )
        return _parse_json_response(response.choices[0].message.content)


class AnthropicProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError(
                "anthropic package not installed. Run: pip install anthropic"
            ) from exc
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def analyze(self, stack_trace: str, source_context: str) -> dict[str, Any]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Stack trace:\n{stack_trace}\n\nSource context:\n{source_context}",
                }
            ],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return _parse_json_response(text)


def _parse_json_response(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(f"LLM response was not valid JSON: {exc}") from exc


def get_llm_provider() -> BaseLLMProvider:
    settings = get_settings()
    if not settings.LLM_API_KEY:
        raise LLMProviderError(
            "LLM_API_KEY is not set. AutoTriage requires the caller's own "
            "LLM API key — set it via environment variable."
        )

    if settings.LLM_PROVIDER == "openai":
        return OpenAIProvider(settings.LLM_API_KEY, settings.LLM_MODEL)
    if settings.LLM_PROVIDER == "anthropic":
        return AnthropicProvider(settings.LLM_API_KEY, settings.LLM_MODEL)

    raise LLMProviderError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")
