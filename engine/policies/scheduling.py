"""
Standard Built-in Scheduling Policies for NetSim-RT
CSL559 Computer Systems Design - IIT Bhilai

Implements:
- FCFS (First-Come First-Served)
- SJF (Shortest Job First - Non-preemptive)
- SRTF (Shortest Remaining Time First - Preemptive)
- RoundRobin (Configurable Quantum)
- StaticPriority (Strict Priority: book > browse)
- MLFQ (Multi-Level Feedback Queue with Starvation Boost)
- EDF (Earliest Deadline First)
- WFQ (Weighted Fair Queueing)
- ProcessorSharing (Idealized Time-Sharing)
"""

import heapq
from collections import deque
from typing import Optional, List, Tuple
from engine.models import Request
from engine.policies.base import BaseSchedulingPolicy, register_policy


@register_policy("fcfs")
class FCFSPolicy(BaseSchedulingPolicy):
    """First-Come First-Served (FIFO) queue."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.queue: deque[Request] = deque()

    def add_request(self, request: Request, now: float) -> bool:
        self.queue.append(request)
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if self.queue:
            return self.queue.popleft()
        return None

    def queue_length(self) -> int:
        return len(self.queue)


@register_policy("sjf")
class SJFPolicy(BaseSchedulingPolicy):
    """Shortest Job First (non-preemptive). Minimizes mean waiting time for a fixed batch."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.heap: List[Tuple[float, float, int, Request]] = []

    def add_request(self, request: Request, now: float) -> bool:
        # Key: (service_time, arrival_time, request_id)
        heapq.heappush(self.heap, (request.service_time, request.arrival_time, request.id, request))
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if self.heap:
            _, _, _, req = heapq.heappop(self.heap)
            return req
        return None

    def queue_length(self) -> int:
        return len(self.heap)


@register_policy("srtf")
class SRTFPolicy(BaseSchedulingPolicy):
    """Shortest Remaining Time First (preemptive)."""
    is_preemptive: bool = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.heap: List[Tuple[float, float, int, Request]] = []

    def add_request(self, request: Request, now: float) -> bool:
        heapq.heappush(self.heap, (request.remaining_time, request.arrival_time, request.id, request))
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if self.heap:
            _, _, _, req = heapq.heappop(self.heap)
            return req
        return None

    def queue_length(self) -> int:
        return len(self.heap)

    def should_preempt(self, active_request: Request, new_request: Request) -> bool:
        # Preempt if incoming request has strictly smaller remaining service time
        return new_request.remaining_time < (active_request.remaining_time - 0.0001)


@register_policy("rr")
@register_policy("round_robin")
class RoundRobinPolicy(BaseSchedulingPolicy):
    """Round Robin scheduling with configurable time quantum."""
    def __init__(self, quantum: float = 0.010, **kwargs):
        super().__init__(**kwargs)
        self.quantum = quantum
        self.queue: deque[Request] = deque()

    def add_request(self, request: Request, now: float) -> bool:
        self.queue.append(request)
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if self.queue:
            return self.queue.popleft()
        return None

    def on_quantum_expired(self, request: Request, now: float) -> None:
        # Re-queue at the tail
        self.queue.append(request)

    def queue_length(self) -> int:
        return len(self.queue)


@register_policy("priority")
@register_policy("static_priority")
class StaticPriorityPolicy(BaseSchedulingPolicy):
    """
    Strict Static Priority:
    Priority 0 ('book', dynamic high value) > Priority 1 ('browse', static GET).
    FCFS within each priority level.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.high_queue: deque[Request] = deque()  # book
        self.low_queue: deque[Request] = deque()   # browse

    def add_request(self, request: Request, now: float) -> bool:
        if request.priority == 0 or request.req_class == "book":
            self.high_queue.append(request)
        else:
            self.low_queue.append(request)
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if self.high_queue:
            return self.high_queue.popleft()
        if self.low_queue:
            return self.low_queue.popleft()
        return None

    def queue_length(self) -> int:
        return len(self.high_queue) + len(self.low_queue)


@register_policy("mlfq")
class MLFQPolicy(BaseSchedulingPolicy):
    """
    Multi-Level Feedback Queue with 3 Priority Levels:
    - Q0: 10ms quantum (fast turnaround for short jobs)
    - Q1: 20ms quantum
    - Q2: 40ms quantum / FCFS tail
    Includes periodic starvation avoidance (priority boost every 2.0s).
    """
    def __init__(self, base_quantum: float = 0.010, boost_interval: float = 2.0, **kwargs):
        super().__init__(**kwargs)
        self.base_quantum = base_quantum
        self.boost_interval = boost_interval
        self.last_boost = 0.0
        self.queues = [deque(), deque(), deque()]  # levels 0, 1, 2
        self.req_levels: dict[int, int] = {}       # req_id -> level

    def _maybe_boost(self, now: float):
        if now - self.last_boost >= self.boost_interval:
            self.last_boost = now
            # Boost all requests to highest priority Q0
            while self.queues[1]:
                req = self.queues[1].popleft()
                self.req_levels[req.id] = 0
                self.queues[0].append(req)
            while self.queues[2]:
                req = self.queues[2].popleft()
                self.req_levels[req.id] = 0
                self.queues[0].append(req)

    def add_request(self, request: Request, now: float) -> bool:
        self._maybe_boost(now)
        level = self.req_levels.get(request.id, 0)
        self.queues[level].append(request)
        return True

    def select_next(self, now: float) -> Optional[Request]:
        self._maybe_boost(now)
        for level in range(3):
            if self.queues[level]:
                return self.queues[level].popleft()
        return None

    def on_quantum_expired(self, request: Request, now: float) -> None:
        current_level = self.req_levels.get(request.id, 0)
        # Demote down to maximum level 2
        next_level = min(2, current_level + 1)
        self.req_levels[request.id] = next_level
        self.queues[next_level].append(request)

    def get_quantum(self, request: Request) -> float:
        level = self.req_levels.get(request.id, 0)
        return self.base_quantum * (2 ** level)

    def queue_length(self) -> int:
        return sum(len(q) for q in self.queues)


@register_policy("edf")
class EDFPolicy(BaseSchedulingPolicy):
    """Earliest Deadline First. Optimal for single-server preemptive feasibility."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.heap: List[Tuple[float, float, int, Request]] = []

    def add_request(self, request: Request, now: float) -> bool:
        heapq.heappush(self.heap, (request.deadline, request.arrival_time, request.id, request))
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if self.heap:
            _, _, _, req = heapq.heappop(self.heap)
            return req
        return None

    def queue_length(self) -> int:
        return len(self.heap)


@register_policy("wfq")
class WFQPolicy(BaseSchedulingPolicy):
    """
    Weighted Fair Queueing (Demers, Keshav, Shenker 1989):
    Approximates Generalized Processor Sharing by tracking virtual finish times:
    F_i = max(V(t), F_{i-1}) + L_i / w_i
    Default weights: book = 3.0, browse = 1.0.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.heap: List[Tuple[float, float, int, Request]] = []
        self.virtual_time = 0.0
        self.last_finish_by_flow: dict[str, float] = {}

    def add_request(self, request: Request, now: float) -> bool:
        self.virtual_time = max(self.virtual_time, now)
        flow_key = request.req_class
        weight = 3.0 if request.req_class == "book" else 1.0
        request.weight = weight
        
        last_f = self.last_finish_by_flow.get(flow_key, self.virtual_time)
        v_start = max(self.virtual_time, last_f)
        v_finish = v_start + (request.service_time / weight)
        self.last_finish_by_flow[flow_key] = v_finish
        request.virtual_finish_time = v_finish
        
        heapq.heappush(self.heap, (v_finish, request.arrival_time, request.id, request))
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if self.heap:
            _, _, _, req = heapq.heappop(self.heap)
            return req
        return None

    def queue_length(self) -> int:
        return len(self.heap)


@register_policy("ps")
@register_policy("processor_sharing")
class ProcessorSharingPolicy(BaseSchedulingPolicy):
    """Idealized Processor Sharing with small discrete 2ms time slices."""
    def __init__(self, quantum: float = 0.002, **kwargs):
        super().__init__(**kwargs)
        self.quantum = quantum
        self.queue: deque[Request] = deque()

    def add_request(self, request: Request, now: float) -> bool:
        self.queue.append(request)
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if self.queue:
            return self.queue.popleft()
        return None

    def on_quantum_expired(self, request: Request, now: float) -> None:
        self.queue.append(request)

    def queue_length(self) -> int:
        return len(self.queue)
