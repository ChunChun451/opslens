# OpsLens — progress log

Newest entry at the bottom. One entry per milestone (see `CLAUDE.md` section 1.2).

---

## Session 0 — 15 Oct 2026 — Planning (plan v2)

**Built**
- `CLAUDE.md` rewritten as plan v2. Original kept in `docs/CLAUDE_v1.md`.
- `docs/PLAN.md`: 23 changes from v1 with reasons, 2026 research links, risks, team tracks,
  demo outline, attack questions, day-1 checklist.

**Key decisions (all in `docs/PLAN.md` section 2)**
- 56 days of data (train 1–35, validation 36–42, test 43–56).
- 5 planted problems + decoys; blind recall on 20 random plant sets; live Plant-a-problem.
- Real data: UCI ServiceNow incident log (has `made_sla`).
- Classification cascade (local model first, LLM only when unsure).
- Decision tick 2 min for all policies; scarcity cost; starvation guard; Erlang-C staffing.
- LLM never writes digits; What-if tab; UI track in a parallel session from 18 Oct.

**Numbers printed:** none yet (planning only).

**Open issues**
- ~~TrueInk overlap~~ — resolved 15 Oct: OpsLens is the only finale project; all days go to it.
- Free LLM limits to be checked in our own accounts (blogs disagree).
- Project still in OneDrive; M1 moves it to `C:\dev\opslens` with its own git repo.

**Next step:** M1 in a new session at `C:\dev\opslens`.

---

## M1 — 15 Oct 2026 — Repo, LLM layer, privacy, data

**Built**
- Project moved to `C:\dev\opslens` (own git repo, branch `main`), outside OneDrive.
- Python 3.12.15 venv (`.venv`). Versions frozen in `requirements.lock.txt`
  (pandas 3.0.6, numpy 2.5.4, scikit-learn 1.9.1, lightgbm 4.7.0, ortools 9.15, openai 3.31).
- `opslens/config.py`: YAML loader + our own `.env` reader (no python-dotenv).
- `opslens/privacy.py`: 10 ordered regex masks (email, UPI, Luhn-checked card, Aadhaar, PAN,
  order ID, phone, house/flat, PIN, long numbers).
- `opslens/llm/`: `LLMClient.ask_json` = mask → cache → per-provider daily budget →
  per-minute window → send → JSON parse (+1 repair) → fallback → cache. Providers:
  Gemini (`gemini-3.1-flash-lite`), Groq (`openai/gpt-oss-20b`), mock.
- `scripts/download_data.py` + `data/SOURCES.md` (licences, SHA-256).
- `scripts/ping_llm.py` (`mingw32-make ping`): lists visible models, sends one real request.
- `Makefile` (works with `mingw32-make`), `pytest.ini` (temp files inside the project).

**Numbers printed**
- Tests: 31 passed (17 privacy, 14 LLM layer).
- Bitext: 26,872 rows, 27 intents. UCI: 141,712 events, 24,918 incidents, 2016–2017,
  `made_sla` False on 9,215 of 141,712 events (incident-level rate computed in M3).

**Open issues**
- **Ping not run yet: no API keys in `.env`.** Owner pastes Gemini + Groq keys, then
  `mingw32-make ping` and records the visible model names here.
- Bitext has no food intents → `data/text_bank.py` templates (M2).
- pytest needs `--basetemp=.pytest_tmp` on this PC (system temp folder is locked).

**Next step:** M2 — text bank, generator (56 days, 5 plants, decoys), simulator, baselines, CRN.
