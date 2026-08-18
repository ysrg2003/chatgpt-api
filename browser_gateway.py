"""Single-session ChatGPT browser gateway.

All Playwright operations are serialized through one asyncio lock. The gateway is
intentionally isolated from HTTP and OpenAI-compatible response formatting.
"""
from __future__ import annotations

import asyncio
import base64
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
        self.last_request_at = 0.0
        self.startup_error: str | None = None
        self.image_data_cache: dict[str, str] = {}
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
                        classes = (await candidate.get_attribute("class") or "").lower()
                        if "fallbacktextarea" in classes or "fallback-textarea" in classes:
                            # ChatGPT's fallback editor is present in the DOM but is
                            # not interactive when the rich editor is active.
                            continue
                        if not await candidate.is_visible() or not await candidate.is_editable():
                            continue
                        try:
                            box = await candidate.bounding_box()
                            if not box or box["width"] < 4 or box["height"] < 4:
                                continue
                            # Some ChatGPT shells mark the real, visible ProseMirror
                            # editor as aria-hidden=true. Visibility, editability, and
                            # non-zero geometry are stronger interaction signals.
                            await candidate.scroll_into_view_if_needed(timeout=1_000)
                        except Exception:
                            continue
                        return candidate
                except Exception:
                    continue
            await asyncio.sleep(0.5)
        return None

    async def _input_diagnostics(self) -> str:
        if self.page is None:
            return "page=none"
        parts = [f"url={self.page.url}"]
        try:
            parts.append(f"title={(await self.page.title())[:80]}")
        except Exception:
            parts.append("title=unavailable")
        for selector in ("#prompt-textarea", "textarea", 'div[contenteditable="true"]'):
            try:
                locator = self.page.locator(selector)
                count = await locator.count()
                entries = []
                for index in range(min(count, 3)):
                    candidate = locator.nth(index)
                    try:
                        hidden = (await candidate.get_attribute("aria-hidden") or "").lower()
                        classes = (await candidate.get_attribute("class") or "")[:80]
                        visible = await candidate.is_visible()
                        editable = await candidate.is_editable()
                        box = await candidate.bounding_box()
                        geometry = "none" if not box else f"{int(box['width'])}x{int(box['height'])}"
                        entries.append(f"{index}:hidden={hidden},class={classes},visible={visible},editable={editable},box={geometry}")
                    except Exception:
                        entries.append(f"{index}:inspect=error")
                parts.append(f"{selector}:count={count}[{' | '.join(entries)}]")
            except Exception:
                parts.append(f"{selector}:count=error")
        return " ".join(parts)

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

    async def send_message(self, prompt: str, *, capture_images: bool = False) -> dict[str, Any]:
        async with self.lock:
            if not self.ready or self.page is None:
                return {"success": False, "error": self.startup_error or "Browser is not ready"}
            try:
                previous_count = await self._assistant_count()
                previous_text = await self._latest_assistant_text()
                previous_image_count = await self._image_count() if capture_images else 0
                submitted = False
                interaction_error = ""
                for attempt in range(2):
                    input_box = await self.find_input(10)
                    if input_box is None and self.page is not None:
                        try:
                            await self.page.reload(wait_until="domcontentloaded", timeout=45_000)
                        except Exception:
                            await self.page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=45_000)
                        input_box = await self.find_input(12)
                    if input_box is None:
                        continue
                    try:
                        try:
                            await input_box.click(timeout=8_000)
                        except Exception:
                            await input_box.click(timeout=8_000, force=True)
                        await input_box.fill(prompt, timeout=8_000)
                        await asyncio.sleep(0.2)
                        send_button = self.page.locator(
                            'button[data-testid="send-button"], '
                            'button[aria-label*="Send prompt" i], '
                            'button[aria-label="Send" i]'
                        )
                        sent_by_button = False
                        for send_index in range(await send_button.count()):
                            candidate_send = send_button.nth(send_index)
                            if await candidate_send.is_visible() and await candidate_send.is_enabled():
                                try:
                                    await candidate_send.click(timeout=8_000)
                                except Exception:
                                    await candidate_send.click(timeout=8_000, force=True)
                                sent_by_button = True
                                break
                        if not sent_by_button:
                            await input_box.press("Enter", timeout=8_000)
                        submitted = True
                        break
                    except Exception as exc:
                        interaction_error = self._safe_error(exc)[:240]
                        if attempt == 0 and self.page is not None:
                            try:
                                await self.page.reload(wait_until="domcontentloaded", timeout=45_000)
                            except Exception:
                                pass
                if not submitted:
                    diagnostic = await self._input_diagnostics()
                    if interaction_error:
                        diagnostic += f" interaction={interaction_error}"
                    LOGGER.warning("ChatGPT input interaction unavailable: %s", diagnostic)
                    raise RuntimeError(f"Could not interact with ChatGPT input ({diagnostic})")
                self.last_request_at = time.time()

                response_text, images = await self._wait_for_response(
                    prompt, previous_count, previous_text, previous_image_count, capture_images
                )
                return {"success": True, "response": response_text, "images": images, "prompt": prompt}
            except Exception as exc:
                LOGGER.exception("ChatGPT request failed")
                return {"success": False, "error": self._safe_error(exc)}

    async def _wait_for_response(
        self,
        prompt: str,
        previous_count: int,
        previous_text: str,
        previous_image_count: int,
        capture_images: bool,
    ) -> tuple[str, list[dict[str, str]]]:
        if self.page is None:
            raise RuntimeError("Browser page is unavailable")
        last_text = ""
        last_images: list[dict[str, str]] = []
        last_image_signature = ""
        stable_samples = 0
        image_stable_samples = 0
        deadline = time.monotonic() + self.settings.request_timeout_seconds
        while time.monotonic() < deadline:
            current_text, current_images = await self._extract_response(
                prompt, previous_count, previous_text, previous_image_count, capture_images
            )
            generation_active = await self._generation_active()
            image_signature = "|".join(item.get("src", "") for item in current_images)
            changed = bool(current_text or current_images)
            if current_images and image_signature == last_image_signature:
                image_stable_samples += 1
            else:
                image_stable_samples = 0
            if current_text and current_text == last_text and not generation_active:
                stable_samples += 1
            else:
                stable_samples = 0
            if changed and (current_text != last_text or image_signature != last_image_signature):
                last_text = current_text
                last_images = current_images
                last_image_signature = image_signature
            if current_images and image_stable_samples >= 3 and (not generation_active or image_stable_samples >= 8):
                return last_text.strip(), last_images
            if current_text and stable_samples >= 4 and not generation_active:
                return last_text.strip(), last_images
            await asyncio.sleep(1)
        if last_text or last_images:
            return last_text.strip(), last_images
        diagnostic = await self._response_diagnostics()
        raise TimeoutError(f"ChatGPT response did not stabilize before timeout ({diagnostic})")

    async def _response_diagnostics(self) -> str:
        if self.page is None:
            return "page=none"
        parts = []
        for selector in ('[data-message-author-role="assistant"]', "main article", "main"):
            try:
                locator = self.page.locator(selector)
                count = await locator.count()
                lengths = []
                for index in range(min(count, 3)):
                    try:
                        lengths.append(str(len(await locator.nth(index).inner_text(timeout=2_000))))
                    except Exception:
                        lengths.append("error")
                parts.append(f"{selector}:count={count},lengths={','.join(lengths)}")
            except Exception:
                parts.append(f"{selector}:error")
        parts.append(f"generation_active={await self._generation_active()}")
        return " ".join(parts)

    async def _generation_active(self) -> bool:
        if self.page is None:
            return False
        try:
            return await self.page.locator(
                'button[data-testid="stop-button"], button[aria-label*="Stop" i]'
            ).count() > 0
        except Exception:
            return False

    async def _image_count(self) -> int:
        if self.page is None:
            return 0
        try:
            return await self.page.locator("main img").count()
        except Exception:
            return 0

    async def _assistant_count(self) -> int:
        if self.page is None:
            return 0
        try:
            return await self.page.locator('[data-message-author-role="assistant"]').count()
        except Exception:
            return 0

    async def _latest_assistant_text(self) -> str:
        if self.page is None:
            return ""
        try:
            messages = self.page.locator('[data-message-author-role="assistant"]')
            count = await messages.count()
            if count:
                return (await messages.nth(count - 1).inner_text(timeout=3_000)).strip()
        except Exception:
            pass
        return ""

    async def _extract_response(
        self,
        prompt: str,
        previous_count: int,
        previous_text: str,
        previous_image_count: int,
        capture_images: bool,
    ) -> tuple[str, list[dict[str, str]]]:
        if self.page is None:
            return "", []
        try:
            global_images = (
                await self._extract_images(self.page.locator("main"), start_index=previous_image_count)
                if capture_images
                else []
            )
            messages = self.page.locator('[data-message-author-role="assistant"]')
            count = await messages.count()
            if count:
                latest = messages.nth(count - 1)
                text = (await latest.inner_text(timeout=3_000)).strip()
                images = (await self._extract_images(latest) if capture_images else []) or global_images
                if count > previous_count or text != previous_text or images:
                    return self._clean_response(text, prompt), images
                return "", []
            if global_images:
                return "", global_images
        except Exception:
            pass
        return "", []

    async def _download_image_data_url(self, src: str) -> str:
        if not src or self.page is None:
            return ""
        if src in self.image_data_cache:
            return self.image_data_cache[src]
        try:
            data_url = await self.page.evaluate(
                """
                async (url) => {
                    const response = await fetch(url, {credentials: 'include'});
                    if (!response.ok) throw new Error(`image fetch failed: ${response.status}`);
                    const blob = await response.blob();
                    const buffer = await blob.arrayBuffer();
                    const bytes = new Uint8Array(buffer);
                    let binary = '';
                    const chunk = 0x8000;
                    for (let i = 0; i < bytes.length; i += chunk) {
                        binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
                    }
                    return `data:${blob.type || 'image/png'};base64,${btoa(binary)}`;
                }
                """,
                src,
            )
            if isinstance(data_url, str) and data_url.startswith("data:"):
                self.image_data_cache[src] = data_url
                return data_url
        except Exception:
            LOGGER.warning("Could not download generated image inside browser session", exc_info=True)
        return ""

    @staticmethod
    def _is_generated_image_candidate(src: str, alt: str) -> bool:
        source = src.lower()
        description = alt.lower()
        if src.startswith("blob:"):
            return True
        if "generated image" in description or "generated_image" in description:
            return True
        if "backend-api" in source and ("file_" in source or "estuary" in source or "/content" in source):
            return True
        return src.startswith("data:") and "generated" in description

    async def _extract_images(self, container: Any, start_index: int = 0) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        seen: set[str] = set()
        try:
            image_locators = container.locator("img")
            count = await image_locators.count()
            for index in range(start_index, count):
                image = image_locators.nth(index)
                src = (await image.evaluate("(node) => node.currentSrc || node.src || node.getAttribute('data-src') || ''") or "").strip()
                if not src:
                    try:
                        src = (await image.locator("xpath=ancestor::a[1]").get_attribute("href") or "").strip()
                    except Exception:
                        src = ""
                if not src or src in seen:
                    continue
                alt = (await image.get_attribute("alt") or "").strip()
                if not self._is_generated_image_candidate(src, alt):
                    continue
                seen.add(src)
                item: dict[str, str] = {"src": src, "alt": alt}
                if src.startswith("blob:"):
                    try:
                        binary = await image.screenshot(type="png")
                        item["data_url"] = "data:image/png;base64," + base64.b64encode(binary).decode("ascii")
                    except Exception:
                        pass
                elif src.startswith("data:"):
                    item["data_url"] = src
                elif src.startswith(("http://", "https://")):
                    data_url = await self._download_image_data_url(src)
                    if data_url:
                        item["data_url"] = data_url
                images.append(item)
        except Exception:
            return images
        return images

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
