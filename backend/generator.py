"""
Persona generator — one LLM call to produce a structured panel
of 3-5 distinct personas from an audience description.
"""

import json
import os
import logging
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

ACCENT_COLORS = ["#818CF8", "#A78BFA", "#38BDF8", "#C084FC", "#F472B6", "#FBBF24", "#34D399"]

SYSTEM_PROMPT = """You are a synthetic-user-testing persona designer. Given a 1-2 sentence audience description, you produce a panel of distinct test personas that cover the range of users in that audience.

Each persona must follow this exact JSON schema:
{
  "name": "FirstName — Role/Archetype",
  "traits": "age, context, tech comfort, device, behavior patterns, relevant background",
  "disability": null | "motor" | "blind" | "low_vision" | "cognitive",
  "allowed_actions": ["click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
  "perception_mode": "full" | "ax_tree_only" | "zoomed",
  "viewport_zoom": 1.0,
  "frustration_budget": <int 2-6>,
  "tolerance_rules": ["rule 1", "rule 2", ...],
  "temperature": <float 0.4-0.8>
}

RULES:
- Generate 3-5 personas (as specified in the count parameter)
- Each persona must be DISTINCT — different archetype, different frustration threshold, different concerns
- At least one persona should have low patience / low frustration_budget (2-3)
- At least one persona should be more patient / exploratory (frustration_budget 4-6)
- If the audience includes people with disabilities or accessibility needs, add appropriate disability personas:
  - motor disability: remove "click" from allowed_actions, keep "key", "type", "scroll", "navigate", "wait", "report_friction", "give_up". perception_mode: "full"
  - blind: perception_mode: "ax_tree_only", allowed_actions includes "click" and "key"
  - low_vision: perception_mode: "zoomed", viewport_zoom: 2.0
  - cognitive: perception_mode: "full", lower frustration_budget (2-3)
- tolerance_rules should be specific to that persona's likely pain points (2-4 rules each)
- Traits should feel like a real person — include age, location/context, device, relevant habits
- temperature: lower (0.4-0.5) for methodical/cautious users, higher (0.6-0.8) for exploratory/impatient users
- Names should reflect the cultural context of the audience when appropriate

Respond with ONLY valid JSON — no markdown, no code fences:
{
  "personas": [ ... array of persona objects ... ],
  "composition": "broad" or "focused",
  "rationale": "brief explanation of why these personas cover the audience"
}"""


def _parse_response(raw: str) -> dict:
    """Parse JSON from LLM response, stripping code fences."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _assign_colors(personas: list) -> list:
    """Assign accent colors to personas that don't have one."""
    for i, p in enumerate(personas):
        if not p.get("accent_color"):
            p["accent_color"] = ACCENT_COLORS[i % len(ACCENT_COLORS)]
    return personas


def _validate_persona(p: dict) -> dict:
    """Ensure all required fields exist with valid values."""
    valid_actions = {"click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"}
    valid_modes = {"full", "ax_tree_only", "zoomed"}
    valid_disabilities = {None, "motor", "blind", "low_vision", "cognitive"}

    p.setdefault("name", "Unnamed Persona")
    p.setdefault("traits", "")
    if p.get("disability") not in valid_disabilities:
        p["disability"] = None
    p["allowed_actions"] = [a for a in p.get("allowed_actions", list(valid_actions)) if a in valid_actions]
    if not p["allowed_actions"]:
        p["allowed_actions"] = list(valid_actions)
    if p.get("perception_mode") not in valid_modes:
        p["perception_mode"] = "full"
    p.setdefault("viewport_zoom", 1.0)
    p["frustration_budget"] = max(1, min(10, int(p.get("frustration_budget", 4))))
    if not isinstance(p.get("tolerance_rules"), list):
        p["tolerance_rules"] = []
    p["temperature"] = max(0.1, min(1.0, float(p.get("temperature", 0.6))))

    # Enforce disability constraints
    if p["disability"] == "motor" and "click" in p["allowed_actions"]:
        p["allowed_actions"].remove("click")
    if p["disability"] == "blind":
        p["perception_mode"] = "ax_tree_only"
    if p["disability"] == "low_vision":
        p["perception_mode"] = "zoomed"
        p.setdefault("viewport_zoom", 2.0)

    return p


async def generate_personas(audience_description: str, count: int = 4) -> dict:
    """
    Generate a panel of personas from an audience description.
    One LLM call, returns structured persona data.
    """
    llm_key = os.environ.get("EMERGENT_LLM_KEY", os.environ.get("OPENAI_API_KEY", ""))
    chat = LlmChat(
        api_key=llm_key,
        session_id=f"persona-gen-{uuid.uuid4()}",
        system_message=SYSTEM_PROMPT,
    ).with_model("openai", "gpt-5")

    user_msg = (
        f"Audience: {audience_description}\n"
        f"Generate exactly {count} personas.\n"
        f"Return only the JSON object."
    )

    raw = await chat.send_message(UserMessage(text=user_msg))
    parsed = _parse_response(raw)

    personas = parsed.get("personas", [])
    # Validate and sanitize each persona
    personas = [_validate_persona(p) for p in personas]
    personas = _assign_colors(personas)

    return {
        "personas": personas,
        "composition": parsed.get("composition", "broad"),
        "rationale": parsed.get("rationale", ""),
        "audience_description": audience_description,
    }
