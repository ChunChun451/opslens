"""A fake LLM provider for tests and offline runs. No network, fully predictable.

Why this design:
- Tests must not depend on Google or Groq being up, or on our free quota.
- Two modes:
  1. `replies=[...]`: return these strings in order (lets a test simulate a broken reply,
     then a good one).
  2. `handler=fn`: compute a reply from the messages (later used to fake classification).
  Default (neither given): echo a small valid JSON object.
- `sent` records every request, so a test can check that PII was masked BEFORE sending.

Example:
    >>> p = MockProvider(replies=['{"ok": true}'])
    >>> p.send([{"role": "user", "content": "hi"}])
    '{"ok": true}'
"""

from __future__ import annotations

import json
from typing import Callable

from opslens.llm.base import ProviderConfig


class MockProvider:
    """Predictable stand-in for a real LLM."""

    def __init__(
        self,
        config: ProviderConfig | None = None,
        replies: list[str] | None = None,
        handler: Callable[[list[dict[str, str]]], str] | None = None,
        fail_times: int = 0,
    ) -> None:
        self.config = config or ProviderConfig(name="mock", kind="mock", model="mock-1")
        self._replies = list(replies or [])
        self._handler = handler
        self._fail_times = fail_times  # raise an error this many times first (tests fallback)
        self.sent: list[list[dict[str, str]]] = []

    def send(self, messages: list[dict[str, str]]) -> str:
        self.sent.append(messages)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise ConnectionError("mock provider: simulated outage")
        if self._replies:
            return self._replies.pop(0)
        if self._handler is not None:
            return self._handler(messages)
        user_text = messages[-1]["content"]
        return json.dumps({"mock": True, "chars": len(user_text)})
