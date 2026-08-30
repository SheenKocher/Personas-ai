"""
Developer-facing report generator.

Turns a run's raw journey + signals into a prioritized, plain-language report
a product team can act on: what broke, who it hurts, and how to fix it.
Third-party ad/analytics console noise is separated from real product issues.
One GPT-5 call per run (or per batch), cached on the run/batch.
"""

import json
import os
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

# Hosts whose console errors / failed requests are almost never the product's own bug.
THIRD_PARTY_HOSTS = (
    "amazon-adsystem.com", "doubleclick.net", "googlesyndication.com", "google-analytics.com",
    "googletagmanager.com", "facebook.net", "fbcdn.net", "hotjar.com", "segment.io",
    "segment.com", "sentry.io", "bugsnag.com", "newrelic.com", "nr-data.net", "adnxs.com",
    "criteo.com", "taboola.com", "outbrain.com", "scorecardresearch.com", "quantserve.com",
    "clarity.ms", "cloudfront.net", "optimizely.com", "mixpanel.com", "amplitude.com",
    "branch.io", "onetrust.com", "cookielaw.org", "tiktok.com", "snapchat.com", "bing.com",
    "yieldlab", "weborama", "zeotap", "adform.net",
)

SYSTEM_PROMPT = """You are a senior UX and accessibility engineer. You just watched a synthetic \
test user (a persona with defined traits, sometimes a disability) attempt a goal on a website. \
You are given their step-by-step journey and the automatically-detected friction signals.

Write a report for the PRODUCT TEAM that owns this site. It must be understandable by a \
developer or designer who was not watching, and every issue must be actionable.

Rules:
- Judge from the USER'S point of view and this persona's constraints (e.g. a keyboard-only or \
low-vision user). Tie impact to real people.
- SEPARATE real product issues from noise. Third-party ad/analytics/consent scripts throwing \
console errors, "blocked script execution" in sandboxed ad frames, preload warnings, WebGL \
fallback warnings, and 404s on tracking/telemetry beacons are NOT the product's bug — list \
them briefly under noise_ignored, do not make them issues.
- A 404 on a real page/route the user tried to reach, a control that doesn't respond to click \
or keyboard, a dead end, an unexpectedly long path, confusing labels, or missing feedback \
ARE real issues.
- Order issues by severity (most damaging first). Be concrete: name the element/screen, quote \
the label, cite the step number.
- "recommendation" must be a specific fix a developer can implement, not "improve UX".
- If the persona reached the goal easily, say so plainly and keep issues short.

Respond with ONLY valid JSON, no markdown fences:
{
  "goal_achieved": true | false,
  "headline": "one sentence: did it work, and the single biggest takeaway",
  "summary": "2-4 sentences describing the journey in plain language",
  "issues": [
    {
      "title": "short imperative or noun phrase",
      "severity": "critical" | "high" | "medium" | "low",
      "category": "accessibility" | "usability" | "performance" | "content" | "bug" | "navigation",
      "what_happened": "what the user experienced, with step number and element",
      "user_impact": "who is blocked/slowed and how badly",
      "evidence": "concrete pointer: step N, selector/label, signal text, HTTP code",
      "recommendation": "specific implementable fix"
    }
  ],
  "positives": ["things that worked well for this persona"],
  "noise_ignored": ["categories of third-party/telemetry noise excluded from the issues above"]
}"""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_third_party(text_or_url: str, target_host: str) -> bool:
    t = (text_or_url or "").lower()
    if any(h in t for h in THIRD_PARTY_HOSTS):
        return True
    # A URL clearly on another host than the site under test.
    h = _host(text_or_url)
    if h and target_host and target_host not in h and h not in target_host:
        # only treat as third-party if it actually looks like a URL host
        if "." in h:
            return True
    return False


def _parse(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.split("\n") if not l.strip().startswith("```")).strip()
    return json.loads(text)


def _persona_brief(p: dict) -> str:
    bits = [p.get("name", "Test user")]
    if p.get("traits"):
        bits.append(p["traits"])
    if p.get("disability"):
        bits.append(f"disability: {p['disability']}")
    if p.get("perception_mode") and p["perception_mode"] != "full":
        bits.append(f"perception: {p['perception_mode']}")
    aa = p.get("allowed_actions")
    if aa and "click" not in aa:
        bits.append("cannot use mouse/click (keyboard only)")
    if p.get("tolerance_rules"):
        bits.append("will abandon if: " + "; ".join(p["tolerance_rules"]))
    return " | ".join(bits)


async def _build_packet(db, run_doc: dict) -> dict:
    run_id = str(run_doc["_id"])
    target = run_doc.get("target", "")
    target_host = _host(target)

    steps = await db.steps.find({"run_id": run_id}).sort("index", 1).to_list(60)
    signals = await db.signals.find({"run_id": run_id}).sort("severity", -1).to_list(400)

    step_lines = []
    for s in steps:
        act = s.get("action", {}) or {}
        tgt = act.get("selector") or act.get("url") or act.get("key") or act.get("text") or ""
        res = s.get("action_result", {}) or {}
        status = "ok" if res.get("success", True) else f"FAILED: {res.get('error', '')}"
        if s.get("action_rejected"):
            status = "REJECTED (not allowed for this persona)"
        step_lines.append(
            f"  {s.get('index')}. [{act.get('type', '?')}] {str(tgt)[:120]} -> {status}"
            f"\n     thought: {str(s.get('reasoning', ''))[:200]}"
            f"\n     at: {s.get('location', '')}"
        )

    real, noise = [], []
    for sig in signals:
        line = f"  [sev {sig.get('severity')}] ({sig.get('source')}) {sig.get('description', '')[:240]}  @ {sig.get('screen', '')}"
        if sig.get("source") in ("console_error", "failed_request") and _is_third_party(
            sig.get("description", "") + " " + sig.get("screen", ""), target_host
        ):
            noise.append(line)
        else:
            real.append(line)

    return {
        "run_id": run_id,
        "persona": _persona_brief(run_doc.get("persona", {})),
        "goal": run_doc.get("goal", ""),
        "target": target,
        "outcome": run_doc.get("outcome", ""),
        "error": run_doc.get("error"),
        "text": (
            f"PERSONA: {_persona_brief(run_doc.get('persona', {}))}\n"
            f"GOAL: {run_doc.get('goal', '')}\n"
            f"SITE: {target}\n"
            f"FINAL OUTCOME: {run_doc.get('outcome', '')}"
            + (f" ({run_doc['error']})" if run_doc.get("error") else "")
            + "\n\nJOURNEY (step by step):\n" + ("\n".join(step_lines) or "  (no steps recorded)")
            + "\n\nDETECTED SIGNALS (likely product-related):\n" + ("\n".join(real[:120]) or "  (none)")
            + "\n\nDETECTED SIGNALS (likely third-party / telemetry noise):\n" + ("\n".join(noise[:40]) or "  (none)")
        ),
    }


def _llm():
    return LlmChat(
        api_key=os.environ.get("EMERGENT_LLM_KEY", os.environ.get("OPENAI_API_KEY", "")),
        session_id=f"report-{datetime.now(timezone.utc).timestamp()}",
        system_message=SYSTEM_PROMPT,
    ).with_model("openai", "gpt-5")


async def generate_run_report(db, run_id: str, refresh: bool = False) -> dict:
    from bson import ObjectId
    run_doc = await db.runs.find_one({"_id": ObjectId(run_id)})
    if not run_doc:
        raise ValueError("Run not found")

    if not refresh and run_doc.get("report"):
        return {**run_doc["report"], "cached": True, "run_id": run_id}

    packet = await _build_packet(db, run_doc)
    raw = await _llm().send_message(UserMessage(text=packet["text"] + "\n\nReturn only the JSON object."))
    try:
        report = _parse(raw)
    except json.JSONDecodeError:
        logger.warning("Report JSON parse failed for run %s", run_id)
        report = {"goal_achieved": None, "headline": "Could not generate a structured report.",
                  "summary": raw[:500], "issues": [], "positives": [], "noise_ignored": []}

    report.update({
        "run_id": run_id,
        "persona_name": run_doc.get("persona", {}).get("name"),
        "goal": run_doc.get("goal"),
        "outcome": run_doc.get("outcome"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.runs.update_one({"_id": run_doc["_id"]}, {"$set": {"report": report}})
    return {**report, "cached": False}


async def generate_batch_report(db, batch_id: str, refresh: bool = False) -> dict:
    runs = await db.runs.find({"batch_id": batch_id}).sort("started_at", 1).to_list(12)
    if not runs:
        raise ValueError("Batch not found")

    packets = [await _build_packet(db, r) for r in runs[:6]]
    combined = (
        f"This is a BATCH of {len(packets)} personas run against the same goal. "
        f"Synthesize ONE report. When multiple personas hit the same issue, say so and list "
        f"affected_personas.\n\n"
        + "\n\n========================================\n\n".join(p["text"] for p in packets)
    )
    raw = await _llm().send_message(UserMessage(text=combined + "\n\nReturn only the JSON object."))
    try:
        report = _parse(raw)
    except json.JSONDecodeError:
        report = {"goal_achieved": None, "headline": "Could not generate a structured report.",
                  "summary": raw[:500], "issues": [], "positives": [], "noise_ignored": []}

    report.update({
        "batch_id": batch_id,
        "persona_count": len(runs),
        "goal": runs[0].get("goal"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    return report
