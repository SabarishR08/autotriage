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


def retry_with_backoff(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    backoff_factor: float = 1.0,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    """Execute callable with exponential backoff retry logic (default max 3 attempts)."""
    attempt = 0
    while attempt < max_attempts:
        try:
            return func(*args, **kwargs)
        except retry_exceptions:
            attempt += 1
            if attempt >= max_attempts:
                raise
            time.sleep(backoff_factor * (2 ** (attempt - 1)))
    return func(*args, **kwargs)


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
                "openai package not installed"
            ) from exc
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def analyze(self, stack_trace: str, source_context: str) -> dict[str, Any]:
        prompt = f"Stack Trace:\n{stack_trace}\n\nSource Context:\n{source_context}"
        try:
            def _call():
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )

            response = rate_limit_aware_call(_call)
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as exc:
            raise LLMProviderError(f"OpenAI analysis failed: {exc}") from exc


class AnthropicProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str):
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMProviderError(
                "anthropic package not installed"
            ) from exc
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def analyze(self, stack_trace: str, source_context: str) -> dict[str, Any]:
        prompt = f"Stack Trace:\n{stack_trace}\n\nSource Context:\n{source_context}"
        try:
            def _call():
                return self.client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )

            response = rate_limit_aware_call(_call)
            content = response.content[0].text
            return json.loads(content)
        except Exception as exc:
            raise LLMProviderError(f"Anthropic analysis failed: {exc}") from exc


def get_llm_provider() -> BaseLLMProvider:
    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower()
    if provider == "openai":
        return OpenAIProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL or "gpt-4o",
        )
    elif provider == "anthropic":
        return AnthropicProvider(
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL or "claude-3-5-sonnet-20241022",
        )
    else:
        raise LLMProviderError(f"Unsupported LLM provider: {provider}")
