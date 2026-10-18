"""M8: one command reproduces every number → eval/results.json and docs/NUMBERS.md.

Run:  mingw32-make eval            (or .venv/Scripts/python.exe eval/run_eval.py)
      ... run_eval.py --assemble   (only rebuild results.json + NUMBERS.md from eval/parts/)
      ... run_eval.py --blind      (also re-run the 35-minute blind recall test)
      ... --assemble --keep-brief  (reuse the brief already in results.json, no LLM call)

Steps (each writes eval/parts/<name>.json):
  classification → patterns → risk → forecast → opslens (test-day comparison) → ablations
  [→ blind]. Then everything is mapped into the schema of opslens/results_schema.py
  (validated by pydantic) and NUMBERS.md is generated from results.json — never typed by hand.
The LLM calls in classification come from the SQLite cache, so a re-run needs no network.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opslens.config import load_config  # noqa: E402
from opslens.ingest import load_history  # noqa: E402
from opslens.optimize import Candidate, SolveStats, solve  # noqa: E402
from opslens.results_schema import Results  # noqa: E402

PARTS = ROOT / "eval" / "parts"
STEPS = [("classification", "eval/run_classification.py"), ("patterns", "eval/run_patterns.py"),
         ("risk", "eval/run_risk.py"), ("forecast", "eval/run_forecast.py"),
         ("opslens", "eval/run_opslens.py"), ("ablations", "eval/run_ablations.py"),
         ("playbooks", "eval/run_playbooks.py"), ("baseline_c", "eval/run_baseline_c.py"),
         ("best_baselines", "eval/run_best_baselines.py"), ("floor", "eval/run_floor.py"),
         ("realdesk", "eval/run_realdesk.py")]


def run_steps(with_blind: bool) -> dict[str, float]:
    timings = {}
    steps = STEPS + ([("blind", "eval/run_blind.py")] if with_blind else [])
    for name, script in steps:
        started = time.perf_counter()
        print(f"== {name}", flush=True)
        subprocess.run([sys.executable, script], cwd=ROOT, check=True)
        timings[name] = round(time.perf_counter() - started, 1)
    return timings


def part(name: str) -> dict:
    return json.loads((PARTS / f"{name}.json").read_text(encoding="utf-8"))


def scale_test() -> dict:
    """Optimiser on 5,000 waiting tickets × 500 free agents (top-30 tickets per agent)."""
    rng = np.random.default_rng(0)
    agents = [f"a{i}" for i in range(500)]
    cands = [Candidate(int(t), a, float(rng.uniform(0.05, 3)), False, "x", "")
             for a in agents for t in rng.choice(5000, 30, replace=False)]
    started = time.perf_counter()
    chosen = solve(cands, {a: 1 for a in agents}, 5.0, SolveStats())
    return {"tickets": 5000, "agents": 500, "edges": len(cands), "assigned": len(chosen),
            "seconds": round(time.perf_counter() - started, 3)}


def delay_decomposition() -> dict:
    """Where a ticket's time goes, per owning team (history days 1-42): waiting for the first
    agent, being worked on, and everything after the first pickup (transfers, reopens, re-queues)."""
    from opslens.classify import TEAM_OF
    h = load_history()
    h = h[h["day"] <= load_config("calendar")["splits"]["validation_last_day"]]
    h = h.assign(team=h["final_category"].map(TEAM_OF))
    out = {}
    for team, g in h.groupby("team"):
        wait, handle, total = g["wait_min"].mean(), g["handled_min"].mean(), g["resolution_min"].mean()
        out[team] = {"waiting": round(float(wait), 1), "handling": round(float(handle), 1),
                     "after_first_pickup": round(float(max(total - wait - handle, 0.0)), 1)}
    return out


def version_record(version: str, note: str) -> dict:
    """Test-day results of an earlier OpsLens policy version, kept on purpose."""
    if not (PARTS / f"ablations_{version}.json").exists():
        return {}
    abl, sim = part(f"ablations_{version}"), part(f"sim_{version}")
    breach = {k: v["kpis"]["turnaround.breach_pct"]["mean"] for k, v in sim["policies"].items()}
    return {"test_breach_pct": breach, "stress": abl["stress"], "ablations": abl["ablations"], "note": note}


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def assemble(timings: dict[str, float]) -> dict:
    cal = load_config("calendar")
    sp = cal["splits"]
    cls, pat, rsk, fc, sim, abl, blind = (part(n) for n in
                                           ("classification", "patterns", "risk", "forecast", "sim", "ablations", "blind"))
    tuning = part("tuning") if (PARTS / "tuning.json").exists() else {}
    agents = pd.read_csv(ROOT / "data" / "generated" / "agents.csv")
    names = dict(zip(agents["agent_id"], agents["name"]))
    n_tickets = int(sum(1 for _ in open(ROOT / "data" / "generated" / "history.csv", encoding="utf-8")) - 1)

    day0 = (sim["replay"]["day"] - 1) * 1440
    replay = {**sim["replay"], "start_minute": day0 + 18 * 60}
    solver_ms = [s["median_ms"] for s in sim["solver"]]
    blind_s = blind["summary"]
    results = {
        "meta": {"fixture": False, "generated_at": datetime.now().isoformat(timespec="seconds"),
                 "git_commit": git_commit(), "data_seed": int(load_config("generator")["seed"]), "n_tickets": n_tickets,
                 "start_date": cal["start_date"], "days": cal["days"], "train_days": [1, sp["train_last_day"]],
                 "validation_days": [sp["train_last_day"] + 1, sp["validation_last_day"]],
                 "test_days": [sp["validation_last_day"] + 1, sp["test_last_day"]],
                 "run_seconds": float(sum(timings.values()))},
        "sim": {"seeds": sim["seeds"], "test_days": sim["test_days"], "policies": sim["policies"],
                "comparisons": sim["comparisons"], "replay": replay},
        "patterns": {"cards": pat["cards"], "recall": pat["recall"],
                     "blind_recall": {"sets": blind_s["sets"], "planted": blind_s["planted"], "found": blind_s["found"],
                                      "found_pct": blind_s["found_pct"], "diagnosed_pct": blind_s["diagnosed_pct"],
                                      "unplanted_cards_per_set": blind_s["unplanted_cards_per_set"],
                                      "clean_set_cards": blind_s["clean_set_cards"]},
                     "live_detection_latency_min": pat["live_detection_latency_min"],
                     "delay_decomposition": delay_decomposition()},
        "classification": {"accuracy_local": cls["accuracy_local"], "accuracy_cascade": cls["accuracy_cascade"],
                           "accuracy_llm_sample": cls.get("accuracy_llm_sample"), "pct_sent_to_llm": cls["pct_sent_to_llm"],
                           "transfers_avoided_per_100": cls["transfers_avoided_per_100"], "confusion": cls["confusion"],
                           "clusters": cls["clusters"]},
        "forecast": {"wape_model": fc["metrics"]["wape_model"], "wape_naive": fc["metrics"]["wape_naive"],
                     "coverage_80": fc["metrics"]["coverage_80"], "coverage_90": fc["metrics"]["coverage_90"],
                     "horizon": fc["horizon"],
                     "bottlenecks": [{"team": b["team"], "start": b["start"], "end": b["end"], "text": b["text"],
                                      "peak_gap_agents": b["peak_gap_agents"], "agent_hours_short": b["agent_hours_short"]}
                                     for b in sorted(fc["bottlenecks"], key=lambda b: -b["agent_hours_short"])[:12]]},
        "risk": {"auc": rsk["test"]["auc"], "pr_auc": rsk["test"]["pr_auc"], "top10_precision": rsk["test"]["top10_precision"],
                 "brier": rsk["test"]["brier"], "base_rate": rsk["test"]["base_rate"], "calibration": rsk["test"]["calibration"],
                 "at_risk": rsk["at_risk"], "realdata_auc": rsk["realdata"]["auc"], "realdata_n": rsk["realdata"]["n"]},
        "recommendations": {
            "assignments": [{"ticket_id": d["ticket_id"], "agent_id": d["agent_id"], "agent_name": names.get(d["agent_id"], d["agent_id"]),
                             "reason": d["reason"], "value": d["value"]} for d in sim["decisions"][:15]],
            "staffing_moves": [{"text": f"{names.get(m['agent_id'], m['agent_id'])} ({m['agent_id']}, Team {m['team']}): {m['change']}, "
                                        f"days {plan['first_day']}-{plan['last_day']}",
                                "team_from": m["team"], "team_to": m["team"], "agents": [m["agent_id"]],
                                "when": f"days {plan['first_day']}-{plan['last_day']}", "expected_effect": {}}
                               for plan in fc["plans"] for m in plan["moves"]],
        },
        "ablations": [{k: a[k] for k in ("key", "label", "breach_pct", "p90_resolution_min", "delta_breach_vs_full")}
                      for a in abl["ablations"]],
        "sensitivity": abl["sensitivity"],
        "stress": abl["stress"],
        "speed": {"pipeline_seconds": float(sum(timings.values())), "optimizer_ms_median": float(np.median(solver_ms)),
                  "optimizer_ms_max": float(max(s["max_ms"] for s in sim["solver"])), "scale_test": scale_test()},
        "details": {
            "step_seconds": timings,
            "classification": cls["details"],
            "patterns": {"diagnosed": pat["diagnosed"], "unplanted_findings": pat["unplanted_findings"],
                         "explained_anomalies": pat["explained_anomalies"],
                         "live_false_alerts_per_week": pat["live_false_alerts_per_week"]},
            "blind": {"by_type": blind_s["by_type"], "clean_set_cards": blind["clean_set_cards"]},
            "risk": {"at_arrival": rsk["at_arrival"], "rules": rsk["rules"], "realdata": rsk["realdata"],
                     "feature_gain": rsk["feature_gain"]},
            "forecast": {**fc["metrics"], "plans": fc["plans"]},
            "ablations": abl["ablations"],
            "tuning": tuning,
            "weights": sim["weights"],
            # The honest record: policy v1 failed the +25% volume stress test on the test days;
            # v2 was then designed and chosen on validation days only (design_v2), and the test
            # days were re-run once.
            "v1_record": version_record("v1", "aged tickets per hour; under +25% volume old lost tickets crowded out savable P1s."),
            "v2_record": version_record("v2", "aged tickets in SLA units but a lost ticket kept its full age value; still lost "
                                              "the +25% volume test on the test days (it lands on a sale day and a surge)."),
            "design_v2": part("design_v2") if (PARTS / "design_v2.json").exists() else {},
            "design_v3": part("design_v3") if (PARTS / "design_v3.json").exists() else {},
            "v3_record": version_record("v3", "flat cross-skill penalty: a savable ticket with no trained agent who "
                                              "speaks its language on shift (e.g. Hindi refunds at night) waited for "
                                              "one. Replaced by v5 (roster-aware rescue), chosen on validation days."),
            "v3_before_sim_fix": version_record("v3oldsim", "v3 measured before the 18 Oct simulator correction "
                                                            "(a transfer used to shift a ticket's work-time draw)."),
            "design_v4": part("design_v4") if (PARTS / "design_v4.json").exists() else {},
            "design_v5": part("design_v5") if (PARTS / "design_v5.json").exists() else {},
            "confirm_v5": part("confirm_v5") if (PARTS / "confirm_v5.json").exists() else {},
            "sealed_world_5151_v3": part("sealed_world_5151_v3") if (PARTS / "sealed_world_5151_v3.json").exists() else {},
            "test_runs_note": ("Policies run on the test days: v1, v2, v3 and v5 (current), each designed and chosen on "
                               "validation days only; all results are kept here. On 18 Oct the simulator was corrected "
                               "(work-time draws no longer shifted by transfers; off-shift starts refused) and every "
                               "number was regenerated (v3 before the correction: v3_before_sim_fix). v4 was tested on "
                               "validation days and not adopted (design_v4). v5 passed a pre-registered confirmation on "
                               "20 fresh seeds (confirm_v5). Sealed worlds: 4242 (v3, old simulator), 5151 (v3, run "
                               "once), 6262 (v5, generated after v5 was frozen, run once)."),
        },
    }
    if (PARTS / "playbooks.json").exists():
        pb = part("playbooks")
        results["playbooks"] = {k: pb[k] for k in ("test_days", "seeds", "playbooks", "all", "opslens_all_vs_baseline_b", "base")}
    if (PARTS / "baseline_c.json").exists():
        results["baseline_c"] = with_means(part("baseline_c"))
    # Not a STEP: run once, after the freeze (eval/run_sealed_world.py); kept as a part file.
    if (PARTS / "sealed_world.json").exists():
        results["sealed_world"] = with_means(part("sealed_world"))
    # The published scheduling rules and clairvoyant least slack (eval/run_best_baselines.py),
    # and the sealed world run again with them (baselines added after the first sealed run).
    if (PARTS / "best_baselines.json").exists():
        results["best_baselines"] = with_perfect_info(with_means(part("best_baselines")))
        if "rescue" in results["best_baselines"]:  # least slack + cross-skill rescue (nested)
            with_means(results["best_baselines"]["rescue"])
    if (PARTS / "sealed_world_rerun.json").exists():
        results["sealed_world_rerun"] = with_perfect_info(with_means(part("sealed_world_rerun")))
    if (PARTS / "floor.json").exists():
        results["floor"] = part("floor")
    if (PARTS / "realdesk.json").exists():  # the real public service desk (UCI), deliverable 1
        results["realdesk"] = part("realdesk")
    if (PARTS / "sealed_world_new.json").exists():  # not a STEP: a new world, run once (corrected simulator)
        sealed = part("sealed_world_new")
        for key in ("test", "best_baselines_test", "rescue_test"):
            if sealed.get(key):
                with_means({key: sealed[key]})
        results["sealed_world_new"] = sealed
    # Challenger arena (CLAUDE.md 7.11): eval-only, run in .venv-challengers, so not a STEP.
    results["details"]["challengers"] = {name: part(f"challenger_{name}") for name in ("forecast", "risk")
                                         if (PARTS / f"challenger_{name}.json").exists()}
    old = ROOT / "eval" / "results.json"
    if "--keep-brief" in sys.argv and old.exists():
        results["brief"] = json.loads(old.read_text(encoding="utf-8"))["brief"]
    else:
        results["brief"] = make_brief(results)
    Results.model_validate(results)  # fails loudly if anything drifted from the contract
    return results


def with_means(section: dict) -> dict:
    """Add {policy: {kpi: mean over seeds}} next to each per_seed block, so the dashboard can
    point every number at a path in results.json (click-to-evidence)."""
    for block in section.values():
        if isinstance(block, dict) and "per_seed" in block:
            block["means"] = {p: {k: sum(s[k] for s in runs) / len(runs) for k in runs[0]}
                              for p, runs in block["per_seed"].items()}
    return section


def with_perfect_info(section: dict) -> dict:
    """What perfect information buys a sorting rule: clairvoyant − least slack, paired by seed
    (the two differ only in knowing the true category and handle time)."""
    from opslens.impact import paired_ci

    for block in section.values():
        if isinstance(block, dict) and "clairvoyant" in block.get("per_seed", {}):
            per = block["per_seed"]
            block["clairvoyant_minus_least_slack"] = {
                k: paired_ci([r[k] for r in per["clairvoyant"]], [r[k] for r in per["least_slack"]])
                for k in ("turnaround.breach_pct", "quality.late_minutes_per_100")}
    return section


def make_brief(r: dict) -> dict:
    """LLM brief with number keys (opslens/brief.py); template if the LLM is unavailable."""
    from opslens.brief import write_brief
    from opslens.llm.client import build_client

    try:
        # Stronger model first: the brief is written once here, never live (config/providers.yaml).
        client = build_client(["gemini_brief", "gemini", "groq"])
    except Exception:  # no keys / no network: the template is always available
        client = None
    return write_brief(r, client)


def template_brief(r: dict) -> dict:
    """Template brief (the LLM version with number keys comes in M10). Numbers are filled from
    the results by key, so the text can never contain a number we did not compute."""
    keys = {
        "a": "sim.policies.baseline_a.kpis.turnaround.breach_pct.mean",
        "b": "sim.policies.baseline_b.kpis.turnaround.breach_pct.mean",
        "o": "sim.policies.opslens.kpis.turnaround.breach_pct.mean",
    }
    pol = r["sim"]["policies"]
    vals = {"a": pol["baseline_a"]["kpis"]["turnaround.breach_pct"]["mean"],
            "b": pol["baseline_b"]["kpis"]["turnaround.breach_pct"]["mean"],
            "o": pol["opslens"]["kpis"]["turnaround.breach_pct"]["mean"]}
    text = (f"On the 14 held-out test days, OpsLens breached {vals['o']:.1f}% of SLAs, against {vals['a']:.1f}% "
            f"for first-in-first-out and {vals['b']:.1f}% for priority-first routing.")
    return {"text": text, "source": "template", "numbers_used": list(keys.values())}


def fmt(x: float, nd: int = 2) -> str:
    return f"{x:,.{nd}f}"


def numbers_md(r: dict) -> str:
    """docs/NUMBERS.md — every headline number, generated from results.json."""
    pol = r["sim"]["policies"]
    k = lambda p, name: pol[p]["kpis"][name]  # noqa: E731
    ci = {(c["baseline"], c["kpi"]): c for c in r["sim"]["comparisons"]}
    lines = [
        "# OpsLens — the numbers", "",
        f"Generated from `eval/results.json` on {r['meta']['generated_at']} (commit {r['meta']['git_commit']}). "
        "Do not edit by hand: run `mingw32-make eval`.", "",
        f"Data: {r['meta']['n_tickets']:,} tickets over {r['meta']['days']} days; train days {r['meta']['train_days']}, "
        f"validation {r['meta']['validation_days']}, test {r['meta']['test_days']}. Simulator seeds {r['sim']['seeds']}.", "",
        "## Baseline vs OpsLens (test days, mean ± std over seeds)", "",
        "| KPI | Baseline A (FIFO) | Baseline B (priority) | Industry standard (skills routing) | OpsLens "
        "| OpsLens − industry standard (95% CI) | OpsLens − B (95% CI) |",
        "|---|---|---|---|---|---|---|",
    ]
    has_d = "baseline_d" in pol
    for name, label in [("turnaround.breach_pct", "SLA breach %"), ("turnaround.p90_resolution_min", "P90 resolution (min)"),
                        ("turnaround.mean_wait_min", "Mean wait (min)"), ("turnaround.max_backlog", "Max backlog (tickets)"),
                        ("productivity.transfers_per_100", "Transfers per 100"), ("productivity.tickets_per_agent_hour", "Tickets per agent-hour"),
                        ("quality.reopen_rate_pct", "Reopen rate %"), ("quality.p99_wait_min", "P99 wait (min)"),
                        ("quality.load_fairness_std", "Load fairness (std of utilisation)"),
                        ("segment.p1_breach_pct", "P1 breach %"), ("segment.hindi_breach_pct", "Hindi customers' breach %")]:
        c = ci[("baseline_b", name)]
        d = ci.get(("baseline_d", name)) if has_d else None
        d_mean = f"{fmt(k('baseline_d', name)['mean'])} ± {fmt(k('baseline_d', name)['std'])}" if has_d else "–"
        d_diff = f"{d['mean_diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}]" if d else "–"
        lines.append(f"| {label} | {fmt(k('baseline_a', name)['mean'])} ± {fmt(k('baseline_a', name)['std'])} | "
                     f"{fmt(k('baseline_b', name)['mean'])} ± {fmt(k('baseline_b', name)['std'])} | {d_mean} | "
                     f"**{fmt(k('opslens', name)['mean'])}** ± {fmt(k('opslens', name)['std'])} | {d_diff} | "
                     f"{c['mean_diff']:+.2f} [{c['ci_low']:+.2f}, {c['ci_high']:+.2f}] |")
    c_a = ci[("baseline_a", "turnaround.breach_pct")]
    lines += ["", f"OpsLens − Baseline A, breach %: {c_a['mean_diff']:+.2f} [{c_a['ci_low']:+.2f}, {c_a['ci_high']:+.2f}].", "",
              "## Which part creates the gain (ablations, test days)", "", "| Variant | Breach % | Δ vs full | P90 (min) |", "|---|---|---|---|"]
    for a in r["details"]["ablations"]:
        lines.append(f"| {a['label']} | {fmt(a['breach_pct']['mean'])} | {a['delta_breach_vs_full']:+.2f} "
                     f"[{a['ci_low']:+.2f}, {a['ci_high']:+.2f}] | {fmt(a['p90_resolution_min']['mean'], 1)} |")
    lines += ["", "## Stress tests (conditions never seen in training)", "", "| Scenario | Baseline A | Baseline B | OpsLens | OpsLens − B |", "|---|---|---|---|---|"]
    for s in r["stress"]:
        lines.append(f"| {s['scenario']} | {fmt(s['baseline_a'])}% | {fmt(s['baseline_b'])}% | **{fmt(s['opslens'])}%** | "
                     f"{s['opslens_minus_b']:+.2f} [{s['ci_low']:+.2f}, {s['ci_high']:+.2f}] |")
    lines += ["", "## Gold-customer weight sensitivity", "", "| Gold weight | Breach % (all) | Breach % (gold) |", "|---|---|---|"]
    for s in r["sensitivity"]:
        lines.append(f"| ×{s['gold_weight']} | {fmt(s['breach_pct'])} | {fmt(s['gold_breach_pct'])} |")
    pat, blind = r["patterns"], r["patterns"]["blind_recall"]
    cls, fc, rk = r["classification"], r["forecast"], r["risk"]
    d = r["details"]
    lines += [
        "", "## Patterns", "",
        f"- Planted problems (main data): found {pat['recall']['found']}/{pat['recall']['planted']}, "
        f"diagnosed {d['patterns']['diagnosed']}/{pat['recall']['planted']}; false alarms {pat['recall']['false_alarms']}.",
        f"- Blind test: {blind['found']}/{blind['planted']} random plants found ({fmt(blind['found_pct'], 1)}%) over "
        f"{blind['sets']} datasets; diagnosed {fmt(blind['diagnosed_pct'], 1)}%.",
        f"- Live detection of the unseen day-47 surge: {fmt(pat['live_detection_latency_min'], 0)} min; "
        f"false alerts {fmt(d['patterns']['live_false_alerts_per_week'], 1)} per week.",
        "", "## Classification (test days)", "",
        f"- Menu choice {fmt(100 * d['classification']['menu_choice_accuracy'], 1)}% → local {fmt(100 * cls['accuracy_local'], 2)}% "
        f"→ cascade {fmt(100 * cls['accuracy_cascade'], 2)}%; LLM alone {fmt(100 * cls['accuracy_llm_sample'], 1)}% (400 tickets).",
        f"- Sent to the LLM: {fmt(cls['pct_sent_to_llm'], 2)}%. Wrong-team routing per 100: "
        f"{fmt(d['classification']['misrouted_per_100_menu'])} → {fmt(d['classification']['misrouted_per_100_opslens'])}.",
        "", "## Risk model (test days)", "",
        f"- AUC {fmt(rk['auc'], 3)} (time-left rule {fmt(d['risk']['rules']['time_left_auc'], 3)}), PR-AUC {fmt(rk['pr_auc'], 3)}, "
        f"top-10% precision {fmt(rk['top10_precision'], 3)}, Brier {fmt(rk['brier'], 4)}; at arrival AUC {fmt(d['risk']['at_arrival']['auc'], 3)}.",
        f"- Real ServiceNow data (UCI, {rk['realdata_n']:,} test incidents): AUC {fmt(rk['realdata_auc'], 3)} "
        f"vs priority rule {fmt(d['risk']['realdata']['priority_rule_auc'], 3)}.",
        "", "## Forecast (test days)", "",
        f"- WAPE {fmt(fc['wape_model'], 3)} vs same-hour-last-week {fmt(fc['wape_naive'], 3)} (Poisson floor {fmt(d['forecast']['wape_noise_floor'], 3)}).",
        f"- Conformal coverage: 80% range {fmt(100 * fc['coverage_80'], 1)}%, 90% range {fmt(100 * fc['coverage_90'], 1)}%.",
    ] + baseline_c_md(r) + best_baselines_md(r) + realdesk_md(r) + floor_md(r) + sealed_new_md(r) + sealed_world_md(r) + sealed_rerun_md(r) + playbooks_md(r) + challengers_md(r) + [
        "", "## Speed", "",
        f"- Optimiser per decision: median {fmt(r['speed']['optimizer_ms_median'], 2)} ms, max {fmt(r['speed']['optimizer_ms_max'], 1)} ms.",
        f"- Scale test: {r['speed']['scale_test']['tickets']:,} tickets × {r['speed']['scale_test']['agents']} agents solved in "
        f"{r['speed']['scale_test']['seconds']} s.",
        f"- Full evaluation pipeline: {fmt(r['speed']['pipeline_seconds'] / 60, 1)} min.", "",
    ]
    return "\n".join(lines)


def playbooks_md(r: dict) -> list[str]:
    pbs = r.get("playbooks")
    if not pbs:
        return []
    lines = ["", "## Fix-at-source playbooks (test days, change vs the same policy without it)", "",
             "| Playbook | Owner | Tickets prevented | Breaches: priority-first | Breaches: OpsLens | Agent-hours (OpsLens) |",
             "|---|---|---|---|---|---|"]

    def cell(d: dict) -> str:
        return f"{d['mean_diff']:+.1f} [{d['ci_low']:+.1f}, {d['ci_high']:+.1f}]"

    for pb in pbs["playbooks"]:
        b, o = pb["effect"]["baseline_b"]["vs_without"], pb["effect"]["opslens"]["vs_without"]
        lines.append(f"| {pb['title']} | {pb['owner']} | {0.0 - o['tickets']['mean_diff'] + 0.0:.0f} | {cell(b['breaches'])} | "
                     f"{cell(o['breaches'])} | {o['agent_hours']['mean_diff']:+.1f} |")
    b, o = pbs["all"]["baseline_b"]["vs_without"], pbs["all"]["opslens"]["vs_without"]
    lines.append(f"| **All together** | | {0.0 - o['tickets']['mean_diff'] + 0.0:.0f} | {cell(b['breaches'])} | {cell(o['breaches'])} | "
                 f"{o['agent_hours']['mean_diff']:+.1f} |")
    h = pbs["opslens_all_vs_baseline_b"]
    base_b = pbs["base"]["baseline_b"]["breaches"]["mean"]
    lines += ["", f"- OpsLens with every playbook vs priority-first today: breaches {cell(h['breaches'])} "
              f"(of {base_b:.0f}), breach % {cell(h['breach_pct'])} points.",
              "- Assumptions (labelled in config/playbooks.yaml) were re-run at their low and high values; "
              "see `playbooks[].sensitivity` in results.json."]
    return lines


def baseline_c_md(r: dict) -> list[str]:
    """Baseline C ("SLA due") and lateness, test days. Empty if eval/run_baseline_c.py has not run."""
    c = r.get("baseline_c")
    if not c:
        return []
    test = c["test"]
    names = {"baseline_a": "Baseline A (FIFO)", "baseline_b": "Baseline B (priority)",
             "baseline_c": "Baseline C (SLA due)", "opslens": "OpsLens"}
    if "baseline_d" in test["per_seed"]:
        names = {**{k: v for k, v in names.items() if k != "opslens"},
                 "baseline_d": "Industry standard (skills routing)", "opslens": "OpsLens"}
    rows = [("turnaround.breach_pct", "SLA breach %"), ("segment.p1_breach_pct", "P1 breach %"),
            ("quality.mean_minutes_late", "Minutes late, mean over breached tickets"),
            ("quality.late_minutes_per_100", "Minutes late per 100 tickets (all customers)"),
            ("quality.p99_wait_min", "P99 wait (min)")]
    lines = ["", "## A stronger baseline: the \"SLA due\" sort, and how late the late customers are (test days)", "",
             "| KPI | " + " | ".join(names.values()) + " | OpsLens − C (95% CI) |", "|" + "---|" * (len(names) + 2)]
    for key, label in rows:
        means = [sum(s[key] for s in test["per_seed"][p]) / len(test["per_seed"][p]) for p in names]
        d = test["opslens_minus_c"][key]
        lines.append(f"| {label} | " + " | ".join(fmt(m) for m in means)
                     + f" | {d['mean_diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}] |")
    lines += ["", "- Baselines C and D have no weights, so nothing was tuned; they ran on validation days first, then once on test days."]
    if "opslens_minus_d" in test:
        d = test["opslens_minus_d"]["turnaround.breach_pct"]
        lines.append(f"- OpsLens − industry standard, breach %: {d['mean_diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}].")
    return lines


BEST_NAMES = {"baseline_c": "C: SLA due (EDF)", "baseline_d": "D: industry standard",
              "least_slack": "Least slack first", "gen_cmu": "Generalized c-mu", "opslens": "OpsLens",
              "clairvoyant": "Clairvoyant least slack*", "clairvoyant_staffed": "Clairvoyant least slack + staffing*"}
BEST_ROWS = [("turnaround.breach_pct", "SLA breach %"), ("segment.p1_breach_pct", "P1 breach %"),
             ("quality.mean_minutes_late", "Minutes late, mean over breached tickets"),
             ("quality.late_minutes_per_100", "Minutes late per 100 tickets"), ("quality.p99_wait_min", "P99 wait (min)")]


def best_table(block: dict, names: dict) -> list[str]:
    """KPI rows (means over seeds) for the policies in `names`, plus OpsLens − each (breach %)."""
    names = {k: v for k, v in names.items() if k in block["means"]}
    lines = ["| KPI | " + " | ".join(names.values()) + " |", "|" + "---|" * (len(names) + 1)]
    for key, label in BEST_ROWS:
        lines.append(f"| {label} | " + " | ".join(fmt(block["means"][p][key]) for p in names) + " |")
    return lines


def ci_text(d: dict, nd: int = 2) -> str:
    return f"{d['mean_diff']:+.{nd}f} [{d['ci_low']:+.{nd}f}, {d['ci_high']:+.{nd}f}]"


def best_baselines_md(r: dict) -> list[str]:
    """The strongest published rules and clairvoyant least slack (eval/run_best_baselines.py)."""
    b = r.get("best_baselines")
    if not b or "test" not in b:
        return []
    v, t = b["validation"], b["test"]
    lines = ["", "## The strongest published rules, and what perfect information buys them (test days)", ""]
    lines += best_table(t, BEST_NAMES)
    lines += ["", "*Not implementable: knows each ticket's true category and true handle time. Not the optimum either "
              "(the true optimum for this many tickets cannot be computed).", "",
              "| OpsLens − … | Breach % (95% CI) | Late minutes per 100 (95% CI) |", "|---|---|---|"]
    for k, label in BEST_NAMES.items():
        if k in t["opslens_minus"]:
            d = t["opslens_minus"][k]
            lines.append(f"| {label} | {ci_text(d['turnaround.breach_pct'])} | {ci_text(d['quality.late_minutes_per_100'], 0)} |")
    pi = t["clairvoyant_minus_least_slack"]["turnaround.breach_pct"]
    lines += ["", f"- What perfect information buys the best rule (clairvoyant − least slack), breach %: {ci_text(pi)}."]
    c = v["cmu_chosen"]
    lines += [f"- Chosen on validation days {v['days'][0]}-{v['days'][1]} only: c-mu tau {c['tau']}, beta {c['beta']} "
              f"(of {len(v['cmu_grid'])} shapes; {v['cmu_rule']}). Validation breach %: OpsLens "
              f"{fmt(v['gate']['opslens_breach_pct'])}, least slack {fmt(v['means']['least_slack']['turnaround.breach_pct'])}, "
              f"c-mu {fmt(v['means']['gen_cmu']['turnaround.breach_pct'])} → gate {'passed' if v['gate']['passed'] else 'FAILED'}; "
              "test days run once."]
    return lines + rescue_md(b.get("rescue"))


RESCUE_NAMES = {"least_slack": "Least slack first", "least_slack_rescue": "Least slack + cross-skill rescue",
                "opslens": "OpsLens"}


def rescue_md(rescue: dict | None) -> list[str]:
    """Least slack with a rule-based cross-skill rescue: the freedom OpsLens has (added 18 Oct)."""
    if not rescue or "test" not in rescue:
        return []
    v, t = rescue["validation"], rescue["test"]
    lines = ["", "### Least slack + cross-skill rescue (the same freedom as OpsLens)", ""]
    lines += best_table(t, RESCUE_NAMES)
    lines.append("| Reopen rate % | " + " | ".join(fmt(t["means"][p]["quality.reopen_rate_pct"]) for p in RESCUE_NAMES) + " |")
    lines += ["", "| OpsLens − … | Breach % (95% CI) | Late minutes per 100 (95% CI) | Reopen rate % (95% CI) |",
              "|---|---|---|---|"]
    for k in ("least_slack_rescue", "least_slack"):
        d = t["opslens_minus"][k]
        lines.append(f"| {RESCUE_NAMES[k]} | {ci_text(d['turnaround.breach_pct'])} | "
                     f"{ci_text(d['quality.late_minutes_per_100'], 0)} | {ci_text(d['quality.reopen_rate_pct'])} |")
    gain = t["rescue_minus_least_slack"]["turnaround.breach_pct"]
    grid = ", ".join(f"{g['threshold_min']} min {fmt(g['breach_pct'])}%" for g in v["grid"])
    lines += ["", f"- What the rescue buys least slack (rescue − plain), breach %: {ci_text(gain)}.",
              f"- Rule: when no skilled agent is free and a ticket's slack is below the threshold but a 1.6× slower "
              f"job can still make the SLA, a free agent with the language takes it as a deliberate cross-skill job. "
              f"Threshold chosen on validation days {v['days'][0]}-{v['days'][1]} only ({v['rule']}): "
              f"{v['threshold_chosen']} min. Validation breach %: {grid}; OpsLens "
              f"{fmt(v['gate']['opslens_breach_pct'])} → gate {'passed' if v['gate']['passed'] else 'FAILED'}; "
              "test days run once. OpsLens and plain least slack were run again beside it and reproduced exactly: "
              f"{'yes' if t['reproduced'] and all(t['reproduced'].values()) else 'NO'}."]
    return lines


def sealed_rerun_md(r: dict) -> list[str]:
    """The sealed world run again with Baseline D and the published rules."""
    s = r.get("sealed_world_rerun")
    if not s or not s.get("best_baselines_test"):
        return []
    t = s["best_baselines_test"]
    lines = ["", f"## Sealed world re-run with every baseline (data seed {s['data_seed']})", ""]
    lines += best_table(t, BEST_NAMES)
    lines += ["", f"- OpsLens − D, breach %: {ci_text(t['opslens_minus']['baseline_d']['turnaround.breach_pct'])}; "
              f"− least slack {ci_text(t['opslens_minus']['least_slack']['turnaround.breach_pct'])}; "
              f"− c-mu {ci_text(t['opslens_minus']['gen_cmu']['turnaround.breach_pct'])}. "
              f"Retrained risk AUC {fmt(s['risk_auc'], 3)}. Classifier: {s['classifier']}.",
              "- Baselines were added after the first sealed run, so this world was run a second time (the first run is "
              "kept above, unchanged). OpsLens weights and the c-mu shape are frozen; nothing was chosen on this world."]
    rt = s.get("rescue_test")
    if rt:
        lines += ["", "Least slack + cross-skill rescue (added after the re-run; this world built a third time, only this "
                  "rule run beside OpsLens and plain least slack):", ""]
        lines += best_table(rt, RESCUE_NAMES)
        lines.append("| Reopen rate % | " + " | ".join(fmt(rt["means"][p]["quality.reopen_rate_pct"]) for p in RESCUE_NAMES) + " |")
        d = rt["opslens_minus"]["least_slack_rescue"]
        lines += ["", f"- OpsLens − least slack + rescue: breach % {ci_text(d['turnaround.breach_pct'])}, late minutes per "
                  f"100 {ci_text(d['quality.late_minutes_per_100'], 0)}, reopen rate % {ci_text(d['quality.reopen_rate_pct'])}. "
                  f"OpsLens and plain least slack reproduced the re-run exactly: "
                  f"{'yes' if rt['reproduced'] and all(rt['reproduced'].values()) else 'NO'}."]
    same = s.get("same_as_first_run") or {}
    if same:
        verdict = "identical to" if all(same.values()) else "NOT identical to"
        lines.append(f"- Policies in both runs ({', '.join(same)}): per-seed results {verdict} the first run.")
    return lines


def sealed_world_md(r: dict) -> list[str]:
    """The world generated after the freeze, evaluated once (eval/run_sealed_world.py)."""
    s = r.get("sealed_world")
    if not s:
        return []
    names = {"baseline_a": "Baseline A (FIFO)", "baseline_b": "Baseline B (priority)",
             "baseline_c": "Baseline C (SLA due)", "opslens": "OpsLens"}
    per = s["test"]["per_seed"]

    def mean(p: str, key: str) -> float:
        return sum(x[key] for x in per[p]) / len(per[p])

    d = s["test"]["opslens_minus_c"]["turnaround.breach_pct"]
    lines = ["", f"## Sealed second world (data seed {s['data_seed']}, generated after the freeze, run once)", "",
             "| KPI | " + " | ".join(names.values()) + " |", "|---|---|---|---|---|"]
    for key, label in (("turnaround.breach_pct", "SLA breach %"), ("quality.late_minutes_per_100", "Minutes late per 100 tickets")):
        lines.append(f"| {label} | " + " | ".join(fmt(mean(p, key)) for p in names) + " |")
    lines += ["", f"- OpsLens − Baseline C, breach %: {d['mean_diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}]. "
              f"Retrained risk AUC {fmt(s['risk_auc'], 3)}. Classifier: {s['classifier']}. Weights unchanged."]
    return lines


def realdesk_md(r: dict) -> list[str]:
    """The real public service desk (eval/run_realdesk.py): every comparison on the test months."""
    d = r.get("realdesk")
    if not d:
        return []
    s, ew, fc, rt = d["summary"], d["early_warning"], d["forecast"], d["routing"]["test"]
    lines = ["", "## The real public service desk (UCI ServiceNow log, CC BY 4.0)", "",
             f"- {s['incidents']:,} incidents, {s['teams']} teams, {s['agents']} agents; {fmt(s['missed_sla_pct'], 1)}% missed their SLA, "
             f"{fmt(s['passed_between_teams_pct'], 1)}% were passed between teams. Learning {s['learning_period'][0]} to "
             f"{s['learning_period'][1]}; test {s['test_period'][0]} to {s['test_period'][1]} ({s['test_incidents']:,} incidents).",
             "- Where open time goes: " + ", ".join(f"{k} {fmt(v, 1)}%" for k, v in s["open_time_share_pct"].items()) + "."]
    lines += [f"- {c['title']}: {fmt(c['value'], 1)} vs {fmt(c['comparison_value'], 1)} ({c['comparison_text']})." for c in d["cards"]]
    lines += ["", "| On the test months | OpsLens | What the desk used |", "|---|---|---|",
              f"| SLA-miss warning 1 h after opening (AUC) | {fmt(ew['auc_opslens'], 3)} | priority field {fmt(ew['auc_priority'], 3)} |",
              f"| Share of all SLA misses in the riskiest 20% | {fmt(ew['caught_top20_opslens_pct'], 1)}% | {fmt(ew['caught_top20_priority_pct'], 1)}% |",
              f"| Daily new incidents per team (WAPE, lower is better) | {fmt(fc['wape_learned'], 3)} | same day last week {fmt(fc['wape_same_day_last_week'], 3)} |",
              f"| Right team first time (OpsLens only when sure, {fmt(rt['sure_share_pct'], 0)}% of incidents) | "
              f"{fmt(rt['opslens_sure_right_pct'], 1)}% | desk on the same incidents {fmt(rt['desk_on_same_right_pct'], 1)}% |",
              "", f"- Not better than the desk: the forecast (check weeks chose {fc['chosen_on_check_weeks']}) and team routing "
              f"(net {rt['net_first_time_right']:+d} incidents: {rt['fixed']} fixed, {rt['made_wrong']} made wrong). Reported, not claimed."]
    return lines


def floor_md(r: dict) -> list[str]:
    """The physical floor and the share of the possible improvement captured (eval/run_floor.py)."""
    f = r.get("floor")
    if not f:
        return []
    return ["", "## How close to perfect (test days)", "",
            f"- Physical floor: {fmt(f['floor_breach_pct_mean'])}% of tickets breach even with unlimited agents and "
            f"perfect routing (their own work and reopens exceed the SLA, or nobody on shift speaks their language).",
            f"- OpsLens is {fmt(f['opslens_above_floor_points'])} points above that floor and captures "
            f"{fmt(f['captured_pct_mean'], 0)}% ± {fmt(f['captured_pct_std'], 0)} of the improvement possible over the "
            f"industry standard: (D − OpsLens) ÷ (D − floor), per seed."]


def sealed_new_md(r: dict) -> list[str]:
    """A new world under the corrected simulator, run once (eval/run_sealed_world.py --new)."""
    s = r.get("sealed_world_new")
    if not s:
        return []
    means = {**s["test"]["means"], **s["best_baselines_test"]["means"], **((s.get("rescue_test") or {}).get("means") or {})}
    names = {"baseline_d": "Industry standard", "least_slack": "Least slack first", "least_slack_rescue": "Least slack + rescue",
             "gen_cmu": "Generalized c-mu", "opslens": "OpsLens"}
    names = {k: v for k, v in names.items() if k in means}
    lines = ["", f"## New sealed world (data seed {s['data_seed']}, corrected simulator, run once)", "",
             "| KPI | " + " | ".join(names.values()) + " | Floor |", "|---|" + "---|" * (len(names) + 1)]
    for key, label in (("turnaround.breach_pct", "SLA breach %"), ("quality.late_minutes_per_100", "Minutes late per 100 tickets")):
        floor = fmt(s["floor"]["floor_breach_pct_mean"]) if key == "turnaround.breach_pct" else "—"
        lines.append(f"| {label} | " + " | ".join(fmt(means[p][key]) for p in names) + f" | {floor} |")
    lines += ["", f"- Share of the possible improvement captured: {fmt(s['floor']['captured_pct_mean'], 0)}% ± "
              f"{fmt(s['floor']['captured_pct_std'], 0)}. Retrained risk AUC {fmt(s['risk_auc'], 3)}. {s['note']}"]
    return lines


def challengers_md(r: dict) -> list[str]:
    ch = r["details"].get("challengers") or {}
    lines = ["", "## Challenger arena (pre-registered: ship only if > 2% better AND within the latency budget)", ""]
    if "forecast" in ch:
        f = ch["forecast"]
        s = f["scores"]["lead_1_24h"]
        lines.append(f"- Forecast: Chronos-2 (zero-shot) WAPE {fmt(s['wape_chronos2'], 3)} vs LightGBM {fmt(s['wape_lightgbm'], 3)} "
                     f"({f['relative_gain_pct']:+.1f}%), 80% coverage {fmt(100 * s['coverage80_chronos2'], 1)}% vs "
                     f"{fmt(100 * s['coverage80_lightgbm_conformal'], 1)}%; one 48 h refresh {fmt(f['one_refresh_s'], 1)} s → **{f['verdict']}**.")
    if "risk" in ch:
        k = ch["risk"]
        lines.append(f"- Risk: TabPFN-3 AUC {fmt(k['scores']['tabpfn3']['auc'], 4)} vs LightGBM {fmt(k['scores']['lightgbm_shipped']['auc'], 4)} "
                     f"({k['relative_gain_pct']:+.2f}%), 300-ticket refresh {fmt(k['refresh_300_s']['tabpfn3'], 2)} s → **{k['verdict']}**.")
    else:
        lines.append("- Risk: TabPFN-3 not run yet (needs the owner's TabPFN licence key).")
    return lines if ch else []


def main() -> int:
    timings: dict[str, float] = {}
    if "--assemble" not in sys.argv:
        timings = run_steps(with_blind="--blind" in sys.argv)
    elif (PARTS / "timings.json").exists():
        timings = json.loads((PARTS / "timings.json").read_text(encoding="utf-8"))
    if timings:
        (PARTS / "timings.json").write_text(json.dumps(timings, indent=1), encoding="utf-8")
    results = assemble(timings)
    (ROOT / "eval" / "results.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    (ROOT / "docs" / "NUMBERS.md").write_text(numbers_md(results), encoding="utf-8")
    print("wrote eval/results.json and docs/NUMBERS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
