"""Backend tests for Prototype Stage: screen graphs CRUD, mockup upload, and prototype run."""
import base64
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://synthetic-tester.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EXISTING_GRAPH_ID = "6a9364ae6d16f9e2217e4aa7"

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture(scope="module")
def created_graph_id():
    """Create a graph and yield its ID for CRUD tests, delete after."""
    payload = {
        "name": "TEST_ProtoFlow",
        "screens": [
            {"id": "home", "name": "Home", "image_url": ""},
            {"id": "pricing", "name": "Pricing", "image_url": ""},
        ],
        "transitions": [{"from_screen": "home", "label": "click Pricing", "to_screen": "pricing"}],
        "start_screen": "home",
    }
    r = requests.post(f"{API}/prototype/graphs", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    yield gid
    try:
        requests.delete(f"{API}/prototype/graphs/{gid}", timeout=10)
    except Exception:
        pass


# --- Health / regression checks ---
def test_health():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_persona_panels_list():
    r = requests.get(f"{API}/persona-panels", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_runs_list():
    r = requests.get(f"{API}/runs?limit=5", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# --- Screen Graph CRUD ---
def test_create_graph(created_graph_id):
    # Verify by GET
    r = requests.get(f"{API}/prototype/graphs/{created_graph_id}", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "TEST_ProtoFlow"
    assert d["start_screen"] == "home"
    assert len(d["screens"]) == 2
    assert len(d["transitions"]) == 1
    assert d["id"] == created_graph_id


def test_list_graphs(created_graph_id):
    r = requests.get(f"{API}/prototype/graphs", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    ids = [g["id"] for g in data]
    assert created_graph_id in ids


def test_patch_graph(created_graph_id):
    r = requests.patch(
        f"{API}/prototype/graphs/{created_graph_id}",
        json={"name": "TEST_ProtoFlow_Renamed"},
        timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "TEST_ProtoFlow_Renamed"

    # Verify persisted
    g = requests.get(f"{API}/prototype/graphs/{created_graph_id}", timeout=10).json()
    assert g["name"] == "TEST_ProtoFlow_Renamed"


def test_get_graph_invalid_id():
    r = requests.get(f"{API}/prototype/graphs/notavalidid", timeout=10)
    assert r.status_code == 400


def test_get_graph_not_found():
    r = requests.get(f"{API}/prototype/graphs/000000000000000000000000", timeout=10)
    assert r.status_code == 404


def test_existing_seeded_graph():
    """Verify the pre-existing graph mentioned in the task."""
    r = requests.get(f"{API}/prototype/graphs/{EXISTING_GRAPH_ID}", timeout=10)
    # It may not exist; skip if 404
    if r.status_code == 404:
        pytest.skip(f"Existing graph {EXISTING_GRAPH_ID} not present in DB")
    assert r.status_code == 200
    d = r.json()
    assert d["name"] == "Tier3 Pricing Flow"
    assert len(d["screens"]) == 3
    assert len(d["transitions"]) == 3
    assert d["start_screen"] == "homepage"


# --- Mockup Upload ---
def test_upload_mockup():
    files = {"file": ("test.png", io.BytesIO(PNG_1X1), "image/png")}
    r = requests.post(f"{API}/prototype/upload-mockup", files=files, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "url" in data
    assert data["url"].startswith("https://")
    assert "public_id" in data


# --- Prototype Run (202) ---
def test_prototype_run_returns_202(created_graph_id):
    body = {"graph_id": created_graph_id, "goal": "Find pricing", "concurrency": 1}
    r = requests.post(f"{API}/prototype/run", json=body, timeout=15)
    assert r.status_code == 202, r.text
    data = r.json()
    assert "batch_id" in data
    assert data["status"] == "started"
    assert data["stage"] == "prototype"
    assert data["persona_count"] >= 1
    assert isinstance(data["personas"], list)


def test_prototype_run_invalid_graph():
    r = requests.post(f"{API}/prototype/run", json={"graph_id": "bad", "goal": "x"}, timeout=10)
    assert r.status_code == 400


def test_prototype_run_not_found_graph():
    r = requests.post(
        f"{API}/prototype/run",
        json={"graph_id": "000000000000000000000000", "goal": "x"},
        timeout=10,
    )
    assert r.status_code == 404


# --- DELETE (run last) ---
def test_delete_graph():
    """Create then delete a graph, verify 404 after."""
    payload = {"name": "TEST_ToDelete", "screens": [], "transitions": [], "start_screen": ""}
    r = requests.post(f"{API}/prototype/graphs", json=payload, timeout=10)
    assert r.status_code == 200
    gid = r.json()["id"]

    r = requests.delete(f"{API}/prototype/graphs/{gid}", timeout=10)
    assert r.status_code == 200
    assert r.json()["deleted"] is True

    r = requests.get(f"{API}/prototype/graphs/{gid}", timeout=10)
    assert r.status_code == 404
