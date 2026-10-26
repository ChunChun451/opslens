from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ProviderConfig:
    name: str
    kind: str
    model: str
    base_url: str = ""
    api_key_env: str = ""
    requests_per_minute: int = 10
    requests_per_day: int = 400
    timeout_s: float = 60.0
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResult:
    data: Any
    raw_text: str
    provider: str
    model: str
    from_cache: bool
    pii_masked: dict[str, int]
    latency_s: float = 0.0


class ChatProvider(Protocol):
    config: ProviderConfig

    def send(self, messages: list[dict[str, str]]) -> str: ...


class LLMUnavailable(RuntimeError):
    pass
class LLMBadJSON(ValueError):
    pass
