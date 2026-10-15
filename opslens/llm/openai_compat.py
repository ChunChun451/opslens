"""Talk to any OpenAI-compatible chat API (Gemini, Groq, ...) with the `openai` SDK.

Why this design:
- Gemini and Groq both expose the OpenAI chat format, so one small class covers both;
  only base_url, model and key differ (config/providers.yaml).
- We ask for JSON output (`response_format = json_object`) and temperature 0, because the
  engine needs structured, repeatable answers, not creative text.
- `max_retries=1`: on the free tier a 429 usually means "daily quota used up", and
  retrying many times only wastes minutes. The client falls back to the next provider.

Example:
    provider = OpenAICompatProvider(config, api_key="...")
    provider.send([{"role": "user", "content": 'Return {"ok": true}'}])  ->  '{"ok": true}'
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from opslens.llm.base import ProviderConfig


class OpenAICompatProvider:
    """One OpenAI-compatible endpoint."""

    def __init__(self, config: ProviderConfig, api_key: str) -> None:
        self.config = config
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=api_key,
            timeout=config.timeout_s,
            max_retries=1,
        )

    def send(self, messages: list[dict[str, str]]) -> str:
        """Send the chat messages and return the reply text ('' if the reply is empty)."""
        params: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        # Provider-specific extras from config, e.g. reasoning_effort for gpt-oss.
        params.update(self.config.extra_params)
        response = self._client.chat.completions.create(**params)
        content = response.choices[0].message.content
        return content or ""

    def list_models(self) -> list[str]:
        """Model IDs this key can use. Used by the ping script to verify names on day 1."""
        return sorted(model.id for model in self._client.models.list())
