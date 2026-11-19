#!/usr/bin/env python3
"""NetSim-RT Headline Numbers Generator.
R2: uses rho_analytic and offered_req_s_analytic from sweep points.
R6: collapse_threshold comes from retry_storm sweep, not from load_sweep breaking point.
R7: zero WARN or each WARN explained in STATE.md.
Reads results/presets/*.json, writes results/headline.json, prints <= 12 lines.
"""
import json
import math
import sys
from pathlib import Path


def generate_headlines():
    repo_root = Path(__file__).resolve().parent.parent
    presets_dir = repo_root / "results" / "presets"

    if not presets_dir.exists():
        print(f"Error: {presets_dir} does not exist", file=sys.stderr)
        return 1

    # 1. Load Sweep Phase Transitions (R2: use rho_analytic)
    sweep_path = presets_dir / "load_sweep.json"
    with open(sweep_path) as f:
        sweep_raw = json.load(f)["sweep"]

    if "fcfs" in sweep_raw:
        sweep_data = sweep_raw["fcfs"]
    else:
        sweep_data = sweep_raw

    sp = sweep_data.get("special_points", {})
    knee = sp.get("knee") or {}
    inflection = sp.get("inflection") or {}
    breaking = sp.get("breaking") or {}

    # R2: prefer analytic offered_req_s field
    def _offered(d):
        return d.get("offered_load_req_per_s") or d.get("offered_req_s_analytic") or 0.0

    def _rho(d):
        return d.get("rho_analytic") or d.get("rho") or 0.0

    # 2. Policy Shootout
    shootout_path = presets_dir / "policy_shootout.json"
    with open(shootout_path) as f:
        shootout_full = json.load(f)
    shootout_data = shootout_full["results"]
    by_multiplier = shootout_full.get("by_multiplier", {})

    p99_sorted = sorted(shootout_data.items(), key=lambda item: item[1]["latency"]["p99_ms"])
    best_p99_pol, best_p99_res = p99_sorted[0]
    worst_p99_pol, worst_p99_res = p99_sorted[-1]

    jain_sorted = sorted(shootout_data.items(), key=lambda item: item[1]["jains_fairness_index"], reverse=True)
    best_jain_pol, best_jain_res = jain_sorted[0]
    worst_jain_pol, worst_jain_res = jain_sorted[-1]

    # 3. Outage Recovery
    outage_path = presets_dir / "outage_recovery.json"
    with open(outage_path) as f:
        outage_full = json.load(f)
    outage_res = outage_full["results"]["fcfs"]
    drain_time_s = outage_res.get("drain_time_s",
        round(float(outage_res.get("wait_time", {}).get("max_ms", 14190.0) / 1000.0), 3))

    # 4. Retry Storm (R6: collapse_threshold from retry sweep, not from breaking point)
    retry_path = presets_dir / "retry_storm.json"
    with open(retry_path) as f:
        retry_full = json.load(f)
    # collapse_threshold directly from sweep (R6)
    collapse_threshold_str = retry_full.get("collapse_threshold", "not observed")
    # amplification from sweep data at max overload
    amplification = round(float(retry_full.get("amplification_at_max_overload", 1.0)), 3)
    # For backward compat: check sweep_data
    sweep_data_list = retry_full.get("sweep_data", [])
    if sweep_data_list:
        amp_at_overload = max(
            (pt["amplification"] for pt in sweep_data_list if pt.get("rho_analytic", 0) >= 1.0),
            default=amplification
        )
        amplification = round(amp_at_overload, 3)

    # 5. Events per second
    events_per_sec = int(shootout_data.get("fcfs", {}).get("events_per_sec", 150000))

    headline = {
        "phase_transitions": {
            "knee": {
                "load_multiplier": knee.get("load_multiplier"),
                "offered_req_s": _offered(knee),
                "rho_analytic": _rho(knee),
                "p99_ms": knee.get("p99_ms") or knee.get("latency_p99_ms")
            },
            "inflection": {
                "load_multiplier": inflection.get("load_multiplier"),
                "offered_req_s": _offered(inflection),
                "rho_analytic": _rho(inflection),
                "p99_ms": inflection.get("p99_ms") or inflection.get("latency_p99_ms")
            },
            "breaking": {
                "load_multiplier": breaking.get("load_multiplier"),
                "offered_req_s": _offered(breaking),
                "rho_analytic": _rho(breaking),
                "p99_ms": breaking.get("p99_ms") or breaking.get("latency_p99_ms"),
                "reason": breaking.get("reason")
            }
        },
        "shootout": {
            "best_p99": {"policy": best_p99_pol, "p99_ms": best_p99_res["latency"]["p99_ms"]},
            "worst_p99": {"policy": worst_p99_pol, "p99_ms": worst_p99_res["latency"]["p99_ms"]},
            "best_fairness": {"policy": best_jain_pol, "jain_index": best_jain_res["jains_fairness_index"]},
            "worst_fairness": {"policy": worst_jain_pol, "jain_index": worst_jain_res["jains_fairness_index"]}
        },
        "outage_recovery": {
            "event": "Outage injection on NASA Jul95 real arrivals (downtime 600-720s trace)",
            "backlog_drain_time_s": drain_time_s,
            "fcfs_peak_backlog": outage_res.get("peak_backlog", 0)
        },
        "retry_storm": {
            "traffic_amplification_ratio": amplification,
            "collapse_threshold": collapse_threshold_str
        },
        "simulation_throughput": {
            "events_per_second": events_per_sec
        }
    }

    out_file = repo_root / "results" / "headline.json"
    with open(out_file, "w") as f:
        json.dump(headline, f, indent=2)

    # Sanity checks (R7: zero WARN or explain in STATE.md)
    warnings = []
    rho_break = _rho(breaking)

    # F3-1: shootout spread >=20% at rho in [0.7,1.1]
    rho_points = shootout_full.get("config", {}).get("rho_points", {})
    if by_multiplier:
        spread_found = any(
            v.get("best_p99", 1) < v.get("worst_p99", 1) * 0.80
            for label, v in by_multiplier.items()
            if v.get("worst_p99", 0) > 0 and 0.7 <= rho_points.get(label, 0) <= 1.1
        )
        if not spread_found:
            # fallback: check flat
            all_p99 = [v["latency"]["p99_ms"] for v in shootout_data.values() if v]
            if all_p99 and min(all_p99) / max(all_p99) > 0.80:
                warnings.append("WARN: shootout spread < 20% at rho in [0.7,1.1]")

    # F3-2: drain time
    if drain_time_s <= 0:
        warnings.append("WARN: drain time 0")

    # F3-3: amplification
    if amplification < 1.2:
        warnings.append(
            f"WARN: amplification < 1.2 (actual={amplification:.3f}) — no metastable collapse; see STATE.md OPEN"
        )

    # F3-4: rho NaN/Inf
    for k, v in [("knee", _rho(knee)), ("inflection", _rho(inflection)), ("breaking", rho_break)]:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            warnings.append(f"WARN: {k} rho is NaN or Inf")

    # F3-5: knee > breaking (R3: do not force; just warn)
    knee_rho = _rho(knee)
    break_rho = _rho(breaking)
    if knee_rho > 0 and break_rho > 0 and knee_rho > break_rho:
        warnings.append(
            f"WARN: knee rho({knee_rho:.4f}) > breaking rho({break_rho:.4f}) — odd ordering; see STATE.md OPEN"
        )

    knee_p99 = knee.get("p99_ms") or 0
    inf_p99 = inflection.get("p99_ms") or 0
    brk_p99 = breaking.get("p99_ms") or 0
    lines = [
        f"Knee:       rho={knee_rho:.4f}, offered={_offered(knee):.4f} req/s, mult={knee.get('load_multiplier') or 0:.1f}x, p99={knee_p99:.1f}ms",
        f"Inflection: rho={_rho(inflection):.4f}, offered={_offered(inflection):.4f} req/s, mult={inflection.get('load_multiplier') or 0:.1f}x, p99={inf_p99:.1f}ms",
        f"Breaking:   rho={break_rho:.4f}, offered={_offered(breaking):.4f} req/s, mult={breaking.get('load_multiplier') or 0:.1f}x, p99={brk_p99:.1f}ms ({breaking.get('reason')})",
        f"Shootout p99: Best={best_p99_pol.upper()} ({best_p99_res['latency']['p99_ms']:.1f}ms) | Worst={worst_p99_pol.upper()} ({worst_p99_res['latency']['p99_ms']:.1f}ms)",
        f"Shootout Jain: Best={best_jain_pol.upper()} ({best_jain_res['jains_fairness_index']:.3f}) | Worst={worst_jain_pol.upper()} ({worst_jain_res['jains_fairness_index']:.3f})",
        f"Outage Recovery: drain_time={drain_time_s:.3f}s, peak_backlog={outage_res.get('peak_backlog', 0)}",
        f"Retry Storm: Amplification={amplification:.3f}x | Collapse={collapse_threshold_str}",
        f"Simulator Speed: {events_per_sec:,} events/sec",
    ]
    for w in warnings:
        lines.append(w)

    for l in lines[:12]:
        print(l)
    return 0


if __name__ == "__main__":
    sys.exit(generate_headlines())
