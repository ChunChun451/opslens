from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opslens.config import load_config
from opslens.llm.client import LLMClient, build_provider

SYSTEM = (
    "You classify food-delivery support tickets. Reply with JSON only: "
    '{"category": one of [late_delivery, missing_item, wrong_item, refund, payment_failure, '
    'app_bug, account, restaurant_partner], "confidence": number between 0 and 1}'
)
TICKET = "Paisa kat gaya but order place nahi hua. Call me on 9876543210 asap"

INTERESTING = ("flash-lite", "flash", "gpt-oss", "llama", "qwen")


def ping(name: str) -> bool:
    provider = build_provider(name)
    if provider is None:
        print(f"[{name}] SKIPPED - no API key in .env")
        return False
    print(f"[{name}] model in config: {provider.config.model}")
    try:
        models = provider.list_models()
        shown = [m for m in models if any(word in m for word in INTERESTING)]
        print(f"[{name}] {len(models)} models visible; relevant: {shown[:15]}")
        if not any(m.endswith(provider.config.model) for m in models):
            print(f"[{name}] WARNING: configured model not in the list - update config/providers.yaml")
    except Exception as exc:
        print(f"[{name}] could not list models: {exc}")

    client = LLMClient([provider], cache=None, limiter=None)
    try:
        result = client.ask_json("ping", SYSTEM, TICKET)
    except Exception as exc:
        print(f"[{name}] FAILED: {exc}")
        return False
    print(f"[{name}] OK in {result.latency_s:.2f}s  json={result.data}  masked={result.pii_masked}")
    return True


def main() -> int:
    cfg = load_config("providers")
    names = [n for n, block in cfg["providers"].items() if block["kind"] != "mock"]
    results = {name: ping(name) for name in names}
    print("SUMMARY:", results)
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
