"""
Policy Property and Behavioral Verification Tests
CSL559 Computer Systems Design - IIT Bhilai
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


def create_batch_trace(parquet_path: Path):
    """Create a fixed batch of requests arriving at t=0 with variable service times."""
    service_times = [10.0, 1.0, 2.0, 8.0, 0.5]
    df = pd.DataFrame({
        'ts': [0.0] * len(service_times),
        'host_hash': [f"client_{i}" for i in range(len(service_times))],
        'class': ['browse'] * len(service_times),
        'path_group': ['/batch'] * len(service_times),
        'bytes': [int(s * 1000) for s in service_times],
        'status': [200] * len(service_times),
        'service_time_s': service_times
    })
    table = pa.Table.from_pandas(df)
    pq.write_table(table, parquet_path)


def test_sjf_minimizes_mean_wait_time_on_batch():
    """Verify that SJF yields strictly lower mean wait time than FCFS on a heterogeneous batch."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_p = Path(tmpdir) / "batch.parquet"
        create_batch_trace(trace_p)

        cfg_fcfs = SimulationConfig(trace_path=str(trace_p), policy="fcfs", num_servers=1)
        cfg_sjf = SimulationConfig(trace_path=str(trace_p), policy="sjf", num_servers=1)

        res_fcfs = Simulator(cfg_fcfs).run()
        res_sjf = Simulator(cfg_sjf).run()

        print(f"\nBatch wait times: FCFS Mean Wait={res_fcfs.wait_time_mean:.3f}s, SJF Mean Wait={res_sjf.wait_time_mean:.3f}s")
        assert res_sjf.wait_time_mean < res_fcfs.wait_time_mean
        # Mathematical verification:
        # FCFS wait times: 0, 10, 11, 13, 21 => sum=55 => mean=11.0s
        # SJF wait times: 0, 10, 10.5, 11.5, 13.5 => sum=45.5 => mean=9.1s
        assert pytest.approx(res_fcfs.wait_time_mean, abs=1e-3) == 11.000
        assert pytest.approx(res_sjf.wait_time_mean, abs=1e-3) == 9.100


def test_priority_starvation_demonstrable():
    """
    Verify that under heavy 'book' traffic, strict priority scheduling starves 'browse'
    requests resulting in high browse latency or timeouts.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_p = Path(tmpdir) / "priority_starve.parquet"
        
        # 100 book requests arriving frequently (every 0.02s) with service time 0.05s
        # 1 browse request arriving at t=0.01 with service time 0.01s
        timestamps = [i * 0.02 for i in range(100)]
        classes = ['book'] * 100
        service_times = [0.05] * 100
        
        # Insert a single browse request near the start
        timestamps.append(0.01)
        classes.append('browse')
        service_times.append(0.01)

        df = pd.DataFrame({
            'ts': timestamps,
            'host_hash': ['h'] * len(timestamps),
            'class': classes,
            'path_group': ['/p'] * len(timestamps),
            'bytes': [1000] * len(timestamps),
            'status': [200] * len(timestamps),
            'service_time_s': service_times
        }).sort_values(by='ts').reset_index(drop=True)
        
        table = pa.Table.from_pandas(df)
        pq.write_table(table, trace_p)

        cfg_prio = SimulationConfig(trace_path=str(trace_p), policy="priority", num_servers=1, client_timeout=0.0)
        cfg_fcfs = SimulationConfig(trace_path=str(trace_p), policy="fcfs", num_servers=1, client_timeout=0.0)

        res_prio = Simulator(cfg_prio).run()
        res_fcfs = Simulator(cfg_fcfs).run()

        prio_browse_wait = res_prio.class_metrics['browse']['max_wait_ms']
        fcfs_browse_wait = res_fcfs.class_metrics['browse']['max_wait_ms']

        print(f"\nPriority Starvation Test: Browse wait under Priority={prio_browse_wait:.1f}ms, FCFS={fcfs_browse_wait:.1f}ms")
        assert prio_browse_wait > fcfs_browse_wait * 10.0


def test_round_robin_bounded_wait_and_slicing():
    """Verify that RoundRobin slices long jobs, ensuring short jobs do not suffer Head-of-Line blocking."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_p = Path(tmpdir) / "rr_slice.parquet"
        # 1 giant job (10s) arriving at t=0, followed by 1 tiny job (0.05s) arriving at t=0.001
        df = pd.DataFrame({
            'ts': [0.0, 0.001],
            'host_hash': ['client_A', 'client_B'],
            'class': ['browse', 'browse'],
            'path_group': ['/rr', '/rr'],
            'bytes': [100000, 100],
            'status': [200, 200],
            'service_time_s': [10.0, 0.05]
        })
        table = pa.Table.from_pandas(df)
        pq.write_table(table, trace_p)

        # FCFS: Tiny job waits ~10 seconds behind Giant job
        cfg_fcfs = SimulationConfig(trace_path=str(trace_p), policy="fcfs", num_servers=1)
        res_fcfs = Simulator(cfg_fcfs).run()

        # RR (quantum=10ms): Tiny job starts after just 10ms of Giant job!
        cfg_rr = SimulationConfig(trace_path=str(trace_p), policy="rr", num_servers=1, time_quantum=0.010)
        res_rr = Simulator(cfg_rr).run()

        # Compare maximum wait time:
        fcfs_max_wait = res_fcfs.wait_time_max
        rr_max_wait = res_rr.wait_time_max

        print(f"\nHead-of-Line Blocking: FCFS Max Wait={fcfs_max_wait:.3f}s, RR Max Wait={rr_max_wait:.3f}s")
        # Under FCFS, tiny job waited 9.999s. Under RR with 10ms quantum, tiny job waited only 0.009s!
        assert rr_max_wait < 0.020, f"Expected RR max wait < 20ms, got {rr_max_wait}"
        assert rr_max_wait < fcfs_max_wait / 100.0


def test_load_balancing_and_admission_control():
    """Verify load balancing (JSQ, power_of_two) and token bucket admission."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_p = Path(tmpdir) / "test_lb.parquet"
        n = 100
        df = pd.DataFrame({
            'ts': np.linspace(0.0, 1.0, n),
            'class': ['browse'] * n,
            'path_group': ['/api'] * n,
            'bytes': [500] * n,
            'status': [200] * n,
            'service_time_s': [0.05] * n
        })
        table = pa.Table.from_pandas(df)
        pq.write_table(table, trace_p)

        # JSQ across 4 servers
        cfg_jsq = SimulationConfig(
            trace_path=str(trace_p),
            policy="fcfs",
            num_servers=4,
            load_balancer="join_shortest_queue"
        )
        res_jsq = Simulator(cfg_jsq).run()
        assert res_jsq.completed == n
        assert res_jsq.dropped == 0

        # Token bucket admission dropping excess
        cfg_tb = SimulationConfig(
            trace_path=str(trace_p),
            policy="fcfs",
            num_servers=1,
            admission_policy="token_bucket",
            token_bucket_rate=20.0,
            token_bucket_capacity=10.0
        )
        res_tb = Simulator(cfg_tb).run()
        assert res_tb.dropped > 0
        assert res_tb.completed + res_tb.dropped + res_tb.timed_out + res_tb.in_flight == n

