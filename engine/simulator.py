"""
High-Performance Heap-Based Discrete-Event Simulator Engine
CSL559 Computer Systems Design - IIT Bhilai

Architecture:
- Deterministic priority queue event heap (heapq)
- Multi-server processor pool (c >= 1)
- Pluggable scheduling policies (FCFS, SJF, SRTF, RR, Priority, MLFQ, EDF, WFQ, PS, Custom)
- Drop-tail admission control & client timeouts
- Time-weighted queue length & utilization integration
"""

import time
import heapq
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
import pandas as pd

from engine.models import Request, SimulationConfig, SimulationResult
from engine.policies.base import BaseSchedulingPolicy, get_policy
import engine.policies.scheduling  # Ensure standard policies are registered


# Event types
EVENT_ARRIVAL = 1
EVENT_COMPLETION = 2
EVENT_QUANTUM_EXPIRE = 3
EVENT_TIMEOUT = 4


class Simulator:
    """Discrete-Event Simulator for trace replay and scheduling evaluation."""
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.policy: BaseSchedulingPolicy = get_policy(
            config.policy,
            quantum=config.time_quantum
        )
        self.num_servers = config.num_servers
        self.queue_capacity = config.queue_capacity
        self.client_timeout = config.client_timeout
        self.slo_target = config.slo_target_s

        # Event heap: list of tuples (event_time, event_id, event_type, payload)
        self.event_heap: List[Tuple[float, int, int, Any]] = []
        self._event_counter = 0

        # State tracking
        self.now = 0.0
        self.idle_servers: List[int] = list(range(self.num_servers))
        self.active_requests: Dict[int, Request] = {}  # server_id -> Request
        self.all_requests: List[Request] = []

        # Time-weighted metrics accumulators
        self.last_state_change_time = 0.0
        self.area_queue_length = 0.0
        self.area_busy_servers = 0.0
        self.max_queue_depth = 0

        # Timeline recording
        self.timeline_samples: List[Dict[str, float]] = []
        self.last_sample_time = 0.0
        self.sample_interval = 1.0  # Will be adjusted after loading trace

    def _push_event(self, event_time: float, event_type: int, payload: Any):
        self._event_counter += 1
        heapq.heappush(self.event_heap, (event_time, self._event_counter, event_type, payload))

    def _update_time_weighted_stats(self, next_time: float):
        delta = next_time - self.last_state_change_time
        if delta > 0.0:
            q_len = self.policy.queue_length()
            busy_cnt = self.num_servers - len(self.idle_servers)
            self.area_queue_length += q_len * delta
            self.area_busy_servers += busy_cnt * delta
            if q_len > self.max_queue_depth:
                self.max_queue_depth = q_len
            self.last_state_change_time = next_time

    def _record_timeline_sample(self):
        if self.now - self.last_sample_time >= self.sample_interval:
            self.last_sample_time = self.now
            busy_cnt = self.num_servers - len(self.idle_servers)
            util = busy_cnt / float(self.num_servers)
            q_len = self.policy.queue_length()
            self.timeline_samples.append({
                "time_s": round(self.now, 2),
                "queue_depth": q_len,
                "utilization": round(util, 4),
                "active_servers": busy_cnt
            })

    def load_trace(self) -> int:
        """Load and schedule all arrivals from Parquet trace file."""
        df = pd.read_parquet(self.config.trace_path)
        
        # Apply window slicing if specified
        if self.config.window_start_s is not None:
            w_start = self.config.window_start_s
            df = df[df['ts'] >= w_start]
        if self.config.window_duration_s is not None:
            w_start = self.config.window_start_s or 0.0
            df = df[df['ts'] <= (w_start + self.config.window_duration_s)]
            
        if self.config.max_requests is not None:
            df = df.iloc[:self.config.max_requests]

        total = len(df)
        if total == 0:
            return 0

        # Normalize start timestamp
        t0 = df['ts'].iloc[0]
        # Offered load scaling: load_multiplier compresses inter-arrival intervals
        multiplier = max(0.001, self.config.load_multiplier)
        
        # Calculate dynamic timeline sampling interval (max ~200 points)
        sim_est_duration = (df['ts'].iloc[-1] - t0) / multiplier
        self.sample_interval = max(0.5, sim_est_duration / 200.0)

        for i, row in enumerate(df.itertuples(index=False)):
            arr_time = (row.ts - t0) / multiplier
            st = float(row.service_time_s)
            req_class = str(getattr(row, 'class', getattr(row, '_2', 'browse')))
            path_grp = str(row.path_group)
            b = int(row.bytes)
            status = int(row.status)
            priority = 0 if req_class == "book" else 1
            deadline = arr_time + self.slo_target
            
            req = Request(
                id=i,
                arrival_time=arr_time,
                service_time=st,
                remaining_time=st,
                req_class=req_class,
                path_group=path_grp,
                bytes=b,
                status=status,
                deadline=deadline,
                priority=priority
            )
            self.all_requests.append(req)
            self._push_event(arr_time, EVENT_ARRIVAL, req)

        return total

    def run(self) -> SimulationResult:
        """Execute simulation until all events are processed."""
        real_start_clock = time.perf_counter()
        total_arrivals = self.load_trace()
        if total_arrivals == 0:
            raise ValueError(f"Trace {self.config.trace_path} produced 0 requests.")

        processed_events = 0

        while self.event_heap:
            ev_time, _, ev_type, payload = heapq.heappop(self.event_heap)
            self._update_time_weighted_stats(ev_time)
            self.now = ev_time
            processed_events += 1

            if ev_type == EVENT_ARRIVAL:
                self._handle_arrival(payload)
            elif ev_type == EVENT_COMPLETION:
                self._handle_completion(payload)
            elif ev_type == EVENT_QUANTUM_EXPIRE:
                self._handle_quantum_expire(payload)
            elif ev_type == EVENT_TIMEOUT:
                self._handle_timeout(payload)

            self._record_timeline_sample()

        real_elapsed = time.perf_counter() - real_start_clock
        return self._compute_results(real_elapsed, processed_events)

    def _handle_arrival(self, req: Request):
        # Drop-tail queue limit check
        if self.policy.queue_length() >= self.queue_capacity:
            req.dropped = True
            return

        # Schedule client timeout event
        if self.client_timeout > 0:
            timeout_time = self.now + self.client_timeout
            self._push_event(timeout_time, EVENT_TIMEOUT, req)

        # Check for idle server
        if self.idle_servers:
            server_id = self.idle_servers.pop(0)
            self._dispatch_to_server(req, server_id)
        else:
            # Check preemptive scheduling (e.g. SRTF)
            preempted = False
            if self.policy.is_preemptive:
                # Find server with highest remaining time job
                worst_server = -1
                worst_rem = req.remaining_time
                for s_id, act_req in self.active_requests.items():
                    if self.policy.should_preempt(act_req, req):
                        if act_req.remaining_time > worst_rem:
                            worst_rem = act_req.remaining_time
                            worst_server = s_id
                            
                if worst_server >= 0:
                    preempted = True
                    victim = self.active_requests[worst_server]
                    # Put victim back into policy queue
                    self.policy.add_request(victim, self.now)
                    victim.context_switches += 1
                    # Dispatch new request to that server
                    self._dispatch_to_server(req, worst_server)

            if not preempted:
                self.policy.add_request(req, self.now)

    def _dispatch_to_server(self, req: Request, server_id: int):
        if req.start_time < 0.0:
            req.start_time = self.now
        req.server_id = server_id
        self.active_requests[server_id] = req

        # Check if policy uses quantum slicing (RR, MLFQ, PS)
        quantum = getattr(self.policy, "quantum", None)
        if hasattr(self.policy, "get_quantum"):
            quantum = self.policy.get_quantum(req)

        if quantum is not None and req.remaining_time > quantum:
            # Quantum event
            completion_time = self.now + quantum
            req.remaining_time -= quantum
            self._push_event(completion_time, EVENT_QUANTUM_EXPIRE, (server_id, req))
        else:
            # Completion event
            completion_time = self.now + req.remaining_time
            req.remaining_time = 0.0
            self._push_event(completion_time, EVENT_COMPLETION, (server_id, req))

    def _handle_completion(self, payload: Tuple[int, Request]):
        server_id, req = payload
        # Ensure request is still the active one on this server
        if self.active_requests.get(server_id) is not req:
            return

        req.finish_time = self.now
        del self.active_requests[server_id]

        # Allocate server to next waiting request from policy
        next_req = self.policy.select_next(self.now)
        while next_req and (next_req.dropped or next_req.timed_out):
            next_req = self.policy.select_next(self.now)

        if next_req:
            self._dispatch_to_server(next_req, server_id)
        else:
            self.idle_servers.append(server_id)

    def _handle_quantum_expire(self, payload: Tuple[int, Request]):
        server_id, req = payload
        if self.active_requests.get(server_id) is not req:
            return

        req.context_switches += 1
        del self.active_requests[server_id]

        # Return request to policy
        self.policy.on_quantum_expired(req, self.now)

        # Select next request
        next_req = self.policy.select_next(self.now)
        while next_req and (next_req.dropped or next_req.timed_out):
            next_req = self.policy.select_next(self.now)

        if next_req:
            self._dispatch_to_server(next_req, server_id)
        else:
            self.idle_servers.append(server_id)

    def _handle_timeout(self, req: Request):
        # If still in queue (has not started service), flag timed out
        if req.start_time < 0.0 and not req.dropped:
            req.timed_out = True

    def _compute_results(self, real_elapsed: float, processed_events: int) -> SimulationResult:
        sim_duration = max(0.001, self.now)
        completed_reqs = [r for r in self.all_requests if r.finish_time >= 0.0 and not r.timed_out]
        dropped_reqs = [r for r in self.all_requests if r.dropped]
        timed_out_reqs = [r for r in self.all_requests if r.timed_out]
        in_flight = len(self.all_requests) - len(completed_reqs) - len(dropped_reqs) - len(timed_out_reqs)

        total_arr = len(self.all_requests)
        completed_cnt = len(completed_reqs)
        dropped_cnt = len(dropped_reqs)
        timeout_cnt = len(timed_out_reqs)

        throughput = completed_cnt / sim_duration
        offered_load = total_arr / sim_duration

        # Goodput: successfully completed within SLO target
        good_completions = [r for r in completed_reqs if r.latency <= self.slo_target]
        goodput = len(good_completions) / sim_duration

        latencies = [r.latency for r in completed_reqs]
        wait_times = [r.wait_time for r in completed_reqs]

        if latencies:
            lat_mean = float(np.mean(latencies))
            lat_p50 = float(np.percentile(latencies, 50))
            lat_p95 = float(np.percentile(latencies, 95))
            lat_p99 = float(np.percentile(latencies, 99))
            lat_p999 = float(np.percentile(latencies, 99.9))
            lat_max = float(np.max(latencies))
            slo_pct = float(100.0 * len(good_completions) / len(completed_reqs))

            # Jain's fairness index on slowdown (latency / service_time >= 1.0)
            slowdowns = np.array([max(1.0, r.latency / max(0.0001, r.service_time)) for r in completed_reqs])
            sum_s = np.sum(slowdowns)
            sum_sq = np.sum(slowdowns ** 2)
            n_s = len(slowdowns)
            jain = float((sum_s ** 2) / (n_s * sum_sq)) if sum_sq > 0 else 1.0
        else:
            lat_mean = lat_p50 = lat_p95 = lat_p99 = lat_p999 = lat_max = 0.0
            slo_pct = 0.0
            jain = 1.0

        if wait_times:
            wt_mean = float(np.mean(wait_times))
            wt_p50 = float(np.percentile(wait_times, 50))
            wt_p95 = float(np.percentile(wait_times, 95))
            wt_p99 = float(np.percentile(wait_times, 99))
            wt_max = float(np.max(wait_times))
        else:
            wt_mean = wt_p50 = wt_p95 = wt_p99 = wt_max = 0.0

        # Server utilization: (total busy time) / (c * total duration)
        total_server_time = self.num_servers * sim_duration
        utilization = float(np.clip(self.area_busy_servers / total_server_time, 0.0, 1.0))
        mean_q_len = float(self.area_queue_length / sim_duration)

        # Per-class breakdown
        class_metrics = {}
        for c in ("browse", "book"):
            c_completed = [r for r in completed_reqs if r.req_class == c]
            if c_completed:
                c_lats = [r.latency for r in c_completed]
                class_metrics[c] = {
                    "count": len(c_completed),
                    "mean_latency_ms": round(float(np.mean(c_lats)) * 1000.0, 2),
                    "p95_latency_ms": round(float(np.percentile(c_lats, 95)) * 1000.0, 2),
                    "p99_latency_ms": round(float(np.percentile(c_lats, 99)) * 1000.0, 2),
                    "max_wait_ms": round(float(max(r.wait_time for r in c_completed)) * 1000.0, 2),
                }

        events_per_sec = float(processed_events / real_elapsed) if real_elapsed > 0 else 0.0

        return SimulationResult(
            policy=self.config.policy,
            num_servers=self.num_servers,
            load_multiplier=self.config.load_multiplier,
            total_arrivals=total_arr,
            completed=completed_cnt,
            dropped=dropped_cnt,
            timed_out=timeout_cnt,
            in_flight=in_flight,
            sim_duration_s=sim_duration,
            real_runtime_s=real_elapsed,
            events_per_sec=events_per_sec,
            throughput_req_per_s=throughput,
            goodput_req_per_s=goodput,
            offered_load_req_per_s=offered_load,
            latency_mean=lat_mean,
            latency_p50=lat_p50,
            latency_p95=lat_p95,
            latency_p99=lat_p99,
            latency_p999=lat_p999,
            latency_max=lat_max,
            wait_time_mean=wt_mean,
            wait_time_p50=wt_p50,
            wait_time_p95=wt_p95,
            wait_time_p99=wt_p99,
            wait_time_max=wt_max,
            server_utilization=utilization,
            mean_queue_length=mean_q_len,
            max_queue_length=self.max_queue_depth,
            drop_rate=float(dropped_cnt / total_arr),
            timeout_rate=float(timeout_cnt / total_arr),
            slo_attainment_pct=slo_pct,
            jains_fairness_index=jain,
            class_metrics=class_metrics,
            timeline=self.timeline_samples
        )
