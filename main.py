import os
import uuid
import time
import asyncio
import threading
import json
import re
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


API_KEY = os.getenv("API_KEY", "CHANGE_ME_TO_A_STRONG_SECRET_KEY")


class AsyncBrowserThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        self.ready_event = threading.Event()
        self.playwright = None
        self.context = None

        self.request_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._start_called = False
        self.startup_error = None

    def run(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_browser())
        except Exception as e:
            self.startup_error = e
            self.ready_event.set()
            return

        self.ready_event.set()
        print("[LITE-SERVER] Browser ready")
        self.loop.run_forever()

    async def _start_browser(self):
        from playwright.async_api import async_playwright

        print("[LITE-SERVER] Starting browser...")
        self.playwright = await async_playwright().start()

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir="./chrome-profile-real",
            headless=True,
            channel="chrome",
            args=[
                "--profile-directory=Default",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage-for-fast-performance",
                "--disable-setuid-sandbox",
            ],
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        await self.context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # --- حقن الكوكيز مرة واحدة فقط هنا ---
        cookies_path = os.path.join(os.path.dirname(__file__), "chatgpt_cookies.txt")
        if os.path.exists(cookies_path):
            cookies = []
            with open(cookies_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.strip().split("\t")
                    if len(parts) >= 7:
                        domain, _, path, secure, expires, name, value = parts
                        cookies.append({
                            "name": name,
                            "value": value,
                            "domain": domain,
                            "path": path,
                            "expires": int(expires) if expires.isdigit() else -1,
                            "httpOnly": False,
                            "secure": secure.upper() == "TRUE",
                            "sameSite": "Lax"
                        })
            if cookies:
                await self.context.add_cookies(cookies)
                print(f"[LITE-SERVER] Injected {len(cookies)} cookies from chatgpt_cookies.txt")
                # أغلق كل الصفحات المفتوحة ليتم تفعيل الكوكيز
                if len(self.context.pages) > 5:
                    for page in self.context.pages:
                        try:
                            await page.close()
                        except Exception:
                            pass
        # --- نهاية حقن الكوكيز ---

        # --- نهاية حقن الكوكيز ---

        # Keepalive helpers (class-level methods)
    def start_keepalive(self, interval_seconds=86400):
        """Start a keepalive worker inside the browser thread's event loop that periodically
        navigates to chatgpt.com to refresh session cookies. Safe to call multiple times.
        """
        self._ensure_started()
        if getattr(self, "_keepalive_started", False):
            return
        self._keepalive_started = True
        try:
            asyncio.run_coroutine_threadsafe(self._keepalive_loop(interval_seconds), self.loop)
        except Exception as e:
            print("[LITE-SERVER] Failed to schedule keepalive:", e)

    async def _keepalive_loop(self, interval_seconds):
        # Wait until browser is ready
        while not self.ready_event.is_set():
            await asyncio.sleep(0.5)
        print(f"[LITE-SERVER] Keepalive loop started (interval={interval_seconds}s)")
        while True:
            try:
                page = await self.context.new_page()
                try:
                    await page.goto("https://chatgpt.com/", wait_until="networkidle", timeout=60000)
                    await asyncio.sleep(5)
                except Exception as e:
                    print("[LITE-SERVER] Keepalive navigation error:", e)
                try:
                    await page.close()
                except Exception:
                    pass
            except Exception as e:
                print("[LITE-SERVER] Keepalive error:", e)
                try:
                    await self._restart_browser()
                except Exception as ex:
                    print("[LITE-SERVER] Keepalive restart failed:", ex)
            await asyncio.sleep(interval_seconds)

    def do_one_keepalive(self, wait=True, timeout=60):
        """Trigger a single keepalive visit in the running browser context.
        Returns True on success, or raises/returns False on failure.
        """
        self._ensure_started()
        # Wait until browser is ready
        if not self.ready_event.wait(timeout=timeout):
            raise Exception("Browser not ready for keepalive")
        try:
            future = asyncio.run_coroutine_threadsafe(self._do_one_visit(), self.loop)
            if wait:
                return future.result(timeout=timeout)
            return True
        except Exception as e:
            print("[LITE-SERVER] do_one_keepalive failed:", e)
            return False

    async def _do_one_visit(self):
        try:
            page = await self.context.new_page()
            try:
                await page.goto("https://chatgpt.com/", wait_until="networkidle", timeout=60000)
                await asyncio.sleep(5)
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
            return True
        except Exception as e:
            print("[LITE-SERVER] _do_one_visit error:", e)
            raise

    def _ensure_started(self):
        with self._start_lock:
            if not self._start_called:
                self.start()
                self._start_called = True

    async def _talk_to_chatgpt(self, prompt: str):
        context = self.context
        if context is None:
            raise RuntimeError("Browser context is not initialized")

        # دائماً افتح صفحة جديدة لضمان تفعيل الكوكيز
        page = await context.new_page()

        try:
            page.set_default_timeout(600000)
            await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
            await self._wait_until_chat_ready(page)

            await page.fill("#prompt-textarea", prompt)
            await page.press("#prompt-textarea", "Enter")

            await page.wait_for_selector(
                '[data-message-author-role="assistant"]',
                timeout=600000,
            )

            last_text = ""
            unchanged_count = 0
            while unchanged_count < 4:
                messages = await page.query_selector_all(
                    '[data-message-author-role="assistant"]'
                )
                if messages:
                    current_text = await messages[-1].inner_text()
                    if current_text == last_text and current_text.strip() != "":
                        unchanged_count += 1
                    else:
                        last_text = current_text
                        unchanged_count = 0
                await asyncio.sleep(0.5)

            return last_text.strip()

        except Exception as e:
            print(f"[LITE-SERVER] Error: {e}")
            raise
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def _wait_until_chat_ready(self, page):
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_function("document.readyState === 'complete'")

        loading_selectors = [
            '[aria-busy="true"]',
            '[role="progressbar"]',
            '[data-testid*="loading"]',
        ]
        for sel in loading_selectors:
            try:
                await page.wait_for_selector(sel, state="hidden", timeout=5000)
            except Exception:
                pass

        await page.wait_for_selector("#prompt-textarea", state="visible", timeout=60000)
        await page.wait_for_function(
            """
            () => {
                const el = document.querySelector('#prompt-textarea');
                return !!el && !el.disabled && el.getAttribute('aria-disabled') !== 'true';
            }
            """
        )

    def process_request(self, prompt: str):
        self._ensure_started()

        if not self.ready_event.wait(timeout=60):
            raise Exception("Browser startup timed out")

        if self.startup_error is not None:
            raise Exception(f"Browser failed to start: {self.startup_error}")

        with self.request_lock:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._talk_to_chatgpt(prompt), self.loop
                )
                return future.result(timeout=1200)
            except Exception as e:
                error_msg = str(e)
                if (
                    "context" in error_msg and "closed" in error_msg
                ) or (
                    "browser" in error_msg and "closed" in error_msg
                ):
                    print("[LITE-SERVER] Detected closed browser/context, restarting...")
                    asyncio.run_coroutine_threadsafe(self._restart_browser(), self.loop).result(timeout=60)
                    # Retry once
                    future = asyncio.run_coroutine_threadsafe(
                        self._talk_to_chatgpt(prompt), self.loop
                    )
                    return future.result(timeout=1200)
                raise

    async def _restart_browser(self):
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        await self._start_browser()


browser_engine = AsyncBrowserThread()

jobs = {}
job_lock = threading.Lock()
job_executor = ThreadPoolExecutor(max_workers=2)


# ====================================================================
# Smart Prompt Builder
# ====================================================================
def format_prompt(messages, tools=None):
    parts = []
    system_parts = []
    has_tool_results = False
    user_question = ""

    for msg in messages:
        role = msg.get("role", "")
        msg_type = msg.get("type", "")
        content = msg.get("content", "")

        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    text_parts.append(item.get("text", item.get("content", str(item))))
                else:
                    text_parts.append(str(item))
            content = "\n".join(text_parts)

        if role == "system":
            system_parts.append(content)
        elif role == "tool":
            has_tool_results = True
            tool_name = msg.get("name", "tool")
            parts.append(f"[TOOL RESULT from '{tool_name}']:\n{content}")
        elif msg_type == "function_call_output":
            has_tool_results = True
            call_id = msg.get("call_id", "")
            output_content = msg.get("output", content)
            parts.append(f"[TOOL RESULT (call_id: {call_id})]:\n{output_content}")
        elif msg_type == "function_call":
            func_name = msg.get("name", "?")
            func_args = msg.get("arguments", "{}")
            parts.append(
                f"[PREVIOUS TOOL CALL: Called '{func_name}' with arguments: {func_args}]"
            )
        elif role == "assistant":
            assistant_content = content if content else ""
            tool_calls_in_msg = msg.get("tool_calls", [])
            if tool_calls_in_msg:
                tc_descriptions = []
                for tc in tool_calls_in_msg:
                    func = tc.get("function", {})
                    tc_descriptions.append(
                        f"Called '{func.get('name', '?')}' with: {func.get('arguments', '{}')}"
                    )
                assistant_content += "\n[Previous tool calls: " + "; ".join(tc_descriptions) + "]"
            if assistant_content.strip():
                parts.append(f"[Assistant]: {assistant_content}")
        elif role == "user" or (msg_type == "message" and role != "system"):
            user_question = content
            parts.append(content)
            has_tool_results = False
        elif content:
            parts.append(content)

    final = ""

    if system_parts:
        if tools and not has_tool_results:
            final += "=== YOUR ROLE ===\n"
            final += "\n\n".join(system_parts)
            final += "\n=== END OF ROLE ===\n\n"
        else:
            final += "=== SYSTEM INSTRUCTIONS (FOLLOW STRICTLY) ===\n"
            final += "\n\n".join(system_parts)
            final += "\n=== END OF INSTRUCTIONS ===\n\n"

    if tools and not has_tool_results:
        final += format_tools_instruction(tools, user_question)

    if has_tool_results:
        final += "=== CONTEXT FROM TOOLS ===\n"
        final += "The following information was retrieved by the tools you requested.\n"
        final += "Use ONLY this information to answer the user's question.\n\n"

    if parts:
        final += "\n".join(parts)

    if has_tool_results:
        final += "\n\n=== INSTRUCTION ===\n"
        final += "Now answer the user's question based ONLY on the tool results above.\n"

    return final


def format_tools_instruction(tools, user_question=""):
    instruction = "\n=== MANDATORY TOOL USAGE ===\n"
    instruction += "You MUST use one of the tools below to answer this question.\n"
    instruction += "Do NOT answer directly. Do NOT say you don't have information.\n"
    instruction += "You MUST respond with ONLY a JSON object to call the tool.\n\n"

    instruction += "RESPONSE FORMAT - respond with ONLY this JSON, nothing else:\n"
    instruction += '{"tool_calls": [{"name": "TOOL_NAME", "arguments": {"param": "value"}}]}\n\n'

    instruction += "RULES:\n"
    instruction += "- Your ENTIRE response must be valid JSON only\n"
    instruction += "- No markdown, no code blocks, no explanation\n"
    instruction += "- No text before or after the JSON\n\n"

    instruction += "Available tools:\n\n"

    for tool in tools:
        func = tool.get("function", tool)
        name = func.get("name", "unknown")
        desc = func.get("description", "No description")
        params = func.get("parameters", {})

        instruction += f"Tool: {name}\n"
        instruction += f"Description: {desc}\n"

        if params.get("properties"):
            instruction += "Parameters:\n"
            required_params = params.get("required", [])
            for param_name, param_info in params["properties"].items():
                param_type = param_info.get("type", "string")
                param_desc = param_info.get("description", "")
                is_required = "required" if param_name in required_params else "optional"
                instruction += f"  - {param_name} ({param_type}, {is_required}): {param_desc}\n"
        instruction += "\n"

    instruction += "=== END OF TOOLS ===\n\n"

    first_tool = tools[0] if tools else {}
    first_func = first_tool.get("function", first_tool)
    first_name = first_func.get("name", "tool")

    instruction += "EXAMPLE: If the user asks a question, respond with:\n"
    instruction += '{"tool_calls": [{"name": "' + first_name + '", "arguments": {"input": "the user question here"}}]}\n\n'
    instruction += "Now respond with the JSON to call the appropriate tool:\n\n"
    return instruction


def parse_tool_calls(response_text):
    cleaned = response_text.strip()
    if "```" in cleaned:
        code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
        if code_block_match:
            cleaned = code_block_match.group(1).strip()

    json_candidates = [cleaned]
    json_match = re.search(r'\{[\s\S]*"tool_calls"[\s\S]*\}', cleaned)
    if json_match:
        json_candidates.append(json_match.group(0))

    for candidate in json_candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "tool_calls" in parsed:
                raw_calls = parsed["tool_calls"]
                if isinstance(raw_calls, list) and len(raw_calls) > 0:
                    formatted_calls = []
                    for call in raw_calls:
                        tool_name = call.get("name", "")
                        arguments = call.get("arguments", {})
                        if isinstance(arguments, dict):
                            arguments_str = json.dumps(arguments, ensure_ascii=False)
                        else:
                            arguments_str = str(arguments)

                        formatted_calls.append(
                            {
                                "id": f"call_{uuid.uuid4().hex[:24]}",
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": arguments_str,
                                },
                            }
                        )
                    return formatted_calls
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return None


def build_chat_completion_response(response_text, start_time, model, prompt_tokens, tools=None):
    completion_tokens = len(response_text.split())
    tool_calls = None
    if tools:
        tool_calls = parse_tool_calls(response_text)

    if tool_calls:
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
            "object": "chat.completion",
            "created": int(start_time),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls,
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion",
        "created": int(start_time),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def build_responses_api_response(response_text, start_time, model, prompt_tokens, tools=None):
    completion_tokens = len(response_text.split())
    tool_calls = None
    if tools:
        tool_calls = parse_tool_calls(response_text)

    if tool_calls:
        output_items = []
        for tc in tool_calls:
            output_items.append(
                {
                    "type": "function_call",
                    "id": tc["id"],
                    "call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                    "status": "completed",
                }
            )

        return {
            "id": f"resp-{uuid.uuid4().hex[:29]}",
            "object": "response",
            "created_at": int(start_time),
            "model": model,
            "status": "completed",
            "output": output_items,
            "usage": {
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    return {
        "id": f"resp-{uuid.uuid4().hex[:29]}",
        "object": "response",
        "created_at": int(start_time),
        "model": model,
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": response_text}],
            }
        ],
        "usage": {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def run_job(job_id, prompt, model, prompt_tokens, tools=None):
    try:
        with job_lock:
            jobs[job_id] = {
                "status": "running",
                "started_at": int(time.time()),
            }

        response_text = browser_engine.process_request(prompt)
        response = build_chat_completion_response(
            response_text=response_text,
            start_time=time.time(),
            model=model,
            prompt_tokens=prompt_tokens,
            tools=tools,
        )

        with job_lock:
            jobs[job_id] = {
                "status": "done",
                "finished_at": int(time.time()),
                "response": response,
            }
    except Exception as e:
        with job_lock:
            jobs[job_id] = {
                "status": "error",
                "finished_at": int(time.time()),
                "error": str(e),
            }


# ====================================================================
# FastAPI App
# ====================================================================
app = FastAPI(title="mse_ai_api for n8n")
@app.on_event("startup")
async def _on_startup():
    enable = os.getenv("ENABLE_KEEPALIVE", "0")
    if enable == "1":
        interval = int(os.getenv("KEEPALIVE_INTERVAL_SECONDS", "86400"))
        browser_engine.start_keepalive(interval_seconds=interval)
        print(f"[LITE-SERVER] Keepalive enabled: interval={interval}s")


@app.post("/internal/keepalive")
async def internal_keepalive(request: Request):
    authorization = request.headers.get("authorization", "")
    if not authorization or authorization.replace("Bearer ", "").strip() != API_KEY:
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API Key"}})

    try:
        # Trigger a single keepalive visit in the running browser context
        result = browser_engine.do_one_keepalive(wait=True, timeout=60)
        if result is True:
            return {"status": "ok"}
        return JSONResponse(status_code=500, content={"error": str(result)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/v1/jobs")
async def create_job(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON payload"}})

    authorization = request.headers.get("authorization", "")
    if not authorization or authorization.replace("Bearer ", "").strip() != API_KEY:
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API Key"}})

    messages = data.get("messages", [])
    if not messages:
        return JSONResponse(status_code=400, content={"error": {"message": "messages field is required"}})

    tools = data.get("tools", None)
    model = data.get("model", "")
    prompt = format_prompt(messages, tools=tools)
    prompt_tokens = len(prompt.split())
    job_id = str(uuid.uuid4())

    with job_lock:
        jobs[job_id] = {
            "status": "queued",
            "created_at": int(time.time()),
        }

    job_executor.submit(run_job, job_id, prompt, model, prompt_tokens, tools)
    return {"job_id": job_id, "status": "queued"}


@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str):
    with job_lock:
        job = jobs.get(job_id)

    if not job:
        return JSONResponse(status_code=404, content={"error": {"message": "Job not found"}})

    return job


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON payload"}})

    authorization = request.headers.get("authorization", "")
    if not authorization or authorization.replace("Bearer ", "").strip() != API_KEY:
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API Key"}})

    messages = data.get("messages", [])
    if not messages:
        return JSONResponse(status_code=400, content={"error": {"message": "messages field is required"}})

    try:
        tools = data.get("tools", None)
        prompt = format_prompt(messages, tools=tools)

        start_time = time.time()
        print(f"[LITE-SERVER]..... ({len(prompt)} len)")

        response_text = browser_engine.process_request(prompt)
        p_tokens = len(prompt.split())

        return build_chat_completion_response(
            response_text=response_text,
            start_time=start_time,
            model=data.get("model", "gpt-4o-mini"),
            prompt_tokens=p_tokens,
            tools=tools,
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/v1/responses")
async def responses(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON payload"}})

    authorization = request.headers.get("authorization", "")
    if not authorization or authorization.replace("Bearer ", "").strip() != API_KEY:
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API Key"}})

    input_data = data.get("input", "")
    if isinstance(input_data, str):
        messages = [{"role": "user", "content": input_data}]
    elif isinstance(input_data, list):
        messages = input_data
    else:
        messages = data.get("messages", [])

    if not messages:
        return JSONResponse(status_code=400, content={"error": {"message": "input field is required"}})

    try:
        tools = data.get("tools", None)
        instructions = data.get("instructions", "")
        if instructions:
            messages.insert(0, {"role": "system", "content": instructions})

        prompt = format_prompt(messages, tools=tools)
        start_time = time.time()

        response_text = browser_engine.process_request(prompt)
        p_tokens = len(prompt.split())

        return build_responses_api_response(
            response_text=response_text,
            start_time=start_time,
            model=data.get("model", "gpt-4o-mini"),
            prompt_tokens=p_tokens,
            tools=tools,
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": "gpt-4o-mini", "object": "model", "owned_by": "mse_ai_api"}],
    }


@app.get("/")
async def health_check():
    return {"status": "running", "message": "mse_ai_api Server is active!"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=7860)
