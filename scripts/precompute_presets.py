"""
Precompute Demo Presets and Phase Transitions
CSL559 Computer Systems Design - IIT Bhilai

R1: max_requests=None for all EPA sweep/shootout/retry runs (full 47742 req, each run ~0.5s).
R2: Sweep grid by rho_analytic (not multiplier). lam/ES from full trace; mult=rho*c/(lam*ES).
R3: Knee via KneeLocator(x=rho_analytic), inflection via 2nd-derivative restricted to rho<=1.0.
R4: SJF vs FCFS on same rho_grid; both knees/breaking points recorded.
R5: Jain is on slowdown vector; definition written to docs/KNEE_EXPLANATION.md.
R6: Retry storm on full trace, rho 0.8-1.3, timeout=2*p99@rho=0.2, collapse_threshold from sweep.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd

from engine.models import SimulationConfig
from engine.simulator import Simulator
from engine.sweep import run_sweep


# ---------------------------------------------------------------------------
# Analytic trace parameters (R2: derived once from full EPA trace)
# ---------------------------------------------------------------------------
def _epa_params():
    df = pd.read_parquet("data/processed/epa.parquet", columns=["ts", "service_time_s"])
    span = float(df["ts"].iloc[-1] - df["ts"].iloc[0])
    lam = len(df) / span
    es = float(df["service_time_s"].mean())
    es2 = float((df["service_time_s"] ** 2).mean())
    cv2 = es2 / es ** 2 - 1.0
    return lam, es, es2, cv2, span, len(df)


def precompute():
    results_dir = Path("results/presets")
    results_dir.mkdir(parents=True, exist_ok=True)

    print("Loading EPA trace parameters (R2)...")
    lam, es, es2, cv2, span, n_epa = _epa_params()
    c1 = 1
    print(f"  lam={lam:.6f} req/s  ES={es*1000:.4f} ms  ES2={es2*1e6:.4f} us2  cv2={cv2:.4f}  N={n_epa}")

    # R2: rho_grid for sweep (c=1)
    rho_grid = np.logspace(np.log10(0.02), np.log10(1.3), 25).tolist()

    # -----------------------------------------------------------------------
    # PRESET 1: Baseline Workload
    # -----------------------------------------------------------------------
    print("Generating baseline preset...")
    df_epa = pd.read_parquet("data/processed/epa.parquet", columns=["ts"])
    bins_1h = np.arange(df_epa["ts"].iloc[0], df_epa["ts"].iloc[-1], 3600.0)
    c_1h, e_1h = np.histogram(df_epa["ts"].values, bins=bins_1h)
    med_idx = int(np.argmin(np.abs(c_1h - np.median(c_1h))))
    baseline_start = float(e_1h[med_idx])

    baseline_shootout = {}
    for pol in ["fcfs", "sjf", "rr", "static_priority"]:
        cfg = SimulationConfig(
            trace_path="data/processed/epa.parquet",
            policy=pol,
            num_servers=4,
            load_multiplier=1.0,
            window_start_s=baseline_start,
            window_duration_s=3600.0,
            max_requests=None  # R1: full trace
        )
        res = Simulator(cfg).run()
        baseline_shootout[pol] = res.to_dict()

    p_baseline = {
        "id": "baseline",
        "title": "Baseline Workload (Median-Load Hour)",
        "description": "Standard operational load from median-volume 1-hour window, all policies, max_requests=None.",
        "config": {
            "trace_name": "epa",
            "window_start_s": baseline_start,
            "window_duration_s": 3600.0,
            "num_servers": 4,
            "load_multiplier": 1.0
        },
        "results": baseline_shootout
    }
    with open(results_dir / "baseline.json", "w") as f:
        json.dump(p_baseline, f, indent=2)
    print("  baseline done")

    # -----------------------------------------------------------------------
    # PRESET 2: Flash Crowd
    # -----------------------------------------------------------------------
    print("Generating flash crowd preset...")
    df_jul = pd.read_parquet("data/processed/nasa_jul95.parquet", columns=["ts"])
    bins_10m = np.arange(df_jul["ts"].iloc[0], df_jul["ts"].iloc[-1], 600.0)
    c_10m, e_10m = np.histogram(df_jul["ts"].values, bins=bins_10m)
    flash_idx = int(np.argmax(c_10m))
    flash_start = float(e_10m[flash_idx])

    flash_shootout = {}
    for pol in ["fcfs", "sjf", "static_priority", "mlfq"]:
        cfg = SimulationConfig(
            trace_path="data/processed/nasa_jul95.parquet",
            policy=pol,
            num_servers=2,
            load_multiplier=5.0,
            queue_capacity=1000,
            window_start_s=flash_start,
            window_duration_s=600.0,
            max_requests=None  # R1: full window
        )
        res = Simulator(cfg).run()
        flash_shootout[pol] = res.to_dict()

    p_flash = {
        "id": "flash_crowd",
        "title": "Flash Crowd (Busiest 10-Minute Window)",
        "description": "Peak arrival surge on NASA July trace under 5x load compression.",
        "config": {
            "trace_name": "nasa_jul95",
            "window_start_s": flash_start,
            "window_duration_s": 600.0,
            "num_servers": 2,
            "load_multiplier": 5.0
        },
        "results": flash_shootout
    }
    with open(results_dir / "flash_crowd.json", "w") as f:
        json.dump(p_flash, f, indent=2)
    print("  flash crowd done")

    # -----------------------------------------------------------------------
    # PRESET 3: Outage and Recovery
    # -----------------------------------------------------------------------
    print("Generating outage-and-recovery preset...")
    jul95_outage_start = 397800.0
    jul95_outage_dur = 1800.0
    jul95_mult = 34.7
    dt_start_sim = 600.0 / jul95_mult
    dt_end_sim = 720.0 / jul95_mult
    outage_policies = ["fcfs", "sjf", "static_priority"]
    outage_results = {}
    for pol in outage_policies:
        cfg = SimulationConfig(
            trace_path="data/processed/nasa_jul95.parquet",
            policy=pol,
            num_servers=1,
            load_multiplier=jul95_mult,
            window_start_s=jul95_outage_start,
            window_duration_s=jul95_outage_dur,
            server_downtime_start_s=dt_start_sim,
            server_downtime_end_s=dt_end_sim
        )
        sim = Simulator(cfg)
        res = sim.run()
        drain_time = (sim.drain_end_time - dt_end_sim) if sim.drain_end_time else 0.0
        outage_results[pol] = {
            **res.to_dict(),
            "peak_backlog": sim.peak_backlog,
            "drain_time_s": round(drain_time, 2),
            "p99_recovery_ms": round(res.latency_p99 * 1000.0, 2)
        }

    if outage_results.get("fcfs", {}).get("drain_time_s", 0) <= 0:
        raise RuntimeError("drain_time=0: check downtime config")

    p_outage = {
        "id": "outage_recovery",
        "title": "Outage injection on real arrivals",
        "description": (
            f"NASA Jul95 busiest 30-min (trace), c=1, mult={jul95_mult}x (rho~0.6). "
            f"Server downtime sim_time [{dt_start_sim:.2f}s,{dt_end_sim:.2f}s] = trace 600-720s. "
            f"FCFS peak backlog={outage_results['fcfs']['peak_backlog']}, "
            f"drain_time={outage_results['fcfs']['drain_time_s']}s."
        ),
        "config": {
            "trace_name": "nasa_jul95",
            "window_start_s": jul95_outage_start,
            "window_duration_s": jul95_outage_dur,
            "num_servers": 1,
            "load_multiplier": jul95_mult,
            "server_downtime_start_sim_s": dt_start_sim,
            "server_downtime_end_sim_s": dt_end_sim,
            "server_downtime_trace_start_s": 600.0,
            "server_downtime_trace_end_s": 720.0
        },
        "results": outage_results
    }
    with open(results_dir / "outage_recovery.json", "w") as f:
        json.dump(p_outage, f, indent=2)
    print("  outage done")

    # -----------------------------------------------------------------------
    # PRESET 4: Load Sweep — R2/R3/R4: rho_grid, analytic values, FCFS+SJF
    # -----------------------------------------------------------------------
    print("Generating load sweep preset (FCFS + SJF, rho_grid R2/R3/R4)...")
    fcfs_sweep = run_sweep(
        trace_path="data/processed/epa.parquet",
        policy="fcfs",
        num_servers=1,
        rho_grid=rho_grid,
        slo_target_s=0.500,
        max_requests=None,  # R1
        workers=8,
        lam_analytic=lam,
        es_analytic=es,
    )
    sjf_sweep = run_sweep(
        trace_path="data/processed/epa.parquet",
        policy="sjf",
        num_servers=1,
        rho_grid=rho_grid,
        slo_target_s=0.500,
        max_requests=None,  # R1
        workers=8,
        lam_analytic=lam,
        es_analytic=es,
    )
    # R4: record both knees and breaking points
    fcfs_knee = fcfs_sweep.get("special_points", {}).get("knee") or {}
    sjf_knee = sjf_sweep.get("special_points", {}).get("knee") or {}
    fcfs_break = fcfs_sweep.get("special_points", {}).get("breaking") or {}
    sjf_break = sjf_sweep.get("special_points", {}).get("breaking") or {}
    fcfs_knee_rho = fcfs_knee.get("rho", 0)
    sjf_knee_rho = sjf_knee.get("rho", 0)
    print(f"  FCFS knee rho={fcfs_knee_rho:.4f}  SJF knee rho={sjf_knee_rho:.4f}")
    print(f"  FCFS break rho={fcfs_break.get('rho',0):.4f}  SJF break rho={sjf_break.get('rho',0):.4f}")

    if sjf_knee_rho > 0 and fcfs_knee_rho > 0 and sjf_knee_rho <= fcfs_knee_rho:
        with open("STATE.md", "a") as sm:
            sm.write(
                f"\nOPEN: SJF knee rho({sjf_knee_rho:.4f}) NOT right of FCFS knee rho({fcfs_knee_rho:.4f}) — recorded honestly.\n"
            )

    p_sweep = {
        "id": "load_sweep",
        "title": "Load Sweep to Breaking Point (rho-grid, analytic axes)",
        "description": (
            f"25-point rho_grid sweep (rho 0.02–1.3) on EPA full trace (N={n_epa}). "
            f"lam={lam:.6f} req/s, ES={es*1000:.4f} ms, cv2={cv2:.4f}. "
            f"x-axis=rho_analytic (not sim-measured). max_requests=None."
        ),
        "config": {
            "trace_name": "epa",
            "num_servers": 1,
            "slo_target_s": 0.500,
            "rho_grid_min": min(rho_grid),
            "rho_grid_max": max(rho_grid),
            "lam_analytic": lam,
            "es_analytic": es,
            "es2_analytic": es2,
            "cv2": cv2,
            "max_requests": None,
        },
        "sweep": {
            "fcfs": fcfs_sweep,
            "sjf": sjf_sweep
        },
        "comparison": {
            "fcfs_knee_rho": fcfs_knee_rho,
            "sjf_knee_rho": sjf_knee_rho,
            "fcfs_breaking_rho": fcfs_break.get("rho", None),
            "sjf_breaking_rho": sjf_break.get("rho", None),
            "sjf_knee_right_of_fcfs": sjf_knee_rho > fcfs_knee_rho,
        }
    }
    with open(results_dir / "load_sweep.json", "w") as f:
        json.dump(p_sweep, f, indent=2)
    print("  load sweep done")

    # -----------------------------------------------------------------------
    # PRESET 5: Retry Storm — B4: full trace, rho 0.2-1.3 (10 points)
    # -----------------------------------------------------------------------
    print("Generating retry storm preset (B4: full trace, rho 0.2-1.3)...")
    # Timeout: 2 * p99 at rho=0.2 (analytic mult)
    mult_02 = 0.2 * c1 / (lam * es)
    cfg_base = SimulationConfig(
        trace_path="data/processed/epa.parquet",
        policy="fcfs",
        num_servers=1,
        load_multiplier=mult_02,
        max_requests=None  # R1
    )
    base_res = Simulator(cfg_base).run()
    base_p99 = base_res.latency_p99  # seconds
    timeout_s = 2.0 * base_p99
    print(f"  rho=0.2 mult={mult_02:.1f}x p99={base_p99*1000:.1f}ms → timeout={timeout_s*1000:.1f}ms")

    # B4: 10 multipliers with rho 0.2-1.3
    rho_retry = np.linspace(0.2, 1.3, 10).tolist()
    mults_retry = [rho * c1 / (lam * es) for rho in rho_retry]
    sweep_data = []
    for rho_t, mult in zip(rho_retry, mults_retry):
        cfg_no = SimulationConfig(
            trace_path="data/processed/epa.parquet",
            policy="fcfs",
            num_servers=1,
            load_multiplier=float(mult),
            client_timeout=timeout_s,
            retry_on_timeout=False,
            max_retries=0,
            max_requests=None  # R1
        )
        res_no = Simulator(cfg_no).run()
        cfg_yes = SimulationConfig(
            trace_path="data/processed/epa.parquet",
            policy="fcfs",
            num_servers=1,
            load_multiplier=float(mult),
            client_timeout=timeout_s,
            retry_on_timeout=True,
            max_retries=3,
            backoff_base_s=0.05,
            backoff_multiplier=2.0,
            max_requests=None  # R1
        )
        res_yes = Simulator(cfg_yes).run()

        # amplification = total attempts / unique requests
        no_arr = res_no.total_arrivals
        yes_arr = res_yes.total_arrivals
        amp = yes_arr / max(no_arr, 1)

        sweep_data.append({
            "rho_analytic": round(rho_t, 4),
            "mult": round(float(mult), 2),
            "offered_req_s_analytic": round(rho_t * c1 / es, 6),
            "without_retries": res_no.to_dict(),
            "with_retries": res_yes.to_dict(),
            "amplification": round(amp, 4),
        })

    # B4: collapse_threshold = first rho where goodput_with < goodput_without
    collapse_threshold_str = "no metastable collapse observed on this trace"
    for pt in sweep_data:
        if pt["with_retries"]["goodput_req_per_s"] < pt["without_retries"]["goodput_req_per_s"]:
            collapse_threshold_str = (
                f"rho>{pt['rho_analytic']:.4f} "
                f"(goodput_with={pt['with_retries']['goodput_req_per_s']:.4f} < "
                f"goodput_without={pt['without_retries']['goodput_req_per_s']:.4f})"
            )
            break

    # amplification at max overload (rho=1.3)
    heaviest = sweep_data[-1]
    amplification = heaviest["amplification"]
    print(f"  Amplification at rho={heaviest['rho_analytic']:.2f}: {amplification:.3f}x")
    print(f"  Collapse threshold: {collapse_threshold_str}")

    mid = sweep_data[len(sweep_data) // 2]
    old_results = {"no_retries": mid["without_retries"], "with_retries": mid["with_retries"]}

    p_retry = {
        "id": "retry_storm",
        "title": "Retry Storm & Cascading Failure",
        "description": (
            f"c=1 EPA full trace (N={n_epa}), rho 0.2-1.3 (10 points). "
            f"Timeout={timeout_s*1000:.1f}ms (2x p99 at rho=0.2). "
            f"Retries=3, exp backoff+jitter (50ms*2^n). "
            f"Amplification at rho={heaviest['rho_analytic']:.2f}: {amplification:.3f}x. "
            f"collapse_threshold: {collapse_threshold_str}."
        ),
        "config": {
            "trace_name": "epa",
            "num_servers": 1,
            "timeout_s": round(timeout_s, 6),
            "max_retries": 3,
            "backoff_base_s": 0.05,
            "backoff_multiplier": 2.0,
            "rho_range": [0.2, 1.3],
            "lam_analytic": lam,
            "es_analytic": es,
            "max_requests": None,
        },
        "results": old_results,
        "sweep_data": sweep_data,
        "amplification_at_max_overload": round(amplification, 4),
        "collapse_threshold": collapse_threshold_str,
    }
    with open(results_dir / "retry_storm.json", "w") as f:
        json.dump(p_retry, f, indent=2)
    print("  retry storm done")

    # -----------------------------------------------------------------------
    # PRESET 6: Policy Shootout (B3: full trace, c=1, rho 0.4 and 0.6, overload 1.1)
    # -----------------------------------------------------------------------
    print("Generating full policy shootout preset (B3: c=1, rho 0.4, 0.6, 1.1)...")
    shootout_rhos = {"0.4": 0.4, "0.6": 0.6, "1.1": 1.1}
    shootout_multipliers = {
        label: rho * 1 / (lam * es)  # c=1 for shootout
        for label, rho in shootout_rhos.items()
    }
    all_policies = ["fcfs", "sjf", "srtf", "rr", "static_priority", "mlfq"]
    by_rho = {}

    for label, mult in shootout_multipliers.items():
        rho_val = shootout_rhos[label]
        print(f"  Shootout mult={mult:.1f}x (rho={rho_val:.1f}, c=1)...")
        mult_results = {}
        for pol in all_policies:
            try:
                cfg = SimulationConfig(
                    trace_path="data/processed/epa.parquet",
                    policy=pol,
                    num_servers=1,
                    load_multiplier=float(mult),
                    queue_capacity=5000,
                    max_requests=None  # R1
                )
                res = Simulator(cfg).run()
                mult_results[pol] = res.to_dict()
            except Exception as ex:
                print(f"    SKIP {pol} at {label}: {ex}")

        ranked = sorted(
            mult_results.items(),
            key=lambda item: (item[1]["latency"]["p99_ms"], -item[1]["goodput_req_per_s"])
        )
        p99_values = [v["latency"]["p99_ms"] for v in mult_results.values() if v]
        by_rho[label] = {
            "multiplier": round(mult, 2),
            "rho_analytic": rho_val,
            "results": mult_results,
            "ranking": [pol for pol, _ in ranked],
            "best_p99": min(p99_values) if p99_values else 0,
            "worst_p99": max(p99_values) if p99_values else 0
        }

    # B3: headline.json best/worst p99 and Jain come from rho 0.6
    flat_results = by_rho["0.6"]["results"]
    flat_ranked = by_rho["0.6"]["ranking"]
    by_rho["overload"] = by_rho["1.1"]

    p_shootout = {
        "id": "policy_shootout",
        "title": "Comprehensive Policy Shootout",
        "description": (
            f"EPA full trace (N={n_epa}), c=1, max_requests=None. 6 policies at rho 0.4 and 0.6, "
            f"with rho 1.1 as overload entry. Default metrics from rho 0.6."
        ),
        "config": {
            "trace_name": "epa",
            "num_servers": 1,
            "policies": all_policies,
            "rho_points": shootout_rhos,
            "multipliers": {k: round(v, 2) for k, v in shootout_multipliers.items()},
            "lam_analytic": lam,
            "es_analytic": es,
            "max_requests": None,
        },
        "results": flat_results,
        "ranking": flat_ranked,
        "per_rho": by_rho,
        "by_rho": by_rho,
        "by_multiplier": by_rho
    }
    with open(results_dir / "policy_shootout.json", "w") as f:
        json.dump(p_shootout, f, indent=2)
    print("  shootout done")

    print("All presets precomputed successfully into results/presets/")
    return lam, es, es2, cv2


if __name__ == "__main__":
    precompute()
