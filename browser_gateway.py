"""Single-session ChatGPT browser gateway.

All Playwright operations are serialized through one asyncio lock. The gateway is
intentionally isolated from HTTP and OpenAI-compatible response formatting.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrowserSettings:
    cookies_netscape: str
    profile_path: str
    headless: bool
    request_timeout_seconds: float
    ready_timeout_seconds: float


def parse_netscape_cookies(cookie_text: str) -> list[dict[str, Any]]:
    """Parse Netscape cookie export text without logging values."""
    cookies: list[dict[str, Any]] = []
    for raw_line in cookie_text.splitlines():
        line = raw_line.strip("\r\n")
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _include_subdomains, path, secure, expires, name, value = parts[:7]
        if not name:
            continue
        cookie: dict[str, Any] = {
            "name": name,
            "value": value,
            "path": path or "/",
            "secure": secure.upper() == "TRUE",
        }
        if expires.isdigit() and int(expires) > 0:
            cookie["expires"] = int(expires)
        if name.startswith("__Host-"):
            cookie["secure"] = True
            cookie["url"] = "https://chatgpt.com"
            cookie.pop("path", None)
        else:
            cookie["domain"] = domain
        cookies.append(cookie)
    return cookies


class BrowserGateway:
    """Own a persistent browser context and serialize all page actions."""

    def __init__(self, settings: BrowserSettings) -> None:
        self.settings = settings
        self.lock = asyncio.Lock()
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.ready = False
        self.startup_error: str | None = None
        self.last_request_at: float | None = None

    async def start(self) -> None:
        if self.ready:
            return
        if not self.settings.cookies_netscape.strip():
            self.startup_error = "CHATGPT_COOKIES_NETSCAPE is not configured"
            LOGGER.error("Browser unavailable: ChatGPT cookie secret is missing")
            return

        cookies = parse_netscape_cookies(self.settings.cookies_netscape)
        if not cookies:
            self.startup_error = "CHATGPT_COOKIES_NETSCAPE contains no valid cookies"
            LOGGER.error("Browser unavailable: cookie secret contains no valid entries")
            return

        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.settings.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                ],
            )
            self.context = await self.browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
            )
            await self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            accepted = 0
            for cookie in cookies:
                try:
                    await self.context.add_cookies([cookie])
                    accepted += 1
                except Exception:
                    LOGGER.warning("Skipped one invalid cookie entry")
            if accepted == 0:
                raise RuntimeError("No cookie entries could be loaded")

            self.page = await self.context.new_page()
            self.page.set_default_timeout(5_000)
            await self.page.goto(
                "https://chatgpt.com/",
                wait_until="domcontentloaded",
                timeout=int(self.settings.ready_timeout_seconds * 1000),
            )
            if not await self.find_input(self.settings.ready_timeout_seconds):
                raise RuntimeError("ChatGPT input was not found; session may be expired")
            self.ready = True
            self.startup_error = None
            LOGGER.info("ChatGPT browser gateway is ready; loaded %d cookies", accepted)
        except Exception as exc:
            self.startup_error = self._safe_error(exc)
            LOGGER.exception("Browser gateway failed during startup")
            await self.close()

    async def close(self) -> None:
        self.ready = False
        if self.context is not None:
            try:
                await self.context.close()
            except Exception:
                LOGGER.debug("Ignoring browser context cleanup error", exc_info=True)
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                LOGGER.debug("Ignoring browser cleanup error", exc_info=True)
        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                LOGGER.debug("Ignoring Playwright cleanup error", exc_info=True)
        self.context = None
        self.browser = None
        self.playwright = None
        self.page = None

    async def find_input(self, timeout_seconds: float = 15) -> Any | None:
        if self.page is None:
            return None
        selectors = (
            "#prompt-textarea",
            'textarea[placeholder*="Message" i]',
            'textarea[placeholder*="message" i]',
            'textarea[data-id="root"]',
            'textarea[id*="prompt" i]',
            'textarea',
            'div[contenteditable="true"]',
        )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for selector in selectors:
                try:
                    locator = self.page.locator(selector)
                    count = await locator.count()
                    for index in range(count):
                        candidate = locator.nth(index)
                        if await candidate.is_visible():
                            return candidate
                except Exception:
                    continue
            await asyncio.sleep(0.5)
        return None

    async def new_chat(self) -> dict[str, Any]:
        async with self.lock:
            if not self.ready or self.page is None:
                return {"success": False, "error": self.startup_error or "Browser is not ready"}
            try:
                await self.page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60_000)
                if not await self.find_input(20):
                    raise RuntimeError("ChatGPT input was not found after starting a new chat")
                return {"success": True, "message": "New chat started"}
            except Exception as exc:
                self.ready = False
                self.startup_error = self._safe_error(exc)
                return {"success": False, "error": self.startup_error}

    async def send_message(self, prompt: str) -> dict[str, Any]:
        async with self.lock:
            if not self.ready or self.page is None:
                return {"success": False, "error": self.startup_error or "Browser is not ready"}
            try:
                input_box = await self.find_input(15)
                if input_box is None:
                    raise RuntimeError("Could not find ChatGPT input")
                await input_box.click()
                await input_box.fill("")
                await input_box.fill(prompt)
                await input_box.press("Enter")
                self.last_request_at = time.time()

                response = await self._wait_for_response(prompt)
                return {"success": True, "response": response, "prompt": prompt}
            except Exception as exc:
                LOGGER.exception("ChatGPT request failed")
                return {"success": False, "error": self._safe_error(exc)}

    async def _wait_for_response(self, prompt: str) -> str:
        if self.page is None:
            raise RuntimeError("Browser page is unavailable")
        last_text = ""
        stable_samples = 0
        deadline = time.monotonic() + self.settings.request_timeout_seconds
        while time.monotonic() < deadline:
            current_text = await self._extract_response(prompt)
            generation_active = await self._generation_active()
            if current_text and current_text == last_text and not generation_active:
                stable_samples += 1
            else:
                stable_samples = 0
                if current_text:
                    last_text = current_text
            if last_text and stable_samples >= 4 and not generation_active:
                return last_text.strip()
            await asyncio.sleep(1)
        if last_text:
            return last_text.strip()
        raise TimeoutError("ChatGPT response did not stabilize before timeout")

    async def _generation_active(self) -> bool:
        if self.page is None:
            return False
        try:
            return await self.page.locator(
                'button[data-testid="stop-button"], button[aria-label*="Stop" i]'
            ).count() > 0
        except Exception:
            return False

    async def _extract_response(self, prompt: str) -> str:
        if self.page is None:
            return ""
        selectors = (
            '[data-message-author-role="assistant"]',
            "main .agent-turn .markdown",
            'main [data-message-author-role="assistant"] .markdown',
            "main .markdown",
        )
        for selector in selectors:
            try:
                messages = self.page.locator(selector)
                count = await messages.count()
                if count:
                    text = (await messages.nth(count - 1).inner_text(timeout=3_000)).strip()
                    if text:
                        return self._clean_response(text, prompt)
            except Exception:
                continue
        try:
            body = await self.page.locator("body").inner_text(timeout=3_000)
            return self._clean_response(body, prompt)
        except Exception:
            return ""

    @staticmethod
    def _clean_response(text: str, prompt: str) -> str:
        cleaned = text.strip()
        if prompt.strip() in cleaned:
            cleaned = cleaned.split(prompt.strip(), 1)[-1].strip()
        for footer in (
            "ChatGPT can make mistakes. Check important info.",
            "\nThink\n",
            "\nAsk anything",
        ):
            cleaned = cleaned.split(footer, 1)[0].strip()
        return cleaned

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc).strip().replace("\n", " ")
        return message[:500] or exc.__class__.__name__


def browser_settings_from_env() -> BrowserSettings:
    return BrowserSettings(
        cookies_netscape=os.getenv("CHATGPT_COOKIES_NETSCAPE", ""),
        profile_path=os.getenv("CHATGPT_PROFILE_PATH", ""),
        headless=os.getenv("CHATGPT_HEADLESS", "true").lower() in {"1", "true", "yes"},
        request_timeout_seconds=float(os.getenv("CHATGPT_REQUEST_TIMEOUT", "210")),
        ready_timeout_seconds=float(os.getenv("CHATGPT_READY_TIMEOUT", "180")),
    )
