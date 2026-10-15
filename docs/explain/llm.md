# opslens/llm/ — the LLM layer

## What it does
- One function for the whole engine: `LLMClient.ask_json(task, system, user)` → parsed JSON.
- It masks PII, checks a cache, respects free-tier limits, falls back to a second provider,
  and repairs broken JSON once.
- Providers: Gemini Flash-Lite (main), Groq gpt-oss-20b (fallback), and a mock for tests.
- All three use the OpenAI chat format, so one small class (`openai_compat.py`) talks to both
  real ones. Model names live in `config/providers.yaml`.
- If everything fails it raises `LLMUnavailable`, and the caller uses its non-LLM fallback
  (local classifier, template brief). **The engine never depends on the LLM being up.**

## How it works, step by step (`client.py`, `ask_json`)
1. `mask_pii(user)` — personal data becomes tags. Only masked text goes anywhere.
2. Cache lookup — key = SHA-256 of (model, system prompt, masked user text). A hit is free
   and works offline. That is how `make demo` runs with Wi-Fi off.
3. For each provider in order (main, fallback):
   - out of today's budget? skip it (`ratelimit.py`, counter stored in SQLite);
   - per-minute window full? sleep until a slot opens;
   - send, then parse JSON (accepts ```json fences and text around the JSON);
   - broken JSON → send once more with "reply with only the JSON";
   - any error → note it and try the next provider.
4. Save the good reply in the cache, return it with provider, model, latency, PII counts.

## Worked example
Budget in config: Gemini 10 requests/minute, 400/day (published free limits are higher —
we stay below on purpose).
- 09:00:00 classify batch 1 → Gemini, 2.1 s, cached.
- … 10 calls by 09:00:40 → the 11th waits about 20 s, until the first call is 60 s old.
- Gemini returns an error (quota) → the same request goes to Groq → success.
- Next run of the same batch → cache hit, 0 requests, 0 seconds.
In M3 we classify in batches of 25–50 tickets and only the tickets the local model is
unsure about go to the LLM, so a full run needs hundreds of requests, not 56,000.

## Weaknesses
- Daily counters use UTC days; Google resets at midnight Pacific. Our budgets sit below the
  real limits to cover the difference.
- The per-minute window lives in memory: two processes running at once would not see each
  other's calls. We only run one at a time.
- Free-tier limits change without notice. `make ping` shows what our key can use today.

## How to read the code
1. `client.py` → `ask_json` (the whole story in 40 lines).
2. `base.py` → the small types (`ProviderConfig`, `LLMResult`, errors).
3. `openai_compat.py` → the real API call (one `chat.completions.create`).
4. `cache.py`, `ratelimit.py` → plain SQLite.
5. `mock.py` → how tests fake outages and broken JSON.
Tests: `tests/test_llm.py`.
