"""
NetSim-RT Core FastAPI Server
CSL559 Computer Systems Design - IIT Bhilai
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from engine.models import SimulationConfig
from engine.simulator import Simulator
from engine.policies.base import list_available_policies
from server.cache import get_cache
from server.presets_data import PRESETS_CATALOG, get_presets

app = FastAPI(
    title="NetSim-RT API",
    description="Trace-driven Discrete-Event Simulator & Real-Server Emulation Benchmark for CSL559",
    version="0.3.0"
)

# CORS configuration for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "processed"
METADATA_PATH = DATA_DIR / "traces_metadata.json"


# Pydantic Request Schemas
class SimulateRequest(BaseModel):
    trace_name: str = Field(default="epa", description="Trace identifier (e.g. epa, sdsc, nasa_jul95, nasa_aug95, clarknet, azure)")
    policy: str = Field(default="fcfs", description="Scheduling policy")
    num_servers: int = Field(default=4, ge=1, le=32, description="Number of worker servers")
    load_multiplier: float = Field(default=1.0, gt=0.0, le=100.0, description="Load multiplier scaling")
    time_quantum_ms: float = Field(default=10.0, gt=0.1, le=1000.0, description="Time quantum in ms for RR/MLFQ")
    queue_capacity: int = Field(default=50000, ge=1, description="Drop-tail queue capacity")
    client_timeout_s: float = Field(default=30.0, ge=0.0, description="Client timeout in seconds")
    slo_target_ms: float = Field(default=500.0, gt=1.0, description="SLO target latency in ms")
    max_requests: Optional[int] = Field(default=None, ge=10, description="Optional cap on request count")
    window_start_s: Optional[float] = Field(default=None, description="Start timestamp in seconds")
    window_duration_s: Optional[float] = Field(default=None, description="Window duration in seconds")


class ShootoutRequest(BaseModel):
    trace_name: str = Field(default="epa")
    policies: List[str] = Field(default=["fcfs", "sjf", "rr", "priority", "mlfq", "wfq"])
    num_servers: int = Field(default=4, ge=1, le=32)
    load_multiplier: float = Field(default=1.0, gt=0.0)
    time_quantum_ms: float = Field(default=10.0)
    queue_capacity: int = Field(default=50000)
    client_timeout_s: float = Field(default=30.0)
    slo_target_ms: float = Field(default=500.0)
    max_requests: Optional[int] = Field(default=None)
    window_start_s: Optional[float] = Field(default=None)
    window_duration_s: Optional[float] = Field(default=None)


def resolve_trace_path(name: str) -> Path:
    p = DATA_DIR / f"{name}.parquet"
    if not p.exists():
        # Fallback to epa if missing
        fallback = DATA_DIR / "epa.parquet"
        if fallback.exists():
            return fallback
        raise HTTPException(status_code=404, detail=f"Trace file for '{name}' not found at {p}")
    return p


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "NetSim-RT Core API",
        "version": "0.3.0",
        "available_policies": list_available_policies()
    }


@app.get("/api/traces")
def get_traces():
    """Return precomputed metadata and characteristics for all available real traces."""
    if not METADATA_PATH.exists():
        return {"error": "Traces metadata not found. Run scripts/fetch_data.py first."}
    with open(METADATA_PATH, "r") as f:
        metadata = json.load(f)
    return metadata


@app.get("/api/traces/{name}")
def get_trace_details(name: str):
    if not METADATA_PATH.exists():
        raise HTTPException(status_code=404, detail="Metadata not found")
    with open(METADATA_PATH, "r") as f:
        metadata = json.load(f)
    if name not in metadata:
        raise HTTPException(status_code=404, detail=f"Trace '{name}' not found")
    return metadata[name]


@app.get("/api/policies")
def get_policies():
    """Return all registered scheduling policy names."""
    return list_available_policies()


@app.post("/api/simulate")
def run_simulation(req: SimulateRequest):
    """Run discrete-event simulation with caching."""
    trace_path = resolve_trace_path(req.trace_name)
    cache = get_cache()

    config_dict = req.dict()
    config_dict["trace_path"] = str(trace_path)
    
    # Check cache
    cached = cache.get(config_dict)
    if cached:
        cached["cached"] = True
        return cached

    config = SimulationConfig(
        trace_path=str(trace_path),
        policy=req.policy,
        num_servers=req.num_servers,
        load_multiplier=req.load_multiplier,
        time_quantum=req.time_quantum_ms / 1000.0,
        queue_capacity=req.queue_capacity,
        client_timeout=req.client_timeout_s,
        slo_target_s=req.slo_target_ms / 1000.0,
        max_requests=req.max_requests,
        window_start_s=req.window_start_s,
        window_duration_s=req.window_duration_s
    )

    sim = Simulator(config)
    result = sim.run()
    res_dict = result.to_dict()
    res_dict["cached"] = False

    # Store in DuckDB cache
    cache.put(config_dict, res_dict)
    return res_dict


@app.post("/api/shootout")
def run_shootout(req: ShootoutRequest):
    """Run multi-policy comparative shootout on the exact same trace window."""
    trace_path = resolve_trace_path(req.trace_name)
    cache = get_cache()
    
    shootout_results = {}
    for pol in req.policies:
        single_req = SimulateRequest(
            trace_name=req.trace_name,
            policy=pol,
            num_servers=req.num_servers,
            load_multiplier=req.load_multiplier,
            time_quantum_ms=req.time_quantum_ms,
            queue_capacity=req.queue_capacity,
            client_timeout_s=req.client_timeout_s,
            slo_target_ms=req.slo_target_ms,
            max_requests=req.max_requests,
            window_start_s=req.window_start_s,
            window_duration_s=req.window_duration_s
        )
        res = run_simulation(single_req)
        shootout_results[pol] = res

    # Compute comparative rankings: lowest p99 latency & highest goodput
    ranked = sorted(
        shootout_results.items(),
        key=lambda item: (item[1]["latency"]["p99_ms"], -item[1]["goodput_req_per_s"])
    )
    
    return {
        "trace_name": req.trace_name,
        "load_multiplier": req.load_multiplier,
        "num_servers": req.num_servers,
        "results": shootout_results,
        "ranking": [pol for pol, _ in ranked]
    }


@app.get("/api/presets")
def list_presets():
    """List all preconfigured scenario presets."""
    return get_presets()


@app.get("/api/presets/{preset_id}")
def run_preset(preset_id: str):
    """Execute or retrieve precomputed preset scenario."""
    if preset_id not in PRESETS_CATALOG:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
        
    p_info = PRESETS_CATALOG[preset_id]
    cfg = p_info["config"]
    
    shootout_req = ShootoutRequest(
        trace_name=cfg["trace_name"],
        policies=cfg["policies"],
        num_servers=cfg["num_servers"],
        load_multiplier=cfg.get("load_multiplier", 1.0),
        time_quantum_ms=cfg.get("time_quantum", 0.010) * 1000.0,
        queue_capacity=cfg.get("queue_capacity", 50000),
        client_timeout_s=cfg.get("client_timeout", 30.0),
        slo_target_ms=cfg.get("slo_target_s", 0.500) * 1000.0,
        window_start_s=cfg.get("window_start_s"),
        window_duration_s=cfg.get("window_duration_s"),
        max_requests=cfg.get("max_requests", 5000)
    )
    res = run_shootout(shootout_req)
    return {
        "preset": p_info,
        "shootout": res
    }


@app.get("/api/simulate/stream")
async def stream_simulation(
    trace_name: str = "epa",
    policy: str = "fcfs",
    num_servers: int = 4,
    load_multiplier: float = 1.0
):
    """Server-Sent Events (SSE) streaming live queue depth and utilization playback packets."""
    async def event_generator():
        # First run simulation to get timeline
        req = SimulateRequest(
            trace_name=trace_name,
            policy=policy,
            num_servers=num_servers,
            load_multiplier=load_multiplier,
            max_requests=1000
        )
        res = run_simulation(req)
        timeline = res.get("timeline", [])
        
        yield f"data: {json.dumps({'event': 'start', 'total_points': len(timeline)})}\n\n"
        
        for pt in timeline:
            yield f"data: {json.dumps(pt)}\n\n"
            await asyncio.sleep(0.04)  # 25 fps stream
            
        yield f"data: {json.dumps({'event': 'complete', 'summary': res})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4507)
