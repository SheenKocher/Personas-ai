"""
Cross-stage diff — compares signals and outcomes between
prototype and runtime runs for the same persona + goal.
Produces a regression report grouped by screen.
"""

import logging
from collections import defaultdict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _normalize_screen(url: str) -> str:
    """Normalize URL/screen name to a comparable identifier."""
    if not url or url == "unknown":
        return url
    if url.startswith("http"):
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    return url


def _aggregate_screen_signals(signals: list) -> dict:
    """Group a flat signal list by screen, producing score + details."""
    by_screen = defaultdict(lambda: {
        "signals": [],
        "weighted_score": 0.0,
        "max_severity": 0,
        "count": 0,
        "sources": defaultdict(int),
        "types": defaultdict(int),
    })

    for sig in signals:
        screen = _normalize_screen(sig.get("screen", "unknown"))
        sev = sig.get("severity", 1)
        count = sig.get("count", 1)

        sd = by_screen[screen]
        sd["count"] += 1
        sd["weighted_score"] += sev * count
        sd["max_severity"] = max(sd["max_severity"], sev)
        sd["sources"][sig.get("source", "unknown")] += 1
        sd["types"][sig.get("type", "unknown")] += 1
        sd["signals"].append({
            "type": sig.get("type"),
            "severity": sev,
            "description": sig.get("description", "")[:300],
            "source": sig.get("source"),
        })

    # Sort signals by severity desc within each screen
    for sd in by_screen.values():
        sd["signals"].sort(key=lambda s: -s["severity"])
        sd["sources"] = dict(sd["sources"])
        sd["types"] = dict(sd["types"])
        sd["weighted_score"] = round(sd["weighted_score"], 1)

    return dict(by_screen)


def _classify_verdict(proto_score: float, runtime_score: float, proto_exists: bool, runtime_exists: bool) -> str:
    """Classify the cross-stage verdict for a screen."""
    if proto_exists and not runtime_exists:
        return "missing_in_runtime"
    if not proto_exists and runtime_exists:
        return "new_in_runtime"
    if proto_score == 0 and runtime_score == 0:
        return "clean"
    delta = runtime_score - proto_score
    if abs(delta) < 1.5:
        return "unchanged"
    if delta > 0:
        return "regression"
    return "improvement"


def _diff_signals(proto_sigs: list, runtime_sigs: list) -> list:
    """Find signals that changed between stages."""
    changes = []

    # Index by (source, description_prefix)
    proto_keys = {}
    for s in proto_sigs:
        key = (s.get("source", ""), s.get("description", "")[:80])
        proto_keys[key] = s

    runtime_keys = {}
    for s in runtime_sigs:
        key = (s.get("source", ""), s.get("description", "")[:80])
        runtime_keys[key] = s

    # New in runtime (not in prototype)
    for key, sig in runtime_keys.items():
        if key not in proto_keys:
            changes.append({
                "change": "new_in_runtime",
                "severity": sig["severity"],
                "description": sig["description"],
                "source": sig.get("source"),
            })

    # Fixed in runtime (was in prototype, gone in runtime)
    for key, sig in proto_keys.items():
        if key not in runtime_keys:
            changes.append({
                "change": "fixed_in_runtime",
                "severity": sig["severity"],
                "description": sig["description"],
                "source": sig.get("source"),
            })

    # Severity changes
    for key in proto_keys:
        if key in runtime_keys:
            ps = proto_keys[key]
            rs = runtime_keys[key]
            if ps["severity"] != rs["severity"]:
                changes.append({
                    "change": "severity_changed",
                    "old_severity": ps["severity"],
                    "new_severity": rs["severity"],
                    "description": rs["description"],
                    "source": rs.get("source"),
                })

    changes.sort(key=lambda c: -(c.get("severity", 0) or c.get("new_severity", 0)))
    return changes


async def build_cross_stage_diff(
    db,
    goal: str = None,
    prototype_batch_id: str = None,
    runtime_batch_id: str = None,
    prototype_run_ids: list = None,
    runtime_run_ids: list = None,
) -> dict:
    """
    Compare prototype vs runtime signals for the same goal/personas.
    Returns a structured regression report.
    """

    # Resolve prototype runs
    if prototype_run_ids:
        proto_query = {"_id": {"$in": [__import__("bson").ObjectId(r) for r in prototype_run_ids]}}
    elif prototype_batch_id:
        proto_query = {"batch_id": prototype_batch_id, "stage": "prototype"}
    elif goal:
        proto_query = {"goal": {"$regex": goal[:60], "$options": "i"}, "stage": "prototype", "outcome": {"$ne": "in_progress"}}
    else:
        return {"error": "Provide goal, batch IDs, or run IDs"}

    proto_runs = await db.runs.find(proto_query).sort("started_at", -1).to_list(20)

    # Resolve runtime runs
    if runtime_run_ids:
        runtime_query = {"_id": {"$in": [__import__("bson").ObjectId(r) for r in runtime_run_ids]}}
    elif runtime_batch_id:
        runtime_query = {"batch_id": runtime_batch_id, "stage": "runtime"}
    elif goal:
        runtime_query = {"goal": {"$regex": goal[:60], "$options": "i"}, "stage": "runtime", "outcome": {"$ne": "in_progress"}}
    else:
        runtime_query = {"stage": "runtime", "outcome": {"$ne": "in_progress"}}

    runtime_runs = await db.runs.find(runtime_query).sort("started_at", -1).to_list(20)

    if not proto_runs and not runtime_runs:
        return {"error": "No matching runs found for either stage"}

    # Collect run IDs
    proto_ids = [str(r["_id"]) for r in proto_runs]
    runtime_ids = [str(r["_id"]) for r in runtime_runs]

    # Build persona → outcome maps
    proto_outcomes = {}
    runtime_outcomes = {}
    persona_names = set()

    for r in proto_runs:
        name = r.get("persona", {}).get("name", "?")
        proto_outcomes[name] = r.get("outcome", "?")
        persona_names.add(name)

    for r in runtime_runs:
        name = r.get("persona", {}).get("name", "?")
        runtime_outcomes[name] = r.get("outcome", "?")
        persona_names.add(name)

    # Fetch all signals
    all_proto_sigs = await db.signals.find({"run_id": {"$in": proto_ids}}).to_list(5000)
    all_runtime_sigs = await db.signals.find({"run_id": {"$in": runtime_ids}}).to_list(5000)

    # Aggregate by screen
    proto_by_screen = _aggregate_screen_signals(all_proto_sigs)
    runtime_by_screen = _aggregate_screen_signals(all_runtime_sigs)

    # All screens across both stages
    all_screens = set(proto_by_screen.keys()) | set(runtime_by_screen.keys())

    # Build per-screen diff
    screens = []
    regressions = 0
    improvements = 0
    unchanged = 0

    for screen in sorted(all_screens):
        proto_data = proto_by_screen.get(screen)
        runtime_data = runtime_by_screen.get(screen)

        proto_score = proto_data["weighted_score"] if proto_data else 0
        runtime_score = runtime_data["weighted_score"] if runtime_data else 0
        delta = round(runtime_score - proto_score, 1)

        verdict = _classify_verdict(proto_score, runtime_score, proto_data is not None, runtime_data is not None)

        if verdict == "regression":
            regressions += 1
        elif verdict == "improvement":
            improvements += 1
        else:
            unchanged += 1

        changed_signals = _diff_signals(
            proto_data["signals"] if proto_data else [],
            runtime_data["signals"] if runtime_data else [],
        )

        screens.append({
            "screen": screen,
            "verdict": verdict,
            "delta_score": delta,
            "prototype": {
                "weighted_score": proto_score,
                "signal_count": proto_data["count"] if proto_data else 0,
                "max_severity": proto_data["max_severity"] if proto_data else 0,
                "by_source": proto_data["sources"] if proto_data else {},
                "signals": (proto_data["signals"] if proto_data else [])[:10],
            },
            "runtime": {
                "weighted_score": runtime_score,
                "signal_count": runtime_data["count"] if runtime_data else 0,
                "max_severity": runtime_data["max_severity"] if runtime_data else 0,
                "by_source": runtime_data["sources"] if runtime_data else {},
                "signals": (runtime_data["signals"] if runtime_data else [])[:10],
            },
            "changed_signals": changed_signals,
        })

    # Sort: regressions first (by delta descending), then rest
    verdict_order = {"regression": 0, "new_in_runtime": 1, "unchanged": 2, "improvement": 3, "clean": 4, "missing_in_runtime": 5}
    screens.sort(key=lambda s: (verdict_order.get(s["verdict"], 9), -abs(s["delta_score"])))

    effective_goal = goal or (proto_runs[0].get("goal", "") if proto_runs else (runtime_runs[0].get("goal", "") if runtime_runs else ""))

    return {
        "goal": effective_goal,
        "personas_compared": sorted(persona_names),
        "prototype_runs": len(proto_runs),
        "runtime_runs": len(runtime_runs),
        "summary": {
            "total_screens": len(screens),
            "regressions": regressions,
            "improvements": improvements,
            "unchanged": unchanged,
        },
        "outcomes_by_persona": {
            name: {
                "prototype": proto_outcomes.get(name, "—"),
                "runtime": runtime_outcomes.get(name, "—"),
            }
            for name in sorted(persona_names)
        },
        "screens": screens,
    }
