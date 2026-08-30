"""
Browser session module — reusable wrapper around Browserbase + Playwright CDP.
Manages session lifecycle, perception (screenshot, AX tree, errors),
action execution, and screenshot upload to Cloudinary.
All error paths release the Browserbase session.
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


class BrowserUpstreamError(Exception):
    """502 — Browserbase or Cloudinary API failure."""
    pass


class BrowserTimeoutError(Exception):
    """504 — Navigation or action timeout."""
    pass


class BrowserSession:
    """
    Manages a single Browserbase remote browser session.
    Use as async context manager to ensure cleanup.
    """

    def __init__(self):
        self.bb_client = None
        self.bb_session = None
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.cdp = None
        self.console_errors = []
        self.page_errors = []
        self.failed_requests = []
        self._started = False

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Create Browserbase session and connect via CDP."""
        try:
            self.bb_client = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
            self.bb_session = await asyncio.to_thread(
                self.bb_client.sessions.create,
                project_id=os.environ["BROWSERBASE_PROJECT_ID"],
            )
            logger.info("Browserbase session created: %s", self.bb_session.id)
        except Exception as e:
            raise BrowserUpstreamError(f"Failed to create Browserbase session: {e}") from e

        try:
            self.pw = await async_playwright().start()
            self.browser = await self.pw.chromium.connect_over_cdp(self.bb_session.connect_url)
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            self.cdp = await self.context.new_cdp_session(self.page)
        except Exception as e:
            await self.close()
            raise BrowserUpstreamError(f"Failed to connect via CDP: {e}") from e

        # Attach error listeners
        self.page.on("console", self._on_console)
        self.page.on("pageerror", self._on_page_error)
        self.page.on("response", self._on_response)
        self._started = True

    def _on_console(self, msg):
        if msg.type in ("error", "warning"):
            self.console_errors.append({"type": msg.type, "text": msg.text[:2000]})

    def _on_page_error(self, exc):
        self.page_errors.append(str(exc)[:2000])

    def _on_response(self, response):
        if response.status >= 400:
            self.failed_requests.append({
                "url": response.url[:500],
                "status": response.status,
                "status_text": response.status_text,
            })

    async def close(self):
        """Close browser and release Browserbase session. Safe to call multiple times."""
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logger.warning("browser.close() error: %s", e)
            self.browser = None

        if self.pw:
            try:
                await self.pw.stop()
            except Exception as e:
                logger.warning("playwright cleanup error: %s", e)
            self.pw = None

        if self.bb_client and self.bb_session:
            try:
                await asyncio.to_thread(
                    self.bb_client.sessions.update,
                    self.bb_session.id,
                    status="REQUEST_RELEASE",
                )
                logger.info("Browserbase session released: %s", self.bb_session.id)
            except Exception as e:
                logger.warning("Session release error: %s", e)
            self.bb_session = None

        self._started = False

    # --- Perception ---

    async def navigate(self, url: str):
        """Navigate to URL. Raises BrowserTimeoutError on timeout."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            await self.page.wait_for_timeout(1500)
        except PlaywrightTimeoutError as e:
            raise BrowserTimeoutError(f"Navigation to {url} timed out") from e
        except Exception as e:
            raise BrowserUpstreamError(f"Navigation failed: {e}") from e

    async def take_screenshot(self) -> bytes:
        """Capture screenshot as PNG bytes via CDP."""
        try:
            capture = await self.cdp.send("Page.captureScreenshot", {
                "format": "png",
                "captureBeyondViewport": False,
            })
            return base64.b64decode(capture["data"])
        except Exception as e:
            raise BrowserUpstreamError(f"Screenshot failed: {e}") from e

    async def get_ax_tree(self) -> dict:
        """Get accessibility tree via CDP."""
        try:
            ax_result = await self.cdp.send("Accessibility.getFullAXTree")
            nodes = ax_result.get("nodes", [])
            meaningful = [
                {
                    "role": n.get("role", {}).get("value", ""),
                    "name": n.get("name", {}).get("value", ""),
                }
                for n in nodes[:500]
                if n.get("role", {}).get("value") not in ("none", "generic", "InlineTextBox", "StaticText", "")
            ]
            return {"node_count": len(nodes), "nodes": meaningful}
        except Exception as e:
            logger.warning("AX tree extraction failed: %s", e)
            return {"node_count": 0, "nodes": [], "error": str(e)}

    async def perceive(self) -> dict:
        """Full perception: screenshot bytes, AX tree, current URL, title, errors."""
        screenshot_bytes = await self.take_screenshot()
        ax_tree = await self.get_ax_tree()
        current_url = self.page.url
        title = await self.page.title()

        # Snapshot and reset error buffers
        errors = {
            "console_errors": list(self.console_errors),
            "page_errors": list(self.page_errors),
            "failed_requests": list(self.failed_requests),
        }
        self.console_errors.clear()
        self.page_errors.clear()
        self.failed_requests.clear()

        return {
            "screenshot_bytes": screenshot_bytes,
            "ax_tree": ax_tree,
            "current_url": current_url,
            "title": title,
            **errors,
        }

    # --- Action Execution ---

    async def execute_action(self, action: dict) -> dict:
        """
        Execute a browser action. Returns {"success": bool, "error": str|None}.
        Supported types: click, type, scroll, navigate, wait, key
        """
        action_type = action.get("type")
        result = {"success": True, "error": None}

        try:
            if action_type == "click":
                selector = action.get("selector", "")
                await self.page.locator(selector).first.click(timeout=8000)

            elif action_type == "type":
                selector = action.get("selector", "")
                text = action.get("text", "")
                await self.page.locator(selector).first.fill(text, timeout=8000)

            elif action_type == "scroll":
                direction = action.get("direction", "down")
                amount = action.get("amount", 500)
                delta = amount if direction == "down" else -amount
                await self.page.evaluate(f"window.scrollBy(0, {delta})")
                await self.page.wait_for_timeout(500)

            elif action_type == "navigate":
                url = action.get("url", "")
                await self.navigate(url)

            elif action_type == "wait":
                duration = min(action.get("duration_ms", 2000), 5000)
                await self.page.wait_for_timeout(duration)

            elif action_type == "key":
                key = action.get("key", "Tab")
                await self.page.keyboard.press(key)
                await self.page.wait_for_timeout(300)

            else:
                result = {"success": False, "error": f"Unknown action type: {action_type}"}

        except PlaywrightTimeoutError:
            result = {"success": False, "error": f"Action '{action_type}' timed out (selector: {action.get('selector', 'N/A')})"}
        except Exception as e:
            result = {"success": False, "error": f"Action '{action_type}' failed: {str(e)[:500]}"}

        # Brief settling time after any action
        if result["success"] and action_type not in ("wait", "scroll"):
            try:
                await self.page.wait_for_timeout(800)
            except Exception:
                pass

        return result

    # --- Cloudinary Upload ---

    @staticmethod
    async def upload_screenshot(png_bytes: bytes, retries: int = 3):
        """
        Upload screenshot to Cloudinary, return the secure URL.
        Retries transient network failures (RemoteDisconnected, timeouts) with
        backoff. Returns None if every attempt fails — the caller should record
        the step without a screenshot rather than abort the whole run.
        """
        last_err = None
        for attempt in range(retries):
            try:
                result = await asyncio.to_thread(
                    cloudinary.uploader.upload,
                    io.BytesIO(png_bytes),
                    folder="synthtest/screenshots",
                    resource_type="image",
                    format="png",
                )
                return result["secure_url"]
            except Exception as e:
                last_err = e
                logger.warning(
                    "Cloudinary upload attempt %d/%d failed: %s", attempt + 1, retries, e
                )
                if attempt < retries - 1:
                    await asyncio.sleep(1 + attempt * 2)  # 1s, 3s
        logger.error("Cloudinary upload failed after %d attempts: %s", retries, last_err)
        return None
