"""
Signal derivation — post-run analysis of step data to produce
objective and behavioral signals automatically.
"""

import logging
from collections import Counter
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Objective signals — console errors, failed network requests
# ---------------------------------------------------------------------------

def _severity_for_console_error(err: dict) -> int:
    """Map console error type to severity."""
    etype = err.get("type", "")
    text = err.get("text", "").lower()
    if "cors" in text or "blocked" in text:
        return 3
    if etype == "error":
        return 3
    if etype == "warning":
        return 1
    return 2


def _severity_for_failed_request(req: dict) -> int:
    """Map HTTP status to severity."""
    status = req.get("status", 0)
    if status >= 500:
        return 4
    if status == 404:
        return 3
    if status >= 400:
        return 2
    return 1


def _deduplicate_errors(errors: list, key_fn) -> list:
    """Deduplicate by a key function, keeping count."""
    seen = {}
    for e in errors:
        k = key_fn(e)
        if k not in seen:
            seen[k] = {"item": e, "count": 1}
        else:
            seen[k]["count"] += 1
    return list(seen.values())


async def derive_objective_signals(db, run_id: str, stage: str) -> list:
    """
    Pull console errors and failed network requests from step docs,
    create type=objective signals.
    """
    cursor = db.steps.find({"run_id": run_id}).sort("index", 1)
    steps = await cursor.to_list(50)

    signals = []

    # Collect all console errors across steps
    all_console_errors = []
    all_failed_requests = []
    for step in steps:
        screen = step.get("location", "unknown")
        for err in step.get("console_errors", []):
            all_console_errors.append({**err, "screen": screen, "step_index": step["index"]})
        for req in step.get("failed_requests", []):
            all_failed_requests.append({**req, "screen": screen, "step_index": req.get("step_index", step["index"])})

    # Deduplicate console errors by text prefix
    deduped_console = _deduplicate_errors(
        all_console_errors,
        lambda e: e.get("text", "")[:100]
    )
    for entry in deduped_console:
        err = entry["item"]
        count = entry["count"]
        sev = _severity_for_console_error(err)
        text_preview = err.get("text", "")[:200]
        signals.append({
            "run_id": run_id,
            "stage": stage,
            "type": "objective",
            "severity": sev,
            "screen": err.get("screen", "unknown"),
            "description": f"Console {err.get('type', 'error')}: {text_preview}" + (f" (×{count})" if count > 1 else ""),
            "source": "console_error",
            "count": count,
        })

    # Deduplicate failed requests by URL + status
    deduped_requests = _deduplicate_errors(
        all_failed_requests,
        lambda r: f"{r.get('status', 0)}:{urlparse(r.get('url', '')).path}"
    )
    for entry in deduped_requests:
        req = entry["item"]
        count = entry["count"]
        sev = _severity_for_failed_request(req)
        url_short = req.get("url", "")[:150]
        signals.append({
            "run_id": run_id,
            "stage": stage,
            "type": "objective",
            "severity": sev,
            "screen": req.get("screen", "unknown"),
            "description": f"HTTP {req.get('status', '?')} {req.get('status_text', '')}: {url_short}" + (f" (×{count})" if count > 1 else ""),
            "source": "failed_request",
            "count": count,
        })

    return signals


# ---------------------------------------------------------------------------
# Behavioral signals — state revisits, path length, dead-clicks,
#                       keyboard dead-ends
# ---------------------------------------------------------------------------

def _normalize_screen(url: str) -> str:
    """Normalize URL to a screen identifier (path without query/fragment)."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


async def derive_behavioral_signals(db, run_id: str, stage: str, persona: dict) -> list:
    """
    Derive behavioral signals from the step log.
    """
    cursor = db.steps.find({"run_id": run_id}).sort("index", 1)
    steps = await cursor.to_list(50)

    if not steps:
        return []

    signals = []
    disability = persona.get("disability")
    is_keyboard_only = disability == "motor"

    # --- 1. State revisits ---
    screen_visits = Counter()
    screen_first_visit = {}
    for step in steps:
        screen = _normalize_screen(step.get("location", ""))
        if screen:
            screen_visits[screen] += 1
            if screen not in screen_first_visit:
                screen_first_visit[screen] = step["index"]

    for screen, count in screen_visits.items():
        if count >= 2:
            sev = 3 if count >= 3 else 2
            signals.append({
                "run_id": run_id,
                "stage": stage,
                "type": "behavioral",
                "severity": sev,
                "screen": screen,
                "description": f"State revisit: screen visited {count} times (first at step {screen_first_visit[screen]})",
                "source": "state_revisit",
                "count": count,
            })

    # --- 2. Path length analysis ---
    total_steps = len(steps)
    # Unique screens visited (a rough optimal would be the number of unique screens)
    unique_screens = len(set(
        _normalize_screen(s.get("location", ""))
        for s in steps if s.get("location")
    ))
    # If more than double the unique screens or more than 8 steps, flag it
    optimal_estimate = max(unique_screens, 3)
    if total_steps > optimal_estimate * 2:
        excess = total_steps - optimal_estimate
        sev = 3 if total_steps > optimal_estimate * 3 else 2
        signals.append({
            "run_id": run_id,
            "stage": stage,
            "type": "behavioral",
            "severity": sev,
            "screen": _normalize_screen(steps[-1].get("location", "")),
            "description": f"Excessive path length: {total_steps} steps taken, estimated optimal ~{optimal_estimate} ({excess} extra steps)",
            "source": "path_length",
            "count": total_steps,
        })

    # --- 3. Dead-clicks ---
    for i, step in enumerate(steps):
        action = step.get("action", {})
        action_type = action.get("type", "")
        action_result = step.get("action_result", {})
        rejected = step.get("action_rejected", False)

        # Dead-click: action rejected
        if rejected:
            # Already covered by the rejection signal from the engine, skip duplicate
            continue

        # Dead-click: action failed
        if action_type in ("click", "type", "key") and not action_result.get("success", True):
            signals.append({
                "run_id": run_id,
                "stage": stage,
                "type": "behavioral",
                "severity": 2,
                "screen": step.get("location", "unknown"),
                "description": f"Dead-click at step {step['index']}: {action_type} failed — {action_result.get('error', 'unknown')[:150]}",
                "source": "dead_click",
                "count": 1,
            })
            continue

        # Dead-click: click/navigate succeeded but URL didn't change
        if action_type in ("click", "navigate") and action_result.get("success", True):
            current_screen = _normalize_screen(step.get("location", ""))
            # Check next step's location to see if page changed
            if i + 1 < len(steps):
                next_screen = _normalize_screen(steps[i + 1].get("location", ""))
                if current_screen == next_screen and action_type == "navigate":
                    signals.append({
                        "run_id": run_id,
                        "stage": stage,
                        "type": "behavioral",
                        "severity": 2,
                        "screen": current_screen,
                        "description": f"Dead-click at step {step['index']}: {action_type} to '{action.get('url', action.get('selector', '?'))[:80]}' produced no visible page change",
                        "source": "dead_click",
                        "count": 1,
                    })

    # --- 4. Keyboard dead-ends (motor persona only) ---
    if is_keyboard_only:
        consecutive_stuck = 0
        last_screen = None
        stuck_start_step = None

        for step in steps:
            action_type = step.get("action", {}).get("type", "")
            current_screen = _normalize_screen(step.get("location", ""))

            if action_type == "key":
                if current_screen == last_screen:
                    consecutive_stuck += 1
                    if stuck_start_step is None:
                        stuck_start_step = step["index"] - 1
                else:
                    # Emit signal if we were stuck for 2+ consecutive key presses
                    if consecutive_stuck >= 2 and last_screen:
                        signals.append({
                            "run_id": run_id,
                            "stage": stage,
                            "type": "behavioral",
                            "severity": 3,
                            "screen": last_screen,
                            "description": f"Keyboard dead-end: {consecutive_stuck + 1} consecutive key presses on same screen (steps {stuck_start_step}-{step['index'] - 1}), unable to navigate away",
                            "source": "keyboard_dead_end",
                            "count": consecutive_stuck + 1,
                        })
                    consecutive_stuck = 0
                    stuck_start_step = None
            else:
                # Non-key action resets the counter
                if consecutive_stuck >= 2 and last_screen:
                    signals.append({
                        "run_id": run_id,
                        "stage": stage,
                        "type": "behavioral",
                        "severity": 3,
                        "screen": last_screen,
                        "description": f"Keyboard dead-end: {consecutive_stuck + 1} consecutive key presses on same screen (steps {stuck_start_step}-{step['index'] - 1}), unable to navigate away",
                        "source": "keyboard_dead_end",
                        "count": consecutive_stuck + 1,
                    })
                consecutive_stuck = 0
                stuck_start_step = None

            last_screen = current_screen

        # Handle end-of-loop
        if consecutive_stuck >= 2 and last_screen:
            signals.append({
                "run_id": run_id,
                "stage": stage,
                "type": "behavioral",
                "severity": 3,
                "screen": last_screen,
                "description": f"Keyboard dead-end: {consecutive_stuck + 1} consecutive key presses on same screen (ended at step {steps[-1]['index']}), unable to navigate away",
                "source": "keyboard_dead_end",
                "count": consecutive_stuck + 1,
            })

    return signals


# ---------------------------------------------------------------------------
# Main derivation entry point
# ---------------------------------------------------------------------------

async def derive_all_signals(db, run_id: str, stage: str, persona: dict) -> list:
    """
    Run all signal derivation passes and insert results into DB.
    Returns the list of derived signals (without _id).
    """
    objective = await derive_objective_signals(db, run_id, stage)
    behavioral = await derive_behavioral_signals(db, run_id, stage, persona)

    all_derived = objective + behavioral

    # Insert into DB
    if all_derived:
        docs = [s.copy() for s in all_derived]
        await db.signals.insert_many(docs)
        logger.info("Derived %d signals for run %s (%d objective, %d behavioral)",
                     len(all_derived), run_id, len(objective), len(behavioral))

    # Return without _id for JSON serialization
    return [{k: v for k, v in s.items() if k != "_id"} for s in all_derived]


# ---------------------------------------------------------------------------
# Aggregation — worst screens across a batch
# ---------------------------------------------------------------------------

async def aggregate_signals_by_screen(db, batch_id: str = None, run_ids: list = None) -> list:
    """
    Group signals by screen, weighted by frequency × severity.
    Returns a ranked list of worst screens.
    """
    # Resolve run_ids from batch
    if batch_id and not run_ids:
        cursor = db.runs.find({"batch_id": batch_id}, {"_id": 1})
        runs = await cursor.to_list(50)
        run_ids = [str(r["_id"]) for r in runs]

    if not run_ids:
        return []

    # Fetch all signals for these runs
    cursor = db.signals.find({"run_id": {"$in": run_ids}})
    signals = await cursor.to_list(5000)

    if not signals:
        return []

    # Group by normalized screen
    screen_data = {}
    for sig in signals:
        screen = _normalize_screen(sig.get("screen", "unknown"))
        if screen not in screen_data:
            screen_data[screen] = {
                "screen": screen,
                "total_signals": 0,
                "weighted_score": 0.0,
                "max_severity": 0,
                "signal_types": Counter(),
                "signal_sources": Counter(),
                "personas": set(),
                "signals": [],
            }

        sev = sig.get("severity", 1)
        count = sig.get("count", 1)
        weight = count * sev

        sd = screen_data[screen]
        sd["total_signals"] += 1
        sd["weighted_score"] += weight
        sd["max_severity"] = max(sd["max_severity"], sev)
        sd["signal_types"][sig.get("type", "unknown")] += 1
        sd["signal_sources"][sig.get("source", "unknown")] += 1

        # Track which persona reported this
        run_id = sig.get("run_id")
        sd["personas"].add(run_id)

        sd["signals"].append({
            "type": sig.get("type"),
            "severity": sev,
            "description": sig.get("description", "")[:200],
            "source": sig.get("source"),
            "run_id": run_id,
        })

    # Resolve persona names for run_ids
    persona_names = {}
    if run_ids:
        for rid in run_ids:
            from bson import ObjectId
            try:
                rdoc = await db.runs.find_one({"_id": ObjectId(rid)}, {"persona.name": 1})
                if rdoc:
                    persona_names[rid] = rdoc.get("persona", {}).get("name", "?")
            except Exception:
                pass

    # Build ranked result
    ranked = []
    for screen, sd in screen_data.items():
        ranked.append({
            "screen": screen,
            "weighted_score": round(sd["weighted_score"], 1),
            "total_signals": sd["total_signals"],
            "max_severity": sd["max_severity"],
            "affected_runs": len(sd["personas"]),
            "affected_personas": [persona_names.get(rid, rid) for rid in sd["personas"]],
            "by_type": dict(sd["signal_types"]),
            "by_source": dict(sd["signal_sources"]),
            "signals": sorted(sd["signals"], key=lambda s: -s["severity"])[:20],
        })

    # Sort by weighted_score descending
    ranked.sort(key=lambda x: -x["weighted_score"])

    return ranked
