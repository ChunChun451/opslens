"""`make demo`: start the dashboard for the live demo — offline, real results only.

Why: on stage there may be no Wi-Fi, and an invented number must never reach the screen.
So this refuses to start unless eval/results.json exists and is real (meta.fixture is false).
Nothing here calls the internet: results, LLM answers (cached) and the data are local, and
What-if / Plant-a-problem / Upload run the simulator and the pattern finder on this laptop.

Run:  mingw32-make demo   → open http://localhost:8000/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results.json"


def check_results() -> str | None:
    """None if the demo may start, otherwise the reason it may not."""
    if not RESULTS.exists():
        return "eval/results.json is missing: run `mingw32-make eval` first."
    meta = json.loads(RESULTS.read_text(encoding="utf-8")).get("meta", {})
    if meta.get("fixture", True):
        return "eval/results.json is marked as fixture data: the demo only runs on real results."
    for needed in ("data/generated/world_tickets.csv", "data/generated/predictions.csv", "data/generated/models"):
        if not (ROOT / needed).exists():
            return f"{needed} is missing: run `mingw32-make gen` and `mingw32-make eval`."
    return None


def main() -> int:
    problem = check_results()
    if problem:
        print("DEMO REFUSED:", problem)
        return 1
    meta = json.loads(RESULTS.read_text(encoding="utf-8"))["meta"]
    print(f"OpsLens demo: real results from {meta['generated_at']} (commit {meta['git_commit']}). "
          "Open http://localhost:8000/  (Ctrl+C to stop)")
    import uvicorn

    sys.path.insert(0, str(ROOT))
    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
