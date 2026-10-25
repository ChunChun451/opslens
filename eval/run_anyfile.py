"""OpsLens on your file, measured once on the real UCI log exported as an ordinary CSV.

Why: the upload screen computes its report live, for whatever file a judge brings. The pitch
and the Q&A may only quote numbers from eval/results.json, so this step runs the same report on
the UCI incident log written as one row per incident (exactly what a judge's export looks like)
with the suggested mapping, and stores it. It also times a 100,000-row file.

Output: eval/parts/anyfile.json -> results["anyfile"] (eval/run_eval.py --assemble).
Example: learn on the first 70% of 24,918 incidents, score the rest; on Thu 5 May 2016 OpsLens's
flags catch 50 of 111 real misses, the priority field's 22.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from opslens import anyfile as A  # noqa: E402
from server.anyfile_jobs import EXAMPLE, json_safe, keep_example  # noqa: E402
from tests.test_anyfile import delivery_file, mapping_for  # noqa: E402


def main() -> int:
    keep_example()  # writes cache/uci_one_row.csv once
    raw = pd.read_csv(EXAMPLE)
    peek = A.peek(raw)
    mapping = dict(peek["suggested"])
    mapping["features"] = [c["name"] for c in peek["columns"] if c["feature"] and c["name"] not in mapping.values()]
    report = A.analyse(raw, mapping)
    big = delivery_file(n=100_000, days=90)
    started = time.perf_counter()
    A.analyse(big, mapping_for(big), target_min=30)
    out = {"file": "UCI ServiceNow incident log, one row per incident (cache/uci_one_row.csv)", "rows": int(len(raw)),
           "mapping": mapping, **report,
           "scale": {"rows": 100_000, "seconds": round(time.perf_counter() - started, 1),
                     "file": "generated delivery orders (tests/test_anyfile.py), 90 days"}}
    path = ROOT / "eval" / "parts" / "anyfile.json"
    path.write_text(json.dumps(json_safe(out), indent=1), encoding="utf-8")
    w = report["warning"]
    print(f"UCI as a plain CSV: {report['seconds']} s; AUC {w['auc']}; caught {w['caught_pct']}; "
          f"shadow {report['shadow']['date']}: {report['shadow']['caught']} of {report['shadow']['misses']}; "
          f"100k rows in {out['scale']['seconds']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
