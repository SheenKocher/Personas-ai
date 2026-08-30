"""Tests for the Stripe paywall integration."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://synthetic-tester.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Credits endpoint ---
class TestCredits:
    def test_get_credits_shape(self, api):
        r = api.get(f"{BASE_URL}/api/payments/credits", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("can_run", "free_used", "paid_credits", "total_runs", "price"):
            assert k in d, f"missing key {k}: {d}"
        assert isinstance(d["can_run"], bool)
        assert isinstance(d["free_used"], bool)
        assert isinstance(d["paid_credits"], int)
        assert isinstance(d["total_runs"], int)
        assert isinstance(d["price"], (int, float))

    def test_free_used_when_runs_exist(self, api):
        d = api.get(f"{BASE_URL}/api/payments/credits", timeout=30).json()
        # Task says 13+ runs already exist -> free_used True, can_run should equal paid_credits>0
        if d["total_runs"] > 0:
            assert d["free_used"] is True
            assert d["can_run"] == (d["paid_credits"] > 0)


# --- Run gates: 402 responses ---
class TestRunGates:
    def _blocked(self, api):
        d = api.get(f"{BASE_URL}/api/payments/credits", timeout=30).json()
        return not d["can_run"]

    def test_engine_run_402(self, api):
        if not self._blocked(api):
            pytest.skip("Credits available - cannot test 402")
        r = api.post(f"{BASE_URL}/api/engine/run",
                     json={"persona": {"name": "T", "goals": ["x"]}, "url": "https://example.com"},
                     timeout=30)
        assert r.status_code == 402, r.text
        assert "payment" in r.text.lower() or "credit" in r.text.lower()

    def test_engine_run_panel_402(self, api):
        if not self._blocked(api):
            pytest.skip("Credits available - cannot test 402")
        r = api.post(f"{BASE_URL}/api/engine/run-panel",
                     json={"persona_panel_id": "000000000000000000000000",
                           "url": "https://example.com"},
                     timeout=30)
        assert r.status_code == 402, r.text
        assert "payment" in r.text.lower() or "credit" in r.text.lower()

    def test_prototype_run_402(self, api):
        if not self._blocked(api):
            pytest.skip("Credits available - cannot test 402")
        r = api.post(f"{BASE_URL}/api/prototype/run",
                     json={"graph_id": "000000000000000000000000",
                           "goal": "Find the pricing"},
                     timeout=30)
        assert r.status_code == 402, r.text
        assert "payment" in r.text.lower() or "credit" in r.text.lower()


# --- Checkout / status ---
class TestCheckout:
    session_id_holder = {}

    def test_checkout_creates_session(self, api):
        r = api.post(f"{BASE_URL}/api/payments/checkout",
                     json={"origin_url": BASE_URL},
                     timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "checkout_url" in d
        assert "session_id" in d
        assert d["checkout_url"].startswith("https://checkout.stripe.com"), d["checkout_url"]
        assert isinstance(d["session_id"], str) and len(d["session_id"]) > 0
        TestCheckout.session_id_holder["sid"] = d["session_id"]

    def test_status_valid_session(self, api):
        sid = TestCheckout.session_id_holder.get("sid")
        if not sid:
            pytest.skip("no session id from checkout test")
        r = api.get(f"{BASE_URL}/api/payments/status/{sid}", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["session_id"] == sid
        assert "status" in d and "payment_status" in d

    def test_status_invalid_session_404(self, api):
        r = api.get(f"{BASE_URL}/api/payments/status/invalid_session", timeout=30)
        assert r.status_code == 404, r.text


# --- Regression: existing endpoints still work ---
class TestRegression:
    def test_health(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=30)
        assert r.status_code == 200

    def test_persona_panels(self, api):
        r = api.get(f"{BASE_URL}/api/persona-panels", timeout=30)
        assert r.status_code == 200
