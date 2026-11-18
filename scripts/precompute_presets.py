"""
Precompute Demo Presets and Phase Transitions
CSL559 Computer Systems Design - IIT Bhilai
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd

from engine.models import SimulationConfig
from engine.simulator import Simulator
from engine.sweep import run_sweep


def precompute():
    results_dir = Path("results/presets")
    results_dir.mkdir(parents=True, exist_ok=True)

    print("Computing preset windows programmatically...")

    # 1. Baseline: Median-load 1-hour window on epa
    df_epa = pd.read_parquet("data/processed/epa.parquet", columns=["ts"])
    bins_1h = np.arange(df_epa["ts"].iloc[0], df_epa["ts"].iloc[-1], 3600.0)
    c_1h, e_1h = np.histogram(df_epa["ts"].values, bins=bins_1h)
    med_idx = int(np.argmin(np.abs(c_1h - np.median(c_1h))))
    baseline_start = float(e_1h[med_idx])

    # 2. Flash crowd: Busiest 10-minute window on nasa_jul95
    df_jul = pd.read_parquet("data/processed/nasa_jul95.parquet", columns=["ts"])
    bins_10m = np.arange(df_jul["ts"].iloc[0], df_jul["ts"].iloc[-1], 600.0)
    c_10m, e_10m = np.histogram(df_jul["ts"].values, bins=bins_10m)
    flash_idx = int(np.argmax(c_10m))
    flash_start = float(e_10m[flash_idx])

    # 3. Outage & recovery: Hurricane Erin shutdown gap on nasa_aug95
    df_aug = pd.read_parquet("data/processed/nasa_aug95.parquet", columns=["ts"])
    gaps = np.diff(df_aug["ts"].values)
    max_gap_idx = int(np.argmax(gaps))
    outage_start = float(df_aug["ts"].iloc[max_gap_idx] - 300.0)
    outage_dur = float(gaps[max_gap_idx] + 1200.0)

    # PRESET 1: Baseline Workload
    print("Generating baseline preset...")
    baseline_shootout = {}
    for pol in ["fcfs", "sjf", "rr", "static_priority"]:
        cfg = SimulationConfig(
            trace_path="data/processed/epa.parquet",
            policy=pol,
            num_servers=4,
            load_multiplier=1.0,
            window_start_s=baseline_start,
            window_duration_s=3600.0,
            max_requests=5000
        )
        res = Simulator(cfg).run()
        baseline_shootout[pol] = res.to_dict()

    p_baseline = {
        "id": "baseline",
        "title": "Baseline Workload (Median-Load Hour)",
        "description": "Standard operational load sampled from the median-volume 1-hour window comparing baseline policies.",
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

    # PRESET 2: Flash Crowd
    print("Generating flash crowd preset...")
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
            max_requests=10000
        )
        res = Simulator(cfg).run()
        flash_shootout[pol] = res.to_dict()

    p_flash = {
        "id": "flash_crowd",
        "title": "Flash Crowd (Busiest 10-Minute Window)",
        "description": "Peak arrival surge on NASA July trace under 5x load compression driving queues to high utilization.",
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

    # PRESET 3: Outage and Recovery
    print("Generating outage-and-recovery preset...")
    outage_shootout = {}
    for pol in ["fcfs", "sjf", "static_priority"]:
        cfg = SimulationConfig(
            trace_path="data/processed/nasa_aug95.parquet",
            policy=pol,
            num_servers=4,
            load_multiplier=2.0,
            window_start_s=outage_start,
            window_duration_s=outage_dur,
            max_requests=15000
        )
        res = Simulator(cfg).run()
        outage_shootout[pol] = res.to_dict()

    p_outage = {
        "id": "outage_recovery",
        "title": "Hurricane Erin Outage & Recovery",
        "description": "The historical 37.7-hour Kennedy Space Center physical shutdown gap and post-reopening surge.",
        "config": {
            "trace_name": "nasa_aug95",
            "window_start_s": outage_start,
            "window_duration_s": outage_dur,
            "num_servers": 4,
            "load_multiplier": 2.0
        },
        "results": outage_shootout
    }
    with open(results_dir / "outage_recovery.json", "w") as f:
        json.dump(p_outage, f, indent=2)

    # PRESET 4: Load Sweep to Breaking Point
    print("Generating load sweep preset...")
    mults = np.logspace(np.log10(1.0), np.log10(400.0), 25).tolist()
    sweep_data = run_sweep(
        trace_path="data/processed/epa.parquet",
        policy="fcfs",
        num_servers=1,
        multipliers=mults,
        slo_target_s=0.500,
        max_requests=4000,
        workers=8
    )
    p_sweep = {
        "id": "load_sweep",
        "title": "Load Sweep to Breaking Point",
        "description": "25-point logarithmic load sweep from 1x to 400x isolating the Knee, Inflection, and Breaking points.",
        "config": {
            "trace_name": "epa",
            "policy": "fcfs",
            "num_servers": 1,
            "slo_target_s": 0.500
        },
        "sweep": sweep_data
    }
    with open(results_dir / "load_sweep.json", "w") as f:
        json.dump(p_sweep, f, indent=2)

    # PRESET 5: Retry Storm
    print("Generating retry storm preset...")
    retry_shootout = {}
    for retry_flag, label in [(False, "no_retries"), (True, "with_retries")]:
        cfg = SimulationConfig(
            trace_path="data/processed/epa.parquet",
            policy="fcfs",
            num_servers=2,
            load_multiplier=8.0,
            queue_capacity=500,
            client_timeout=0.250,
            retry_on_timeout=retry_flag,
            max_retries=2 if retry_flag else 0,
            backoff_base_s=0.100,
            backoff_multiplier=1.5,
            max_requests=4000
        )
        res = Simulator(cfg).run()
        retry_shootout[label] = res.to_dict()

    p_retry = {
        "id": "retry_storm",
        "title": "Retry Storm & Cascading Failure",
        "description": "Comparison of overloaded system without client retries vs. catastrophic traffic amplification with retries.",
        "config": {
            "trace_name": "epa",
            "num_servers": 2,
            "load_multiplier": 8.0,
            "client_timeout_s": 0.250
        },
        "results": retry_shootout
    }
    with open(results_dir / "retry_storm.json", "w") as f:
        json.dump(p_retry, f, indent=2)

    # PRESET 6: Policy Shootout
    print("Generating full policy shootout preset...")
    all_policies = ["fcfs", "sjf", "srtf", "rr", "static_priority", "mlfq", "wfq"]
    shootout_full = {}
    for pol in all_policies:
        cfg = SimulationConfig(
            trace_path="data/processed/epa.parquet",
            policy=pol,
            num_servers=2,
            load_multiplier=2.5,
            queue_capacity=5000,
            max_requests=4000
        )
        res = Simulator(cfg).run()
        shootout_full[pol] = res.to_dict()

    ranked = sorted(
        shootout_full.items(),
        key=lambda item: (item[1]["latency"]["p99_ms"], -item[1]["goodput_req_per_s"])
    )

    p_shootout = {
        "id": "policy_shootout",
        "title": "Comprehensive Policy Shootout",
        "description": "Direct side-by-side comparison of 7 scheduling policies under identical trace arrivals.",
        "config": {
            "trace_name": "epa",
            "num_servers": 2,
            "load_multiplier": 2.5
        },
        "results": shootout_full,
        "ranking": [pol for pol, _ in ranked]
    }
    with open(results_dir / "policy_shootout.json", "w") as f:
        json.dump(p_shootout, f, indent=2)

    print("All presets precomputed successfully into results/presets/")


if __name__ == "__main__":
    precompute()
