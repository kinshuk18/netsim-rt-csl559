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
) -> Dict[str, Any]:
    """
    Executes a log-spaced load sweep and calculates phase transition points:
    - Knee point (maximum curvature via Kneedle)
    - Inflection point (second derivative sign change)
    - Breaking point (SLO breach or goodput < 0.95 * offered_load)
    """
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
    for r in results:
        offered = r["offered_load_req_per_s"]
        mean_st = r.get("mean_service_time_s", 0.010)
        c = r["num_servers"]
        rho = (offered * mean_st) / float(c) if c > 0 else 0.0
        
        pt = {
            "load_multiplier": r["load_multiplier"],
            "offered_load_req_per_s": round(offered, 2),
            "throughput_req_per_s": round(r["throughput_req_per_s"], 2),
            "goodput_req_per_s": round(r["goodput_req_per_s"], 2),
            "rho": round(rho, 4),
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

    x_offered = [p["offered_load_req_per_s"] for p in sweep_points]
    y_p99 = [p["latency_p99_ms"] for p in sweep_points]
    slo_ms = slo_target_s * 1000.0

    # 1. KNEE POINT
    knee_point = None
    try:
        kl = KneeLocator(x_offered, y_p99, curve="convex", direction="increasing", S=1.0)
        knee_x = kl.knee
        if knee_x is not None:
            idx = min(range(len(x_offered)), key=lambda i: abs(x_offered[i] - knee_x))
            knee_point = {
                "load_multiplier": sweep_points[idx]["load_multiplier"],
                "offered_load_req_per_s": sweep_points[idx]["offered_load_req_per_s"],
                "p99_ms": sweep_points[idx]["latency_p99_ms"],
                "rho": sweep_points[idx]["rho"],
                "description": "Knee: onset of non-linear queueing delay expansion (maximum curvature)"
            }
    except Exception:
        pass

    # 2. INFLECTION POINT (Sign change of second derivative on smoothed curve)
    inflection_point = None
    try:
        if len(sweep_points) >= 5:
            # Use strictly monotonic load multipliers for numerical stability
            x_arr = np.array([p["load_multiplier"] for p in sweep_points], dtype=float)
            y_arr = np.array([p["latency_p99_ms"] for p in sweep_points], dtype=float)
            
            spline = UnivariateSpline(x_arr, y_arr, s=len(x_arr) * 20.0, k=3)
            d2 = spline.derivative(n=2)
            x_eval = np.linspace(float(min(x_arr)), float(max(x_arr)), 300)
            d2_vals = d2(x_eval)
            
            # Find zero-crossings (sign changes of 2nd derivative)
            sign_changes = np.where(np.diff(np.sign(d2_vals)))[0]
            if len(sign_changes) > 0:
                # Select the sign change with highest curvature transition
                best_sc = sign_changes[len(sign_changes) // 2]
                inf_x = float(x_eval[best_sc])
                idx = int(np.argmin(np.abs(x_arr - inf_x)))
                inflection_point = {
                    "load_multiplier": sweep_points[idx]["load_multiplier"],
                    "offered_load_req_per_s": sweep_points[idx]["offered_load_req_per_s"],
                    "p99_ms": sweep_points[idx]["latency_p99_ms"],
                    "rho": sweep_points[idx]["rho"],
                    "description": "Inflection point: sign change of second derivative (delay acceleration transition)"
                }
    except Exception:
        pass

    # 3. BREAKING POINT
    breaking_point = None
    for pt in sweep_points:
        p99_breach = pt["latency_p99_ms"] > slo_ms
        goodput_collapse = pt["goodput_req_per_s"] < (0.95 * pt["offered_load_req_per_s"])
        if p99_breach or goodput_collapse:
            breaking_point = {
                "load_multiplier": pt["load_multiplier"],
                "offered_load_req_per_s": pt["offered_load_req_per_s"],
                "p99_ms": pt["latency_p99_ms"],
                "rho": pt["rho"],
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
        "points": sweep_points,
        "special_points": {
            "knee": knee_point,
            "inflection": inflection_point,
            "breaking": breaking_point
        }
    }
