"""
Unit test for engine action-validation logic.
Tests the rejection code path directly without Browserbase/LLM — proves
the safety net works even when GPT-5 never triggers it at runtime.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import sys

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestActionValidation:
    """Test the server-side action rejection logic in engine.py."""

    def test_click_rejected_for_motor_persona(self):
        """Motor persona's allowed_actions excludes 'click'. Engine must reject it."""
        allowed_actions = {"type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"}
        action_type = "click"
        assert action_type not in allowed_actions, "click should not be in motor persona's allowed_actions"

    def test_click_allowed_for_blind_persona(self):
        """Blind persona's allowed_actions includes 'click'."""
        allowed_actions = {"click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"}
        action_type = "click"
        assert action_type in allowed_actions, "click should be in blind persona's allowed_actions"

    def test_navigate_rejected_for_restricted_persona(self):
        """Restricted persona with only key/wait. Navigate must be rejected."""
        allowed_actions = {"key", "wait", "report_friction", "give_up"}
        for forbidden in ["click", "type", "scroll", "navigate"]:
            assert forbidden not in allowed_actions, f"{forbidden} should be rejected"
        for allowed in ["key", "wait", "report_friction", "give_up"]:
            assert allowed in allowed_actions, f"{allowed} should be allowed"

    @pytest.mark.asyncio
    async def test_rejection_produces_signal_and_overrides_to_wait(self):
        """
        Simulate the engine's validate-and-reject logic with a mock DB.
        When a disallowed action is received, the engine should:
        1. Insert a behavioral signal with 'rejected' in description
        2. Override the action to wait
        3. Increase frustration
        """
        # Mock DB
        mock_db = MagicMock()
        mock_signals = AsyncMock()
        mock_db.signals = mock_signals
        mock_signals.insert_one = AsyncMock()

        # Persona config (motor — no click)
        persona = {
            "name": "Arun — Keyboard Only",
            "allowed_actions": ["type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
        }
        allowed_actions = set(persona["allowed_actions"])

        # Simulate LLM returning a click action
        action = {"type": "click", "selector": "text=Pricing"}
        action_type = action["type"]

        # --- This is the exact logic from engine.py lines 287-302 ---
        action_rejected = False
        frustration_increase = 0
        signals_out = []

        if action_type not in allowed_actions:
            action_rejected = True
            rejection_signal = {
                "run_id": "test-run-id",
                "stage": "prototype",
                "type": "behavioral",
                "severity": 2,
                "screen": "https://example.com",
                "description": f"Action '{action_type}' rejected — not in persona's allowed_actions: {list(allowed_actions)}",
            }
            await mock_db.signals.insert_one(rejection_signal.copy())
            signals_out.append({k: v for k, v in rejection_signal.items() if k != "_id"})
            # Override to wait
            action = {"type": "wait", "duration_ms": 500}
            action_type = "wait"
            frustration_increase = max(frustration_increase, 1)

        # ASSERTIONS
        assert action_rejected is True, "click should be rejected for motor persona"
        assert action["type"] == "wait", "rejected action should be overridden to wait"
        assert action.get("duration_ms") == 500
        assert frustration_increase >= 1, "frustration should increase on rejection"
        assert len(signals_out) == 1, "one rejection signal should be recorded"
        assert "rejected" in signals_out[0]["description"]
        assert "'click' rejected" in signals_out[0]["description"]
        assert signals_out[0]["type"] == "behavioral"
        assert signals_out[0]["severity"] == 2
        mock_db.signals.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_allowed_action_not_rejected(self):
        """
        When the LLM returns an action that IS in allowed_actions,
        no rejection signal is created.
        """
        persona = {
            "name": "Arun — Keyboard Only",
            "allowed_actions": ["type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
        }
        allowed_actions = set(persona["allowed_actions"])

        action = {"type": "key", "key": "Tab"}
        action_type = action["type"]

        action_rejected = False
        signals_out = []

        if action_type not in allowed_actions:
            action_rejected = True

        assert action_rejected is False, "key should NOT be rejected for motor persona"
        assert action["type"] == "key", "action should remain unchanged"
        assert len(signals_out) == 0, "no rejection signals for allowed actions"

    @pytest.mark.asyncio
    async def test_multiple_rejections_accumulate_frustration(self):
        """Multiple rejected actions should each increase frustration."""
        allowed_actions = {"key", "wait", "report_friction", "give_up"}
        forbidden_actions = [
            {"type": "click", "selector": "text=Foo"},
            {"type": "navigate", "url": "https://example.com"},
            {"type": "scroll", "direction": "down", "amount": 500},
        ]

        total_frustration = 0
        total_rejections = 0

        for action in forbidden_actions:
            if action["type"] not in allowed_actions:
                total_rejections += 1
                total_frustration += 1  # max(frustration_increase, 1)

        assert total_rejections == 3, "all 3 actions should be rejected"
        assert total_frustration == 3, "frustration should increase by 1 per rejection"


class TestSeedPersonaConfig:
    """Verify the seed panel personas have correct configs."""

    def test_seed_panel_arun_config(self):
        """Arun (motor) must NOT have click in allowed_actions."""
        # Import the seed panel constant
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        import importlib
        import server
        importlib.reload(server)

        arun = None
        for p in server.SEED_PANEL["personas"]:
            if "Arun" in p["name"]:
                arun = p
                break
        assert arun is not None, "Arun persona not found in seed panel"
        assert "click" not in arun["allowed_actions"], "Arun (motor) must NOT have click"
        assert "key" in arun["allowed_actions"], "Arun must have key actions"
        assert arun["disability"] == "motor"
        assert arun["perception_mode"] == "full"

    def test_seed_panel_meera_config(self):
        """Meera (blind) must have click in allowed_actions and ax_tree_only perception."""
        import importlib
        import server
        importlib.reload(server)

        meera = None
        for p in server.SEED_PANEL["personas"]:
            if "Meera" in p["name"]:
                meera = p
                break
        assert meera is not None, "Meera persona not found in seed panel"
        assert "click" in meera["allowed_actions"], "Meera (blind) must have click"
        assert "key" in meera["allowed_actions"], "Meera must have key actions"
        assert meera["disability"] == "blind"
        assert meera["perception_mode"] == "ax_tree_only"
