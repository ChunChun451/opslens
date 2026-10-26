from __future__ import annotations

import json
from typing import Callable

from opslens.llm.base import ProviderConfig


class MockProvider:
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
        self._fail_times = fail_times
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
