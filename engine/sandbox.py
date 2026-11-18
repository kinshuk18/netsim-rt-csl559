"""
NetSim-RT Sandboxed Custom Policy Execution Engine
CSL559 Computer Systems Design - IIT Bhilai
"""

import ast
import multiprocessing as mp
import resource
import time
from collections import deque
from typing import Dict, Any, List, Optional, Tuple

from engine.models import Request, SimulationConfig, SimulationResult
from engine.policies.base import BaseSchedulingPolicy, register_policy
from engine.simulator import Simulator

FORBIDDEN_BUILTINS = {
    "open", "eval", "exec", "compile", "__import__", "getattr", "setattr",
    "delattr", "globals", "locals", "vars", "input", "breakpoint", "help",
    "exit", "quit"
}

POLICY_TEMPLATES = {
    "sjf_custom": {
        "name": "Shortest Job First (Custom)",
        "description": "Selects the pending request with the minimum service time.",
        "code": """def select_next(queue, now, state):
    if not queue:
        return 0
    best_idx = 0
    best_st = queue[0]['service_time']
    for i in range(1, len(queue)):
        if queue[i]['service_time'] < best_st:
            best_st = queue[i]['service_time']
            best_idx = i
    return best_idx
"""
    },
    "priority_custom": {
        "name": "Class Priority (Book > Browse)",
        "description": "Scans queue for dynamic 'book' transactions first, falling back to browse.",
        "code": """def select_next(queue, now, state):
    if not queue:
        return 0
    for i, req in enumerate(queue):
        if req.get('req_class') == 'book':
            return i
    return 0
"""
    },
    "aging_custom": {
        "name": "Anti-Starvation Aging",
        "description": "Combines wait time and service time to prevent long requests from starving.",
        "code": """def select_next(queue, now, state):
    if not queue:
        return 0
    best_idx = 0
    best_score = -1.0
    for i, req in enumerate(queue):
        wait_time = max(0.0001, now - req['arrival_time'])
        score = wait_time / max(0.001, req['service_time'])
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx
"""
    }
}


def validate_code_ast(code: str) -> Tuple[bool, Optional[str]]:
    """
    Validates user python code against security allowlist:
    - No import statements
    - No dunder (starts with _) attributes or methods
    - No execution of forbidden builtins (open, exec, eval, getattr, etc.)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax Error: {e.msg} at line {e.lineno}"

    has_select_next = False

    for node in ast.walk(tree):
        # Disallow imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, "Security Violation: Imports are strictly forbidden."

        # Disallow dunder attributes
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                return False, f"Security Violation: Access to private attribute '{node.attr}' is forbidden."

        # Disallow forbidden calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_BUILTINS:
                    return False, f"Security Violation: Calling builtin '{node.func.id}' is forbidden."

        # Check function definition
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("_"):
                return False, f"Security Violation: Function name '{node.name}' cannot start with underscore."
            if node.name == "select_next":
                has_select_next = True

    if not has_select_next:
        return False, "Missing required function: def select_next(queue, now, state):"

    return True, None


@register_policy("custom_script")
class CustomScriptPolicy(BaseSchedulingPolicy):
    """Wraps user-defined python select_next logic in simulation queue."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.queue: deque[Request] = deque()
        self.state: Dict[str, Any] = {}
        self.user_func = kwargs.get("user_func", None)

    def add_request(self, request: Request, now: float) -> bool:
        self.queue.append(request)
        return True

    def select_next(self, now: float) -> Optional[Request]:
        if not self.queue:
            return None
        if self.user_func is None or len(self.queue) == 1:
            return self.queue.popleft()

        # Build serialized lightweight queue representation
        q_view = [
            {
                "id": r.id,
                "arrival_time": r.arrival_time,
                "service_time": r.service_time,
                "remaining_time": r.remaining_time,
                "req_class": r.req_class,
                "priority": r.priority,
                "bytes": r.bytes,
            }
            for r in self.queue
        ]

        try:
            chosen_idx = self.user_func(q_view, now, self.state)
            if isinstance(chosen_idx, int) and 0 <= chosen_idx < len(self.queue):
                req = self.queue[chosen_idx]
                del self.queue[chosen_idx]
                return req
        except Exception:
            pass

        return self.queue.popleft()

    def queue_length(self) -> int:
        return len(self.queue)


def _child_worker(code: str, config_dict: Dict[str, Any], conn):
    """Runs simulation in child process with hard resource limits."""
    try:
        # Enforce POSIX resource limits (CPU seconds = 3s, memory = 512MB)
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        mem_bytes = 512 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

        # Safe global execution environment
        safe_globals = {
            "__builtins__": {
                "min": min, "max": max, "len": len, "range": range,
                "enumerate": enumerate, "abs": abs, "round": round,
                "int": int, "float": float, "bool": bool, "sum": sum,
                "sorted": sorted, "dict": dict, "list": list
            }
        }
        loc: Dict[str, Any] = {}
        exec(code, safe_globals, loc)
        user_fn = loc.get("select_next")

        config = SimulationConfig(**config_dict)
        sim = Simulator(config)
        # Inject custom policy
        sim.policy = CustomScriptPolicy(user_func=user_fn)
        res = sim.run()
        conn.send(("OK", res.to_dict()))
    except Exception as e:
        conn.send(("ERROR", str(e)))
    finally:
        conn.close()


def run_sandboxed_simulation(
    code: str,
    config_dict: Dict[str, Any],
    timeout_s: float = 5.0
) -> Dict[str, Any]:
    """
    Executes user policy code in an isolated child process with setrlimit and timeout.
    Falls back gracefully to FCFS if validation, timeout, or runtime error occurs.
    """
    valid, err_msg = validate_code_ast(code)
    if not valid:
        # Fall back to FCFS with warning
        config = SimulationConfig(**config_dict)
        config.policy = "fcfs"
        res = Simulator(config).run()
        d = res.to_dict()
        d["custom_policy_status"] = "rejected"
        d["custom_policy_error"] = err_msg
        d["fallback"] = "fcfs"
        return d

    parent_conn, child_conn = mp.Pipe()
    p = mp.Process(target=_child_worker, args=(code, config_dict, child_conn))
    p.start()
    p.join(timeout=timeout_s)

    if p.is_alive():
        p.terminate()
        p.join(timeout=0.5)
        # Timeout occurred: fall back to FCFS
        config = SimulationConfig(**config_dict)
        config.policy = "fcfs"
        res = Simulator(config).run()
        d = res.to_dict()
        d["custom_policy_status"] = "timeout"
        d["custom_policy_error"] = f"Execution exceeded wall-clock limit of {timeout_s}s. Reverted to FCFS."
        d["fallback"] = "fcfs"
        return d

    if parent_conn.poll():
        status, payload = parent_conn.recv()
        if status == "OK":
            payload["custom_policy_status"] = "success"
            payload["policy"] = "custom_script"
            return payload
        else:
            # Runtime error in user code: fall back to FCFS
            config = SimulationConfig(**config_dict)
            config.policy = "fcfs"
            res = Simulator(config).run()
            d = res.to_dict()
            d["custom_policy_status"] = "error"
            d["custom_policy_error"] = f"Runtime error in user code: {payload}. Reverted to FCFS."
            d["fallback"] = "fcfs"
            return d

    # Pipe empty
    config = SimulationConfig(**config_dict)
    config.policy = "fcfs"
    res = Simulator(config).run()
    d = res.to_dict()
    d["custom_policy_status"] = "failed"
    d["custom_policy_error"] = "Process terminated unexpectedly. Reverted to FCFS."
    d["fallback"] = "fcfs"
    return d
