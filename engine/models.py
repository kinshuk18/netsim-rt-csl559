"""
NetSim-RT Simulation Models and Datatypes
CSL559 Computer Systems Design - IIT Bhilai
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import numpy as np


@dataclass(slots=True)
class Request:
    """Represents a discrete client request in the simulator."""
    id: int
    arrival_time: float
    service_time: float
    remaining_time: float
    req_class: str = "browse"        # "browse" (cheap GET) or "book" (expensive dynamic)
    path_group: str = "/"
    bytes: int = 0
    status: int = 200
    deadline: float = 0.0           # For EDF scheduling
    priority: int = 1               # 0 = high priority (book), 1 = normal priority (browse)
    weight: float = 1.0             # For WFQ scheduling
    virtual_finish_time: float = 0.0
    
    # Lifecycle timestamps recorded by simulator
    start_time: float = -1.0
    finish_time: float = -1.0
    server_id: int = -1
    dropped: bool = False
    timed_out: bool = False
    context_switches: int = 0
    retries: int = 0

    @property
    def latency(self) -> float:
        """Total response time: wait_time + total execution time."""
        if self.finish_time >= 0.0:
            return self.finish_time - self.arrival_time
        return -1.0

    @property
    def wait_time(self) -> float:
        """Queue delay before first service."""
        if self.start_time >= 0.0:
            return self.start_time - self.arrival_time
        return -1.0


@dataclass
class SimulationConfig:
    """Configuration parameters for a simulation run."""
    trace_path: str
    policy: str = "fcfs"
    num_servers: int = 4
    queue_capacity: int = 50000      # Max pending queue depth (drop-tail)
    time_quantum: float = 0.010      # 10ms quantum for Round Robin / MLFQ
    load_multiplier: float = 1.0     # Time-compression factor (offered load scaling)
    client_timeout: float = 30.0     # Client timeout in seconds
    slo_target_s: float = 0.500      # 500ms SLO target
    load_balancer: str = "central_queue"  # central_queue, round_robin, random, join_shortest_queue, power_of_two
    admission_policy: str = "drop_tail"   # none, drop_tail, token_bucket
    token_bucket_rate: float = 1000.0     # tokens/sec for token_bucket
    token_bucket_capacity: float = 100.0  # max bucket depth
    retry_on_timeout: bool = False
    max_retries: int = 0
    backoff_base_s: float = 0.5
    backoff_multiplier: float = 2.0
    seed: int = 42
    max_requests: Optional[int] = None
    window_start_s: Optional[float] = None
    window_duration_s: Optional[float] = None
    # Server downtime injection: during [server_downtime_start_s, server_downtime_end_s]
    # servers do not start new work (arrivals queue up). Times are in sim-time (seconds).
    server_downtime_start_s: Optional[float] = None
    server_downtime_end_s: Optional[float] = None


@dataclass
class SimulationResult:
    """Comprehensive performance metrics returned by NetSim-RT."""
    policy: str
    num_servers: int
    load_multiplier: float
    total_arrivals: int
    completed: int
    dropped: int
    timed_out: int
    in_flight: int
    
    sim_duration_s: float
    real_runtime_s: float
    events_per_sec: float
    
    # Throughput & Goodput
    throughput_req_per_s: float      # Total completions / duration
    goodput_req_per_s: float         # Successful completions within SLO & without timeout / duration
    offered_load_req_per_s: float
    
    # Latency Percentiles (seconds)
    latency_mean: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    latency_p999: float
    latency_max: float
    
    # Wait Time Percentiles (seconds)
    wait_time_mean: float
    wait_time_p50: float
    wait_time_p95: float
    wait_time_p99: float
    wait_time_max: float             # Identifies starvation
    
    # System Metrics
    server_utilization: float        # Fraction [0.0, 1.0]
    mean_queue_length: float         # Time-weighted average queue depth L_q
    max_queue_length: int
    drop_rate: float                 # dropped / total_arrivals
    timeout_rate: float              # timed_out / total_arrivals
    slo_attainment_pct: float        # % of completed requests with latency <= SLO
    
    # Fairness & Starvation
    jains_fairness_index: float      # Jain's index on slowdown (latency / service_time)
    class_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # Time-series samples for playback UI (sampled up to 200 points)
    timeline: List[Dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy,
            "num_servers": self.num_servers,
            "load_multiplier": round(self.load_multiplier, 4),
            "total_arrivals": self.total_arrivals,
            "completed": self.completed,
            "dropped": self.dropped,
            "timed_out": self.timed_out,
            "in_flight": self.in_flight,
            "sim_duration_s": round(self.sim_duration_s, 2),
            "real_runtime_s": round(self.real_runtime_s, 4),
            "events_per_sec": round(self.events_per_sec, 1),
            "throughput_req_per_s": round(self.throughput_req_per_s, 2),
            "goodput_req_per_s": round(self.goodput_req_per_s, 2),
            "offered_load_req_per_s": round(self.offered_load_req_per_s, 2),
            "latency": {
                "mean_ms": round(self.latency_mean * 1000.0, 2),
                "p50_ms": round(self.latency_p50 * 1000.0, 2),
                "p95_ms": round(self.latency_p95 * 1000.0, 2),
                "p99_ms": round(self.latency_p99 * 1000.0, 2),
                "p999_ms": round(self.latency_p999 * 1000.0, 2),
                "max_ms": round(self.latency_max * 1000.0, 2),
            },
            "wait_time": {
                "mean_ms": round(self.wait_time_mean * 1000.0, 2),
                "p50_ms": round(self.wait_time_p50 * 1000.0, 2),
                "p95_ms": round(self.wait_time_p95 * 1000.0, 2),
                "p99_ms": round(self.wait_time_p99 * 1000.0, 2),
                "max_ms": round(self.wait_time_max * 1000.0, 2),
            },
            "server_utilization": round(self.server_utilization, 4),
            "mean_queue_length": round(self.mean_queue_length, 2),
            "max_queue_length": self.max_queue_length,
            "drop_rate": round(self.drop_rate, 4),
            "timeout_rate": round(self.timeout_rate, 4),
            "slo_attainment_pct": round(self.slo_attainment_pct, 2),
            "jains_fairness_index": round(self.jains_fairness_index, 4),
            "class_metrics": self.class_metrics,
            "timeline": self.timeline,
        }
