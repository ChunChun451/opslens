"""The real-desk digital twin (Plan v4 W14): calibrate, gate, and only then compare.

Run:  .venv/Scripts/python.exe eval/run_realdesk_twin.py   -> eval/parts/realdesk_twin.json
(eval/run_realdesk.py puts it into results.realdesk.twin.) Every rule is in
docs/explain/realdesk_twin.md, committed before the first run (e53d623).

Steps: 1. calibrate share and k on the LEARNING months (desk policy, 20 runs);
2. the gate on the CHECK months; if it fails, stop: nothing runs on the test months;
3. (gate passed) choose OpsLens's form on the check months, compare on the test months once,
   sensitivity, hours equivalent.
Result (24 Oct): the gate FAILED (missed 27.9% vs 22.4% real, median pickup 0.00 h vs 0.13 h), so the
twin is reported as "built, did not match reality" and steps 3-5 were not run.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens import realdesk as R  # noqa: E402
from opslens import realdesk_twin as T  # noqa: E402
from opslens.adapters.uci_incidents import load_uci  # noqa: E402

PARTS = ROOT / "eval" / "parts"
SHARES = [0.1, 0.25, 0.5, 0.75, 1.0]
SLOTS = [1, 2, 3, 5]
GATE = {"missed_points": 3.0, "median_pickup_ratio": 0.25, "within_1h_points": 5.0}
LIMITS = {"3 - Moderate": 91.0, "4 - Low": 325.0}   # the W3 rule (results.realdesk.fasttrack.deadline_rule)


def loss(twin: dict, real: dict) -> float:
    """The pre-registered calibration loss (each term in units of its gate tolerance)."""
    ratio = max(twin["median_pickup_h"], 1e-6) / max(real["median_pickup_h"], 1e-6)
    return (abs(twin["missed_pct"] - real["missed_pct"]) / GATE["missed_points"]
            + abs(np.log(ratio)) / np.log(1 + GATE["median_pickup_ratio"])
            + abs(twin["picked_within_1h_pct"] - real["picked_within_1h_pct"]) / GATE["within_1h_points"])


def gate(twin: dict, real: dict) -> dict:
    checks = {
        "missed": abs(twin["missed_pct"] - real["missed_pct"]) <= GATE["missed_points"],
        "median_pickup": abs(twin["median_pickup_h"] / real["median_pickup_h"] - 1) <= GATE["median_pickup_ratio"],
        "within_1h": abs(twin["picked_within_1h_pct"] - real["picked_within_1h_pct"]) <= GATE["within_1h_points"],
    }
    return {"checks": checks, "passed": bool(all(checks.values()))}


def main() -> int:
    started = time.perf_counter()
    incidents, events = load_uci()
    learn, check, test = R.masks(incidents)
    inp = T.build_input(incidents, events, LIMITS)
    scored = np.isin(incidents["priority_raw"].astype(str), list(LIMITS)) & incidents["resolution_min"].notna().to_numpy()
    real_pick = T.real_pickup(incidents, events)
    recorded = ~np.isnan(real_pick)
    real_res = incidents["resolution_min"].to_numpy()

    def m(mask, res, pick):
        return T.measure(mask, scored, inp.deadline, res, pick, recorded)

    real = {"learning": m(learn, real_res, real_pick), "check": m(check, real_res, real_pick)}
    grid = []
    for share in SHARES:
        for k in SLOTS:
            r = T.run(inp, share, k, T.Policy())
            row = {"share": share, "k": k, "learning": m(learn, r.resolved, r.pickup), "check": m(check, r.resolved, r.pickup)}
            row["loss"] = loss(row["learning"], real["learning"])
            grid.append(row)
            print(f"share {share} k {k}: learning missed {row['learning']['missed_pct']:.1f} (real {real['learning']['missed_pct']:.1f}), "
                  f"median pickup {row['learning']['median_pickup_h']:.2f} h ({real['learning']['median_pickup_h']:.2f}), "
                  f"within 1 h {row['learning']['picked_within_1h_pct']:.1f}% ({real['learning']['picked_within_1h_pct']:.1f}); loss {row['loss']:.2f}")
    best = min(grid, key=lambda r: (r["loss"], r["k"], r["share"]))
    g = gate(best["check"], real["check"])
    out = {"pre_registration": "docs/explain/realdesk_twin.md (commit e53d623)", "limits_h": LIMITS,
           "validation": {"grid": [{"share": r["share"], "k": r["k"], "loss": r["loss"], "learning": r["learning"]} for r in grid],
                          "calibrated": {"share": best["share"], "k": best["k"], "loss": best["loss"]},
                          "real": real, "twin_learning": best["learning"], "twin_check": best["check"],
                          "tolerances": GATE, **g}}
    print(f"calibrated share {best['share']} k {best['k']}; CHECK twin {best['check']} vs real {real['check']} -> "
          f"gate {'PASSED' if g['passed'] else 'FAILED'} {g['checks']}")
    if not g["passed"]:
        out["status"] = "built, did not match reality: not shown, nothing ran on the test months"
    else:
        # Steps 3-5 (OpsLens form chosen on check, test once, sensitivity, hours) are written only
        # if a twin passes the gate; this one did not (24 Oct), so they were never built or run.
        raise SystemExit("gate passed: build the pre-registered comparison before going on")
    out["seconds"] = time.perf_counter() - started
    (PARTS / "realdesk_twin.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote eval/parts/realdesk_twin.json ({out['seconds']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
