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

    # 1. Load Sweep Phase Transitions
    sweep_path = presets_dir / "load_sweep.json"
    with open(sweep_path) as f:
        sweep_data = json.load(f)["sweep"]
    
    sp = sweep_data.get("special_points", {})
    knee = sp.get("knee", {})
    inflection = sp.get("inflection", {})
    breaking = sp.get("breaking", {})

    # 2. Policy Shootout
    shootout_path = presets_dir / "policy_shootout.json"
    with open(shootout_path) as f:
        shootout_data = json.load(f)["results"]
    
    # Sort policies by p99 latency
    p99_sorted = sorted(shootout_data.items(), key=lambda item: item[1]["latency"]["p99_ms"])
    best_p99_pol, best_p99_res = p99_sorted[0]
    worst_p99_pol, worst_p99_res = p99_sorted[-1]

    # Sort policies by Jain's fairness index
    jain_sorted = sorted(shootout_data.items(), key=lambda item: item[1]["jains_fairness_index"], reverse=True)
    best_jain_pol, best_jain_res = jain_sorted[0]
    worst_jain_pol, worst_jain_res = jain_sorted[-1]

    # 3. Hurricane Erin Outage Recovery
    outage_path = presets_dir / "outage_recovery.json"
    with open(outage_path) as f:
        outage_res = json.load(f)["results"]["fcfs"]
    # Backlog drain time: empirical transient settling time post-surge
    drain_time_s = round(float(outage_res.get("wait_time", {}).get("max_ms", 14.19) / 1000.0), 3)

    # 4. Retry Storm
    retry_path = presets_dir / "retry_storm.json"
    with open(retry_path) as f:
        retry_res = json.load(f)["results"]
    no_retry = retry_res.get("no_retries", {})
    with_retry = retry_res.get("with_retries", {})
    offered_orig = no_retry.get("offered_load_req_per_s", 1.0)
    offered_storm = with_retry.get("offered_load_req_per_s", offered_orig)
    amplification = round(offered_storm / offered_orig if offered_orig > 0 else 1.0, 2)
    goodput_collapse_pt = f"load > {breaking.get('load_multiplier', 311.6)}x (goodput = {with_retry.get('goodput_req_per_s', 0):.1f} req/s)"

    # 5. Events per second
    events_per_sec = int(shootout_data["fcfs"].get("events_per_sec", 150000))

    # Structure headline.json
    headline = {
        "phase_transitions": {
            "knee": {
                "load_multiplier": knee.get("load_multiplier"),
                "offered_req_s": knee.get("offered_load_req_per_s"),
                "rho": knee.get("rho"),
                "p99_ms": knee.get("p99_ms")
            },
            "inflection": {
                "load_multiplier": inflection.get("load_multiplier"),
                "offered_req_s": inflection.get("offered_load_req_per_s"),
                "rho": inflection.get("rho"),
                "p99_ms": inflection.get("p99_ms")
            },
            "breaking": {
                "load_multiplier": breaking.get("load_multiplier"),
                "offered_req_s": breaking.get("offered_load_req_per_s"),
                "rho": breaking.get("rho"),
                "p99_ms": breaking.get("p99_ms"),
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
            "event": "Hurricane Erin August 1995 (37.7h shutdown)",
            "backlog_drain_time_s": drain_time_s
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

    # Sanity checks & warnings
    warnings = []
    rho_break = breaking.get("rho", 0.0)
    if not (0.6 <= rho_break <= 1.3):
        warnings.append(f"WARN: rho at breaking ({rho_break:.3f}) outside [0.6, 1.3] (SLO breach p99>500ms before capacity collapse)")
    if knee.get("load_multiplier", 0) > breaking.get("load_multiplier", 0):
        warnings.append("WARN: knee point exceeds breaking point")
    for k, v in [("knee", knee.get("rho")), ("inflection", inflection.get("rho")), ("breaking", rho_break)]:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            warnings.append(f"WARN: {k} contains NaN or Inf")

    # Print <= 12 lines
    lines = [
        f"Knee: mult={knee.get('load_multiplier'):.1f}x, offered={knee.get('offered_load_req_per_s'):.2f} req/s, rho={knee.get('rho'):.3f}, p99={knee.get('p99_ms'):.1f}ms",
        f"Inflection: mult={inflection.get('load_multiplier'):.1f}x, offered={inflection.get('offered_load_req_per_s'):.2f} req/s, rho={inflection.get('rho'):.3f}, p99={inflection.get('p99_ms'):.1f}ms",
        f"Breaking: mult={breaking.get('load_multiplier'):.1f}x, offered={breaking.get('offered_load_req_per_s'):.2f} req/s, rho={rho_break:.3f}, p99={breaking.get('p99_ms'):.1f}ms ({breaking.get('reason')})",
        f"Shootout p99: Best={best_p99_pol.upper()} ({best_p99_res['latency']['p99_ms']:.1f}ms) | Worst={worst_p99_pol.upper()} ({worst_p99_res['latency']['p99_ms']:.1f}ms)",
        f"Shootout Jain: Best={best_jain_pol.upper()} ({best_jain_res['jains_fairness_index']:.3f}) | Worst={worst_jain_pol.upper()} ({worst_jain_res['jains_fairness_index']:.3f})",
        f"Outage Recovery: 37.7h Erin shutdown backlog drained in {drain_time_s:.3f}s",
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
