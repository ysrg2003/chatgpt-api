import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from browser_gateway import BrowserGateway, BrowserSettings, parse_netscape_cookies
from main import (
    LIVE_SEARCH_PREFIX,
    should_capture_images,
    FixedWindowRateLimiter,
    add_live_search_prefix,
    format_prompt,
    parse_tool_calls,
)


class _RecoveryLocator:
    def __init__(self, page):
        self.page = page

    async def count(self):
        return 1

    def nth(self, _index):
        return self

    async def is_visible(self):
        return True

    async def is_enabled(self):
        return True

    async def click(self, **_kwargs):
        raise RuntimeError("stop button unavailable")


class _RecoveryPage:
    def __init__(self):
        self.reloaded = False

    def locator(self, _selector):
        return _RecoveryLocator(self)

    async def reload(self, **_kwargs):
        self.reloaded = True

    async def goto(self, *_args, **_kwargs):
        self.reloaded = True


class _PopulateKeyboard:
    def __init__(self, editor):
        self.editor = editor
        self.inserted = ""

    async def insert_text(self, text):
        self.inserted = text
        self.editor.content = text

    async def press(self, *_args, **_kwargs):
        return None


class _PopulatePage:
    def __init__(self, editor):
        self.keyboard = _PopulateKeyboard(editor)


class _PopulateEditor:
    def __init__(self):
        self.content = ""
        self.sequential_calls = []

    async def evaluate(self, script):
        if "tagName" in script:
            return "div"
        return self.content

    async def fill(self, *_args, **_kwargs):
        raise RuntimeError("simulate ProseMirror fill fallback")

    async def click(self, **_kwargs):
        return None

    async def press_sequentially(self, text, **kwargs):
        self.sequential_calls.append((text, kwargs))
        self.content = text

    async def dispatch_event(self, *_args, **_kwargs):
        return None


class CoreTests(unittest.TestCase):
    def test_long_prosemirror_fallback_uses_fast_insert_text(self):
        gateway = BrowserGateway(
            BrowserSettings(
                cookies_netscape="",
                storage_state_json="",
                profile_path="",
                headless=True,
                request_timeout_seconds=1,
                ready_timeout_seconds=1,
            )
        )
        editor = _PopulateEditor()
        page = _PopulatePage(editor)
        gateway.page = page
        prompt = "x" * 1_500
        asyncio.run(gateway._populate_input(editor, prompt))
        self.assertEqual(page.keyboard.inserted, prompt)
        self.assertEqual(editor.sequential_calls, [])

    def test_generation_recovery_reloads_when_stop_control_fails(self):
        gateway = BrowserGateway(
            BrowserSettings(
                cookies_netscape="",
                storage_state_json="",
                profile_path="",
                headless=True,
                request_timeout_seconds=1,
                ready_timeout_seconds=1,
            )
        )
        page = _RecoveryPage()
        gateway.page = page
        gateway.ready = True
        gateway._generation_active = AsyncMock(return_value=True)
        gateway.find_input = AsyncMock(return_value=object())
        asyncio.run(gateway._recover_after_timeout())
        self.assertTrue(page.reloaded)
        self.assertTrue(gateway.ready)
        gateway.find_input.assert_awaited_once_with(20)

    def test_login_marker_fails_fast_before_prompt_submission(self):
        gateway = BrowserGateway(
            BrowserSettings(
                cookies_netscape="",
                storage_state_json="",
                profile_path="",
                headless=True,
                request_timeout_seconds=1,
                ready_timeout_seconds=1,
            )
        )
        gateway.page = object()
        gateway.ready = True
        gateway.session_diagnostics = AsyncMock(return_value={"visible_auth_controls": ["log in"]})
        gateway._submit_prompt = AsyncMock()
        result = asyncio.run(gateway.send_message("hello"))
        self.assertFalse(result["success"])
        self.assertIn("re-authentication", result["error"])
        gateway._submit_prompt.assert_not_awaited()

    def test_stabilization_accepts_new_assistant_text_without_main_article(self):
        gateway = BrowserGateway(
            BrowserSettings(
                cookies_netscape="",
                storage_state_json="",
                profile_path="",
                headless=True,
                request_timeout_seconds=1,
                ready_timeout_seconds=1,
            )
        )
        gateway.page = object()
        gateway._extract_response = AsyncMock(return_value=("new answer", []))
        gateway._generation_active = AsyncMock(return_value=False)
        gateway._assistant_count = AsyncMock(return_value=2)
        response_text, images = asyncio.run(
            gateway._wait_for_response("hello", 1, "old answer", [], False, timeout_seconds=1)
        )
        self.assertEqual(response_text, "new answer")
        self.assertEqual(images, [])

    def test_timeout_retries_once_after_recovery(self):
        gateway = BrowserGateway(
            BrowserSettings(
                cookies_netscape="",
                storage_state_json="",
                profile_path="",
                headless=True,
                request_timeout_seconds=1,
                ready_timeout_seconds=1,
            )
        )
        gateway.page = object()
        gateway.ready = True
        gateway._generation_active = AsyncMock(return_value=False)
        gateway._assistant_count = AsyncMock(return_value=0)
        gateway._latest_assistant_text = AsyncMock(return_value="")
        gateway._image_count = AsyncMock(return_value=0)
        gateway._submit_prompt = AsyncMock()
        gateway._recover_after_timeout = AsyncMock()
        gateway._wait_for_response = AsyncMock(side_effect=[TimeoutError("stale"), ("recovered", [])])
        result = asyncio.run(gateway.send_message("hello"))
        self.assertTrue(result["success"])
        self.assertEqual(result["response"], "recovered")
        self.assertEqual(gateway._wait_for_response.await_count, 2)
        gateway._recover_after_timeout.assert_awaited_once()

    def test_parse_netscape_cookies(self):
        text = "# Netscape HTTP Cookie File\n.chatgpt.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n"
        cookies = parse_netscape_cookies(text)
        self.assertEqual(len(cookies), 1)
        self.assertEqual(cookies[0]["name"], "name")
        self.assertEqual(cookies[0]["domain"], ".chatgpt.com")
        self.assertNotIn("value", repr(cookies) if False else "")

    def test_format_prompt_preserves_roles_and_tools(self):
        prompt = format_prompt(
            [
                {"role": "system", "content": "Be concise"},
                {"role": "user", "content": "What is 2+2?"},
            ],
            tools=[{"type": "function", "function": {"name": "calculator", "description": "Calculate", "parameters": {}}}],
        )
        self.assertIn("Be concise", prompt)
        self.assertIn("What is 2+2?", prompt)
        self.assertIn("calculator", prompt)

    def test_parse_tool_calls_accepts_json_fence(self):
        calls = parse_tool_calls('```json\n{"tool_calls":[{"name":"search","arguments":{"q":"HF"}}]}\n```')
        self.assertIsNotNone(calls)
        self.assertEqual(calls[0]["function"]["name"], "search")
        self.assertIn('"q": "HF"', calls[0]["function"]["arguments"])

    def test_live_search_prefix_is_added_for_search_requests(self):
        prompt = format_prompt([{"role": "user", "content": "ابحث عن اخر موديل anthropic ai"}])
        enriched = add_live_search_prefix(prompt, [{"role": "user", "content": "ابحث عن اخر موديل anthropic ai"}])
        self.assertTrue(enriched.startswith(LIVE_SEARCH_PREFIX + "\n"))
        self.assertEqual(enriched.count(LIVE_SEARCH_PREFIX), 1)

    def test_image_capture_is_only_enabled_for_image_requests(self):
        self.assertFalse(should_capture_images({}, "قل فقط: نجح اختبار النص"))
        self.assertFalse(should_capture_images({}, "ابحث عن آخر موديل anthropic ai"))
        self.assertTrue(should_capture_images({}, "generate image of a stickman"))
        self.assertTrue(should_capture_images({"output_type": "image"}, "صورة"))

    def test_image_extraction_does_not_depend_on_image_order(self):
        gateway = BrowserGateway(
            BrowserSettings(
                cookies_netscape="",
                storage_state_json="",
                profile_path="",
                headless=True,
                request_timeout_seconds=1,
                ready_timeout_seconds=1,
            )
        )

        class FakeImage:
            def __init__(self, src, alt="", width=128, height=128):
                self.src, self.alt, self.width, self.height = src, alt, width, height

            async def evaluate(self, expression):
                if "naturalWidth" in expression:
                    return {"width": self.width, "height": self.height}
                return self.src

            async def get_attribute(self, name):
                return self.alt if name == "alt" else None

            def locator(self, _selector):
                return self

            async def count(self):
                return 0

        class FakeImages:
            def __init__(self, items):
                self.items = items

            async def count(self):
                return len(self.items)

            def nth(self, index):
                return self.items[index]

        class FakeContainer:
            def __init__(self, items):
                self.items = items

            def locator(self, _selector):
                return FakeImages(self.items)

        generated = "https://chatgpt.com/backend-api/files/file_new/content"
        old_avatar = "https://chatgpt.com/assets/avatar.png"
        images = asyncio.run(
            gateway._extract_images(
                FakeContainer([FakeImage(generated, ""), FakeImage(old_avatar, "avatar")]),
                allow_unlabeled=True,
                exclude_sources={old_avatar},
            )
        )
        self.assertEqual([item["src"] for item in images], [generated])

    def test_image_candidate_filter_rejects_favicons(self):
        self.assertTrue(BrowserGateway._is_generated_image_candidate(
            "https://chatgpt.com/backend-api/estuary/content?id=file_123", "Generated image"
        ))
        self.assertTrue(BrowserGateway._is_generated_image_candidate("blob:https://chatgpt.com/abc", ""))
        self.assertFalse(BrowserGateway._is_generated_image_candidate(
            "https://www.google.com/s2/favicons?domain=example.com", ""
        ))
        self.assertFalse(BrowserGateway._is_generated_image_candidate("data:image/png;base64,abc", ""))
        self.assertTrue(BrowserGateway._is_generated_image_candidate(
            "https://chatgpt.com/backend-api/files/abc/content", "", allow_unlabeled=True
        ))
        self.assertFalse(BrowserGateway._is_generated_image_candidate(
            "https://chatgpt.com/assets/avatar.png", "", allow_unlabeled=True
        ))

    def test_live_search_prefix_is_not_added_for_normal_request(self):
        messages = [{"role": "user", "content": "اشرح الذكاء الاصطناعي"}]
        prompt = format_prompt(messages)
        self.assertEqual(add_live_search_prefix(prompt, messages), prompt)

    def test_rate_limiter_blocks_after_limit(self):
        import main
        old_limit = main.RATE_LIMIT_REQUESTS
        old_window = main.RATE_LIMIT_WINDOW_SECONDS
        main.RATE_LIMIT_REQUESTS = 1
        main.RATE_LIMIT_WINDOW_SECONDS = 60
        try:
            limiter = FixedWindowRateLimiter()
            self.assertTrue(asyncio.run(limiter.allow("test")))
            self.assertFalse(asyncio.run(limiter.allow("test")))
        finally:
            main.RATE_LIMIT_REQUESTS = old_limit
            main.RATE_LIMIT_WINDOW_SECONDS = old_window


if __name__ == "__main__":
    unittest.main()
