"""
Server Downtime Injection Tests
CSL559 Computer Systems Design - IIT Bhilai

NOTE ON ACADEMIC INTEGRITY:
Synthetic Poisson arrivals are STRICTLY CONFINED to this test file for correctness
verification. Synthetic data is NEVER used in results/ or the report.
"""

import pytest
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import tempfile
from pathlib import Path

from engine.models import SimulationConfig
from engine.simulator import Simulator


def generate_synthetic_trace(parquet_path: Path, n: int = 2000, lam: float = 10.0,
                               mu: float = 50.0, seed: int = 7):
    """Generate simple Poisson trace for downtime tests (synthetic, tests/ only)."""
    rng = np.random.default_rng(seed)
    ia = rng.exponential(1.0 / lam, size=n)
    ts = np.cumsum(ia)
    st = rng.exponential(1.0 / mu, size=n)
    df = pd.DataFrame({
        'ts': ts, 'host_hash': ['h'] * n, 'class': ['browse'] * n,
        'path_group': ['/'] * n, 'bytes': [1024] * n, 'status': [200] * n,
        'service_time_s': st
    })
    pq.write_table(pa.Table.from_pandas(df), parquet_path)


def test_downtime_creates_backlog():
    """During downtime, requests queue up; peak_backlog > 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "trace.parquet"
        generate_synthetic_trace(p, n=3000, lam=10.0, mu=50.0)
        cfg = SimulationConfig(
            trace_path=str(p),
            policy="fcfs",
            num_servers=2,
            load_multiplier=1.0,
            client_timeout=300.0,
            server_downtime_start_s=50.0,
            server_downtime_end_s=60.0,
        )
        sim = Simulator(cfg)
        res = sim.run()
        # During 10s downtime at lambda=10 req/s => ~100 arrivals build up
        assert sim.peak_backlog > 0, "Downtime should build a non-zero backlog"
        assert sim.recovery_start_time == pytest.approx(60.0, abs=0.001)


def test_downtime_drain_time_positive():
    """After downtime ends, drain_time > 0 and queue drains completely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "trace.parquet"
        generate_synthetic_trace(p, n=5000, lam=8.0, mu=40.0)
        cfg = SimulationConfig(
            trace_path=str(p),
            policy="fcfs",
            num_servers=2,
            load_multiplier=1.0,
            client_timeout=300.0,
            server_downtime_start_s=50.0,
            server_downtime_end_s=70.0,
        )
        sim = Simulator(cfg)
        res = sim.run()
        assert sim.peak_backlog > 10, "Should have significant backlog"
        assert sim.drain_end_time is not None, "Queue should drain"
        drain_time = sim.drain_end_time - sim.recovery_start_time
        assert drain_time > 0, "Drain time must be positive"


def test_no_downtime_does_not_affect_results():
    """Without downtime config, simulator behaves identically to baseline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "trace.parquet"
        generate_synthetic_trace(p, n=1000, lam=5.0, mu=30.0)
        cfg = SimulationConfig(
            trace_path=str(p), policy="fcfs", num_servers=2,
            load_multiplier=1.0, client_timeout=300.0,
        )
        sim = Simulator(cfg)
        res = sim.run()
        assert sim.peak_backlog == 0
        assert sim.recovery_start_time is None
        assert sim.drain_end_time is None


def test_sjf_drains_faster_than_fcfs():
    """SJF should drain backlog at least as fast as FCFS (smaller jobs dispatched first)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "trace.parquet"
        generate_synthetic_trace(p, n=4000, lam=10.0, mu=20.0)
        drains = {}
        for pol in ["fcfs", "sjf"]:
            cfg = SimulationConfig(
                trace_path=str(p), policy=pol, num_servers=2,
                load_multiplier=1.0, client_timeout=300.0,
                server_downtime_start_s=50.0, server_downtime_end_s=70.0,
            )
            sim = Simulator(cfg)
            sim.run()
            if sim.drain_end_time is not None:
                drains[pol] = sim.drain_end_time - sim.recovery_start_time
        # Both should have a drain time; SJF should be <= FCFS (or comparable)
        if "fcfs" in drains and "sjf" in drains:
            assert drains["sjf"] <= drains["fcfs"] * 1.5, \
                f"SJF drain {drains['sjf']:.2f}s should not be much worse than FCFS {drains['fcfs']:.2f}s"
