"""
NetSim-RT Load Sweep and Phase Transition Analysis Engine
CSL559 Computer Systems Design - IIT Bhilai
"""

import json
from concurrent.futures import ProcessPoolExecutor
from typing import List, Dict, Any, Optional
import numpy as np
from kneed import KneeLocator
from scipy.interpolate import UnivariateSpline

from engine.models import SimulationConfig
from engine.simulator import Simulator


def _simulate_worker(args: tuple) -> Dict[str, Any]:
    cfg_dict = args[0]
    config = SimulationConfig(**cfg_dict)
    sim = Simulator(config)
    res = sim.run()
    d = res.to_dict()
    service_times = [r.service_time for r in sim.all_requests if r.finish_time >= 0.0]
    mean_st = float(np.mean(service_times)) if service_times else 0.010
    d["mean_service_time_s"] = mean_st
    return d


def run_sweep(
    trace_path: str,
    policy: str = "fcfs",
    num_servers: int = 4,
    # rho_grid takes precedence over multipliers when provided
    rho_grid: Optional[List[float]] = None,
    multipliers: Optional[List[float]] = None,
    num_points: int = 25,
    slo_target_s: float = 0.500,
    window_start_s: Optional[float] = None,
    window_duration_s: Optional[float] = None,
    max_requests: Optional[int] = None,
    time_quantum: float = 0.010,
    queue_capacity: int = 50000,
    load_balancer: str = "central_queue",
    admission_policy: str = "drop_tail",
    workers: int = 8,
    # analytic trace parameters for rho-grid mode
    lam_analytic: Optional[float] = None,
    es_analytic: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Executes a load sweep and calculates phase transition points.

    R2: When rho_grid is provided (preferred), multipliers are derived analytically:
        mult = rho * c / (lam_analytic * es_analytic)
    so that rho_analytic = mult * lam_analytic * es_analytic / c is exactly the
    requested rho — not a sim-measured approximation.

    Phase transitions (R3):
    - Knee: KneeLocator(x=rho_analytic, y=p99, curve='convex', direction='increasing')
    - Inflection: second-derivative sign change on smoothed curve, restricted to rho<=1.0
    - Breaking: lowest rho with p99>SLO or goodput<95% offered
    """
    import pandas as pd

    # Derive lam and ES from trace if not provided (for rho-grid mode)
    if rho_grid is not None and (lam_analytic is None or es_analytic is None):
        df_tr = pd.read_parquet(trace_path, columns=["ts", "service_time_s"])
        span = float(df_tr["ts"].iloc[-1] - df_tr["ts"].iloc[0])
        lam_analytic = len(df_tr) / span
        es_analytic = float(df_tr["service_time_s"].mean())

    if rho_grid is not None:
        # R2: build multipliers analytically from rho targets
        c = float(num_servers)
        multipliers = [
            float(rho * c / (lam_analytic * es_analytic))
            for rho in rho_grid
        ]

    if multipliers is None:
        multipliers = np.logspace(np.log10(0.1), np.log10(50.0), num_points).tolist()

    configs = []
    for m in multipliers:
        cfg = {
            "trace_path": trace_path,
            "policy": policy,
            "num_servers": num_servers,
            "load_multiplier": float(m),
            "slo_target_s": slo_target_s,
            "window_start_s": window_start_s,
            "window_duration_s": window_duration_s,
            "max_requests": max_requests,
            "time_quantum": time_quantum,
            "queue_capacity": queue_capacity,
            "load_balancer": load_balancer,
            "admission_policy": admission_policy,
        }
        configs.append((cfg,))

    n_workers = min(workers, len(configs))
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        results = list(executor.map(_simulate_worker, configs))

    results.sort(key=lambda r: r["load_multiplier"])

    sweep_points = []
    for i, r in enumerate(results):
        # R2: use analytic values, not sim-derived ones
        if rho_grid is not None and lam_analytic is not None and es_analytic is not None:
            rho_a = float(rho_grid[i]) if i < len(rho_grid) else (
                r["load_multiplier"] * lam_analytic * es_analytic / float(num_servers)
            )
            offered_a = r["load_multiplier"] * lam_analytic
        else:
            offered_a = r["offered_load_req_per_s"]
            mean_st = r.get("mean_service_time_s", 0.010)
            c = r["num_servers"]
            rho_a = (offered_a * mean_st) / float(c) if c > 0 else 0.0

        pt = {
            "load_multiplier": r["load_multiplier"],
            "offered_load_req_per_s": round(r["offered_load_req_per_s"], 4),
            "offered_req_s_analytic": round(offered_a, 6),
            "throughput_req_per_s": round(r["throughput_req_per_s"], 4),
            "goodput_req_per_s": round(r["goodput_req_per_s"], 4),
            "rho": round(rho_a, 6),
            "rho_analytic": round(rho_a, 6),
            "latency_p50_ms": r["latency"]["p50_ms"],
            "latency_p95_ms": r["latency"]["p95_ms"],
            "latency_p99_ms": r["latency"]["p99_ms"],
            "latency_p999_ms": r["latency"]["p999_ms"],
            "latency_mean_ms": r["latency"]["mean_ms"],
            "server_utilization": r["server_utilization"],
            "mean_queue_length": r["mean_queue_length"],
            "drop_rate": r["drop_rate"],
            "timeout_rate": r["timeout_rate"],
            "slo_attainment_pct": r["slo_attainment_pct"],
            "jains_fairness_index": r["jains_fairness_index"]
        }
        sweep_points.append(pt)

    # R3: Use rho_analytic as x-axis for phase detection
    x_rho = [p["rho_analytic"] for p in sweep_points]
    x_offered = [p["offered_req_s_analytic"] for p in sweep_points]
    y_p99 = [p["latency_p99_ms"] for p in sweep_points]
    slo_ms = slo_target_s * 1000.0

    # 1. KNEE POINT (R3: x=rho_analytic, restricted to rho<=breaking_rho+1grid to avoid plateau artifact)
    # First find breaking rho to set the ceiling for knee search
    _break_rho = 1.0
    for pt in sweep_points:
        p99_breach = pt["latency_p99_ms"] > slo_ms
        goodput_collapse = pt["goodput_req_per_s"] < (0.95 * pt["offered_req_s_analytic"])
        if p99_breach or goodput_collapse:
            _break_rho = pt["rho_analytic"]
            break

    knee_point = None
    try:
        x_arr_full = np.array(x_rho, dtype=float)
        y_arr_full = np.array(y_p99, dtype=float)
        # Restrict to rho <= breaking_rho (pre-saturation convex growth region)
        mask_knee = x_arr_full <= _break_rho + 1e-9
        x_knee_sub = x_arr_full[mask_knee].tolist()
        y_knee_sub = y_arr_full[mask_knee].tolist()
        if len(x_knee_sub) >= 3:
            kl = KneeLocator(x_knee_sub, y_knee_sub, curve="convex", direction="increasing", S=1.0)
            knee_x = kl.knee
            if knee_x is not None:
                idx = min(range(len(x_rho)), key=lambda i: abs(x_rho[i] - knee_x))
                knee_point = {
                    "load_multiplier": sweep_points[idx]["load_multiplier"],
                    "offered_load_req_per_s": sweep_points[idx]["offered_req_s_analytic"],
                    "p99_ms": sweep_points[idx]["latency_p99_ms"],
                    "rho": sweep_points[idx]["rho_analytic"],
                    "description": "Knee: onset of non-linear queueing delay expansion (max curvature on rho vs p99, rho<=breaking_rho)"
                }
    except Exception:
        pass

    # 2. INFLECTION POINT (R3: second-derivative sign change, rho<=1.0)
    inflection_point = None
    try:
        if len(sweep_points) >= 5:
            x_arr = np.array(x_rho, dtype=float)
            y_arr = np.array(y_p99, dtype=float)
            # Restrict to rho <= 1.0 for inflection search
            mask = x_arr <= 1.0
            x_sub = x_arr[mask]
            y_sub = y_arr[mask]
            if len(x_sub) >= 5:
                spline = UnivariateSpline(x_sub, y_sub, s=len(x_sub) * 20.0, k=3)
                d2 = spline.derivative(n=2)
                x_eval = np.linspace(float(x_sub.min()), float(x_sub.max()), 300)
                d2_vals = d2(x_eval)
                sign_changes = np.where(np.diff(np.sign(d2_vals)))[0]
                if len(sign_changes) > 0:
                    best_sc = sign_changes[len(sign_changes) // 2]
                    inf_x = float(x_eval[best_sc])
                    idx = int(np.argmin(np.abs(x_arr - inf_x)))
                    inflection_point = {
                        "load_multiplier": sweep_points[idx]["load_multiplier"],
                        "offered_load_req_per_s": sweep_points[idx]["offered_req_s_analytic"],
                        "p99_ms": sweep_points[idx]["latency_p99_ms"],
                        "rho": sweep_points[idx]["rho_analytic"],
                        "description": "Inflection point: second-derivative sign change on rho-p99 curve (rho<=1.0)"
                    }
    except Exception:
        pass

    # 3. BREAKING POINT (R3: lowest rho with p99>SLO or goodput<95% offered)
    breaking_point = None
    for pt in sweep_points:
        p99_breach = pt["latency_p99_ms"] > slo_ms
        goodput_collapse = pt["goodput_req_per_s"] < (0.95 * pt["offered_req_s_analytic"])
        if p99_breach or goodput_collapse:
            breaking_point = {
                "load_multiplier": pt["load_multiplier"],
                "offered_load_req_per_s": pt["offered_req_s_analytic"],
                "p99_ms": pt["latency_p99_ms"],
                "rho": pt["rho_analytic"],
                "reason": "p99 > SLO" if p99_breach and not goodput_collapse else (
                    "goodput < 95% offered" if goodput_collapse and not p99_breach else "both SLO breach and goodput collapse"
                ),
                "description": "Breaking point: system capacity collapse / SLO violation"
            }
            break

    return {
        "policy": policy,
        "num_servers": num_servers,
        "slo_target_s": slo_target_s,
        "lam_analytic": lam_analytic,
        "es_analytic": es_analytic,
        "points": sweep_points,
        "special_points": {
            "knee": knee_point,
            "inflection": inflection_point,
            "breaking": breaking_point
        }
    }
