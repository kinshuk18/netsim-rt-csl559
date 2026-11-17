"""
Base Scheduling Policy Interface and Factory Registry
CSL559 Computer Systems Design - IIT Bhilai
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Type
import heapq
from collections import deque
from engine.models import Request


class BaseSchedulingPolicy(ABC):
    """Abstract Strategy interface for request scheduling."""
    name: str = "base"
    is_preemptive: bool = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @abstractmethod
    def add_request(self, request: Request, now: float) -> bool:
        """Add newly arrived request into policy queue."""
        pass

    @abstractmethod
    def select_next(self, now: float) -> Optional[Request]:
        """Select next request to schedule onto an idle server."""
        pass

    @abstractmethod
    def queue_length(self) -> int:
        """Current number of requests waiting in queue."""
        pass

    def on_quantum_expired(self, request: Request, now: float) -> None:
        """Called by round-robin/MLFQ when a quantum expires with remaining service."""
        # Default behavior: re-add to queue
        self.add_request(request, now)

    def should_preempt(self, active_request: Request, new_request: Request) -> bool:
        """Determine if an incoming request should preempt currently executing request."""
        return False


_POLICY_REGISTRY: Dict[str, Type[BaseSchedulingPolicy]] = {}


def register_policy(name: str):
    """Decorator to register a scheduling policy implementation."""
    def decorator(cls: Type[BaseSchedulingPolicy]):
        _POLICY_REGISTRY[name.lower()] = cls
        cls.name = name.lower()
        return cls
    return decorator


def get_policy(name: str, **kwargs) -> BaseSchedulingPolicy:
    """Factory method to instantiate a registered policy."""
    key = name.lower()
    if key not in _POLICY_REGISTRY:
        raise ValueError(f"Unknown scheduling policy '{name}'. Available: {list(_POLICY_REGISTRY.keys())}")
    return _POLICY_REGISTRY[key](**kwargs)


def list_available_policies() -> List[str]:
    """Return all registered policy names."""
    return sorted(list(_POLICY_REGISTRY.keys()))
