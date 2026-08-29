"""Tests for the /api/spike/run endpoint - real Browserbase + Cloudinary calls.
Keep minimal (one spike call max) to avoid consuming external quota.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SPIKE_TIMEOUT = 180  # spike takes ~10-15s but allow slack for cold Browserbase sessions


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def spike_result(client):
    """Run the spike once and share the result across all tests in this module."""
    r = client.post(f"{API}/spike/run",
                    json={"target_url": "https://tier3.college"},
                    timeout=SPIKE_TIMEOUT)
    assert r.status_code == 200, f"Spike failed: {r.status_code} {r.text}"
    return r.json()


# ---------- Health check (pre-requisite) ----------
def test_health(client):
    r = client.get(f"{API}/health", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- Spike response shape ----------
class TestSpikeRun:
    def test_run_object(self, spike_result):
        run = spike_result.get("run")
        assert run is not None, "Missing 'run' in spike response"
        assert run.get("outcome") == "success", f"Expected outcome=success, got {run.get('outcome')}"
        assert run.get("target") == "https://tier3.college"
        assert run.get("browserbase_session_id"), "Missing browserbase_session_id"
        assert isinstance(run.get("browserbase_session_id"), str)
        assert run.get("id"), "Missing run id"

    def test_step_object(self, spike_result):
        step = spike_result.get("step")
        assert step is not None, "Missing 'step' in spike response"
        # Screenshot URL
        screenshot = step.get("screenshot_after_url")
        assert screenshot, "screenshot_after_url is empty"
        assert "res.cloudinary.com" in screenshot, f"Expected cloudinary URL, got {screenshot}"
        # AX tree with nodes
        ax_tree = step.get("accessibility_tree")
        assert ax_tree is not None
        node_count = ax_tree.get("node_count", 0)
        assert node_count > 0, f"Expected AX node_count > 0, got {node_count}"
        # arrays present
        assert isinstance(step.get("console_errors"), list)
        assert isinstance(step.get("failed_requests"), list)
        assert step.get("id"), "Missing step id"
        assert step.get("run_id") == spike_result["run"]["id"]

    def test_screenshot_url_reachable(self, spike_result):
        url = spike_result["step"]["screenshot_after_url"]
        r = requests.head(url, timeout=30, allow_redirects=True)
        assert r.status_code == 200, f"Screenshot not reachable: {r.status_code} {url}"


# ---------- Persistence in MongoDB ----------
class TestSpikePersistence:
    def test_run_persisted(self, client, spike_result):
        rid = spike_result["run"]["id"]
        r = client.get(f"{API}/runs", timeout=30)
        assert r.status_code == 200
        runs = r.json()
        assert any(x.get("id") == rid for x in runs), f"Run {rid} not found in /api/runs"

    def test_step_persisted(self, client, spike_result):
        sid = spike_result["step"]["id"]
        rid = spike_result["run"]["id"]
        r = client.get(f"{API}/steps", params={"run_id": rid}, timeout=30)
        assert r.status_code == 200
        steps = r.json()
        assert any(x.get("id") == sid for x in steps), f"Step {sid} not found in /api/steps"


# ---------- Default target (no body / empty body) ----------
# NOTE: Skipping running default-target spike to avoid a second real Browserbase session.
# Instead we verify the endpoint accepts an empty body without validation error by
# reading OpenAPI schema semantics: SpikeRunRequest.target_url has a default.
def test_default_target_declared():
    """Verify SpikeRunRequest has a default target_url so empty body is valid.
    Direct model import avoids consuming a second Browserbase session."""
    import sys
    sys.path.insert(0, "/app/backend")
    from server import SpikeRunRequest  # noqa: E402
    inst = SpikeRunRequest()
    assert inst.target_url == "https://tier3.college"
    # also verify explicit empty dict works
    inst2 = SpikeRunRequest(**{})
    assert inst2.target_url == "https://tier3.college"


# ---------- Regression: previous CRUD endpoints still work ----------
class TestRegression:
    def test_persona_panels_still_work(self, client):
        r = client.get(f"{API}/persona-panels", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_delete_run_still_works(self, client):
        r = client.post(f"{API}/runs", json={"stage": "prototype", "goal": "TEST_regression"}, timeout=15)
        assert r.status_code == 200
        rid = r.json()["id"]
        r = client.delete(f"{API}/runs/{rid}", timeout=15)
        assert r.status_code == 200
