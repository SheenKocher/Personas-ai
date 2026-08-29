"""Backend API tests for synthetic user testing tool."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://synthetic-tester.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Health ----------
def test_health(client):
    r = client.get(f"{API}/health", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- Seed persona panel ----------
def test_seed_panel_exists(client):
    r = client.get(f"{API}/persona-panels", timeout=15)
    assert r.status_code == 200
    panels = r.json()
    assert isinstance(panels, list)
    seed = [p for p in panels if p.get("client_ref") == "seed-demo"]
    assert len(seed) >= 1, "Seed persona panel missing"
    personas = seed[0].get("personas", [])
    assert len(personas) == 5
    names = [p["name"].split(" ")[0] for p in personas]
    for expected in ["Priya", "Arun", "Meera", "Devika", "Farhan"]:
        assert expected in names
    # Meera screen reader check
    meera = next(p for p in personas if p["name"].startswith("Meera"))
    assert meera["perception_mode"] == "ax_tree_only"


# ---------- Runs CRUD ----------
class TestRunsCRUD:
    def test_create_list_get_patch_delete(self, client):
        payload = {
            "stage": "prototype",
            "target": "https://example.com",
            "goal": "TEST_ complete signup",
            "persona": {"name": "TEST_Persona"},
            "outcome": "in_progress",
        }
        r = client.post(f"{API}/runs", json=payload)
        assert r.status_code == 200, r.text
        run = r.json()
        assert run["target"] == payload["target"]
        assert run["stage"] == "prototype"
        assert run["outcome"] == "in_progress"
        assert run.get("id")
        rid = run["id"]

        # list
        r = client.get(f"{API}/runs")
        assert r.status_code == 200
        assert any(x["id"] == rid for x in r.json())

        # get by id
        r = client.get(f"{API}/runs/{rid}")
        assert r.status_code == 200
        assert r.json()["id"] == rid

        # patch
        r = client.patch(f"{API}/runs/{rid}", json={"outcome": "success"})
        assert r.status_code == 200
        assert r.json()["outcome"] == "success"

        # get again to verify persistence
        r = client.get(f"{API}/runs/{rid}")
        assert r.json()["outcome"] == "success"

        # delete
        r = client.delete(f"{API}/runs/{rid}")
        assert r.status_code == 200
        r = client.get(f"{API}/runs/{rid}")
        assert r.status_code == 404

    def test_invalid_stage_422(self, client):
        r = client.post(f"{API}/runs", json={"stage": "invalid_stage"})
        assert r.status_code == 422


# ---------- Steps CRUD ----------
class TestStepsCRUD:
    def test_step_flow(self, client):
        # create parent run
        run = client.post(f"{API}/runs", json={"stage": "runtime"}).json()
        rid = run["id"]

        step_payload = {
            "run_id": rid,
            "index": 1,
            "action": {"type": "click", "selector": "#btn"},
            "reasoning": "TEST_click submit",
        }
        r = client.post(f"{API}/steps", json=step_payload)
        assert r.status_code == 200, r.text
        step = r.json()
        sid = step["id"]
        assert step["run_id"] == rid
        assert step["reasoning"] == "TEST_click submit"

        # list filtered
        r = client.get(f"{API}/steps", params={"run_id": rid})
        assert r.status_code == 200
        assert any(s["id"] == sid for s in r.json())

        # get
        r = client.get(f"{API}/steps/{sid}")
        assert r.status_code == 200

        # delete
        r = client.delete(f"{API}/steps/{sid}")
        assert r.status_code == 200
        r = client.get(f"{API}/steps/{sid}")
        assert r.status_code == 404

        # cleanup run
        client.delete(f"{API}/runs/{rid}")


# ---------- Signals CRUD ----------
class TestSignalsCRUD:
    def test_signal_flow(self, client):
        run = client.post(f"{API}/runs", json={"stage": "prototype"}).json()
        rid = run["id"]
        payload = {
            "run_id": rid,
            "stage": "prototype",
            "type": "behavioral",
            "severity": 3,
            "screen": "checkout",
            "description": "TEST_hesitation",
        }
        r = client.post(f"{API}/signals", json=payload)
        assert r.status_code == 200, r.text
        sig = r.json()
        sid = sig["id"]
        assert sig["type"] == "behavioral"
        assert sig["severity"] == 3

        # invalid severity
        bad = dict(payload, severity=99)
        assert client.post(f"{API}/signals", json=bad).status_code == 422

        # list with filter
        r = client.get(f"{API}/signals", params={"run_id": rid, "severity_min": 2})
        assert r.status_code == 200
        assert any(s["id"] == sid for s in r.json())

        # get
        assert client.get(f"{API}/signals/{sid}").status_code == 200

        # delete
        assert client.delete(f"{API}/signals/{sid}").status_code == 200
        assert client.get(f"{API}/signals/{sid}").status_code == 404

        client.delete(f"{API}/runs/{rid}")


# ---------- Persona Panels CRUD ----------
class TestPanelsCRUD:
    def test_panel_flow(self, client):
        payload = {
            "client_ref": "TEST_project_x",
            "audience_description": "TEST_ audience",
            "composition": "focused",
            "personas": [{"name": "TEST_p1", "accent_color": "#fff"}],
        }
        r = client.post(f"{API}/persona-panels", json=payload)
        assert r.status_code == 200, r.text
        panel = r.json()
        pid = panel["id"]
        assert panel["client_ref"] == "TEST_project_x"
        assert panel["composition"] == "focused"

        # list
        r = client.get(f"{API}/persona-panels")
        assert any(p["id"] == pid for p in r.json())

        # get
        assert client.get(f"{API}/persona-panels/{pid}").status_code == 200

        # patch
        r = client.patch(f"{API}/persona-panels/{pid}", json={"composition": "broad"})
        assert r.status_code == 200
        assert r.json()["composition"] == "broad"

        # verify persistence
        r = client.get(f"{API}/persona-panels/{pid}")
        assert r.json()["composition"] == "broad"

        # delete
        assert client.delete(f"{API}/persona-panels/{pid}").status_code == 200
        assert client.get(f"{API}/persona-panels/{pid}").status_code == 404

    def test_delete_nonexistent(self, client):
        # 24-char valid ObjectId that shouldn't exist
        r = client.delete(f"{API}/persona-panels/507f1f77bcf86cd799439011")
        assert r.status_code == 404
