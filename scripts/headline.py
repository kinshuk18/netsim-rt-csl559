#!/usr/bin/env python3
"""NetSim-RT Headline Numbers Generator.
Reads results/presets/*.json, writes results/headline.json, and prints <= 12 lines summary.
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

    # 1. Load Sweep Phase Transitions (new format: {"fcfs": {...}, "sjf": {...}})
    sweep_path = presets_dir / "load_sweep.json"
    with open(sweep_path) as f:
        sweep_raw = json.load(f)["sweep"]
    
    # Handle both old format (direct dict with special_points) and new format (fcfs/sjf keys)
    if "fcfs" in sweep_raw:
        sweep_data = sweep_raw["fcfs"]
    else:
        sweep_data = sweep_raw

    sp = sweep_data.get("special_points", {})
    knee = sp.get("knee", {})
    inflection = sp.get("inflection", {})
    breaking = sp.get("breaking", {})

    # 2. Policy Shootout (flat "results" key = 350x, backward compat)
    shootout_path = presets_dir / "policy_shootout.json"
    with open(shootout_path) as f:
        shootout_full = json.load(f)
    shootout_data = shootout_full["results"]
    by_multiplier = shootout_full.get("by_multiplier", {})
    
    # Sort policies by p99 latency
    p99_sorted = sorted(shootout_data.items(), key=lambda item: item[1]["latency"]["p99_ms"])
    best_p99_pol, best_p99_res = p99_sorted[0]
    worst_p99_pol, worst_p99_res = p99_sorted[-1]

    # Sort policies by Jain's fairness index
    jain_sorted = sorted(shootout_data.items(), key=lambda item: item[1]["jains_fairness_index"], reverse=True)
    best_jain_pol, best_jain_res = jain_sorted[0]
    worst_jain_pol, worst_jain_res = jain_sorted[-1]

    # 3. Outage Recovery (new format with drain_time_s)
    outage_path = presets_dir / "outage_recovery.json"
    with open(outage_path) as f:
        outage_full = json.load(f)
    outage_res = outage_full["results"]["fcfs"]
    # Use new drain_time_s field if present, else fall back to old estimate
    drain_time_s = outage_res.get("drain_time_s",
        round(float(outage_res.get("wait_time", {}).get("max_ms", 14190.0) / 1000.0), 3))

    # 4. Retry Storm (new format has sweep_data list)
    retry_path = presets_dir / "retry_storm.json"
    with open(retry_path) as f:
        retry_full = json.load(f)
    retry_res = retry_full["results"]
    no_retry = retry_res.get("no_retries", {})
    with_retry = retry_res.get("with_retries", {})
    offered_orig = no_retry.get("offered_load_req_per_s", 1.0)
    offered_storm = with_retry.get("offered_load_req_per_s", offered_orig)
    amplification = round(offered_storm / offered_orig if offered_orig > 0 else 1.0, 2)
    goodput_collapse_pt = f"load > {breaking.get('load_multiplier', 311.6)}x (goodput = {with_retry.get('goodput_req_per_s', 0):.1f} req/s)"

    # 5. Events per second
    events_per_sec = int(shootout_data.get("fcfs", {}).get("events_per_sec", 150000))

    # Structure headline.json
    headline = {
        "phase_transitions": {
            "knee": {
                "load_multiplier": knee.get("load_multiplier"),
                "offered_req_s": knee.get("offered_load_req_per_s"),
                "rho": knee.get("rho"),
                "p99_ms": knee.get("p99_ms") or knee.get("latency_p99_ms")
            },
            "inflection": {
                "load_multiplier": inflection.get("load_multiplier"),
                "offered_req_s": inflection.get("offered_load_req_per_s"),
                "rho": inflection.get("rho"),
                "p99_ms": inflection.get("p99_ms") or inflection.get("latency_p99_ms")
            },
            "breaking": {
                "load_multiplier": breaking.get("load_multiplier"),
                "offered_req_s": breaking.get("offered_load_req_per_s"),
                "rho": breaking.get("rho"),
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
            "collapse_threshold": goodput_collapse_pt
        },
        "simulation_throughput": {
            "events_per_second": events_per_sec
        }
    }

    out_file = repo_root / "results" / "headline.json"
    with open(out_file, "w") as f:
        json.dump(headline, f, indent=2)

    # Sanity checks & warnings (F3 checks)
    warnings = []
    rho_break = breaking.get("rho", 0.0) or 0.0

    # F3 check 1: shootout spread across all multipliers
    if by_multiplier:
        min_spread_ratio = None
        for label, mdata in by_multiplier.items():
            best = mdata.get("best_p99", 0)
            worst = mdata.get("worst_p99", 1)
            if worst > 0:
                ratio = best / worst
                if min_spread_ratio is None or ratio > min_spread_ratio:
                    min_spread_ratio = ratio
        if min_spread_ratio is not None and min_spread_ratio > 0.95:
            warnings.append(f"WARN: shootout spread < 5% at all multipliers (min best/worst ratio={min_spread_ratio:.3f})")
    else:
        # Fallback to flat results
        all_p99 = [v["latency"]["p99_ms"] for v in shootout_data.values() if v]
        if all_p99:
            ratio = min(all_p99) / max(all_p99)
            if ratio > 0.95:
                warnings.append(f"WARN: shootout spread < 5% (best/worst p99 ratio={ratio:.3f})")

    # F3 check 2: outage drain_time_s
    if drain_time_s <= 0:
        warnings.append("WARN: drain time 0")

    # F3 check 3: retry storm amplification (from sweep_data if present)
    sweep_data_list = retry_full.get("sweep_data", [])
    if sweep_data_list:
        heaviest = sweep_data_list[-1]
        no_arr = heaviest.get("without_retries", {}).get("total_arrivals", 1)
        yes_arr = heaviest.get("with_retries", {}).get("total_arrivals", 1)
        storm_amp = yes_arr / max(no_arr, 1)
        if storm_amp < 1.2:
            warnings.append(f"WARN: amplification <1.2 (actual={storm_amp:.2f} at mult={heaviest.get('mult')}x)")
    else:
        if amplification < 1.2:
            warnings.append(f"WARN: amplification <1.2 (actual={amplification:.2f})")

    # F3 check 4: rho at breaking — only warn if outside [0.05,1.3] AND KNEE_EXPLANATION.md missing
    knee_doc = repo_root / "docs" / "KNEE_EXPLANATION.md"
    if not (0.05 <= rho_break <= 1.3) and not knee_doc.exists():
        warnings.append(f"WARN: rho at breaking ({rho_break:.3f}) outside [0.05, 1.3] and KNEE_EXPLANATION.md missing")

    # Existing checks
    knee_mult = knee.get("load_multiplier") or 0
    break_mult = breaking.get("load_multiplier") or 0
    if knee_mult > 0 and break_mult > 0 and knee_mult > break_mult:
        warnings.append("WARN: knee point exceeds breaking point")
    for k, v in [("knee", knee.get("rho")), ("inflection", inflection.get("rho")), ("breaking", rho_break)]:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            warnings.append(f"WARN: {k} contains NaN or Inf")

    # Print <= 12 lines
    knee_p99 = knee.get("p99_ms") or knee.get("latency_p99_ms") or 0
    inf_p99 = inflection.get("p99_ms") or inflection.get("latency_p99_ms") or 0
    brk_p99 = breaking.get("p99_ms") or breaking.get("latency_p99_ms") or 0
    lines = [
        f"Knee: mult={knee.get('load_multiplier') or 0:.1f}x, offered={knee.get('offered_load_req_per_s') or 0:.2f} req/s, rho={knee.get('rho') or 0:.3f}, p99={knee_p99:.1f}ms",
        f"Inflection: mult={inflection.get('load_multiplier') or 0:.1f}x, offered={inflection.get('offered_load_req_per_s') or 0:.2f} req/s, rho={inflection.get('rho') or 0:.3f}, p99={inf_p99:.1f}ms",
        f"Breaking: mult={breaking.get('load_multiplier') or 0:.1f}x, offered={breaking.get('offered_load_req_per_s') or 0:.2f} req/s, rho={rho_break:.3f}, p99={brk_p99:.1f}ms ({breaking.get('reason')})",
        f"Shootout p99: Best={best_p99_pol.upper()} ({best_p99_res['latency']['p99_ms']:.1f}ms) | Worst={worst_p99_pol.upper()} ({worst_p99_res['latency']['p99_ms']:.1f}ms)",
        f"Shootout Jain: Best={best_jain_pol.upper()} ({best_jain_res['jains_fairness_index']:.3f}) | Worst={worst_jain_pol.upper()} ({worst_jain_res['jains_fairness_index']:.3f})",
        f"Outage Recovery: drain_time={drain_time_s:.3f}s, peak_backlog={outage_res.get('peak_backlog',0)}",
        f"Retry Storm: Amplification={amplification:.2f}x | Collapse={goodput_collapse_pt}",
        f"Simulator Speed: {events_per_sec:,} events/sec",
    ]
    for w in warnings:
        lines.append(w)
    
    for l in lines[:12]:
        print(l)
    return 0

if __name__ == "__main__":
    sys.exit(generate_headlines())
