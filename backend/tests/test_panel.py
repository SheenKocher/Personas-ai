"""Backend tests for parallel panel engine + server-side action enforcement.

Focus:
- GET /api/engine/batch/{batch_id} shape for the pre-completed batch.
- Verify Arun (motor / keyboard-only) has NO 'click' in allowed_actions.
- Verify Meera (blind / screen-reader) HAS 'click' and perception_mode=ax_tree_only.
- Verify Arun's pre-completed run has ONLY key-based actions (no click).
- Verify Meera's pre-completed run allows click actions.
- SERVER-SIDE ENFORCEMENT: start ONE real engine run with a heavily restricted
  persona (allowed_actions=['key','wait','report_friction','give_up']). Poll
  until complete; verify at least one 'rejected' behavioral signal and that
  rejected actions were replaced by wait.
- Regression: /api/health, /api/persona-panels.

Cost note: exactly ONE POST /api/engine/run is issued (the enforcement test).
Everything else is read-only GETs against already-persisted data.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

# Pre-completed batch + runs seeded by the main agent — read-only.
COMPLETED_BATCH_ID = "ddb4c7d5-4bd8-402d-86ac-94c43ee51169"
ARUN_RUN_ID = "6a93590d9746e27fc9e34414"    # keyboard-only, key actions only
MEERA_RUN_ID = "6a93590d9746e27fc9e34415"   # screen-reader, click allowed


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# GET /api/engine/batch/{batch_id}
# ---------------------------------------------------------------------------

class TestCompletedBatch:
    def test_batch_shape_and_three_completed_runs(self, client):
        r = client.get(f"{API}/engine/batch/{COMPLETED_BATCH_ID}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()

        assert data["batch_id"] == COMPLETED_BATCH_ID
        assert data["total_runs"] == 3, f"expected 3 runs, got {data.get('total_runs')}"
        assert data["all_done"] is True
        assert data["still_running"] is False

        runs = data["runs"]
        assert isinstance(runs, list) and len(runs) == 3

        names = {r_.get("persona_name", "") for r_ in runs}
        # Personas expected: Priya, Arun, Meera (allowing '—' suffix)
        assert any(n.startswith("Priya") for n in names), f"Priya missing: {names}"
        assert any(n.startswith("Arun") for n in names), f"Arun missing: {names}"
        assert any(n.startswith("Meera") for n in names), f"Meera missing: {names}"

        for run in runs:
            assert run["outcome"] != "in_progress", f"run {run['run_id']} still in_progress"
            assert run["outcome"] in ("success", "gave_up", "max_steps")
            # summary counts present on completed runs
            assert "total_steps" in run
            assert "total_signals" in run
            assert "rejected_actions" in run, "rejected_actions missing from batch summary"
            assert isinstance(run["rejected_actions"], int)
            assert run.get("started_at") and run.get("ended_at")

    def test_batch_nonexistent_returns_404(self, client):
        r = client.get(f"{API}/engine/batch/does-not-exist-batch-id", timeout=15)
        assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# Persona panel seed content — Arun/Meera constraints
# ---------------------------------------------------------------------------

class TestSeedPersonaConstraints:
    @pytest.fixture(scope="class")
    def seed_personas(self, client):
        panels = client.get(f"{API}/persona-panels", timeout=15).json()
        seed = next((p for p in panels if p.get("client_ref") == "seed-demo"), None)
        assert seed is not None, "seed panel missing"
        return seed["personas"]

    def test_arun_has_no_click(self, seed_personas):
        arun = next((p for p in seed_personas if p.get("name", "").startswith("Arun")), None)
        assert arun is not None, "Arun persona missing from seed panel"
        assert arun.get("disability") == "motor"
        actions = arun.get("allowed_actions") or []
        assert "click" not in actions, f"Arun (motor) must NOT have 'click' in allowed_actions: {actions}"
        # sanity: he should still have key/type/etc.
        assert "key" in actions and "type" in actions

    def test_meera_has_click_and_ax_tree_only(self, seed_personas):
        meera = next((p for p in seed_personas if p.get("name", "").startswith("Meera")), None)
        assert meera is not None, "Meera persona missing from seed panel"
        assert meera.get("disability") == "blind"
        actions = meera.get("allowed_actions") or []
        assert "click" in actions, f"Meera (blind) MUST have 'click' in allowed_actions: {actions}"
        assert meera.get("perception_mode") == "ax_tree_only", (
            f"Meera perception_mode should be ax_tree_only, got {meera.get('perception_mode')}"
        )


# ---------------------------------------------------------------------------
# Pre-completed Arun / Meera runs — action-type composition
# ---------------------------------------------------------------------------

class TestArunAndMeeraRuns:
    def test_arun_run_only_key_actions(self, client):
        r = client.get(f"{API}/engine/run/{ARUN_RUN_ID}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["still_running"] is False
        assert data["outcome"] != "in_progress"

        persona = data.get("persona") or {}
        assert persona.get("name", "").startswith("Arun"), f"expected Arun, got {persona.get('name')}"
        assert "click" not in (persona.get("allowed_actions") or [])

        steps = data.get("steps") or []
        assert len(steps) > 0, "Arun run has no steps"

        # Zero click actions among Arun's steps
        click_steps = [s for s in steps if (s.get("action") or {}).get("type") == "click"]
        assert len(click_steps) == 0, (
            f"Arun (keyboard-only) has {len(click_steps)} click actions — should be 0"
        )
        # And he should have used 'key' at least once (that's how he navigates)
        key_steps = [s for s in steps if (s.get("action") or {}).get("type") == "key"]
        assert len(key_steps) >= 1, "Arun should have at least one 'key' action"

    def test_meera_run_allows_click(self, client):
        r = client.get(f"{API}/engine/run/{MEERA_RUN_ID}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["still_running"] is False
        assert data["outcome"] != "in_progress"

        persona = data.get("persona") or {}
        assert persona.get("name", "").startswith("Meera"), f"expected Meera, got {persona.get('name')}"
        assert "click" in (persona.get("allowed_actions") or [])
        assert persona.get("perception_mode") == "ax_tree_only"

        steps = data.get("steps") or []
        assert len(steps) > 0, "Meera run has no steps"
        click_steps = [s for s in steps if (s.get("action") or {}).get("type") == "click"]
        # Meera CAN click; expect at least one click across her run
        assert len(click_steps) >= 1, (
            f"Meera (screen-reader, click allowed) should have executed at least one click; "
            f"got {len(click_steps)} across {len(steps)} steps"
        )


# ---------------------------------------------------------------------------
# SERVER-SIDE ENFORCEMENT: rejected actions logged, replaced by wait
# ---------------------------------------------------------------------------

class TestServerSideActionEnforcement:
    """Start ONE real engine run with a heavily restricted persona and verify
    the engine's validation layer (engine.py '3. VALIDATE') rejects disallowed
    actions server-side (not just via prompt).

    Restricted persona: only ['key','wait','report_friction','give_up'].
    The LLM will almost certainly try click/type/scroll/navigate — those must
    be rejected and logged as behavioral signals with 'rejected' in the
    description; the action must be overridden to wait.
    """

    def test_restricted_persona_rejects_disallowed_actions(self, client):
        restricted_persona = {
            "name": "TEST_Restricted Bot",
            "traits": "test persona with severely restricted actions",
            "disability": None,
            "allowed_actions": ["key", "wait", "report_friction", "give_up"],
            "perception_mode": "full",
            "frustration_budget": 10,
            "tolerance_rules": [],
            "temperature": 0.6,
        }
        payload = {
            "target_url": "https://tier3.college",
            "goal": "TEST_enforcement — try to click things you cannot click",
            "stage": "prototype",
            "persona": restricted_persona,
        }
        r = client.post(f"{API}/engine/run", json=payload, timeout=20)
        # POST returns 202 (background pattern)
        assert r.status_code in (200, 202), r.text
        data = r.json()
        run_id = data.get("run_id")
        assert run_id and len(run_id) == 24
        assert data.get("status") == "started"

        # Poll every 15s up to 180s
        deadline = time.time() + 180
        final = None
        while time.time() < deadline:
            time.sleep(15)
            rr = client.get(f"{API}/engine/run/{run_id}", timeout=30)
            assert rr.status_code == 200, rr.text
            d = rr.json()
            if d.get("outcome") in ("success", "gave_up", "max_steps") and d.get("still_running") is False:
                final = d
                break
        assert final is not None, f"Engine run {run_id} did not complete within 180s"

        steps = final.get("steps") or []
        signals = final.get("signals") or []
        assert len(steps) > 0, "restricted run produced no steps"

        # (a) at least one behavioral signal with 'rejected' in description
        rejected_signals = [
            s for s in signals
            if s.get("type") == "behavioral" and "rejected" in (s.get("description") or "").lower()
        ]
        assert len(rejected_signals) >= 1, (
            f"expected >=1 behavioral 'rejected' signal, got 0. All signals: {signals}"
        )
        # signal should mention the disallowed action name or the allowed list
        sample = rejected_signals[0]
        assert 1 <= sample.get("severity", 0) <= 5

        # (b) verify a rejected action was replaced with wait
        # Fetch full steps via /api/steps to inspect action_rejected flag
        sr = client.get(f"{API}/steps", params={"run_id": run_id, "limit": 200}, timeout=30)
        assert sr.status_code == 200, sr.text
        full_steps = sr.json()
        # after rejection the persisted action.type should be 'wait'
        # (engine overrides action = {"type": "wait", "duration_ms": 500})
        wait_actions_from_rejection = [
            s for s in full_steps
            if (s.get("action") or {}).get("type") == "wait"
            and (s.get("action") or {}).get("duration_ms") == 500
        ]
        # Not a hard equality (LLM might legitimately also emit wait), but with
        # our restricted persona at least one rejection => at least one such wait.
        assert len(wait_actions_from_rejection) >= 1, (
            "expected at least one wait(duration_ms=500) marker from a rejection override"
        )

        # All executed step action types (after override) must be within the
        # allowed set — the engine must not persist disallowed actions.
        allowed = set(restricted_persona["allowed_actions"])
        offenders = [
            s for s in full_steps
            if (s.get("action") or {}).get("type") not in allowed
        ]
        assert len(offenders) == 0, (
            f"engine persisted {len(offenders)} steps with disallowed action types "
            f"(post-override): {[(s.get('action') or {}).get('type') for s in offenders[:5]]}"
        )


# ---------------------------------------------------------------------------
# Regression: previous endpoints still work
# ---------------------------------------------------------------------------

class TestRegression:
    def test_health(self, client):
        r = client.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_persona_panels_list(self, client):
        r = client.get(f"{API}/persona-panels", timeout=15)
        assert r.status_code == 200
        panels = r.json()
        assert isinstance(panels, list) and len(panels) >= 1
        assert any(p.get("client_ref") == "seed-demo" for p in panels)
