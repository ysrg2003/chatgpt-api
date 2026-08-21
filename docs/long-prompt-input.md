# Long-prompt input handling

## Symptom

A prompt near 1,000 characters could return HTTP 503 even though the Space health endpoint reported `ready=true`. This was not the configured prompt-size validator: `MAX_PROMPT_CHARS` defaults to 50,000, and prompts above that limit are rejected with HTTP 400 (`Prompt is empty or too large`).

## Root cause

The ChatGPT Web editor is a visible, editable ProseMirror `div`. The old fallback path populated that editor with:

```python
await input_box.press_sequentially(prompt, delay=5, timeout=12_000)
```

For a longer prompt, the fixed five-millisecond delay per character exhausted the 12-second timeout before the editor was populated. `_submit_prompt()` then raised `RuntimeError`, and `main.py` correctly mapped an unsuccessful browser gateway result to HTTP 503.

The public replica-02 container log confirmed:

```text
Locator.press_sequentially: Timeout 12000ms exceeded
Could not interact with ChatGPT input
POST /v1/chat/completions HTTP/1.1 503 Service Unavailable
```

## Fix

`BrowserGateway._populate_input()` now uses the following order:

1. Use Playwright `fill()` with a bounded 20-second timeout.
2. If the ProseMirror editor rejects `fill()`, use one fast `keyboard.insert_text(prompt)` operation.
3. If that operation is unavailable, use `press_sequentially()` with `delay=0` and a length-aware bounded timeout.
4. Verify the resulting editor content before dispatching the input event and submitting with Enter or the send button.

The fix is in `browser_gateway.py` and is covered by a regression test using a 1,500-character ProseMirror prompt.

## Verification

The source test suite passed 15 tests. After publishing the fix to `Yousefsg/chatgpt-api-replica-02`, a single text-only request with a 1,500-character prompt returned HTTP 200 with a non-empty assistant response. No image request was used.

The router vendor snapshot has the same SHA256 as the source runtime file. Replica-01 and replica-04 were not modified.
