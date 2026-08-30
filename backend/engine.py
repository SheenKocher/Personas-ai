"""
Persona engine — stage-agnostic agent loop.
perceive → think (LLM) → act → record → repeat
until goal reached, give_up, or MAX_STEPS.

Also provides run_panel_parallel for concurrent multi-persona runs.
"""

import asyncio
import json
import os
import logging
import uuid
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage

from browser import BrowserSession, BrowserUpstreamError, BrowserTimeoutError

logger = logging.getLogger(__name__)

MAX_STEPS = 15


def _build_system_prompt(persona: dict, goal: str, target_url: str) -> str:
    """Build the LLM system prompt from persona config."""
    name = persona.get("name", "Test User")
    traits = persona.get("traits", "")
    disability = persona.get("disability")
    perception_mode = persona.get("perception_mode", "full")
    frustration_budget = persona.get("frustration_budget", 5)
    tolerance_rules = persona.get("tolerance_rules", [])
    allowed_actions = persona.get("allowed_actions", ["click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"])
    temperature = persona.get("temperature", 0.6)

    disability_text = ""
    if disability == "motor":
        disability_text = "You have a motor impairment and navigate entirely by keyboard. You CANNOT use a mouse or click. Only use keyboard actions (key, type)."
    elif disability == "blind":
        disability_text = "You are blind and use a screen reader. You CANNOT see the screen. You can only perceive the accessibility tree text. Judge everything by the AX tree structure."
    elif disability == "low_vision":
        disability_text = f"You have low vision and use {persona.get('viewport_zoom', 2.0)}x zoom. Elements may overlap or clip at this zoom level."
    elif disability == "cognitive":
        disability_text = "You have low literacy and are unfamiliar with this product. You are easily overwhelmed by dense text or jargon."

    perception_text = ""
    if perception_mode == "ax_tree_only":
        perception_text = "You CANNOT see the visual screen. You only receive the accessibility tree (a text listing of page elements with their roles and names). This is what a screen reader would announce."
    elif perception_mode == "zoomed":
        perception_text = f"You see the page at {persona.get('viewport_zoom', 2.0)}x zoom. Some elements may be clipped or overlapping."
    else:
        perception_text = "You see the full page content through its accessibility tree."

    rules_text = "\n".join(f"  - {r}" for r in tolerance_rules) if tolerance_rules else "  (none)"
    actions_text = ", ".join(allowed_actions)

    return f"""You are {name}, a synthetic test user.

TRAITS: {traits}
{disability_text}

GOAL: {goal}
TARGET: {target_url}

PERCEPTION: {perception_text}
FRUSTRATION BUDGET: {frustration_budget} (you give up when cumulative frustration reaches this)

TOLERANCE RULES (report friction when you notice these):
{rules_text}

ALLOWED ACTIONS: {actions_text}

At each step you receive the current page state (accessibility tree of elements with their roles and names). Decide what action to take next.

Respond with ONLY valid JSON — no markdown, no code fences, just the JSON object:
{{
  "reasoning": "your thought process as {name} (first person, stay in character)",
  "action": {{
    "type": "one of: {actions_text}",
    ... action-specific fields below ...
  }},
  "goal_reached": false,
  "frustration_increase": 0
}}

ACTION FORMATS:
- click: {{"type": "click", "selector": "text=ButtonText or a:has-text(\\"LinkText\\") or css-selector"}}
- type: {{"type": "type", "selector": "input-selector", "text": "what to type"}}
- scroll: {{"type": "scroll", "direction": "down|up", "amount": 500}}
- navigate: {{"type": "navigate", "url": "https://..."}}
- wait: {{"type": "wait", "duration_ms": 2000}}
- key: {{"type": "key", "key": "Tab|Enter|Escape|ArrowDown|Space|..."}}
- report_friction: {{"type": "report_friction", "description": "what's wrong", "severity": 1-5}}
- give_up: {{"type": "give_up", "reason": "why you're abandoning the task"}}

SELECTOR TIPS (use accessibility tree names):
- text=Pricing → clicks element containing "Pricing"
- a:has-text("Sign In") → clicks a link with that text
- button:has-text("Submit") → clicks a button
- input[placeholder="Email"] → targets an input
- [role="navigation"] >> text=About → scoped selector

RULES:
- Only use actions from your ALLOWED ACTIONS list
- Set goal_reached=true when you've accomplished the goal
- Set frustration_increase (0-2) based on how frustrating this step was
- report_friction doesn't count as a browser action — the loop continues after it
- give_up ends the run immediately
- Stay in character as {name}"""


def _ax_tree_to_text(ax_tree: dict, perception_mode: str) -> str:
    """Convert structured AX tree to readable text for the LLM."""
    nodes = ax_tree.get("nodes", [])
    if not nodes:
        return "(empty — no accessible elements found)"

    lines = []
    for n in nodes:
        role = n.get("role", "")
        name = n.get("name", "")
        if name:
            lines.append(f"[{role}] \"{name}\"")
        else:
            lines.append(f"[{role}]")

    return "\n".join(lines)


def _parse_llm_response(raw: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


async def run_persona_engine(
    db,
    target_url: str,
    goal: str,
    persona: dict,
    stage: str = "prototype",
    existing_run_id: str = None,
) -> dict:
    """
    Execute the full agent loop for one persona.
    Returns dict with run summary, steps, and signals.
    If existing_run_id is provided, uses that run document instead of creating a new one.
    """
    run_id = None
    run_oid = None
    session_id = None
    steps_out = []
    signals_out = []
    outcome = "in_progress"
    frustration = 0
    frustration_budget = persona.get("frustration_budget", 5)
    allowed_actions = set(persona.get("allowed_actions", [
        "click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"
    ]))

    now_start = datetime.now(timezone.utc).isoformat()

    if existing_run_id:
        # Use existing run document (created by the endpoint for background pattern)
        from bson import ObjectId
        run_id = existing_run_id
        run_oid = ObjectId(run_id)
    else:
        # Create run document
        run_doc = {
            "stage": stage,
            "persona": persona,
            "target": target_url,
            "goal": goal,
            "outcome": "in_progress",
            "started_at": now_start,
            "ended_at": None,
        }
        run_result = await db.runs.insert_one(run_doc)
        run_id = str(run_result.inserted_id)
        run_oid = run_result.inserted_id

    # Initialize LLM chat — use Emergent key (universal access) with GPT-5
    system_prompt = _build_system_prompt(persona, goal, target_url)
    llm_key = os.environ.get("EMERGENT_LLM_KEY", os.environ.get("OPENAI_API_KEY", ""))
    chat = LlmChat(
        api_key=llm_key,
        session_id=f"persona-run-{run_id}",
        system_message=system_prompt,
    ).with_model("openai", "gpt-5")

    async with BrowserSession() as browser:
        session_id = browser.bb_session.id if browser.bb_session else None

        # Update run with session id
        await db.runs.update_one(
            {"_id": run_oid},
            {"$set": {"browserbase_session_id": session_id}},
        )

        # Initial navigation
        try:
            await browser.navigate(target_url)
        except BrowserTimeoutError:
            outcome = "gave_up"
            await _finalize_run(db, run_oid, outcome, session_id)
            return {"run_id": run_id, "outcome": outcome, "steps": [], "signals": [], "error": "Initial navigation timed out"}

        step_history = []

        for step_index in range(MAX_STEPS):
            now_step = datetime.now(timezone.utc).isoformat()

            # 1. PERCEIVE
            perception = await browser.perceive()
            # A failed screenshot upload must NOT kill the run — record the step
            # without an image and keep going.
            screenshot_url = await BrowserSession.upload_screenshot(perception["screenshot_bytes"]) or ""

            ax_text = _ax_tree_to_text(perception["ax_tree"], persona.get("perception_mode", "full"))

            # Build history summary for context
            history_text = ""
            if step_history:
                history_lines = []
                for h in step_history[-5:]:  # last 5 steps
                    history_lines.append(f"Step {h['index']}: {h['action_type']} → {'OK' if h['success'] else 'FAILED: ' + h.get('error', '')}")
                history_text = "\n".join(history_lines)

            # Console errors from this perception
            errors_text = ""
            if perception["console_errors"]:
                error_lines = [f"  [{e['type']}] {e['text'][:200]}" for e in perception["console_errors"][:5]]
                errors_text = "\n".join(error_lines)

            # 2. THINK — LLM call
            errors_section = f"Console errors:\n{errors_text}" if errors_text else "No console errors."
            history_section = f"Previous steps:\n{history_text}" if history_text else "This is the first step."

            user_msg = (
                f"Step {step_index + 1}/{MAX_STEPS}\n"
                f"Frustration: {frustration}/{frustration_budget}\n"
                f"URL: {perception['current_url']}\n"
                f"Title: {perception['title']}\n\n"
                f"Accessibility tree:\n{ax_text}\n\n"
                f"{errors_section}\n\n"
                f"{history_section}"
            )

            llm_response_raw = ""
            parsed = None
            try:
                llm_response_raw = await chat.send_message(UserMessage(text=user_msg))
                parsed = _parse_llm_response(llm_response_raw)
            except json.JSONDecodeError:
                logger.warning("LLM returned invalid JSON on step %d, retrying", step_index)
                try:
                    retry_msg = "Your previous response was not valid JSON. Please respond with ONLY a valid JSON object, no markdown fences."
                    llm_response_raw = await chat.send_message(UserMessage(text=retry_msg))
                    parsed = _parse_llm_response(llm_response_raw)
                except (json.JSONDecodeError, Exception):
                    parsed = {
                        "reasoning": "Failed to parse LLM response, defaulting to wait",
                        "action": {"type": "wait", "duration_ms": 1000},
                        "goal_reached": False,
                        "frustration_increase": 1,
                    }
            except Exception as e:
                logger.error("LLM call failed on step %d: %s", step_index, e)
                parsed = {
                    "reasoning": f"LLM call error: {str(e)[:200]}",
                    "action": {"type": "wait", "duration_ms": 1000},
                    "goal_reached": False,
                    "frustration_increase": 1,
                }

            reasoning = parsed.get("reasoning", "")
            action = parsed.get("action", {})
            goal_reached = parsed.get("goal_reached", False)
            frustration_increase = min(parsed.get("frustration_increase", 0), 2)

            action_type = action.get("type", "wait")

            # 3. VALIDATE — reject if not in allowed_actions
            action_rejected = False
            if action_type not in allowed_actions:
                action_rejected = True
                rejection_signal = {
                    "run_id": run_id,
                    "stage": stage,
                    "type": "behavioral",
                    "severity": 2,
                    "screen": perception["current_url"],
                    "description": f"Action '{action_type}' rejected — not in persona's allowed_actions: {list(allowed_actions)}",
                    "source": "action_rejected",
                }
                await db.signals.insert_one(rejection_signal.copy())
                signals_out.append({k: v for k, v in rejection_signal.items() if k != "_id"})
                # Override to wait
                action = {"type": "wait", "duration_ms": 500}
                action_type = "wait"
                frustration_increase = max(frustration_increase, 1)

            # 4. ACT — execute browser action (skip for report_friction and give_up)
            action_result = {"success": True, "error": None}
            if action_type == "report_friction":
                # Record friction signal
                friction_signal = {
                    "run_id": run_id,
                    "stage": stage,
                    "type": "reported",
                    "severity": min(max(action.get("severity", 3), 1), 5),
                    "screen": perception["current_url"],
                    "description": action.get("description", "Friction reported by persona"),
                    "source": "persona_report",
                }
                await db.signals.insert_one(friction_signal.copy())
                signals_out.append({k: v for k, v in friction_signal.items() if k != "_id"})

            elif action_type == "give_up":
                outcome = "gave_up"
            else:
                action_result = await browser.execute_action(action)

            # 5. RECORD — write step document
            step_doc = {
                "run_id": run_id,
                "index": step_index,
                "action": action,
                "reasoning": reasoning,
                "screenshot_before_url": screenshot_url,
                "screenshot_after_url": None,  # filled after action
                "location": perception["current_url"],
                "timestamp": now_step,
                "action_result": action_result,
                "action_rejected": action_rejected,
                "frustration_at_step": frustration,
                "llm_response_raw": llm_response_raw[:5000],
                "console_errors": perception.get("console_errors", []),
                "page_errors": perception.get("page_errors", []),
                "failed_requests": perception.get("failed_requests", []),
            }

            # Take after-screenshot for non-meta actions
            if action_type not in ("report_friction", "give_up", "wait") and action_result["success"]:
                try:
                    after_bytes = await browser.take_screenshot()
                    after_url = await BrowserSession.upload_screenshot(after_bytes)
                    step_doc["screenshot_after_url"] = after_url
                except Exception as e:
                    logger.warning("After-screenshot failed: %s", e)

            await db.steps.insert_one(step_doc)
            steps_out.append({
                "index": step_index,
                "action": action,
                "reasoning": reasoning[:300],
                "success": action_result["success"],
                "error": action_result.get("error"),
                "screenshot_before_url": screenshot_url,
                "screenshot_after_url": step_doc["screenshot_after_url"],
                "goal_reached": goal_reached,
                "action_rejected": action_rejected,
            })

            step_history.append({
                "index": step_index,
                "action_type": action_type,
                "success": action_result["success"],
                "error": action_result.get("error", ""),
                "location": perception["current_url"],
            })

            # Update frustration
            frustration += frustration_increase

            # Check termination conditions
            if goal_reached:
                outcome = "success"
                break
            if outcome == "gave_up":
                break
            if frustration >= frustration_budget:
                outcome = "gave_up"
                # Record a signal for budget exceeded
                budget_signal = {
                    "run_id": run_id,
                    "stage": stage,
                    "type": "behavioral",
                    "severity": 4,
                    "screen": perception["current_url"],
                    "description": f"Frustration budget exhausted ({frustration}/{frustration_budget})",
                    "source": "frustration_budget",
                }
                await db.signals.insert_one(budget_signal.copy())
                signals_out.append({k: v for k, v in budget_signal.items() if k != "_id"})
                break

        else:
            # Exhausted MAX_STEPS
            outcome = "max_steps"

    # Derive objective and behavioral signals from step data
    from signals import derive_all_signals
    derived = await derive_all_signals(db, run_id, stage, persona)
    signals_out.extend(derived)

    # Finalize run
    await _finalize_run(db, run_oid, outcome, session_id)

    return {
        "run_id": run_id,
        "outcome": outcome,
        "total_steps": len(steps_out),
        "total_signals": len(signals_out),
        "final_frustration": frustration,
        "browserbase_session_id": session_id,
        "steps": steps_out,
        "signals": signals_out,
    }


async def _finalize_run(db, run_oid, outcome: str, session_id: str = None):
    """Update the run document with final outcome and timestamps."""
    updates = {
        "outcome": outcome,
        "ended_at": datetime.now(timezone.utc).isoformat(),
    }
    if session_id:
        updates["browserbase_session_id"] = session_id
    await db.runs.update_one({"_id": run_oid}, {"$set": updates})



async def _run_single_persona_safe(db, run_id: str, target_url: str, goal: str, persona: dict, stage: str) -> dict:
    """Wrapper that catches all errors for a single persona in a parallel batch."""
    persona_name = persona.get("name", "Unknown")
    try:
        result = await run_persona_engine(
            db=db,
            target_url=target_url,
            goal=goal,
            persona=persona,
            stage=stage,
            existing_run_id=run_id,
        )
        logger.info("Persona '%s' (run %s) finished: %s", persona_name, run_id, result.get("outcome"))
        return result
    except Exception as e:
        logger.exception("Persona '%s' (run %s) failed: %s", persona_name, run_id, e)
        from bson import ObjectId
        try:
            await db.runs.update_one(
                {"_id": ObjectId(run_id)},
                {"$set": {"outcome": "gave_up", "ended_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            pass
        return {
            "run_id": run_id,
            "persona_name": persona_name,
            "outcome": "gave_up",
            "error": str(e),
            "total_steps": 0,
            "total_signals": 0,
        }


async def run_panel_parallel(
    db,
    target_url: str,
    goal: str,
    personas: list,
    stage: str = "prototype",
    concurrency: int = 3,
    batch_id: str = None,
) -> dict:
    """
    Run multiple personas concurrently against the same target and goal.
    Each persona gets its own isolated Browserbase session.
    Returns a batch summary with all run results.
    """
    if not batch_id:
        batch_id = str(uuid.uuid4())
    now_start = datetime.now(timezone.utc).isoformat()

    # Limit to concurrency cap
    selected = personas[:concurrency]
    logger.info(
        "Starting parallel batch %s: %d personas, target=%s, goal=%s",
        batch_id, len(selected), target_url, goal[:60],
    )

    # Pre-create all run documents so we have IDs before launching
    run_ids = []
    for persona in selected:
        run_doc = {
            "stage": stage,
            "persona": persona,
            "target": target_url,
            "goal": goal,
            "outcome": "in_progress",
            "started_at": now_start,
            "ended_at": None,
            "batch_id": batch_id,
        }
        result = await db.runs.insert_one(run_doc)
        run_ids.append(str(result.inserted_id))

    # Launch all engines concurrently
    tasks = [
        _run_single_persona_safe(db, run_id, target_url, goal, persona, stage)
        for run_id, persona in zip(run_ids, selected)
    ]
    results = await asyncio.gather(*tasks)

    return {
        "batch_id": batch_id,
        "target_url": target_url,
        "goal": goal,
        "stage": stage,
        "concurrency": len(selected),
        "started_at": now_start,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "runs": [
            {
                "run_id": r.get("run_id"),
                "persona_name": r.get("persona_name") or (selected[i].get("name") if i < len(selected) else "?"),
                "outcome": r.get("outcome"),
                "total_steps": r.get("total_steps", 0),
                "total_signals": r.get("total_signals", 0),
                "final_frustration": r.get("final_frustration"),
                "error": r.get("error"),
            }
            for i, r in enumerate(results)
        ],
    }
