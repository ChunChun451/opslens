from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens import realdesk as R
from opslens import realdesk_twin as T
from opslens.adapters.uci_incidents import load_uci

PARTS = ROOT / "eval" / "parts"
SHARES = [0.1, 0.25, 0.5, 0.75, 1.0]
SLOTS = [1, 2, 3, 5]
GATE = {"missed_points": 3.0, "median_pickup_ratio": 0.25, "within_1h_points": 5.0}
LIMITS = {"3 - Moderate": 91.0, "4 - Low": 325.0}


def loss(twin: dict, real: dict) -> float:
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
        raise SystemExit("gate passed: build the pre-registered comparison before going on")
    out["seconds"] = time.perf_counter() - started
    (PARTS / "realdesk_twin.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote eval/parts/realdesk_twin.json ({out['seconds']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
