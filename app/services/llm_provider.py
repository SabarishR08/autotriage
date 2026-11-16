"""
LLM provider abstraction.

AutoTriage never bundles or charges for LLM usage — the caller supplies
their own API key (env var LLM_API_KEY) for whichever provider they set
via LLM_PROVIDER ("openai" | "anthropic"). Both providers are called with
the same prompt contract and must return the same JSON shape.
"""

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, TypeVar

from app.core.config import get_settings

T = TypeVar("T")

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


def rate_limit_aware_call(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    **kwargs: Any,
) -> T:
    """Execute callable and sleep/retry if a rate limit error (429) occurs."""
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            status_code = getattr(exc, "status_code", getattr(exc, "code", None))
            is_429 = (
                status_code == 429
                or "429" in str(exc)
                or "rate limit" in str(exc).lower()
            )
            if is_429 and attempt < max_retries:
                time.sleep(backoff_factor * (2**attempt))
            else:
                raise


class BaseLLMProvider(ABC):
    @abstractmethod
    def analyze(self, stack_trace: str, source_context: str) -> dict[str, Any]:
        """Return a dict matching the schema documented in SYSTEM_PROMPT."""


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError(
                "openai package not installed. Run: pip install openai"
            ) from exc
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model

    def analyze(self, stack_trace: str, source_context: str) -> dict[str, Any]:
        response = rate_limit_aware_call(
            self._client.chat.completions.create,
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
        response = rate_limit_aware_call(
            self._client.messages.create,
            model=self._model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Stack trace:\n{stack_trace}\n\nSource context:\n{source_context}",
                }
            ],
            temperature=0,
        )
        content = response.content[0].text
        return _parse_json_response(content)


def _parse_json_response(content: str | None) -> dict[str, Any]:
    if not content:
        raise LLMProviderError("Empty response from LLM provider")
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(f"Failed to parse LLM JSON response: {exc}") from exc

    required_keys = {
        "root_cause",
        "affected_files",
        "confidence",
        "suggested_fix",
        "patch_diff",
    }
    if not isinstance(data, dict) or not required_keys.issubset(data.keys()):
        raise LLMProviderError(f"LLM response missing required keys: {cleaned}")
    return data


def get_llm_provider() -> BaseLLMProvider:
    settings = get_settings()
    provider = (settings.LLM_PROVIDER or "openai").lower()
    api_key = settings.LLM_API_KEY
    if not api_key:
        raise LLMProviderError("LLM_API_KEY environment variable is not set")
    model = settings.LLM_MODEL
    if provider == "openai":
        return OpenAIProvider(
            api_key=api_key,
            model=model or "gpt-4o",
            base_url=settings.LLM_BASE_URL,
        )
    elif provider == "anthropic":
        return AnthropicProvider(
            api_key=api_key,
            model=model or "claude-3-5-sonnet-20241022",
        )
    else:
        raise LLMProviderError(f"Unsupported LLM_PROVIDER: '{provider}'")
