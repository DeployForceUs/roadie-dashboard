"""Portable, side-effect-free watcher health decisions.

No macOS, Android, process or filesystem dependencies. Adapters supply
observations; this module only classifies them.
"""
from dataclasses import dataclass
from enum import Enum


class Health(str, Enum):
    STARTING = "starting"
    HEALTHY = "healthy"
    STALLED = "stalled"
    EXITED = "exited"
    INVALID = "invalid"


@dataclass(frozen=True)
class Observation:
    now: float
    started_at: float
    process_alive: bool
    heartbeat_at: float | None = None
    heartbeat_owner_matches: bool = False
    heartbeat_state: str = ""
    exit_code: int | None = None


def classify(observation: Observation, stale_seconds: float = 60) -> Health:
    """Fail closed on invalid clocks and mismatched heartbeat ownership.

    HEALTHY means a recent heartbeat only; it does NOT imply successful
    gig processing or Android application health.
    """
    o = observation
    if stale_seconds <= 0 or o.now < o.started_at:
        return Health.INVALID
    if not o.process_alive:
        return Health.EXITED
    if o.heartbeat_at is None:
        return Health.STARTING if o.now - o.started_at <= stale_seconds else Health.STALLED
    if o.heartbeat_at > o.now or o.heartbeat_at < o.started_at:
        return Health.INVALID
    if not o.heartbeat_owner_matches:
        return Health.INVALID
    return Health.HEALTHY if o.now - o.heartbeat_at <= stale_seconds else Health.STALLED
