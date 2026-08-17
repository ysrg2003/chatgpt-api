from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from browser_gateway import BrowserGateway, browser_settings_from_env


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger(__name__)
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "").strip()
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
RATE_LIMIT_REQUESTS = max(0, int(os.getenv("RATE_LIMIT_REQUESTS", "20")))
RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")))
MAX_PROMPT_CHARS = max(1_000, int(os.getenv("MAX_PROMPT_CHARS", "50_000")))


def _request_id() -> str:
    return uuid.uuid4().hex[:16]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.browser = BrowserGateway(browser_settings_from_env())
    app.state.start_task = asyncio.create_task(app.state.browser.start())
    yield
    app.state.start_task.cancel()
    try:
        await app.state.start_task
    except asyncio.CancelledError:
        pass
    await app.state.browser.close()


app = FastAPI(title="ChatGPT Web API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    async def allow(self, key: str) -> bool:
        if RATE_LIMIT_REQUESTS <= 0:
            return True
        now = time.monotonic()
        async with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= RATE_LIMIT_WINDOW_SECONDS:
                start, count = now, 0
            if count >= RATE_LIMIT_REQUESTS:
                self._windows[key] = (start, count)
                return False
            self._windows[key] = (start, count + 1)
            if len(self._windows) > 10_000:
                self._windows = {key: self._windows[key]}
            return True


limiter = FixedWindowRateLimiter()


def _auth_error() -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": {"message": "Invalid API Key", "type": "authentication_error"}})


def authorized(request: Request) -> bool:
    if not API_SECRET_KEY:
        return False
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    return scheme.lower() == "bearer" and bool(token) and token.strip() == API_SECRET_KEY


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown"))[:128]


def _safe_error(message: str) -> dict[str, Any]:
    return {"error": {"message": message[:500], "type": "server_error"}}


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text", item.get("content", ""))
                if isinstance(value, str):
                    parts.append(value)
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def format_tools_instruction(tools: list[dict[str, Any]], user_question: str) -> str:
    lines = [
        "=== MANDATORY TOOL USAGE ===",
        "You MUST use one of the tools below to answer the question.",
        "Respond with ONLY valid JSON and no markdown.",
        '{"tool_calls":[{"name":"TOOL_NAME","arguments":{"param":"value"}}]}',
        "Available tools:",
    ]
    for tool in tools:
        function = tool.get("function", tool) if isinstance(tool, dict) else {}
        name = function.get("name", "unknown")
        description = function.get("description", "No description")
        parameters = function.get("parameters", {})
        lines.append(f"Tool: {name}\nDescription: {description}")
        if isinstance(parameters, dict) and parameters.get("properties"):
            lines.append("Parameters:")
            for key, info in parameters["properties"].items():
                required = "required" if key in parameters.get("required", []) else "optional"
                lines.append(f"- {key} ({info.get('type', 'string')}, {required}): {info.get('description', '')}")
    lines.append("=== END OF TOOLS ===")
    if user_question:
        lines.append(f"Question: {user_question}")
    return "\n".join(lines)


def format_prompt(messages: list[dict[str, Any]], tools: Any = None) -> str:
    parts: list[str] = []
    system_parts: list[str] = []
    user_question = ""
    has_tool_results = False
    for message in messages:
        role = str(message.get("role", ""))
        message_type = str(message.get("type", ""))
        content = _content_to_text(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
        elif role == "tool":
            has_tool_results = True
            parts.append(f"[TOOL RESULT from '{message.get('name', 'tool')}']:\n{content}")
        elif message_type == "function_call_output":
            has_tool_results = True
            parts.append(f"[TOOL RESULT (call_id: {message.get('call_id', '')})]:\n{message.get('output', content)}")
        elif message_type == "function_call":
            parts.append(f"[PREVIOUS TOOL CALL: {message.get('name', '?')} {message.get('arguments', '{}')}]")
        elif role == "assistant":
            assistant_text = content
            for call in message.get("tool_calls", []) or []:
                function = call.get("function", {}) if isinstance(call, dict) else {}
                assistant_text += f"\n[Previous tool call: {function.get('name', '?')} {function.get('arguments', '{}')}]"
            if assistant_text.strip():
                parts.append(f"[Assistant]: {assistant_text}")
        elif role == "user":
            user_question = content
            parts.append(content)
        elif content:
            parts.append(content)
    prompt = ""
    if system_parts:
        prompt += "=== SYSTEM INSTRUCTIONS ===\n" + "\n\n".join(system_parts) + "\n=== END OF INSTRUCTIONS ===\n\n"
    if tools and not has_tool_results:
        prompt += format_tools_instruction(tools, user_question) + "\n\n"
    if has_tool_results:
        prompt += "=== CONTEXT FROM TOOLS ===\nUse the tool results above to answer the user.\n\n"
    prompt += "\n".join(parts)
    if has_tool_results:
        prompt += "\n\n=== END TOOL CONTEXT ==="
    return prompt.strip()


def parse_tool_calls(response_text: str) -> list[dict[str, Any]] | None:
    cleaned = response_text.strip()
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
    candidates = [cleaned]
    match = re.search(r'\{[\s\S]*"tool_calls"[\s\S]*\}', cleaned)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        raw_calls = parsed.get("tool_calls") if isinstance(parsed, dict) else None
        if not isinstance(raw_calls, list) or not raw_calls:
            continue
        calls = []
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue
            arguments = raw_call.get("arguments", {})
            calls.append({
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": str(raw_call.get("name", "")),
                    "arguments": json.dumps(arguments, ensure_ascii=False) if isinstance(arguments, dict) else str(arguments),
                },
            })
        return calls or None
    return None


def _validate_messages(data: Any) -> tuple[list[dict[str, Any]] | None, JSONResponse | None]:
    messages = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list) or not messages:
        return None, JSONResponse(status_code=400, content={"error": {"message": "messages field is required"}})
    if len(messages) > 100:
        return None, JSONResponse(status_code=400, content={"error": {"message": "Too many messages"}})
    normalized: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            return None, JSONResponse(status_code=400, content={"error": {"message": "Each message must be an object"}})
        normalized.append(message)
    return normalized, None


async def _authorized_request(request: Request) -> JSONResponse | None:
    if not authorized(request):
        return _auth_error()
    if not await limiter.allow(_client_key(request)):
        return JSONResponse(status_code=429, content={"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}})
    return None


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = _request_id()
    try:
        response = await call_next(request)
    except Exception:
        LOGGER.exception("Unhandled request failure")
        response = JSONResponse(status_code=500, content=_safe_error("Internal server error"))
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get("/")
async def root(request: Request):
    gateway: BrowserGateway = request.app.state.browser
    return {
        "status": "running" if gateway.ready else "initializing",
        "ready": gateway.ready,
        "service": "chatgpt-web-api",
        "health": "/health",
        "error": gateway.startup_error,
    }


@app.get("/health")
async def health(request: Request):
    gateway: BrowserGateway = request.app.state.browser
    if gateway.ready:
        return {"status": "running", "ready": True, "service": "chatgpt-web-api"}
    if gateway.startup_error:
        return JSONResponse(status_code=503, content={"status": "error", "ready": False, "error": gateway.startup_error})
    return JSONResponse(status_code=200, content={"status": "initializing", "ready": False})


@app.get("/status")
async def status(request: Request):
    auth_error = await _authorized_request(request)
    if auth_error:
        return auth_error
    gateway: BrowserGateway = request.app.state.browser
    return {
        "server": "running",
        "browser_ready": gateway.ready,
        "browser_error": gateway.startup_error,
        "last_request_at": gateway.last_request_at,
        "endpoints": ["/v1/models", "/v1/chat/completions", "/v1/responses", "/new-chat", "/health"],
    }


@app.get("/v1/models")
async def list_models(request: Request):
    auth_error = await _authorized_request(request)
    if auth_error:
        return auth_error
    return {"object": "list", "data": [{"id": "gpt-4o-mini", "object": "model", "owned_by": "chatgpt-web-api"}]}


@app.post("/new-chat")
async def new_chat(request: Request):
    auth_error = await _authorized_request(request)
    if auth_error:
        return auth_error
    result = await request.app.state.browser.new_chat()
    return JSONResponse(status_code=200 if result.get("success") else 503, content=result)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    auth_error = await _authorized_request(request)
    if auth_error:
        return auth_error
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON payload"}})
    messages, validation_error = _validate_messages(data)
    if validation_error:
        return validation_error
    prompt = format_prompt(messages or [], data.get("tools"))
    if not prompt or len(prompt) > MAX_PROMPT_CHARS:
        return JSONResponse(status_code=400, content={"error": {"message": "Prompt is empty or too large"}})
    started = int(time.time())
    result = await request.app.state.browser.send_message(prompt)
    if not result.get("success"):
        return JSONResponse(status_code=503, content=_safe_error(str(result.get("error", "Browser request failed"))))
    response_text = str(result["response"])
    calls = parse_tool_calls(response_text) if data.get("tools") else None
    message: dict[str, Any] = {"role": "assistant", "content": None, "tool_calls": calls} if calls else {"role": "assistant", "content": response_text}
    prompt_tokens = len(prompt.split())
    completion_tokens = len(response_text.split())
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:29]}",
        "object": "chat.completion",
        "created": started,
        "model": data.get("model", "gpt-4o-mini"),
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if calls else "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
    }


@app.post("/v1/responses")
async def responses(request: Request):
    auth_error = await _authorized_request(request)
    if auth_error:
        return auth_error
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON payload"}})
    input_data = data.get("input", "")
    if isinstance(input_data, str):
        messages = [{"role": "user", "content": input_data}]
    elif isinstance(input_data, list):
        messages = input_data
    else:
        messages = data.get("messages", [])
    if data.get("instructions"):
        messages = [{"role": "system", "content": data["instructions"]}] + messages
    if not isinstance(messages, list) or not messages:
        return JSONResponse(status_code=400, content={"error": {"message": "input field is required"}})
    prompt = format_prompt(messages, data.get("tools"))
    if not prompt or len(prompt) > MAX_PROMPT_CHARS:
        return JSONResponse(status_code=400, content={"error": {"message": "Input is empty or too large"}})
    started = int(time.time())
    result = await request.app.state.browser.send_message(prompt)
    if not result.get("success"):
        return JSONResponse(status_code=503, content=_safe_error(str(result.get("error", "Browser request failed"))))
    response_text = str(result["response"])
    calls = parse_tool_calls(response_text) if data.get("tools") else None
    output = ([{"type": "function_call", "id": call["id"], "call_id": call["id"], "name": call["function"]["name"], "arguments": call["function"]["arguments"], "status": "completed"} for call in calls] if calls else [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": response_text}]}])
    output_tokens = len(response_text.split())
    input_tokens = len(prompt.split())
    return {
        "id": f"resp-{uuid.uuid4().hex[:29]}",
        "object": "response",
        "created_at": started,
        "model": data.get("model", "gpt-4o-mini"),
        "status": "completed",
        "output": output,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens},
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "7860")), reload=False)
