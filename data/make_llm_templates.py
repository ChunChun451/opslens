"""One-time: ask an LLM for varied customer messages per category, to make the ticket text
less templated. Output: data/llm_templates.json (committed, with model name and prompt).

Why: with ~10 hand-written templates per category the classifier memorises them (99.9%
accuracy — not believable). Real customers phrase things in endless ways. 32 requests
(8 categories × English/Hinglish × short/long, 20 messages each) give ~600 message patterns.

Model choice: the messages are written by Groq's Qwen, while the cascade classifies with
Gemini, so the classifier is never grading text written by itself. Groq's free tier refuses
requests expecting more than 1,000 output tokens, hence 20 messages per request.

Run once:  .venv/Scripts/python.exe data/make_llm_templates.py   (about 35 minutes: 1 request/min)
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.classify import CATEGORY_HELP  # noqa: E402
from opslens.llm.client import build_client  # noqa: E402

OUT = ROOT / "data" / "llm_templates.json"
ALLOWED_SLOTS = {"{dish}", "{restaurant}", "{side}", "{mins}", "{amount}", "{order_ref}"}
STYLES = {
    "en": "English, casual chat style, some lower-case and small typos, like real app users in India",
    "hi": "Hinglish (Hindi written in Latin letters, mixed with English words), like real chat messages in India",
}
LENGTHS = {"short": "mostly short messages (3 to 12 words)", "long": "mostly longer messages (12 to 30 words)"}
SYSTEM = "You write realistic, varied customer-support messages for training data. Reply with JSON only."


def prompt_for(category: str, language: str, length: str) -> str:
    return (
        f"Write 20 different messages a customer of an Indian food-delivery app might send to support "
        f"about this issue: {CATEGORY_HELP[category]}.\n"
        f"Style: {STYLES[language]}; {LENGTHS[length]}.\n"
        "Vary the tone (angry, polite, confused, sarcastic) and the details. "
        "Where natural, use these placeholders exactly: {dish}, {restaurant}, {side}, {mins}, {amount}, {order_ref}. "
        "About 1 in 5 messages may also mention a second, smaller issue. "
        "Do not include names, phone numbers, emails or real brand names.\n"
        'JSON: {"messages": ["...", "..."]}'
    )


TONE_LABEL = re.compile(r"^(angry|polite|confused|sarcastic)( tone| face)?\s*[:.!-]+\s*", re.IGNORECASE)


def clean(message: str) -> str | None:
    text = " ".join(str(message).split())
    text = TONE_LABEL.sub("", text)  # the model sometimes copies the tone word from the prompt
    for slot in set(re.findall(r"\{[^}]*\}", text)) - ALLOWED_SLOTS:
        text = text.replace(slot, "")  # unknown placeholder → drop it
    text = re.sub(r"\d{6,}", "", text).strip()  # no long numbers (they would look like IDs)
    return text if 3 <= len(text.split()) <= 40 else None


def main() -> int:
    client = build_client(["groq"])
    model = client.providers[0].config.model
    out: dict[str, dict[str, list[str]]] = {}
    for category in CATEGORY_HELP:
        out[category] = {}
        for language in STYLES:
            messages: list = []
            for length in LENGTHS:
                result = client.ask_json("make_templates", SYSTEM, prompt_for(category, language, length))
                messages += result.data.get("messages", []) if isinstance(result.data, dict) else []
            kept = sorted({m for m in (clean(x) for x in messages) if m})
            out[category][language] = kept
            print(f"{category:20s} {language}: {len(kept)} messages", flush=True)
    payload = {
        "model": model, "created": date.today().isoformat(), "system": SYSTEM,
        "prompt_example": prompt_for("refund", "hi", "short"), "templates": out,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
