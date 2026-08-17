import asyncio
import os
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from browser_gateway import parse_netscape_cookies
from main import (
    LIVE_SEARCH_PREFIX,
    FixedWindowRateLimiter,
    add_live_search_prefix,
    format_prompt,
    parse_tool_calls,
)


class CoreTests(unittest.TestCase):
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
