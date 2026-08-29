"""Tests for POST /api/generate-personas persona generator endpoint."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://synthetic-tester.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

VALID_ACTIONS = {"click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"}
VALID_MODES = {"full", "ax_tree_only", "zoomed"}
VALID_DISABILITIES = {None, "motor", "blind", "low_vision", "cognitive"}


@pytest.fixture(scope="module")
def generated():
    """Single real LLM call — reused for multiple assertions to save credits."""
    r = requests.post(
        f"{API}/generate-personas",
        json={
            "audience_description": (
                "Users of an accessibility-focused e-commerce app: includes older adults "
                "with low vision, one motor-impaired keyboard user, one blind screen-reader "
                "user, and impatient young professionals."
            ),
            "count": 5,
        },
        timeout=90,
    )
    assert r.status_code == 200, f"Generation failed: {r.status_code} {r.text}"
    return r.json()


def test_health():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200


def test_response_shape(generated):
    assert "personas" in generated
    assert "composition" in generated
    assert "rationale" in generated
    assert isinstance(generated["personas"], list)
    assert 3 <= len(generated["personas"]) <= 5


def test_persona_schema(generated):
    required = {"name", "traits", "disability", "allowed_actions",
                "perception_mode", "viewport_zoom", "frustration_budget",
                "tolerance_rules", "temperature", "accent_color"}
    for p in generated["personas"]:
        missing = required - set(p.keys())
        assert not missing, f"Missing fields: {missing} in {p.get('name')}"
        assert p["disability"] in VALID_DISABILITIES
        assert p["perception_mode"] in VALID_MODES
        assert all(a in VALID_ACTIONS for a in p["allowed_actions"])
        assert 1 <= p["frustration_budget"] <= 10
        assert 0.1 <= p["temperature"] <= 1.0


def test_frustration_distribution(generated):
    budgets = [p["frustration_budget"] for p in generated["personas"]]
    assert any(2 <= b <= 3 for b in budgets), f"No low-patience persona: {budgets}"
    assert any(4 <= b <= 6 for b in budgets), f"No patient persona: {budgets}"


def test_tolerance_rules(generated):
    for p in generated["personas"]:
        rules = p["tolerance_rules"]
        assert isinstance(rules, list)
        assert 2 <= len(rules) <= 4, f"{p['name']}: has {len(rules)} rules"


def test_disability_constraints(generated):
    for p in generated["personas"]:
        if p["disability"] == "motor":
            assert "click" not in p["allowed_actions"], f"motor persona has click: {p['name']}"
        if p["disability"] == "blind":
            assert p["perception_mode"] == "ax_tree_only", f"blind not ax_tree_only: {p['name']}"


def test_count_three():
    """Separate call with count=3."""
    r = requests.post(
        f"{API}/generate-personas",
        json={"audience_description": "College students using a note-taking app on laptops.", "count": 3},
        timeout=90,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["personas"]) == 3


def test_invalid_count():
    r = requests.post(
        f"{API}/generate-personas",
        json={"audience_description": "test", "count": 10},
        timeout=15,
    )
    assert r.status_code == 422
