"""
NetSim-RT Real Trace Load Generator.

Replays real HTTP arrival patterns and derived service times against the emulation
server using asynchronous HTTP/1.1 pipelining with exact dilation scaling.

Mathematical Model & Preservation of Utilization:
-------------------------------------------------
Given:
  - Base empirical trace window with arrival timestamps {t_i} and service times {s_i}
  - Time-dilation factor D = 2.5
  - Worker concurrency c = 4
  - Scaled service time s_i' = s_i * D
  - System capacity mu = c / E[s_i'] req/s
For target utilization rho in [0.30, 0.50, 0.70, 0.85, 0.95, 1.08]:
  - Target offered load lambda = rho * mu req/s
  - Time-compression multiplier M = lambda / lambda_raw
  - Scheduled arrival T_i = (t_i - t_0) / M
  - Offered utilization rho = (lambda * E[s_i']) / c is strictly preserved.
"""

import os
import sys
import time
import json
import logging
import argparse
import asyncio
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("loadgen")


async def replay_level(
    client: httpx.AsyncClient,
    base_url: str,
    requests_slice: List[Dict[str, float]],
    target_rho: float,
    system_capacity_rps: float,
    duration_s: float = 20.0,
) -> Dict[str, Any]:
    """Replays a single load level for duration_s and records response latencies."""
    target_lambda = target_rho * system_capacity_rps
    raw_duration = requests_slice[-1]["ts"] - requests_slice[0]["ts"]
    raw_rate = len(requests_slice) / max(raw_duration, 1.0)
    multiplier = target_lambda / max(raw_rate, 1e-4)

    t0_raw = requests_slice[0]["ts"]
    logger.info(
        "Load level rho=%.2f: target_rate=%.1f req/s (multiplier=%.2fx, duration=%.1fs)",
        target_rho,
        target_lambda,
        multiplier,
        duration_s,
    )

    results = []
    active_tasks = set()
    test_start = time.perf_counter()

    async def worker_call(req_dict: Dict[str, float], sched_delay: float):
        t_sent = time.perf_counter()
        st = req_dict["service_time_s"]
        url = f"{base_url}/work?service_time_s={st:.6f}&client_timeout_s=5.0"
        try:
            resp = await client.get(url)
            t_recv = time.perf_counter()
            lat_ms = (t_recv - t_sent) * 1000.0
            results.append({
                "status": resp.status_code,
                "latency_ms": lat_ms,
                "sched_delay_ms": sched_delay * 1000.0,
            })
        except httpx.TimeoutException:
            results.append({"status": 504, "latency_ms": 5000.0, "sched_delay_ms": 0.0})
        except Exception:
            results.append({"status": 500, "latency_ms": 0.0, "sched_delay_ms": 0.0})

    req_idx = 0
    total_trace_reqs = len(requests_slice)

    while True:
        elapsed = time.perf_counter() - test_start
        if elapsed >= duration_s:
            break

        req_data = requests_slice[req_idx % total_trace_reqs]
        # In case we wrap around, advance the virtual arrival offset
        wrap_count = req_idx // total_trace_reqs
        virtual_arr_offset = wrap_count * (raw_duration / multiplier)
        sched_time = ((req_data["ts"] - t0_raw) / multiplier) + virtual_arr_offset

        now_offset = time.perf_counter() - test_start
        wait_s = sched_time - now_offset
        if wait_s > 0:
            await asyncio.sleep(wait_s)

        sched_drift = (time.perf_counter() - test_start) - sched_time
        task = asyncio.create_task(worker_call(req_data, sched_drift))
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)

        req_idx += 1

    # Drain remaining in-flight requests
    drain_start = time.perf_counter()
    if active_tasks:
        await asyncio.wait(active_tasks, timeout=3.0)

    # Compute metrics
    latencies = [r["latency_ms"] for r in results if r["status"] == 200]
    drops = sum(1 for r in results if r["status"] == 503)
    timeouts = sum(1 for r in results if r["status"] == 504)
    completed = len(latencies)
    throughput = completed / duration_s

    p50 = float(np.percentile(latencies, 50)) if latencies else 0.0
    p95 = float(np.percentile(latencies, 95)) if latencies else 0.0
    p99 = float(np.percentile(latencies, 99)) if latencies else 0.0

    logger.info(
        "Level rho=%.2f summary: completed=%d, drops=%d, timeouts=%d, throughput=%.1f rps, p50=%.2fms, p99=%.2fms",
        target_rho,
        completed,
        drops,
        timeouts,
        throughput,
        p50,
        p99,
    )

    return {
        "rho_target": target_rho,
        "multiplier": float(multiplier),
        "target_rate_rps": float(target_lambda),
        "completed": completed,
        "drops": drops,
        "timeouts": timeouts,
        "throughput_rps": round(throughput, 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
    }


async def run_loadgen(
    trace_path: str,
    base_url: str = "http://127.0.0.1:8008",
    num_servers: int = 4,
    dilation_factor: float = 2.5,
    duration_per_level_s: float = 20.0,
    output_path: str = "results/emulation_results.json",
    cores: Optional[str] = None,
):
    """Executes the 6-level real system emulation sweep."""
    if cores:
        try:
            core_ids = [int(c.strip()) for c in cores.split(",")]
            os.sched_setaffinity(0, set(core_ids))
            logger.info("Load generator pinned to cores %s", core_ids)
        except Exception as e:
            logger.warning("Affinity pinning error: %s", e)

    logger.info("Loading trace slice from %s", trace_path)
    df = pd.read_parquet(trace_path)
    
    # Filter to representative busy window (e.g. ts >= 396000)
    if "ts" in df.columns:
        df_win = df[df["ts"] >= 396000.0]
        if len(df_win) < 3000:
            df_win = df
    else:
        df_win = df

    df_slice = df_win.iloc[:5000].copy()
    mean_raw_svc = df_slice["service_time_s"].mean()
    mean_dilated_svc = mean_raw_svc * dilation_factor
    capacity_rps = num_servers / mean_dilated_svc

    logger.info(
        "Trace window: %d reqs, raw_mean_svc=%.4fs, dilated_mean_svc=%.4fs, c=%d capacity=%.1f req/s",
        len(df_slice),
        mean_raw_svc,
        mean_dilated_svc,
        num_servers,
        capacity_rps,
    )

    # Prepare requests slice with dilated service times
    requests_slice = []
    for row in df_slice.itertuples(index=False):
        requests_slice.append({
            "ts": float(row.ts),
            "service_time_s": float(row.service_time_s) * dilation_factor,
        })

    target_rhos = [0.30, 0.50, 0.70, 0.85, 0.95, 1.08]
    level_results = []

    limits = httpx.Limits(max_connections=600, max_keepalive_connections=300)
    timeout = httpx.Timeout(6.0, connect=2.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        # Check server health
        try:
            r = await client.get(f"{base_url}/health")
            if r.status_code != 200:
                raise RuntimeError(f"Server health check failed: {r.text}")
            logger.info("Emulation server health verified: %s", r.json())
        except Exception as e:
            logger.error("Failed to connect to emulation server at %s: %s", base_url, e)
            sys.exit(1)

        for rho in target_rhos:
            res = await replay_level(
                client=client,
                base_url=base_url,
                requests_slice=requests_slice,
                target_rho=rho,
                system_capacity_rps=capacity_rps,
                duration_s=duration_per_level_s,
            )
            level_results.append(res)
            # Drain cooldown between levels
            await asyncio.sleep(2.0)

    output = {
        "scenario": "NASA-Jul95 Dilated Trace Emulation",
        "num_servers": num_servers,
        "dilation_factor": dilation_factor,
        "duration_per_level_s": duration_per_level_s,
        "capacity_rps": round(capacity_rps, 2),
        "levels": level_results,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    logger.info("Emulation results written to %s", output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetSim-RT Real Load Generator")
    parser.add_argument("--trace", type=str, default="data/processed/nasa_jul95.parquet")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8008")
    parser.add_argument("--servers", type=int, default=4)
    parser.add_argument("--dilation", type=float, default=2.5)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--cores", type=str, default="8,9,10,11,12,13,14,15")
    parser.add_argument("--output", type=str, default="results/emulation_results.json")
    args = parser.parse_args()

    asyncio.run(run_loadgen(
        trace_path=args.trace,
        base_url=args.url,
        num_servers=args.servers,
        dilation_factor=args.dilation,
        duration_per_level_s=args.duration,
        output_path=args.output,
        cores=args.cores,
    ))
