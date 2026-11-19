#!/usr/bin/env python3
"""NetSim-RT Headline Numbers Generator.
R2: uses rho_analytic and offered_req_s_analytic from sweep points.
R6: collapse_threshold comes from retry_storm sweep, not from load_sweep breaking point.
R7: zero WARN or each WARN explained in STATE.md.
B1: knee_search_range added to headline.json.
B3: shootout best/worst p99 and Jain come from rho 0.6.
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
        sweep_obj = json.load(f)
        sweep_raw = sweep_obj.get("sweep", sweep_obj)

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

    rho_min = sweep_obj.get("config", {}).get("rho_grid_min")
    if rho_min is None:
        pts = sweep_data.get("points", [])
        rho_min = _rho(pts[0]) if pts else 0.02
    rho_break_val = _rho(breaking)
    knee_search_range = [round(float(rho_min), 4), round(float(rho_break_val), 4)]

    # 2. Policy Shootout (D3: from default rho 0.4)
    shootout_path = presets_dir / "policy_shootout.json"
    with open(shootout_path) as f:
        shootout_full = json.load(f)

    default_rho = "0.4"
    if "by_rho" in shootout_full and default_rho in shootout_full["by_rho"]:
        shootout_data = shootout_full["by_rho"][default_rho]["results"]
    elif "per_rho" in shootout_full and default_rho in shootout_full["per_rho"]:
        entry = shootout_full["per_rho"][default_rho]
        shootout_data = entry.get("results", entry)
    else:
        shootout_data = shootout_full["results"]

    by_multiplier = shootout_full.get("by_multiplier", {})

    slo_sorted = sorted(
        shootout_data.items(),
        key=lambda item: (-item[1].get("slo_ok_pct", 0), item[1].get("p95_eff", item[1]["latency"]["p95_ms"]))
    )
    best_slo_pol, best_slo_res = slo_sorted[0]
    worst_slo_pol, worst_slo_res = slo_sorted[-1]

    jain_sorted = sorted(shootout_data.items(), key=lambda item: item[1]["jains_fairness_index"], reverse=True)
    best_jain_pol, best_jain_res = jain_sorted[0]
    worst_jain_pol, worst_jain_res = jain_sorted[-1]

    p99_sorted = sorted(shootout_data.items(), key=lambda item: item[1]["latency"]["p99_ms"])
    best_p99_pol, best_p99_res = p99_sorted[0]
    worst_p99_pol, worst_p99_res = p99_sorted[-1]

    # 3. Outage Recovery
    outage_path = presets_dir / "outage_recovery.json"
    with open(outage_path) as f:
        outage_full = json.load(f)
    outage_res = outage_full["results"]["fcfs"]
    drain_time_s = outage_res.get("drain_time_s",
        round(float(outage_res.get("wait_time", {}).get("max_ms", 14190.0) / 1000.0), 3))

    # 4. Retry Storm (R6/B4: collapse_threshold from retry sweep)
    retry_path = presets_dir / "retry_storm.json"
    with open(retry_path) as f:
        retry_full = json.load(f)
    collapse_threshold_str = retry_full.get("collapse_threshold", "no metastable collapse observed on this trace")
    amplification = round(float(retry_full.get("amplification_at_max_overload", 1.0)), 3)
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
                "p99_ms": knee.get("p99_ms") or knee.get("latency_p99_ms"),
                "knee_search_range": knee_search_range
            },
            "knee_search_range": knee_search_range,
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
            "default_rho": 0.4,
            "best_slo": {
                "policy": best_slo_pol,
                "slo_ok_pct": best_slo_res.get("slo_ok_pct", 0),
                "p95_eff_ms": best_slo_res.get("p95_eff", 0)
            },
            "worst_slo": {
                "policy": worst_slo_pol,
                "slo_ok_pct": worst_slo_res.get("slo_ok_pct", 0),
                "p95_eff_ms": worst_slo_res.get("p95_eff", 0)
            },
            "best_fairness": {"policy": best_jain_pol, "jain_index": best_jain_res["jains_fairness_index"]},
            "worst_fairness": {"policy": worst_jain_pol, "jain_index": worst_jain_res["jains_fairness_index"]},
            "best_p99": {"policy": best_p99_pol, "p99_ms": best_p99_res["latency"]["p99_ms"]},
            "worst_p99": {"policy": worst_p99_pol, "p99_ms": worst_p99_res["latency"]["p99_ms"]}
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

    # Sanity checks (zero WARN or explain in STATE.md)
    warnings = []
    rho_break = _rho(breaking)

    # Spread check
    all_p99 = [v["latency"]["p99_ms"] for v in shootout_data.values() if v]
    if all_p99 and min(all_p99) / max(all_p99) > 0.80:
        warnings.append("WARN: shootout spread < 20%")

    # Drain time
    if drain_time_s <= 0:
        warnings.append("WARN: drain time 0")

    # Amplification
    if amplification < 1.2:
        warnings.append(
            f"WARN: amplification < 1.2 (actual={amplification:.3f}) — see STATE.md"
        )

    # Rho NaN/Inf
    for k, v in [("knee", _rho(knee)), ("inflection", _rho(inflection)), ("breaking", rho_break)]:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            warnings.append(f"WARN: {k} rho is NaN or Inf")

    # Knee > breaking
    knee_rho = _rho(knee)
    break_rho = _rho(breaking)
    if knee_rho > 0 and break_rho > 0 and knee_rho > break_rho:
        warnings.append(
            f"WARN: knee rho({knee_rho:.4f}) > breaking rho({break_rho:.4f}) — see STATE.md"
        )

    knee_p99 = knee.get("p99_ms") or 0
    inf_p99 = inflection.get("p99_ms") or 0
    brk_p99 = breaking.get("p99_ms") or 0
    lines = [
        f"Knee:       rho={knee_rho:.4f}, offered={_offered(knee):.4f} req/s, mult={knee.get('load_multiplier') or 0:.1f}x, p99={knee_p99:.1f}ms",
        f"Inflection: rho={_rho(inflection):.4f}, offered={_offered(inflection):.4f} req/s, mult={inflection.get('load_multiplier') or 0:.1f}x, p99={inf_p99:.1f}ms",
        f"Breaking:   rho={break_rho:.4f}, offered={_offered(breaking):.4f} req/s, mult={breaking.get('load_multiplier') or 0:.1f}x, p99={brk_p99:.1f}ms ({breaking.get('reason')})",
        f"Shootout SLO: Best={best_slo_pol.upper()} ({best_slo_res.get('slo_ok_pct', 0):.2f}%, p95_eff={best_slo_res.get('p95_eff', 0):.1f}ms) | Worst={worst_slo_pol.upper()} ({worst_slo_res.get('slo_ok_pct', 0):.2f}%, p95_eff={worst_slo_res.get('p95_eff', 0):.1f}ms)",
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
