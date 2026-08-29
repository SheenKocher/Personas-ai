"""Backend tests for the Persona Engine endpoints.

Focus:
- POST /api/engine/run returns run_id + status:started immediately (no waiting).
- GET /api/engine/run/{run_id} for valid completed run: outcome, steps, signals.
- Invalid / nonexistent IDs => 400 / 404.
- Persona resolution paths (explicit persona / seed fallback / persona_panel_id).
- Previously-existing CRUD endpoints still work.

IMPORTANT: We do NOT wait for real engine runs to complete (they cost real
Browserbase + Cloudinary + LLM calls). We only assert the immediate response
shape, and then delete the created run doc from DB via DELETE /api/runs/{id}
so we don't leak in-progress entries. The background asyncio task will keep
running but that's fine — it will just fail to update a missing doc.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

# Completed run IDs seeded by the main agent (do NOT re-run these).
COMPLETED_RUN_ID = "6a9352683b24d270e9e8be86"      # 10 steps, 2 signals, gave_up
COMPLETED_RUN_ID_2 = "6a935131879ba779c87ac762"    # 12 steps


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# Completed run inspection
# ---------------------------------------------------------------------------

class TestCompletedEngineRun:
    def test_get_completed_run_full_shape(self, client):
        r = client.get(f"{API}/engine/run/{COMPLETED_RUN_ID}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()

        # basic shape
        assert data["run_id"] == COMPLETED_RUN_ID
        assert data["outcome"] == "gave_up"
        assert data["still_running"] is False
        assert data["stage"] in ("prototype", "runtime")
        assert data.get("target"), "target missing"
        assert data.get("goal"), "goal missing"
        assert data.get("started_at") and data.get("ended_at")
        assert data.get("browserbase_session_id"), "browserbase_session_id missing on completed run"

        # persona
        persona = data.get("persona") or {}
        assert persona.get("name", "").startswith("Priya"), f"expected Priya persona, got {persona.get('name')}"
        assert "allowed_actions" in persona and isinstance(persona["allowed_actions"], list)

        # steps
        steps = data.get("steps") or []
        assert data.get("total_steps") == 10, f"expected 10 steps, got {data.get('total_steps')}"
        assert len(steps) == 10
        indexes = [s["index"] for s in steps]
        assert indexes == sorted(indexes), "steps not sorted by index"
        allowed_types = {"click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"}
        for s in steps:
            act = s.get("action") or {}
            assert act.get("type") in allowed_types, f"unexpected action type: {act}"
            assert isinstance(s.get("reasoning", ""), str)
            # at least some should have screenshots (Cloudinary)
        with_shot = [s for s in steps if s.get("screenshot_before_url") or s.get("screenshot_after_url")]
        assert len(with_shot) >= 1, "no steps have Cloudinary screenshot URLs"
        for s in with_shot[:3]:
            url = s.get("screenshot_before_url") or s.get("screenshot_after_url")
            assert "res.cloudinary.com" in url, f"non-Cloudinary URL: {url}"

        # For a gave_up outcome the run ended either via explicit give_up action
        # or via exhausting the frustration budget (last friction report). Both are valid.
        assert steps[-1]["action"].get("type") in {"give_up", "report_friction"}, (
            f"unexpected last action for gave_up run: {steps[-1]['action']}"
        )

        # signals
        signals = data.get("signals") or []
        assert data.get("total_signals") == 2, f"expected 2 signals, got {data.get('total_signals')}"
        assert len(signals) == 2
        for sig in signals:
            assert sig.get("type") in ("objective", "behavioral", "reported")
            assert 1 <= sig.get("severity", 0) <= 5
            assert isinstance(sig.get("description", ""), str) and sig["description"]
        # sorted by severity desc
        sevs = [s["severity"] for s in signals]
        assert sevs == sorted(sevs, reverse=True)

    def test_second_completed_run_step_count(self, client):
        r = client.get(f"{API}/engine/run/{COMPLETED_RUN_ID_2}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("total_steps") == 12, f"expected 12 steps, got {data.get('total_steps')}"
        assert data["still_running"] is False


# ---------------------------------------------------------------------------
# Error handling on GET
# ---------------------------------------------------------------------------

class TestGetEngineRunErrors:
    def test_invalid_id_returns_400(self, client):
        r = client.get(f"{API}/engine/run/not-a-valid-id", timeout=15)
        assert r.status_code == 400, r.text

    def test_nonexistent_valid_id_returns_404(self, client):
        # syntactically valid 24-char ObjectId that shouldn't exist
        r = client.get(f"{API}/engine/run/507f1f77bcf86cd799439011", timeout=15)
        assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# POST /api/engine/run — immediate response shape only (no waiting)
# ---------------------------------------------------------------------------

def _cleanup_run(client, run_id):
    try:
        client.delete(f"{API}/runs/{run_id}", timeout=10)
    except Exception:
        pass


class TestPostEngineRunImmediate:
    def test_post_returns_run_id_immediately_seed_persona(self, client):
        payload = {
            "target_url": "https://tier3.college",
            "goal": "TEST_immediate response shape only",
            "stage": "prototype",
            # no persona => should fall back to seed panel first persona (Priya)
        }
        t0 = time.time()
        r = client.post(f"{API}/engine/run", json=payload, timeout=15)
        elapsed = time.time() - t0

        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "started"
        assert data.get("run_id"), "run_id missing"
        assert len(data["run_id"]) == 24, "run_id should be a 24-char ObjectId string"
        # must return quickly — the engine loop runs in background
        assert elapsed < 10, f"POST took {elapsed:.1f}s, expected fast return"

        run_id = data["run_id"]

        # Verify the run doc was created and stores Priya as the resolved persona
        rr = client.get(f"{API}/runs/{run_id}", timeout=15)
        assert rr.status_code == 200, rr.text
        run_doc = rr.json()
        assert run_doc["target"] == payload["target_url"]
        assert run_doc["goal"] == payload["goal"]
        assert run_doc["stage"] == "prototype"
        persona_name = (run_doc.get("persona") or {}).get("name", "")
        assert persona_name.startswith("Priya"), f"expected seed Priya persona, got '{persona_name}'"

        _cleanup_run(client, run_id)

    def test_post_with_persona_panel_id_resolves_persona(self, client):
        # find seed panel id
        panels = client.get(f"{API}/persona-panels", timeout=15).json()
        seed = next((p for p in panels if p.get("client_ref") == "seed-demo"), None)
        assert seed is not None, "seed panel missing"
        panel_id = seed["id"]

        payload = {
            "target_url": "https://tier3.college",
            "goal": "TEST_persona_panel_id resolution",
            "stage": "prototype",
            "persona_panel_id": panel_id,
            "persona_index": 2,  # Meera
        }
        r = client.post(f"{API}/engine/run", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        run_id = data["run_id"]

        run_doc = client.get(f"{API}/runs/{run_id}", timeout=15).json()
        persona_name = (run_doc.get("persona") or {}).get("name", "")
        assert persona_name.startswith("Meera"), f"expected Meera at index 2, got '{persona_name}'"

        _cleanup_run(client, run_id)

    def test_post_with_invalid_persona_panel_id(self, client):
        r = client.post(
            f"{API}/engine/run",
            json={"target_url": "https://tier3.college", "goal": "x", "persona_panel_id": "bad-id"},
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_post_with_nonexistent_persona_panel_id(self, client):
        r = client.post(
            f"{API}/engine/run",
            json={
                "target_url": "https://tier3.college",
                "goal": "x",
                "persona_panel_id": "507f1f77bcf86cd799439011",
            },
            timeout=15,
        )
        assert r.status_code == 404, r.text

    def test_post_with_persona_index_out_of_range(self, client):
        panels = client.get(f"{API}/persona-panels", timeout=15).json()
        seed = next(p for p in panels if p.get("client_ref") == "seed-demo")
        r = client.post(
            f"{API}/engine/run",
            json={
                "target_url": "https://tier3.college",
                "goal": "x",
                "persona_panel_id": seed["id"],
                "persona_index": 999,
            },
            timeout=15,
        )
        assert r.status_code == 400, r.text


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

    def test_runs_create_list_delete(self, client):
        payload = {
            "stage": "prototype",
            "target": "https://example.com",
            "goal": "TEST_regression",
        }
        r = client.post(f"{API}/runs", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]

        r = client.get(f"{API}/runs", timeout=15)
        assert r.status_code == 200
        assert any(x["id"] == rid for x in r.json())

        r = client.delete(f"{API}/runs/{rid}", timeout=15)
        assert r.status_code == 200
