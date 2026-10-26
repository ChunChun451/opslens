from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from opslens import anyfile as A
from server.anyfile_jobs import EXAMPLE, json_safe, keep_example
from tests.test_anyfile import delivery_file, mapping_for


def main() -> int:
    keep_example()
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
