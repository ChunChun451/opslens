# Judge Q&A

Questions a sharp industry judge would ask, with model answers under 60 words.
Every number must come from our results or code. "Attack" = a question meant to break us.
Grouped by module; newest milestone at the bottom.

---

## M1 — Privacy and the LLM layer

**Q1. You send customer tickets to Google and Groq. Isn't that a privacy problem?**
Every ticket passes through `mask_pii()` inside the LLM client before any network call.
Phones, emails, UPI IDs, cards (Luhn-checked), Aadhaar, PAN, order IDs, flat numbers and PIN
codes become tags. The cache stores only masked text. A test checks that the mock provider
never receives the raw phone number.

**Q2. (Attack) Regex masking misses things. What about names?**
True — names and free-text street names are not caught today, and we say so. Two things
limit the risk: the LLM only sees the tickets our local model is unsure about, not
all of them; and production would add a named-entity model (e.g. Presidio) before the regex
step. That is in PRODUCTION.md.

**Q3. What happens if Gemini's free tier runs out during your demo?**
Nothing visible. Every reply is cached by a hash of the masked prompt, so the demo replays
from SQLite with Wi-Fi off. Live, the client falls back to Groq, and if both fail the
engine uses the local classifier and a template brief. The LLM is never on the critical path.

**Q4. Why not just call the API directly? Why build a client layer?**
Five jobs every call needs: PII masking, cache, per-minute and per-day limits, fallback
provider, and JSON repair. Doing them once means no module can forget one. It is about 150
lines and fully tested with a mock (outage, broken JSON, budget used up).

**Q5. (Attack) Free tiers change every month. How do you know your model names work?**
We don't trust blogs. `make ping` lists the models our own key can see, sends one real
request to each provider, and warns if the configured model name is missing. Names and
limits live in `config/providers.yaml`, so a change is a config edit, not a code change.
