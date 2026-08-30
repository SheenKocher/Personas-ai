"""
Per-run pause/resume control. A tiny shared registry (no DB, no circular imports)
so the engine loop (engine.py / prototype_engine.py) and the API layer (server.py)
can coordinate on the same asyncio.Event for a given run_id.

Event semantics: set() = running, clear() = paused. The engine loop awaits the
event at the top of each step, so a pause takes effect after the in-flight step
finishes, not mid-action.
"""

import asyncio

_events: dict = {}  # run_id -> asyncio.Event


def register(run_id: str) -> asyncio.Event:
    """Create (or return the existing) pause event for a run, defaulting to running."""
    ev = _events.get(run_id)
    if ev is None:
        ev = asyncio.Event()
        ev.set()
        _events[run_id] = ev
    return ev


def get(run_id: str):
    return _events.get(run_id)


def discard(run_id: str):
    _events.pop(run_id, None)


def pause(run_id: str) -> bool:
    ev = _events.get(run_id)
    if ev is None:
        return False
    ev.clear()
    return True


def resume(run_id: str) -> bool:
    ev = _events.get(run_id)
    if ev is None:
        return False
    ev.set()
    return True


def is_paused(run_id: str) -> bool:
    ev = _events.get(run_id)
    return ev is not None and not ev.is_set()
