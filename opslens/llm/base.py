"""Shared types for the LLM layer: provider settings, the result object and errors.

Why this design:
- A provider is anything with a `send(messages) -> str` method. Real providers
  (openai_compat.py) and the test provider (mock.py) both follow this shape, so the
  client does not care which one it talks to. No inheritance needed.
- `ProviderConfig` is filled from config/providers.yaml, so changing a model name is a
  config edit, not a code change.

Example:
    >>> cfg = ProviderConfig(name="mock", kind="mock", model="mock-1")
    >>> cfg.requests_per_minute
    10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ProviderConfig:
    """Settings for one LLM provider (one block in config/providers.yaml)."""

    name: str
    kind: str  # "openai_compat" or "mock"
    model: str
    base_url: str = ""
    api_key_env: str = ""
    requests_per_minute: int = 10
    requests_per_day: int = 400
    timeout_s: float = 60.0
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResult:
    """What the client returns: parsed JSON plus where it came from."""

    data: Any  # parsed JSON (dict or list)
    raw_text: str
    provider: str
    model: str
    from_cache: bool
    pii_masked: dict[str, int]  # e.g. {"[PHONE]": 1} — what was masked before sending
    latency_s: float = 0.0


class ChatProvider(Protocol):
    """Anything that can answer a chat request with text."""

    config: ProviderConfig

    def send(self, messages: list[dict[str, str]]) -> str: ...


class LLMUnavailable(RuntimeError):
    """Raised when every provider failed or is out of daily budget."""


class LLMBadJSON(ValueError):
    """Raised when a reply cannot be parsed as JSON even after one retry."""
