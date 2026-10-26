from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from opslens.config import load_config, load_env_file, project_path
from opslens.llm.base import ChatProvider, LLMBadJSON, LLMResult, LLMUnavailable, ProviderConfig
from opslens.llm.cache import LLMCache, make_cache_key
from opslens.llm.mock import MockProvider
from opslens.llm.openai_compat import OpenAICompatProvider
from opslens.llm.ratelimit import RateLimiter
from opslens.privacy import mask_pii

log = logging.getLogger(__name__)

JSON_RETRY_NUDGE = "Your last reply was not valid JSON. Reply again with only the JSON, nothing else."
MAX_RETRY_WAIT_S = 90.0


def retry_after_seconds(message: str) -> float | None:
    match = re.search(r"try again in (?:(\d+)m)?([\d.]+)(ms|s)", message)
    if not match:
        return None
    minutes = float(match.group(1) or 0)
    value = float(match.group(2))
    seconds = value / 1000.0 if match.group(3) == "ms" else value
    return minutes * 60.0 + seconds


def parse_json_reply(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for open_char, close_char in (("{", "}"), ("[", "]")):
        start = cleaned.find(open_char)
        end = cleaned.rfind(close_char)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMBadJSON(f"reply is not JSON: {text[:120]!r}")


class LLMClient:
    def __init__(
        self,
        providers: list[ChatProvider],
        cache: LLMCache | None = None,
        limiter: RateLimiter | None = None,
        sleep_fn=time.sleep,
    ) -> None:
        if not providers:
            raise LLMUnavailable("no LLM provider configured")
        self.providers = providers
        self.cache = cache
        self.limiter = limiter
        self._sleep = sleep_fn

    def ask_json(self, task: str, system: str, user: str) -> LLMResult:
        masked = mask_pii(user)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": masked.text},
        ]

        cached = self._from_cache(system, masked.text, masked.counts)
        if cached is not None:
            return cached

        errors: list[str] = []
        for provider in self.providers:
            cfg = provider.config
            if self.limiter and not self.limiter.has_daily_budget(cfg.name, cfg.requests_per_day):
                errors.append(f"{cfg.name}: daily budget used up")
                continue
            started = time.perf_counter()
            try:
                text, data = self._send_and_parse(provider, messages)
            except Exception as exc:
                wait = retry_after_seconds(str(exc))
                if wait is not None and wait <= MAX_RETRY_WAIT_S:
                    log.info("LLM provider %s rate-limited; waiting %.0fs", cfg.name, wait)
                    self._sleep(wait + 1.0)
                    try:
                        text, data = self._send_and_parse(provider, messages)
                    except Exception as exc2:
                        exc = exc2
                    else:
                        exc = None
                if exc is not None:
                    log.warning("LLM provider %s failed on task %s: %s", cfg.name, task, exc)
                    errors.append(f"{cfg.name}: {exc}")
                    continue
            if self.cache is not None:
                key = make_cache_key(cfg.model, system, masked.text)
                self.cache.put(key, task, cfg.name, cfg.model, text)
            return LLMResult(
                data=data,
                raw_text=text,
                provider=cfg.name,
                model=cfg.model,
                from_cache=False,
                pii_masked=masked.counts,
                latency_s=time.perf_counter() - started,
            )
        raise LLMUnavailable("all providers failed: " + "; ".join(errors))

    def _from_cache(self, system: str, masked_user: str, counts: dict[str, int]) -> LLMResult | None:
        if self.cache is None:
            return None
        for provider in self.providers:
            key = make_cache_key(provider.config.model, system, masked_user)
            text = self.cache.get(key)
            if text is None:
                continue
            try:
                data = parse_json_reply(text)
            except LLMBadJSON:
                continue
            return LLMResult(data, text, provider.config.name, provider.config.model, True, counts)
        return None

    def _send_and_parse(self, provider: ChatProvider, messages: list[dict[str, str]]) -> tuple[str, Any]:
        text = self._send(provider, messages)
        try:
            return text, parse_json_reply(text)
        except LLMBadJSON:
            retry_messages = messages + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": JSON_RETRY_NUDGE},
            ]
            text = self._send(provider, retry_messages)
            return text, parse_json_reply(text)

    def _send(self, provider: ChatProvider, messages: list[dict[str, str]]) -> str:
        cfg = provider.config
        if self.limiter is not None:
            self.limiter.wait_for_slot(cfg.name, cfg.requests_per_minute)
            self.limiter.record_call(cfg.name)
        return provider.send(messages)


def provider_config(name: str, block: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        kind=block["kind"],
        model=block["model"],
        base_url=block.get("base_url", ""),
        api_key_env=block.get("api_key_env", ""),
        requests_per_minute=int(block.get("requests_per_minute", 10)),
        requests_per_day=int(block.get("requests_per_day", 400)),
        timeout_s=float(block.get("timeout_s", 60)),
        extra_params=dict(block.get("extra_params") or {}),
    )


def build_provider(name: str) -> ChatProvider | None:
    load_env_file()
    cfg = load_config("providers")
    pc = provider_config(name, cfg["providers"][name])
    if pc.kind == "mock":
        return MockProvider(pc)
    api_key = os.environ.get(pc.api_key_env, "")
    if not api_key:
        log.warning("No %s in environment or .env - provider %s skipped", pc.api_key_env, name)
        return None
    return OpenAICompatProvider(pc, api_key)


def build_client(
    names: list[str] | None = None, use_cache: bool = True, db_path: Path | None = None
) -> LLMClient:
    cfg = load_config("providers")
    chosen = names or [cfg["main"], cfg["fallback"]]
    providers = [p for p in (build_provider(n) for n in chosen) if p is not None]
    db_path = db_path or project_path(cfg["cache_db"])
    cache = LLMCache(db_path) if use_cache else None
    return LLMClient(providers, cache=cache, limiter=RateLimiter(db_path))
