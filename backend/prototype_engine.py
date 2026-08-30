"""
Prototype stage engine — runs personas against a mockup state graph
instead of a live browser. Uses GPT-5 vision to analyze mockup images.

Actions become intent statements matched against labeled transitions.
Unmatched intents become dead-end friction signals.
Produces stage=prototype runs using the exact same schema as runtime.
"""

import asyncio
import base64
import json
import os
import logging
import uuid
import httpx
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from ws_manager import broadcaster
import run_control

logger = logging.getLogger(__name__)

# Step cap per prototype run — see engine.py. Override with MAX_STEPS in env.
MAX_STEPS = int(os.environ.get("MAX_STEPS", "25"))


def _build_prototype_system_prompt(persona: dict, goal: str, graph_name: str) -> str:
    """Build system prompt for prototype mockup testing."""
    name = persona.get("name", "Test User")
    traits = persona.get("traits", "")
    disability = persona.get("disability")
    perception_mode = persona.get("perception_mode", "full")
    frustration_budget = persona.get("frustration_budget", 5)
    tolerance_rules = persona.get("tolerance_rules", [])
    allowed_actions = persona.get("allowed_actions", [
        "click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up",
    ])

    disability_text = ""
    if disability == "motor":
        disability_text = "You have a motor impairment and navigate entirely by keyboard. You CANNOT tap or click elements directly."
    elif disability == "blind":
        disability_text = "You are blind and use a screen reader. You CANNOT see the mockup image. You only know what elements exist from their text descriptions."
    elif disability == "low_vision":
        disability_text = f"You have low vision and use {persona.get('viewport_zoom', 2.0)}x zoom. Small text and controls may be hard to read."
    elif disability == "cognitive":
        disability_text = "You have low literacy and are easily overwhelmed by dense content or jargon."

    perception_text = ""
    if perception_mode == "ax_tree_only":
        perception_text = "You CANNOT see the screen image. You only receive a text description of what elements are on the screen."
    elif perception_mode == "zoomed":
        perception_text = f"You see the screen at {persona.get('viewport_zoom', 2.0)}x zoom."
    else:
        perception_text = "You see the full mockup screen image."

    rules_text = "\n".join(f"  - {r}" for r in tolerance_rules) if tolerance_rules else "  (none)"
    actions_text = ", ".join(allowed_actions)

    return f"""You are {name}, a synthetic test user evaluating a PROTOTYPE (static mockup screens).

TRAITS: {traits}
{disability_text}

GOAL: {goal}
PROTOTYPE: {graph_name}

PERCEPTION: {perception_text}
FRUSTRATION BUDGET: {frustration_budget} (you give up when cumulative frustration reaches this)

TOLERANCE RULES:
{rules_text}

You are testing a PROTOTYPE consisting of static mockup screens. At each step you see the current screen (as an image or description) and a list of available interactions on that screen.

You must declare your INTENT — what you want to do next — as a natural action statement.

Respond with ONLY valid JSON:
{{
  "reasoning": "your thought process as {name} (first person, what you see, what you want to do)",
  "intent": "a natural action statement, e.g. 'tap the Pricing link' or 'click the Sign Up button' or 'scroll down to see more options'",
  "matched_transition": "the label of the transition you think matches your intent, or null if none match",
  "goal_reached": false,
  "frustration_increase": 0,
  "is_friction_report": false,
  "friction_description": "",
  "friction_severity": 0,
  "wants_to_give_up": false,
  "give_up_reason": ""
}}

RULES:
- Study the screen carefully and pick an action that makes progress toward your goal
- If you see a transition that matches your intent, set matched_transition to that exact label
- If NO transition matches what you want to do, set matched_transition to null — this represents a dead-end in the prototype
- If something feels wrong, set is_friction_report=true with description and severity (1-5)
- If you want to give up, set wants_to_give_up=true with a reason
- Set goal_reached=true only when you're confident the goal is accomplished
- frustration_increase: 0 (smooth), 1 (minor hiccup), 2 (significant friction)
- Stay in character as {name}"""


async def _download_image_as_base64(url: str) -> str:
    """Download an image URL and return base64-encoded string."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=15)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("utf-8")


def _build_screen_description(screen: dict, transitions: list) -> str:
    """Build a text description of a screen for blind/AX-tree-only personas."""
    lines = [f"Screen: {screen.get('name', 'Unknown')}"]
    lines.append("")
    if transitions:
        lines.append("Available interactions on this screen:")
        for t in transitions:
            lines.append(f"  - {t['label']}")
    else:
        lines.append("No interactive elements available on this screen.")
    return "\n".join(lines)


def _match_transition(intent: str, matched_label: str, transitions: list) -> dict:
    """
    Try to match the persona's intent to a transition.
    Returns the matched transition dict, or None.
    """
    if not transitions:
        return None

    # 1. If LLM explicitly named a transition, verify it exists
    if matched_label:
        for t in transitions:
            if t["label"].lower().strip() == matched_label.lower().strip():
                return t

    # 2. Fuzzy: check if intent overlaps with any transition label
    intent_lower = intent.lower()
    best = None
    best_score = 0
    for t in transitions:
        label_lower = t["label"].lower()
        # Token overlap score
        intent_tokens = set(intent_lower.split())
        label_tokens = set(label_lower.split())
        overlap = len(intent_tokens & label_tokens)
        if overlap > best_score:
            best_score = overlap
            best = t

    # Require at least 1 meaningful token overlap
    if best and best_score >= 1:
        return best

    return None


def _parse_response(raw: str) -> dict:
    """Parse JSON from LLM response."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


async def run_prototype_engine(
    db,
    graph_id: str,
    goal: str,
    persona: dict,
    existing_run_id: str = None,
    batch_id: str = None,
) -> dict:
    """
    Run a persona against a mockup state graph.
    Same schema as runtime runs, stage=prototype.
    """
    from bson import ObjectId

    # Load the graph
    graph_doc = await db.screen_graphs.find_one({"_id": ObjectId(graph_id)})
    if not graph_doc:
        raise ValueError(f"Screen graph {graph_id} not found")

    screens_by_id = {s["id"]: s for s in graph_doc.get("screens", [])}
    all_transitions = graph_doc.get("transitions", [])
    start_screen_id = graph_doc.get("start_screen", "")
    graph_name = graph_doc.get("name", "Prototype")

    if start_screen_id not in screens_by_id:
        raise ValueError(f"Start screen '{start_screen_id}' not found in graph")

    stage = "prototype"
    run_id = None
    run_oid = None
    steps_out = []
    signals_out = []
    outcome = "in_progress"
    frustration = 0
    frustration_budget = persona.get("frustration_budget", 5)
    current_screen_id = start_screen_id

    now_start = datetime.now(timezone.utc).isoformat()

    if existing_run_id:
        run_id = existing_run_id
        run_oid = ObjectId(run_id)
    else:
        run_doc = {
            "stage": stage,
            "persona": persona,
            "target": f"prototype:{graph_id}",
            "goal": goal,
            "outcome": "in_progress",
            "started_at": now_start,
            "ended_at": None,
            "graph_id": graph_id,
        }
        result = await db.runs.insert_one(run_doc)
        run_id = str(result.inserted_id)
        run_oid = result.inserted_id

    pause_event = run_control.register(run_id)

    # Initialize LLM
    system_prompt = _build_prototype_system_prompt(persona, goal, graph_name)
    llm_key = os.environ.get("EMERGENT_LLM_KEY", os.environ.get("OPENAI_API_KEY", ""))
    chat = LlmChat(
        api_key=llm_key,
        session_id=f"proto-run-{run_id}",
        system_message=system_prompt,
    ).with_model("openai", "gpt-5")

    perception_mode = persona.get("perception_mode", "full")

    for step_index in range(MAX_STEPS):
        await pause_event.wait()

        now_step = datetime.now(timezone.utc).isoformat()

        current_screen = screens_by_id.get(current_screen_id)
        if not current_screen:
            outcome = "gave_up"
            break

        screen_image_url = current_screen.get("image_url", "")
        screen_name = current_screen.get("name", current_screen_id)

        # Get available transitions from current screen
        available_transitions = [
            t for t in all_transitions if t["from_screen"] == current_screen_id
        ]
        transition_labels = [t["label"] for t in available_transitions]

        # Build the user message
        transitions_text = ""
        if transition_labels:
            transitions_text = "Available interactions:\n" + "\n".join(
                f"  - {lbl}" for lbl in transition_labels
            )
        else:
            transitions_text = "No interactive elements available on this screen."

        msg_text = (
            f"Step {step_index + 1}/{MAX_STEPS}\n"
            f"Frustration: {frustration}/{frustration_budget}\n"
            f"Current screen: {screen_name}\n\n"
            f"{transitions_text}\n\n"
            f"What do you do next to achieve your goal?"
        )

        # Build message with or without image
        file_contents = []
        if perception_mode != "ax_tree_only" and screen_image_url:
            try:
                img_b64 = await _download_image_as_base64(screen_image_url)
                file_contents = [ImageContent(image_base64=img_b64)]
            except Exception as e:
                logger.warning("Failed to download mockup image: %s", e)
                msg_text += f"\n\n(Image could not be loaded: {screen_name})"
        elif perception_mode == "ax_tree_only":
            screen_desc = _build_screen_description(current_screen, available_transitions)
            msg_text = (
                f"Step {step_index + 1}/{MAX_STEPS}\n"
                f"Frustration: {frustration}/{frustration_budget}\n\n"
                f"{screen_desc}\n\n"
                f"What do you do next to achieve your goal?"
            )

        # LLM call
        parsed = None
        llm_raw = ""
        try:
            llm_raw = await chat.send_message(
                UserMessage(text=msg_text, file_contents=file_contents)
            )
            parsed = _parse_response(llm_raw)
        except json.JSONDecodeError:
            try:
                retry_msg = "Your response was not valid JSON. Respond with ONLY valid JSON."
                llm_raw = await chat.send_message(UserMessage(text=retry_msg))
                parsed = _parse_response(llm_raw)
            except Exception:
                parsed = {
                    "reasoning": "Failed to parse response",
                    "intent": "wait",
                    "matched_transition": None,
                    "goal_reached": False,
                    "frustration_increase": 1,
                }
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            parsed = {
                "reasoning": f"LLM error: {str(e)[:200]}",
                "intent": "wait",
                "matched_transition": None,
                "goal_reached": False,
                "frustration_increase": 1,
            }

        reasoning = parsed.get("reasoning", "")
        intent = parsed.get("intent", "")
        matched_label = parsed.get("matched_transition")
        goal_reached = parsed.get("goal_reached", False)
        frustration_increase = min(parsed.get("frustration_increase", 0), 2)
        is_friction = parsed.get("is_friction_report", False)
        wants_give_up = parsed.get("wants_to_give_up", False)

        # Handle friction reports
        if is_friction:
            friction_sig = {
                "run_id": run_id,
                "stage": stage,
                "type": "reported",
                "severity": min(max(parsed.get("friction_severity", 3), 1), 5),
                "screen": screen_name,
                "description": parsed.get("friction_description", "Friction reported"),
                "source": "persona_report",
            }
            await db.signals.insert_one(friction_sig.copy())
            signals_out.append({k: v for k, v in friction_sig.items() if k != "_id"})

        # Handle give up
        if wants_give_up:
            outcome = "gave_up"

        # Try to match intent to a transition
        action_result = {"success": True, "error": None}
        next_screen_id = current_screen_id
        transition_matched = None

        if not wants_give_up and not goal_reached and intent:
            transition_matched = _match_transition(intent, matched_label, available_transitions)

            if transition_matched:
                next_screen_id = transition_matched["to_screen"]
                action_result = {"success": True, "error": None, "transition": transition_matched["label"]}
            else:
                # Dead-end — no matching transition
                action_result = {
                    "success": False,
                    "error": f"No transition matches intent: '{intent}'. Available: {transition_labels}",
                }
                dead_end_sig = {
                    "run_id": run_id,
                    "stage": stage,
                    "type": "behavioral",
                    "severity": 3,
                    "screen": screen_name,
                    "description": f"Dead-end: persona wanted to '{intent}' but no matching interaction exists on '{screen_name}'",
                    "source": "dead_end",
                }
                await db.signals.insert_one(dead_end_sig.copy())
                signals_out.append({k: v for k, v in dead_end_sig.items() if k != "_id"})
                frustration_increase = max(frustration_increase, 1)

        # Record step (same schema as runtime)
        step_doc = {
            "run_id": run_id,
            "index": step_index,
            "action": {
                "type": "intent",
                "intent": intent,
                "matched_transition": transition_matched["label"] if transition_matched else None,
            },
            "reasoning": reasoning,
            "screenshot_before_url": screen_image_url,
            "screenshot_after_url": screens_by_id.get(next_screen_id, {}).get("image_url") if transition_matched else None,
            "location": screen_name,
            "timestamp": now_step,
            "action_result": action_result,
            "action_rejected": False,
            "frustration_at_step": frustration,
            "llm_response_raw": llm_raw[:5000],
            "console_errors": [],
            "page_errors": [],
            "failed_requests": [],
        }
        await db.steps.insert_one(step_doc)

        steps_out.append({
            "index": step_index,
            "action": step_doc["action"],
            "reasoning": reasoning[:300],
            "success": action_result["success"],
            "error": action_result.get("error"),
            "screenshot_before_url": screen_image_url,
            "screenshot_after_url": step_doc["screenshot_after_url"],
            "goal_reached": goal_reached,
            "action_rejected": False,
            "screen": screen_name,
        })

        # Advance screen
        current_screen_id = next_screen_id

        # Update frustration
        frustration += frustration_increase

        await broadcaster.send_step_update(
            batch_id=batch_id,
            run_id=run_id,
            persona=persona,
            step_index=step_index,
            max_steps=MAX_STEPS,
            action=step_doc["action"],
            reasoning=reasoning,
            screenshot_url=step_doc["screenshot_after_url"] or screen_image_url,
            location=screen_name,
            outcome="success" if goal_reached else ("gave_up" if wants_give_up else "in_progress"),
            frustration=frustration,
            frustration_budget=frustration_budget,
        )

        # Check termination
        if goal_reached:
            outcome = "success"
            break
        if outcome == "gave_up":
            break
        if frustration >= frustration_budget:
            outcome = "gave_up"
            budget_sig = {
                "run_id": run_id,
                "stage": stage,
                "type": "behavioral",
                "severity": 4,
                "screen": screen_name,
                "description": f"Frustration budget exhausted ({frustration}/{frustration_budget})",
                "source": "frustration_budget",
            }
            await db.signals.insert_one(budget_sig.copy())
            signals_out.append({k: v for k, v in budget_sig.items() if k != "_id"})
            break
    else:
        outcome = "max_steps"

    # Derive signals
    from signals import derive_all_signals
    derived = await derive_all_signals(db, run_id, stage, persona)
    signals_out.extend(derived)

    # Finalize
    updates = {"outcome": outcome, "ended_at": datetime.now(timezone.utc).isoformat()}
    await db.runs.update_one({"_id": run_oid}, {"$set": updates})

    await broadcaster.send_run_complete(
        batch_id=batch_id,
        run_id=run_id,
        persona_name=persona.get("name", "?"),
        outcome=outcome,
        total_steps=len(steps_out),
        total_signals=len(signals_out),
    )
    run_control.discard(run_id)

    return {
        "run_id": run_id,
        "outcome": outcome,
        "total_steps": len(steps_out),
        "total_signals": len(signals_out),
        "final_frustration": frustration,
        "steps": steps_out,
        "signals": signals_out,
        "persona_name": persona.get("name", "?"),
    }


async def run_prototype_panel(
    db, graph_id: str, goal: str, personas: list,
    concurrency: int = 3, batch_id: str = None,
) -> dict:
    """Run multiple personas concurrently against the same prototype graph."""
    import uuid as _uuid
    from bson import ObjectId

    if not batch_id:
        batch_id = str(_uuid.uuid4())

    now = datetime.now(timezone.utc).isoformat()
    selected = personas[:concurrency]

    # Pre-create runs
    run_ids = []
    for persona in selected:
        run_doc = {
            "stage": "prototype",
            "persona": persona,
            "target": f"prototype:{graph_id}",
            "goal": goal,
            "outcome": "in_progress",
            "started_at": now,
            "ended_at": None,
            "graph_id": graph_id,
            "batch_id": batch_id,
        }
        result = await db.runs.insert_one(run_doc)
        run_ids.append(str(result.inserted_id))

    async def _safe_run(rid, p):
        try:
            return await run_prototype_engine(db, graph_id, goal, p, existing_run_id=rid, batch_id=batch_id)
        except Exception as e:
            logger.exception("Prototype persona '%s' failed", p.get("name"))
            try:
                await db.runs.update_one(
                    {"_id": ObjectId(rid)},
                    {"$set": {"outcome": "gave_up", "ended_at": datetime.now(timezone.utc).isoformat()}},
                )
            except Exception:
                pass
            return {"run_id": rid, "persona_name": p.get("name"), "outcome": "gave_up", "error": str(e)}

    tasks = [_safe_run(rid, p) for rid, p in zip(run_ids, selected)]
    results = await asyncio.gather(*tasks)

    return {
        "batch_id": batch_id,
        "graph_id": graph_id,
        "goal": goal,
        "stage": "prototype",
        "concurrency": len(selected),
        "started_at": now,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "runs": [
            {
                "run_id": r.get("run_id"),
                "persona_name": r.get("persona_name", selected[i].get("name") if i < len(selected) else "?"),
                "outcome": r.get("outcome"),
                "total_steps": r.get("total_steps", 0),
                "total_signals": r.get("total_signals", 0),
                "error": r.get("error"),
            }
            for i, r in enumerate(results)
        ],
    }
