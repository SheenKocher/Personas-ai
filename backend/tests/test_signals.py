"""Backend tests for signal derivation and aggregation endpoints."""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read from frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

PRIYA = "6a93590d9746e27fc9e34413"
ARUN = "6a93590d9746e27fc9e34414"
MEERA = "6a93590d9746e27fc9e34415"
BATCH_ID = "ddb4c7d5-4bd8-402d-86ac-94c43ee51169"
FRESH_RUN_1 = "6a9343fa6fc2884898105256"
FRESH_RUN_2 = "6a9344228af8dbf43bc0fe19"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Sanity: previous endpoints still work ---

class TestSanity:
    def test_health(self, client):
        r = client.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200

    def test_persona_panels(self, client):
        r = client.get(f"{BASE_URL}/api/persona-panels", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


# --- Derivation error cases ---

class TestDeriveErrors:
    def test_derive_invalid_id(self, client):
        r = client.post(f"{BASE_URL}/api/signals/derive/not-a-valid-id", timeout=15)
        assert r.status_code == 400, r.text

    def test_derive_nonexistent_id(self, client):
        # Valid ObjectId format but not in DB
        r = client.post(f"{BASE_URL}/api/signals/derive/000000000000000000000000", timeout=15)
        assert r.status_code == 404, r.text


# --- Aggregation error cases ---

class TestAggregateErrors:
    def test_aggregate_no_params(self, client):
        r = client.get(f"{BASE_URL}/api/signals/aggregate", timeout=15)
        assert r.status_code == 400, r.text


# --- Aggregation happy path ---

class TestAggregationBatch:
    @pytest.fixture(scope="class")
    def agg(self, client):
        r = client.get(
            f"{BASE_URL}/api/signals/aggregate",
            params={"batch_id": BATCH_ID},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def test_structure(self, agg):
        assert "screens" in agg
        assert "total_screens" in agg
        assert agg["batch_id"] == BATCH_ID
        assert isinstance(agg["screens"], list)
        assert len(agg["screens"]) > 0, "Expected at least one screen with signals"

    def test_screen_fields(self, agg):
        s = agg["screens"][0]
        for key in [
            "screen", "weighted_score", "total_signals", "max_severity",
            "affected_personas", "by_type", "by_source", "signals",
        ]:
            assert key in s, f"Missing key {key} in screen: {s}"

    def test_sorted_descending(self, agg):
        scores = [s["weighted_score"] for s in agg["screens"]]
        assert scores == sorted(scores, reverse=True), f"Not sorted desc: {scores}"

    def test_pricing_top(self, agg):
        top = agg["screens"][0]
        assert "/pricing" in top["screen"], (
            f"Expected /pricing at top, got {top['screen']} "
            f"(all screens: {[s['screen'] for s in agg['screens']]})"
        )


# --- Aggregation via run_ids (comma-separated) ---

class TestAggregationRunIds:
    def test_run_ids_csv(self, client):
        r = client.get(
            f"{BASE_URL}/api/signals/aggregate",
            params={"run_ids": f"{PRIYA},{ARUN}"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "screens" in data
        # Should have some signals — Arun has keyboard_dead_end at minimum
        assert data["total_screens"] > 0


# --- Verify specific signals in existing derived data ---

def _get_agg_for_run(client, run_id):
    """Use aggregate endpoint (which returns by_source) to inspect per-run signals."""
    r = client.get(
        f"{BASE_URL}/api/signals/aggregate",
        params={"run_ids": run_id},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _collect_sources(agg):
    sources = {}
    for s in agg.get("screens", []):
        for src, cnt in (s.get("by_source") or {}).items():
            sources[src] = sources.get(src, 0) + cnt
    return sources


class TestSpecificSignals:
    def test_arun_keyboard_dead_end(self, client):
        agg = _get_agg_for_run(client, ARUN)
        sources = _collect_sources(agg)
        assert sources.get("keyboard_dead_end", 0) >= 1, (
            f"Expected keyboard_dead_end for Arun; sources found: {sources}"
        )

    def test_meera_dead_click(self, client):
        agg = _get_agg_for_run(client, MEERA)
        sources = _collect_sources(agg)
        assert sources.get("dead_click", 0) >= 1, (
            f"Expected dead_click for Meera; sources found: {sources}"
        )


# --- Derive on a fresh run (that hasn't been derived yet) ---

class TestDeriveFreshRun:
    def test_derive_fresh(self, client):
        # Try both fresh runs
        last_err = None
        for rid in [FRESH_RUN_1, FRESH_RUN_2]:
            r = client.post(f"{BASE_URL}/api/signals/derive/{rid}", timeout=60)
            if r.status_code == 200:
                data = r.json()
                assert "derived_count" in data
                assert "signals" in data
                assert data["run_id"] == rid
                # Signals list matches derived_count
                assert len(data["signals"]) == data["derived_count"]
                # Each signal must have required fields
                for s in data["signals"]:
                    assert "type" in s and s["type"] in ("objective", "behavioral")
                    assert "severity" in s and isinstance(s["severity"], int)
                    assert "source" in s
                    assert "description" in s
                return
            last_err = (r.status_code, r.text)
        pytest.fail(f"Neither fresh run derived: {last_err}")
