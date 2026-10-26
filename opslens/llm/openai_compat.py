from __future__ import annotations

from typing import Any

from openai import OpenAI

from opslens.llm.base import ProviderConfig


class OpenAICompatProvider:
    def __init__(self, config: ProviderConfig, api_key: str) -> None:
        self.config = config
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=api_key,
            timeout=config.timeout_s,
            max_retries=1,
        )

    def send(self, messages: list[dict[str, str]]) -> str:
        params: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        params.update(self.config.extra_params)
        response = self._client.chat.completions.create(**params)
        content = response.choices[0].message.content
        return content or ""

    def list_models(self) -> list[str]:
        return sorted(model.id for model in self._client.models.list())
