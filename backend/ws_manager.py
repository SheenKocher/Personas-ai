"""
WebSocket connection manager for real-time run updates.
Broadcasts step progress to all connected frontend clients.
"""

import asyncio
import json
import logging
from typing import Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class RunBroadcaster:
    """Manages WebSocket connections and broadcasts run updates."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info("WS client connected (%d total)", len(self._connections))

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)
        logger.info("WS client disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, message: dict):
        """Send a JSON message to all connected clients."""
        if not self._connections:
            return
        payload = json.dumps(message, default=str)
        dead = []
        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.discard(ws)

    async def send_step_update(
        self, batch_id: str, run_id: str, persona: dict,
        step_index: int, max_steps: int, action: dict,
        reasoning: str, screenshot_url: str, location: str,
        outcome: str, frustration: int, frustration_budget: int,
    ):
        await self.broadcast({
            "type": "step_update",
            "batch_id": batch_id or "",
            "run_id": run_id,
            "persona_name": persona.get("name", "?"),
            "persona_accent": persona.get("accent_color", "#818CF8"),
            "persona_disability": persona.get("disability"),
            "persona_perception": persona.get("perception_mode", "full"),
            "step_index": step_index,
            "max_steps": max_steps,
            "action": action,
            "reasoning": reasoning[:300],
            "screenshot_url": screenshot_url,
            "location": location,
            "outcome": outcome,
            "frustration": frustration,
            "frustration_budget": frustration_budget,
        })

    async def send_run_complete(
        self, batch_id: str, run_id: str, persona_name: str,
        outcome: str, total_steps: int, total_signals: int,
    ):
        await self.broadcast({
            "type": "run_complete",
            "batch_id": batch_id or "",
            "run_id": run_id,
            "persona_name": persona_name,
            "outcome": outcome,
            "total_steps": total_steps,
            "total_signals": total_signals,
        })

    async def send_batch_started(self, batch_id: str, personas: list, target_url: str, goal: str):
        await self.broadcast({
            "type": "batch_started",
            "batch_id": batch_id,
            "target_url": target_url,
            "goal": goal,
            "personas": [
                {
                    "name": p.get("name", "?"),
                    "accent_color": p.get("accent_color", "#818CF8"),
                    "disability": p.get("disability"),
                    "perception_mode": p.get("perception_mode", "full"),
                }
                for p in personas
            ],
        })


# Singleton instance
broadcaster = RunBroadcaster()
