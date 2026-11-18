"""
Demo Scenario Presets Definitions and Precomputation
CSL559 Computer Systems Design - IIT Bhilai
"""

import json
from pathlib import Path
from typing import Dict, Any, List

PRESETS_CATALOG = {
    "baseline": {
        "id": "baseline",
        "title": "NASA Baseline Workload",
        "description": "Standard operational load on NASA July trace (1-hour window) with 4 servers comparing standard policies.",
        "config": {
            "trace_path": "data/processed/nasa_jul95.parquet",
            "trace_name": "nasa_jul95",
            "window_start_s": 0.0,
            "window_duration_s": 3600.0,
            "num_servers": 4,
            "load_multiplier": 1.0,
            "queue_capacity": 50000,
            "slo_target_s": 0.500,
            "client_timeout": 30.0,
            "time_quantum": 0.010,
            "policies": ["fcfs", "sjf", "rr", "priority", "wfq"]
        }
    },
    "flash_crowd": {
        "id": "flash_crowd",
        "title": "Flash Crowd (Busiest 10-Minute Window)",
        "description": "Peak arrival surge on NASA July trace with 10x traffic multiplier, driving queues to saturation.",
        "config": {
            "trace_path": "data/processed/nasa_jul95.parquet",
            "trace_name": "nasa_jul95",
            "window_start_s": 7200.0,
            "window_duration_s": 600.0,
            "num_servers": 2,
            "load_multiplier": 8.0,
            "queue_capacity": 500,
            "slo_target_s": 0.500,
            "client_timeout": 5.0,
            "time_quantum": 0.010,
            "policies": ["fcfs", "sjf", "priority", "mlfq"]
        }
    },
    "hurricane_erin": {
        "id": "hurricane_erin",
        "title": "Hurricane Erin Outage & Recovery",
        "description": "The actual August 1-3 1995 Kennedy Space Center physical shutdown gap and immediate thundering-herd recovery backlog.",
        "config": {
            "trace_path": "data/processed/nasa_aug95.parquet",
            "trace_name": "nasa_aug95",
            "window_start_s": 140000.0,
            "window_duration_s": 7200.0,
            "num_servers": 4,
            "load_multiplier": 3.0,
            "queue_capacity": 10000,
            "slo_target_s": 0.500,
            "client_timeout": 15.0,
            "time_quantum": 0.010,
            "policies": ["fcfs", "sjf", "priority"]
        }
    },
    "load_sweep": {
        "id": "load_sweep",
        "title": "Load Sweep to Breaking Point",
        "description": "Offered load sweep from 0.2x to 25x identifying Knee (Kneedle), Inflection point, and SLO breaking point.",
        "config": {
            "trace_path": "data/processed/epa.parquet",
            "trace_name": "epa",
            "num_servers": 2,
            "slo_target_s": 0.500,
            "policies": ["fcfs", "sjf", "rr", "priority"]
        }
    },
    "retry_storm": {
        "id": "retry_storm",
        "title": "Retry Storm & Metastable Failure",
        "description": "Aggressive client timeouts and retries causing traffic amplification, goodput collapse, and queue explosion.",
        "config": {
            "trace_path": "data/processed/epa.parquet",
            "trace_name": "epa",
            "num_servers": 2,
            "load_multiplier": 6.0,
            "client_timeout": 0.200,   # Aggressive 200ms timeout
            "queue_capacity": 1000,
            "policies": ["fcfs", "priority"]
        }
    },
    "autoscale": {
        "id": "autoscale",
        "title": "Dynamic Horizontal Autoscaling",
        "description": "Dynamic capacity scaling (2 to 8 servers) mitigating queue buildup during flash crowd arrivals.",
        "config": {
            "trace_path": "data/processed/epa.parquet",
            "trace_name": "epa",
            "num_servers": 6,
            "load_multiplier": 8.0,
            "queue_capacity": 5000,
            "policies": ["fcfs", "sjf"]
        }
    }
}


def get_presets() -> List[Dict[str, Any]]:
    return list(PRESETS_CATALOG.values())
