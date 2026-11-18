"""
Demo Scenario Presets Definitions and Loader
CSL559 Computer Systems Design - IIT Bhilai
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
PRESETS_DIR = BASE_DIR / "results" / "presets"

PRESET_METADATA = [
    {
        "id": "baseline",
        "title": "Baseline Workload (Median-Load Hour)",
        "description": "Standard operational load on EPA trace comparing FCFS, SJF, RR, and Priority.",
        "type": "shootout"
    },
    {
        "id": "flash_crowd",
        "title": "Flash Crowd (Busiest 10-Minute Window)",
        "description": "Peak arrival surge on NASA July trace with 5x load multiplier.",
        "type": "shootout"
    },
    {
        "id": "outage_recovery",
        "title": "Hurricane Erin Outage & Recovery",
        "description": "Historical 37.7-hour shutdown gap and post-reopening recovery surge on NASA August trace.",
        "type": "shootout"
    },
    {
        "id": "load_sweep",
        "title": "Load Sweep to Breaking Point",
        "description": "Logarithmic load sweep from 1x to 400x isolating Knee, Inflection, and Breaking points.",
        "type": "sweep"
    },
    {
        "id": "retry_storm",
        "title": "Retry Storm & Cascading Failure",
        "description": "Comparison of overloaded system without client retries vs. catastrophic traffic amplification with retries.",
        "type": "shootout"
    },
    {
        "id": "policy_shootout",
        "title": "Comprehensive Policy Shootout",
        "description": "Direct side-by-side comparison of 7 scheduling policies under identical trace arrivals.",
        "type": "shootout"
    }
]


def get_presets() -> List[Dict[str, Any]]:
    presets = []
    for meta in PRESET_METADATA:
        p_file = PRESETS_DIR / f"{meta['id']}.json"
        if p_file.exists():
            try:
                with open(p_file, "r") as f:
                    data = json.load(f)
                    presets.append(data)
                    continue
            except Exception:
                pass
        presets.append(meta)
    return presets


def get_preset_by_id(preset_id: str) -> Optional[Dict[str, Any]]:
    p_file = PRESETS_DIR / f"{preset_id}.json"
    if p_file.exists():
        with open(p_file, "r") as f:
            return json.load(f)
    return None
