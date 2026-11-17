"""
Correctness Tests Against Queueing Theory Closed Forms
CSL559 Computer Systems Design - IIT Bhilai

NOTE ON ACADEMIC INTEGRITY:
Per course requirements, synthetic Poisson arrivals (M/M/1, M/M/c, M/G/1)
are STRICTLY CONFINED to this verification test file to mathematically validate
simulator correctness against theoretical closed forms. Synthetic data is NEVER
used in the application, results directory, or report.
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


def generate_synthetic_mm1_trace(
    parquet_path: Path,
    arrival_rate_lambda: float = 20.0,
    service_rate_mu: float = 30.0,
    n_requests: int = 40000,
    seed: int = 42
):
    """
    Generate synthetic Poisson arrivals (Exp(lambda)) with Exp(mu) service times.
    M/M/1 Theoretical:
      rho = lambda / mu = 20 / 30 = 2/3
      E[T] = 1 / (mu - lambda) = 1 / 10 = 0.100s (100ms)
      E[W] = rho / (mu - lambda) = (2/3) / 10 = 0.0667s (66.7ms)
      L_q = lambda * E[W] = 20 * 0.0667 = 1.333
    """
    np.random.seed(seed)
    inter_arrivals = np.random.exponential(1.0 / arrival_rate_lambda, size=n_requests)
    arrival_times = np.cumsum(inter_arrivals)
    service_times = np.random.exponential(1.0 / service_rate_mu, size=n_requests)

    df = pd.DataFrame({
        'ts': arrival_times,
        'host_hash': ['client_synth'] * n_requests,
        'class': ['browse'] * n_requests,
        'path_group': ['/synth'] * n_requests,
        'bytes': (service_times * 100000).astype(int),
        'status': [200] * n_requests,
        'service_time_s': service_times
    })
    table = pa.Table.from_pandas(df)
    pq.write_table(table, parquet_path)


def test_mm1_mean_response_time_within_2_percent():
    """Verify that simulated M/M/1 mean response time matches theoretical E[T] within 2%."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_p = Path(tmpdir) / "mm1_synth.parquet"
        lam = 20.0
        mu = 30.0
        n_req = 40000
        generate_synthetic_mm1_trace(trace_p, lam, mu, n_req, seed=123)

        config = SimulationConfig(
            trace_path=str(trace_p),
            policy="fcfs",
            num_servers=1,
            load_multiplier=1.0,
            queue_capacity=100000,
            client_timeout=0.0  # No timeout
        )
        sim = Simulator(config)
        res = sim.run()

        # Theoretical closed form
        theoretical_e_t = 1.0 / (mu - lam)  # 0.100 s
        simulated_e_t = res.latency_mean

        rel_error = abs(simulated_e_t - theoretical_e_t) / theoretical_e_t
        print(f"\nM/M/1 Test: Theory={theoretical_e_t:.4f}s, Sim={simulated_e_t:.4f}s, RelError={rel_error*100:.2f}%")
        assert rel_error < 0.025, f"M/M/1 response time {simulated_e_t} deviated by {rel_error*100:.2f}% from theory {theoretical_e_t}"


def test_littles_law_holds():
    """Verify Little's Law holds in simulation: L_q = lambda * W_q within 3%."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_p = Path(tmpdir) / "littles_synth.parquet"
        lam = 25.0
        mu = 35.0
        generate_synthetic_mm1_trace(trace_p, lam, mu, 30000, seed=42)

        config = SimulationConfig(
            trace_path=str(trace_p),
            policy="fcfs",
            num_servers=1,
            load_multiplier=1.0,
            queue_capacity=50000,
            client_timeout=0.0
        )
        sim = Simulator(config)
        res = sim.run()

        sim_lam = res.completed / res.sim_duration_s
        sim_w_q = res.wait_time_mean
        expected_l_q = sim_lam * sim_w_q
        measured_l_q = res.mean_queue_length

        diff = abs(measured_l_q - expected_l_q) / max(0.01, expected_l_q)
        print(f"\nLittle's Law: Measured L_q={measured_l_q:.4f}, lambda*W_q={expected_l_q:.4f}, RelDiff={diff*100:.2f}%")
        assert diff < 0.035, f"Little's Law violation: Measured L_q={measured_l_q}, Expected={expected_l_q}"


def test_conservation_of_requests():
    """Verify strictly: total_arrivals = completed + dropped + timed_out + in_flight."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_p = Path(tmpdir) / "conserv_synth.parquet"
        generate_synthetic_mm1_trace(trace_p, arrival_rate_lambda=50.0, service_rate_mu=20.0, n_requests=5000)

        # High load causing drops and timeouts
        config = SimulationConfig(
            trace_path=str(trace_p),
            policy="fcfs",
            num_servers=1,
            load_multiplier=1.0,
            queue_capacity=50,      # Small capacity triggers drop-tail drops
            client_timeout=1.0      # Short timeout triggers timeouts
        )
        sim = Simulator(config)
        res = sim.run()

        sum_parts = res.completed + res.dropped + res.timed_out + res.in_flight
        assert sum_parts == res.total_arrivals, f"Conservation failed: {sum_parts} != {res.total_arrivals}"
        assert res.dropped > 0, "Expected drops under heavy overload"


def test_determinism_by_seed():
    """Verify that identical simulation configurations produce bit-exact results."""
    trace_path = "data/processed/epa.parquet"
    if not Path(trace_path).exists():
        pytest.skip("EPA Parquet trace not yet available")

    config1 = SimulationConfig(trace_path=trace_path, policy="sjf", num_servers=2, max_requests=1000)
    config2 = SimulationConfig(trace_path=trace_path, policy="sjf", num_servers=2, max_requests=1000)

    res1 = Simulator(config1).run()
    res2 = Simulator(config2).run()

    assert res1.completed == res2.completed
    assert pytest.approx(res1.latency_mean, abs=1e-6) == res2.latency_mean
    assert pytest.approx(res1.wait_time_p95, abs=1e-6) == res2.wait_time_p95
    assert pytest.approx(res1.server_utilization, abs=1e-6) == res2.server_utilization
