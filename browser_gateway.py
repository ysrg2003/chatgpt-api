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
    storage_state_json: str
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
        storage_state: dict[str, Any] | None = None
        storage_state_text = self.settings.storage_state_json.strip()
        if storage_state_text:
            try:
                parsed_state = json.loads(storage_state_text)
                if not isinstance(parsed_state, dict) or not isinstance(parsed_state.get("cookies", []), list):
                    raise ValueError("storage state must be a JSON object with a cookies array")
                storage_state = parsed_state
            except Exception as exc:
                self.startup_error = f"CHATGPT_STORAGE_STATE_JSON is invalid: {self._safe_error(exc)}"
                LOGGER.error("Browser unavailable: storage state secret is invalid")
                return

        cookies = parse_netscape_cookies(self.settings.cookies_netscape)
        if storage_state is None and not cookies:
            self.startup_error = "CHATGPT_COOKIES_NETSCAPE or CHATGPT_STORAGE_STATE_JSON is required"
            LOGGER.error("Browser unavailable: no session state secret is configured")
            return

        try:
            self.playwright = await async_playwright().start()
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ]
            user_agent = (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            if storage_state is not None:
                self.browser = await self.playwright.chromium.launch(
                    headless=self.settings.headless,
                    args=launch_args,
                )
                self.context = await self.browser.new_context(
                    storage_state=storage_state,
                    user_agent=user_agent,
                    viewport={"width": 1440, "height": 900},
                )
            elif self.settings.profile_path:
                os.makedirs(self.settings.profile_path, exist_ok=True)
                self.context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=self.settings.profile_path,
                    headless=self.settings.headless,
                    args=launch_args,
                    user_agent=user_agent,
                    viewport={"width": 1440, "height": 900},
                )
                self.browser = None
            else:
                self.browser = await self.playwright.chromium.launch(
                    headless=self.settings.headless,
                    args=launch_args,
                )
                self.context = await self.browser.new_context(
                    user_agent=user_agent,
                    viewport={"width": 1440, "height": 900},
                )
            await self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            accepted = len(storage_state.get("cookies", [])) if storage_state is not None else 0
            if storage_state is None:
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

    async def session_diagnostics(self) -> dict[str, Any]:
        """Return redacted browser/session signals for authorized operational diagnosis."""
        result: dict[str, Any] = {
            "ready": self.ready,
            "startup_error": self.startup_error,
            "page_url": "",
            "page_title": "",
            "cookie_count": 0,
            "cookie_names": [],
            "input_visible": False,
            "stop_control_count": 0,
            "assistant_count": 0,
            "markers": {},
        }
        if self.context is not None:
            try:
                cookies = await self.context.cookies("https://chatgpt.com/")
                result["cookie_count"] = len(cookies)
                result["cookie_names"] = sorted({str(cookie.get("name", "")) for cookie in cookies if cookie.get("name")})
            except Exception:
                result["cookie_names"] = []
        if self.page is None:
            return result
        try:
            result["page_url"] = self.page.url
            result["page_title"] = (await self.page.title())[:120]
            result["input_visible"] = bool(await self.find_input(1))
            result["stop_control_count"] = await self.page.locator(
                'button[data-testid="stop-button"], button[aria-label*="Stop" i]'
            ).count()
            result["assistant_count"] = await self._assistant_count()
            body_text = (await self.page.locator("body").inner_text(timeout=3_000)).lower()
            for marker in ("log in", "تسجيل الدخول", "session expired", "انتهت الجلسة", "challenge", "verify", "something went wrong"):
                result["markers"][marker] = marker in body_text
            visible_auth_controls: set[str] = set()
            visible_auth_details: list[dict[str, Any]] = []
            for selector in ("button", "a"):
                controls = self.page.locator(selector)
                for index in range(min(await controls.count(), 80)):
                    control = controls.nth(index)
                    try:
                        if not await control.is_visible():
                            continue
                        aria_hidden = (await control.get_attribute("aria-hidden") or "").lower()
                        box = await control.bounding_box()
                        label = " ".join((await control.inner_text(timeout=500)).strip().lower().split())
                    except Exception:
                        continue
                    if aria_hidden == "true" or not box or box["width"] < 2 or box["height"] < 2:
                        continue
                    for marker in ("log in", "sign up", "continue with", "get started", "تسجيل الدخول", "إنشاء حساب"):
                        if marker in label:
                            visible_auth_controls.add(marker)
                            visible_auth_details.append(
                                {
                                    "marker": marker,
                                    "tag": selector,
                                    "href_present": bool(await control.get_attribute("href")),
                                    "box": {"width": round(box["width"], 1), "height": round(box["height"], 1)},
                                }
                            )
            result["visible_auth_controls"] = sorted(visible_auth_controls)
            result["visible_auth_details"] = visible_auth_details[:10]
        except Exception as exc:
            result["diagnostic_error"] = self._safe_error(exc)
        return result

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
                await self.playwright.stop()
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
                await self._open_fresh_conversation()
                return {"success": True, "message": "New chat started"}
            except Exception as exc:
                self.ready = False
                self.startup_error = self._safe_error(exc)
                return {"success": False, "error": self.startup_error}

    async def _open_fresh_conversation(self) -> None:
        if self.page is None:
            raise RuntimeError("Browser page is unavailable")
        clicked = False
        for label in ("New chat", "دردشة جديدة"):
            try:
                links = self.page.locator("a").filter(has_text=label)
                for index in range(await links.count()):
                    candidate = links.nth(index)
                    if await candidate.is_visible() and await candidate.is_enabled():
                        await candidate.click(timeout=8_000)
                        clicked = True
                        break
                if clicked:
                    break
            except Exception:
                continue
        if not clicked:
            await self.page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60_000)
        else:
            await self.page.wait_for_load_state("domcontentloaded", timeout=30_000)
        self.image_data_cache.clear()
        if not await self.find_input(20):
            raise RuntimeError("ChatGPT input was not found after starting a fresh conversation")

    async def send_message(self, prompt: str, *, capture_images: bool = False) -> dict[str, Any]:
        async with self.lock:
            if not self.ready or self.page is None:
                return {"success": False, "error": self.startup_error or "Browser is not ready"}
            session_state = await self.session_diagnostics()
            visible_auth_controls = session_state.get("visible_auth_controls", [])
            if visible_auth_controls:
                return {
                    "success": False,
                    "error": "ChatGPT session requires re-authentication; visible auth control detected",
                }
            recovered_timeout = False
            try:
                for request_attempt in range(2):
                    if not self.ready or self.page is None:
                        return {"success": False, "error": self.startup_error or "Browser recovery failed"}
                    if await self._generation_active():
                        LOGGER.warning(
                            "ChatGPT page still reports an active generation before a new request; attempting recovery"
                        )
                        await self._recover_after_timeout()
                        if not self.ready or self.page is None:
                            return {"success": False, "error": self.startup_error or "Browser recovery failed"}
                    previous_count = await self._assistant_count()
                    previous_text = await self._latest_assistant_text()
                    previous_image_sources = await self._image_sources() if capture_images else []
                    await self._submit_prompt(prompt, previous_count)
                    self.last_request_at = time.time()
                    response_timeout = max(
                        self.settings.request_timeout_seconds,
                        540.0 if capture_images else self.settings.request_timeout_seconds,
                    )
                    try:
                        response_text, images = await self._wait_for_response(
                            prompt,
                            previous_count,
                            previous_text,
                            previous_image_sources,
                            capture_images,
                            timeout_seconds=response_timeout,
                        )
                        return {"success": True, "response": response_text, "images": images, "prompt": prompt}
                    except TimeoutError:
                        await self._recover_after_timeout()
                        recovered_timeout = True
                        if request_attempt == 0 and self.ready and self.page is not None:
                            LOGGER.warning("ChatGPT request timed out; retrying once after fresh-conversation recovery")
                            continue
                        raise
                return {"success": False, "error": "ChatGPT request did not complete after recovery retry"}
            except Exception as exc:
                if isinstance(exc, TimeoutError) and not recovered_timeout:
                    await self._recover_after_timeout()
                LOGGER.exception("ChatGPT request failed")
                return {"success": False, "error": self._safe_error(exc)}

    async def _submit_prompt(self, prompt: str, previous_count: int) -> None:
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
                tag_name = await input_box.evaluate("(el) => el.tagName.toLowerCase()")
                if tag_name == "div":
                    try:
                        await input_box.fill(prompt, timeout=8_000)
                    except Exception:
                        await input_box.press_sequentially(prompt, delay=5, timeout=12_000)
                    current_content = await input_box.evaluate(
                        "(el) => String(el.innerText ?? el.textContent ?? '')"
                    )
                    if current_content.strip() != prompt.strip():
                        await input_box.press_sequentially(prompt, delay=5, timeout=12_000)
                    await input_box.dispatch_event("input", {"inputType": "insertText", "data": prompt})
                else:
                    await input_box.fill(prompt, timeout=8_000)
                await asyncio.sleep(0.2)
                await input_box.focus()
                await self.page.keyboard.press("Enter", delay=20)
                await asyncio.sleep(1.2)
                enter_started_generation = await self._generation_active()
                enter_created_assistant = await self._assistant_count() > previous_count
                if enter_started_generation or enter_created_assistant:
                    LOGGER.info(
                        "ChatGPT prompt submitted with Enter; generation=%s assistant_count_increased=%s",
                        enter_started_generation,
                        enter_created_assistant,
                    )
                else:
                    send_button = self.page.locator(
                        '#composer-submit-button, '
                        'button[data-testid="send-button"], '
                        'button[aria-label*="Send prompt" i], '
                        'button[aria-label="Send" i], '
                        'button[aria-label*="إرسال" i]'
                    )
                    sent_by_button = False
                    for send_index in range(await send_button.count()):
                        candidate_send = send_button.nth(send_index)
                        if await candidate_send.is_visible() and await candidate_send.is_enabled():
                            try:
                                await candidate_send.click(timeout=8_000)
                            except Exception:
                                await candidate_send.click(timeout=8_000, force=True)
                            await asyncio.sleep(1.0)
                            if not await self._submission_started(previous_count):
                                try:
                                    await candidate_send.evaluate("(el) => el.click()")
                                    await asyncio.sleep(1.0)
                                except Exception as dom_click_exc:
                                    LOGGER.debug("DOM send fallback failed: %s", self._safe_error(dom_click_exc))
                            if not await self._submission_started(previous_count):
                                try:
                                    button_box = await candidate_send.bounding_box()
                                    if button_box:
                                        await self.page.mouse.click(
                                            button_box["x"] + button_box["width"] / 2,
                                            button_box["y"] + button_box["height"] / 2,
                                        )
                                        await asyncio.sleep(1.0)
                                        LOGGER.info("ChatGPT send fallback repeated with page mouse click")
                                except Exception as mouse_exc:
                                    LOGGER.debug("Page mouse send fallback failed: %s", self._safe_error(mouse_exc))
                            sent_by_button = await self._submission_started(previous_count)
                            if sent_by_button:
                                LOGGER.info("ChatGPT prompt submitted with explicit send button fallback")
                                break
                            LOGGER.warning("ChatGPT send button did not submit or clear the composer")
                    if not sent_by_button:
                        raise RuntimeError("ChatGPT send control did not submit the prompt")
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

    async def _recover_after_timeout(self) -> None:
        """Stop stale state and open a fresh conversation before the next request."""
        if self.page is None:
            return
        try:
            stop_button = self.page.locator(
                'button[data-testid="stop-button"], button[aria-label*="Stop" i]'
            )
            for index in range(await stop_button.count()):
                candidate = stop_button.nth(index)
                if await candidate.is_visible() and await candidate.is_enabled():
                    try:
                        await candidate.click(timeout=5_000)
                    except Exception:
                        await candidate.click(timeout=5_000, force=True)
                    await asyncio.sleep(0.5)
                    break
        except Exception:
            LOGGER.debug("Could not click ChatGPT stop control during recovery", exc_info=True)
        try:
            # Reloading the same conversation can preserve the broken DOM/session state.
            # Always navigate to the ChatGPT root after a timeout so the next request
            # starts in a fresh conversation, even when the stop control disappeared.
            LOGGER.warning("ChatGPT recovery: opening a fresh conversation after timeout")
            await self._open_fresh_conversation()
            self.ready = True
            self.startup_error = None
        except Exception as exc:
            self.ready = False
            self.startup_error = self._safe_error(exc)
            LOGGER.error("ChatGPT generation recovery failed: %s", self.startup_error)

    async def _wait_for_response(
        self,
        prompt: str,
        previous_count: int,
        previous_text: str,
        previous_image_sources: list[str],
        capture_images: bool,
        timeout_seconds: float | None = None,
    ) -> tuple[str, list[dict[str, str]]]:
        if self.page is None:
            raise RuntimeError("Browser page is unavailable")
        last_text = ""
        last_images: list[dict[str, str]] = []
        last_image_signature = ""
        stable_samples = 0
        image_stable_samples = 0
        deadline = time.monotonic() + (timeout_seconds or self.settings.request_timeout_seconds)
        while time.monotonic() < deadline:
            current_text, current_images = await self._extract_response(
                prompt, previous_count, previous_text, previous_image_sources, capture_images
            )
            generation_active = await self._generation_active()
            image_signature = "|".join(item.get("src", "") for item in current_images)
            changed = bool(current_text or current_images)
            if current_text and not generation_active and (
                current_text != previous_text or await self._assistant_count() > previous_count
            ):
                return current_text.strip(), current_images
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
        try:
            input_box = self.page.locator("#prompt-textarea")
            input_count = await input_box.count()
            input_lengths = []
            for index in range(min(input_count, 2)):
                input_lengths.append(str(len(await input_box.nth(index).evaluate("(el) => String(el.value ?? el.innerText ?? el.textContent ?? '')"))))
            parts.append(f"prompt_count={input_count},prompt_lengths={','.join(input_lengths)}")
        except Exception:
            parts.append("prompt_diagnostic=error")
        try:
            send_buttons = self.page.locator("#composer-submit-button")
            send_count = await send_buttons.count()
            send_states = []
            for index in range(min(send_count, 2)):
                button = send_buttons.nth(index)
                send_states.append(f"{await button.is_visible()}/{await button.is_enabled()}")
            parts.append(f"send_button_count={send_count},send_states={','.join(send_states)}")
        except Exception:
            parts.append("send_button_diagnostic=error")
        return " ".join(parts)

    async def _submission_started(self, previous_count: int) -> bool:
        if self.page is None:
            return False
        if await self._generation_active() or await self._assistant_count() > previous_count:
            return True
        try:
            input_box = self.page.locator("#prompt-textarea")
            count = await input_box.count()
            if count == 0:
                return True
            value = await input_box.first().evaluate("(el) => String(el.value ?? el.innerText ?? el.textContent ?? '')")
            return not value.strip()
        except Exception:
            return False

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

    async def _image_sources(self) -> list[str]:
        if self.page is None:
            return []
        try:
            images = self.page.locator("main img")
            sources: list[str] = []
            for index in range(await images.count()):
                src = (await images.nth(index).evaluate(
                    "(node) => node.currentSrc || node.src || node.getAttribute('data-src') || ''"
                ) or "").strip()
                if src and src not in sources:
                    sources.append(src)
            return sources
        except Exception:
            return []

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
        previous_image_sources: list[str],
        capture_images: bool,
    ) -> tuple[str, list[dict[str, str]]]:
        if self.page is None:
            return "", []
        try:
            global_images = (
                                await self._extract_images(
                    self.page.locator("main"),
                    allow_unlabeled=True,
                    exclude_sources=set(previous_image_sources),
                )
                if capture_images
                else []

            )
            messages = self.page.locator('[data-message-author-role="assistant"]')
            count = await messages.count()
            if count:
                latest = messages.nth(count - 1)
                text = (await latest.inner_text(timeout=3_000)).strip()
                images = (
                    await self._extract_images(
                        latest,
                        allow_unlabeled=True,
                        exclude_sources=set(previous_image_sources),
                    )
                    if capture_images
                    else []
                ) or global_images
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
            if self.context is not None:
                response = await self.context.request.get(src, timeout=30_000)
                if response.ok:
                    body = await response.body()
                    mime_type = (response.headers.get("content-type") or "image/png").split(";", 1)[0]
                    if mime_type.startswith("image/") and body:
                        data_url = f"data:{mime_type};base64,{base64.b64encode(body).decode('ascii')}"
                        self.image_data_cache[src] = data_url
                        return data_url
        except Exception:
            LOGGER.debug("Context request could not download generated image", exc_info=True)
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
    def _is_generated_image_candidate(
        src: str,
        alt: str,
        *,
        allow_unlabeled: bool = False,
        width: int = 0,
        height: int = 0,
    ) -> bool:
        source = src.lower()
        description = alt.lower()
        blocked_markers = ("favicon", "avatar", "profile", "logo", "icon", "emoji", "thumbnail")
        if not src or any(marker in source or marker in description for marker in blocked_markers):
            return False
        if src.startswith("blob:"):
            return True
        if "generated image" in description or "generated_image" in description:
            return True
        if "backend-api" in source and any(marker in source for marker in ("file_", "estuary", "/content", "/files/")):
            return True
        if allow_unlabeled and src.startswith(("https://", "http://")) and (
            "chatgpt.com/backend-api/" in source or "oaidalle" in source
        ):
            return True
        if allow_unlabeled and src.startswith("data:image/") and width >= 64 and height >= 64:
            return True
        return False

    async def _extract_images(
        self,
        container: Any,
        *,
        allow_unlabeled: bool = False,
        exclude_sources: set[str] | None = None,
    ) -> list[dict[str, str]]:
        images: list[dict[str, str]] = []
        seen: set[str] = set()
        try:
            image_locators = container.locator("img")
            count = await image_locators.count()
            excluded = exclude_sources or set()
            for index in range(count):
                image = image_locators.nth(index)
                src = (await image.evaluate("(node) => node.currentSrc || node.src || node.getAttribute('data-src') || ''") or "").strip()
                if not src:
                    try:
                        src = (await image.locator("xpath=ancestor::a[1]").get_attribute("href") or "").strip()
                    except Exception:
                        src = ""
                if not src or src in seen or src in excluded:
                    continue
                alt = (await image.get_attribute("alt") or "").strip()
                try:
                    dimensions = await image.evaluate(
                        "(node) => ({width: node.naturalWidth || 0, height: node.naturalHeight || 0})"
                    )
                    width = int(dimensions.get("width", 0)) if isinstance(dimensions, dict) else 0
                    height = int(dimensions.get("height", 0)) if isinstance(dimensions, dict) else 0
                except Exception:
                    width = height = 0
                if not self._is_generated_image_candidate(
                    src, alt, allow_unlabeled=allow_unlabeled, width=width, height=height
                ):
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
    def _is_image_quota_message(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in ("free plan limit", "image generations requests", "limit resets"))

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        message = str(exc).strip().replace("\n", " ")
        return message[:500] or exc.__class__.__name__


def browser_settings_from_env() -> BrowserSettings:
    return BrowserSettings(
        cookies_netscape=os.getenv("CHATGPT_COOKIES_NETSCAPE", ""),
        storage_state_json=os.getenv("CHATGPT_STORAGE_STATE_JSON", ""),
        profile_path=os.getenv("CHATGPT_PROFILE_PATH", "/tmp/chatgpt-profile"),
        headless=os.getenv("CHATGPT_HEADLESS", "true").lower() in {"1", "true", "yes"},
        request_timeout_seconds=float(os.getenv("CHATGPT_REQUEST_TIMEOUT", "210")),
        ready_timeout_seconds=float(os.getenv("CHATGPT_READY_TIMEOUT", "180")),
    )
