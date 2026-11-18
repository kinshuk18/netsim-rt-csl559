"""
NetSim-RT Core FastAPI Server
CSL559 Computer Systems Design - IIT Bhilai
"""

import os
import json
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine.models import SimulationConfig
from engine.simulator import Simulator
from engine.sweep import run_sweep
from engine.sandbox import run_sandboxed_simulation, POLICY_TEMPLATES
from engine.policies.base import list_available_policies
from server.cache import get_cache
from server.presets_data import get_presets, get_preset_by_id

app = FastAPI(
    title="NetSim-RT API",
    description="Trace-driven Discrete-Event Simulator & Real-Server Emulation Benchmark for CSL559",
    version="0.4.0"
)

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
STATIC_DIR = BASE_DIR / "server" / "static"


# Pydantic Request Schemas
class SimulateRequest(BaseModel):
    trace_name: str = Field(default="epa")
    policy: str = Field(default="fcfs")
    num_servers: int = Field(default=4, ge=1, le=32)
    load_multiplier: float = Field(default=1.0, gt=0.0, le=1000.0)
    time_quantum_ms: float = Field(default=10.0, gt=0.1, le=1000.0)
    queue_capacity: int = Field(default=50000, ge=1)
    client_timeout_s: float = Field(default=30.0, ge=0.0)
    slo_target_ms: float = Field(default=500.0, gt=1.0)
    load_balancer: str = Field(default="central_queue")
    admission_policy: str = Field(default="drop_tail")
    token_bucket_rate: float = Field(default=1000.0)
    token_bucket_capacity: float = Field(default=100.0)
    retry_on_timeout: bool = Field(default=False)
    max_retries: int = Field(default=0)
    max_requests: Optional[int] = Field(default=None)
    window_start_s: Optional[float] = Field(default=None)
    window_duration_s: Optional[float] = Field(default=None)


class ShootoutRequest(BaseModel):
    trace_name: str = Field(default="epa")
    policies: List[str] = Field(default=["fcfs", "sjf", "srtf", "rr", "static_priority", "mlfq", "wfq"])
    num_servers: int = Field(default=4, ge=1, le=32)
    load_multiplier: float = Field(default=1.0, gt=0.0)
    time_quantum_ms: float = Field(default=10.0)
    queue_capacity: int = Field(default=50000)
    client_timeout_s: float = Field(default=30.0)
    slo_target_ms: float = Field(default=500.0)
    load_balancer: str = Field(default="central_queue")
    admission_policy: str = Field(default="drop_tail")
    max_requests: Optional[int] = Field(default=5000)
    window_start_s: Optional[float] = Field(default=None)
    window_duration_s: Optional[float] = Field(default=None)


class SweepRequest(BaseModel):
    trace_name: str = Field(default="epa")
    policy: str = Field(default="fcfs")
    num_servers: int = Field(default=2, ge=1, le=32)
    num_points: int = Field(default=25, ge=5, le=50)
    min_multiplier: float = Field(default=0.1, gt=0.0)
    max_multiplier: float = Field(default=50.0, gt=0.0)
    slo_target_ms: float = Field(default=500.0)
    time_quantum_ms: float = Field(default=10.0)
    queue_capacity: int = Field(default=50000)
    load_balancer: str = Field(default="central_queue")
    admission_policy: str = Field(default="drop_tail")
    max_requests: Optional[int] = Field(default=4000)
    window_start_s: Optional[float] = Field(default=None)
    window_duration_s: Optional[float] = Field(default=None)


class CustomPolicyRequest(BaseModel):
    code: str = Field(..., description="Python source code defining select_next")
    trace_name: str = Field(default="epa")
    num_servers: int = Field(default=4)
    load_multiplier: float = Field(default=1.0)
    queue_capacity: int = Field(default=50000)
    client_timeout_s: float = Field(default=30.0)
    slo_target_ms: float = Field(default=500.0)
    max_requests: Optional[int] = Field(default=3000)
    window_start_s: Optional[float] = Field(default=None)
    window_duration_s: Optional[float] = Field(default=None)


def resolve_trace_path(name: str) -> Path:
    p = DATA_DIR / f"{name}.parquet"
    if not p.exists():
        fallback = DATA_DIR / "epa.parquet"
        if fallback.exists():
            return fallback
        raise HTTPException(status_code=404, detail=f"Trace file for '{name}' not found at {p}")
    return p


# API Routes
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "NetSim-RT Core API",
        "version": "0.4.0",
        "available_policies": list_available_policies()
    }


@app.get("/api/traces")
def get_traces():
    if not METADATA_PATH.exists():
        return {"error": "Traces metadata not found"}
    with open(METADATA_PATH, "r") as f:
        return json.load(f)


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
    return list_available_policies()


@app.get("/api/templates")
def get_templates():
    return POLICY_TEMPLATES


@app.post("/api/simulate")
def run_simulation(req: SimulateRequest):
    trace_path = resolve_trace_path(req.trace_name)
    cache = get_cache()

    config_dict = req.dict()
    config_dict["trace_path"] = str(trace_path)

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
        load_balancer=req.load_balancer,
        admission_policy=req.admission_policy,
        token_bucket_rate=req.token_bucket_rate,
        token_bucket_capacity=req.token_bucket_capacity,
        retry_on_timeout=req.retry_on_timeout,
        max_retries=req.max_retries,
        max_requests=req.max_requests,
        window_start_s=req.window_start_s,
        window_duration_s=req.window_duration_s
    )

    sim = Simulator(config)
    result = sim.run()
    res_dict = result.to_dict()
    res_dict["cached"] = False

    cache.put(config_dict, res_dict)
    return res_dict


@app.post("/api/shootout")
def run_shootout(req: ShootoutRequest):
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
            load_balancer=req.load_balancer,
            admission_policy=req.admission_policy,
            max_requests=req.max_requests,
            window_start_s=req.window_start_s,
            window_duration_s=req.window_duration_s
        )
        res = run_simulation(single_req)
        shootout_results[pol] = res

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


@app.post("/api/sweep")
def run_load_sweep(req: SweepRequest):
    trace_path = resolve_trace_path(req.trace_name)
    cache = get_cache()

    config_dict = req.dict()
    config_dict["trace_path"] = str(trace_path)

    cached = cache.get(config_dict)
    if cached:
        cached["cached"] = True
        return cached

    import numpy as np
    multipliers = np.logspace(
        np.log10(req.min_multiplier),
        np.log10(req.max_multiplier),
        req.num_points
    ).tolist()

    res = run_sweep(
        trace_path=str(trace_path),
        policy=req.policy,
        num_servers=req.num_servers,
        multipliers=multipliers,
        num_points=req.num_points,
        slo_target_s=req.slo_target_ms / 1000.0,
        window_start_s=req.window_start_s,
        window_duration_s=req.window_duration_s,
        max_requests=req.max_requests,
        time_quantum=req.time_quantum_ms / 1000.0,
        queue_capacity=req.queue_capacity,
        load_balancer=req.load_balancer,
        admission_policy=req.admission_policy,
        workers=8
    )
    res["cached"] = False
    cache.put(config_dict, res)
    return res


@app.post("/api/custom_policy")
def execute_custom_policy(req: CustomPolicyRequest):
    trace_path = resolve_trace_path(req.trace_name)
    sim_cfg = {
        "trace_path": str(trace_path),
        "num_servers": req.num_servers,
        "load_multiplier": req.load_multiplier,
        "queue_capacity": req.queue_capacity,
        "client_timeout": req.client_timeout_s,
        "slo_target_s": req.slo_target_ms / 1000.0,
        "max_requests": req.max_requests,
        "window_start_s": req.window_start_s,
        "window_duration_s": req.window_duration_s
    }
    return run_sandboxed_simulation(req.code, sim_cfg, timeout_s=4.0)


@app.get("/api/presets")
def list_presets():
    return get_presets()


@app.get("/api/presets/{preset_id}")
def get_preset(preset_id: str):
    res = get_preset_by_id(preset_id)
    if res is None:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
    return res


# Static files mount for Frontend
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3507)
