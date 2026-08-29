"""
Spike module: remote-browser connection via Browserbase + Playwright CDP.
Navigates to a target URL, captures screenshot, accessibility tree,
console errors, and failed network requests.
Uploads screenshot to Cloudinary; stores results as run + step documents.
"""

import asyncio
import base64
import io
import os
import logging
from datetime import datetime, timezone

import cloudinary
import cloudinary.uploader
from browserbase import Browserbase
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

# --- Cloudinary config ---
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True,
)

DEFAULT_TARGET = "https://tier3.college"


def _upload_screenshot_to_cloudinary(png_bytes: bytes) -> str:
    """Upload raw PNG bytes to Cloudinary, return the secure URL."""
    result = cloudinary.uploader.upload(
        io.BytesIO(png_bytes),
        folder="synthtest/screenshots",
        resource_type="image",
        format="png",
    )
    return result["secure_url"]


def _create_browserbase_session() -> object:
    """Create a Browserbase session (sync SDK call)."""
    bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
    session = bb.sessions.create(
        project_id=os.environ["BROWSERBASE_PROJECT_ID"],
    )
    logger.info("Browserbase session created: %s", session.id)
    return session


async def _run_browser_job(target_url: str) -> dict:
    """
    Async Playwright job:
    1. Create Browserbase session (in thread — sync SDK)
    2. Connect via CDP
    3. Navigate, screenshot, ax-tree, console/network errors
    """
    # Session creation is sync, run in thread
    session = await asyncio.to_thread(_create_browserbase_session)

    console_errors = []
    page_errors = []
    failed_requests = []
    browser = None

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(session.connect_url)
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()

            # Attach listeners BEFORE navigation
            def on_console(msg):
                if msg.type in ("error", "warning"):
                    console_errors.append({"type": msg.type, "text": msg.text[:2000]})

            def on_page_error(exc):
                page_errors.append(str(exc)[:2000])

            def on_response(response):
                if response.status >= 400:
                    failed_requests.append({
                        "url": response.url[:500],
                        "status": response.status,
                        "status_text": response.status_text,
                    })

            page.on("console", on_console)
            page.on("pageerror", on_page_error)
            page.on("response", on_response)

            # Navigate
            nav_error = None
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
                await page.wait_for_timeout(2000)
            except PlaywrightTimeoutError:
                nav_error = "Navigation timed out after 45s"
                console_errors.append({"type": "error", "text": nav_error})

            # Screenshot via CDP
            cdp = await context.new_cdp_session(page)
            capture = await cdp.send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": False,
            })
            screenshot_b64 = capture["data"]
            screenshot_bytes = base64.b64decode(screenshot_b64)

            # Accessibility tree via CDP
            ax_tree = None
            try:
                ax_result = await cdp.send("Accessibility.getFullAXTree")
                nodes = ax_result.get("nodes", [])
                # Flatten to a compact representation
                ax_tree = {
                    "node_count": len(nodes),
                    "nodes": [
                        {
                            "role": n.get("role", {}).get("value", ""),
                            "name": n.get("name", {}).get("value", ""),
                        }
                        for n in nodes[:500]  # cap to avoid oversized docs
                        if n.get("role", {}).get("value") not in ("none", "generic", "InlineTextBox", "StaticText", "")
                    ],
                }
            except Exception as e:
                logger.warning("CDP Accessibility.getFullAXTree failed: %s", e)
                ax_tree = {"error": str(e)}

            final_url = page.url
            title = await page.title()

            return {
                "session_id": session.id,
                "target_url": target_url,
                "final_url": final_url,
                "title": title,
                "screenshot_bytes": screenshot_bytes,
                "accessibility_tree": ax_tree,
                "console_errors": console_errors,
                "page_errors": page_errors,
                "failed_requests": failed_requests,
                "nav_error": nav_error,
            }
        finally:
            if browser:
                await browser.close()


async def execute_spike_run(db, target_url: str = DEFAULT_TARGET) -> dict:
    """
    Run the full spike flow:
    1. Remote browser job (async)
    2. Upload screenshot to Cloudinary (in thread — sync SDK)
    3. Create run + step documents in MongoDB
    Returns dict with run and step data.
    """
    # 1. Run browser job
    result = await _run_browser_job(target_url)

    # 2. Upload screenshot to Cloudinary (sync call, run in thread)
    screenshot_url = await asyncio.to_thread(
        _upload_screenshot_to_cloudinary, result["screenshot_bytes"]
    )
    logger.info("Screenshot uploaded: %s", screenshot_url)

    now = datetime.now(timezone.utc).isoformat()

    # 3. Create run document
    run_doc = {
        "stage": "prototype",
        "persona": {},
        "target": result["target_url"],
        "goal": "spike: verify remote browser connection",
        "outcome": "success" if result["nav_error"] is None else "gave_up",
        "started_at": now,
        "ended_at": now,
        "browserbase_session_id": result["session_id"],
    }
    run_result = await db.runs.insert_one(run_doc)
    run_id = str(run_result.inserted_id)

    # 4. Create step document
    step_doc = {
        "run_id": run_id,
        "index": 0,
        "action": {
            "type": "navigate",
            "url": result["target_url"],
            "final_url": result["final_url"],
            "title": result["title"],
        },
        "reasoning": "Spike: navigate to target, capture screenshot + ax tree + errors",
        "screenshot_before_url": None,
        "screenshot_after_url": screenshot_url,
        "location": result["final_url"],
        "timestamp": now,
        "accessibility_tree": result["accessibility_tree"],
        "console_errors": result["console_errors"],
        "page_errors": result["page_errors"],
        "failed_requests": result["failed_requests"],
    }
    step_result = await db.steps.insert_one(step_doc)
    step_id = str(step_result.inserted_id)

    # 5. Return assembled response
    return {
        "run": {
            "id": run_id,
            "stage": run_doc["stage"],
            "persona": run_doc["persona"],
            "target": run_doc["target"],
            "goal": run_doc["goal"],
            "outcome": run_doc["outcome"],
            "started_at": run_doc["started_at"],
            "ended_at": run_doc["ended_at"],
            "browserbase_session_id": run_doc["browserbase_session_id"],
        },
        "step": {
            "id": step_id,
            "run_id": run_id,
            "index": step_doc["index"],
            "action": step_doc["action"],
            "reasoning": step_doc["reasoning"],
            "screenshot_before_url": step_doc["screenshot_before_url"],
            "screenshot_after_url": step_doc["screenshot_after_url"],
            "location": step_doc["location"],
            "timestamp": step_doc["timestamp"],
            "accessibility_tree": step_doc["accessibility_tree"],
            "console_errors": step_doc["console_errors"],
            "page_errors": step_doc["page_errors"],
            "failed_requests": step_doc["failed_requests"],
        },
    }
