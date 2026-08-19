# ChatGPT generation recovery

## Root cause observed in the live Space

The Hugging Face live browser inspection of replica-04 showed that the Space process and OpenAPI surface were running, but the internal ChatGPT request did not complete. The redacted container log pattern was:

```text
ChatGPT browser gateway is ready; loaded 71 cookies
ChatGPT prompt submitted with explicit send button fallback
TimeoutError: ChatGPT response did not stabilize before timeout
assistant count=1, lengths=0
main article count=0
main count=1
 generation_active=True
send_button_count=1, send_states=True/True
POST /v1/chat/completions 503 Service Unavailable
```

A following request could be misclassified as submitted because `_submission_started()` treated an already-active stop/generation state as proof that the new prompt had been submitted. The same page could therefore remain stuck in a generation state across requests. Public `/health` and the Swagger UI remained available; those checks do not prove that the downstream ChatGPT browser journey is healthy.

## Fix

`BrowserGateway.send_message()` now checks for an active generation before preparing a new request. It invokes `_recover_after_timeout()`, which tries the visible ChatGPT stop control and reloads the page if generation remains active. After reload it requires the prompt input to become available before allowing a new request.

When `_wait_for_response()` reaches a timeout, `send_message()` invokes the same recovery path before returning the redacted failure. This prevents the next request from inheriting a stale generation state. The recovery is bounded, does not copy or log Cookies/Storage State, and does not turn an empty assistant message into a success.

## Verification

The regression test `test_generation_recovery_reloads_when_stop_control_fails` simulates a permanently active generation and verifies that the page reloads and the input is checked again. The source test suite passes 11 tests after this change, and the vendored gateway compiles successfully in `ai-provider-router`.

Live verification remains required after deploying the new source to each Space. A green `/health` or Swagger page is not sufficient; run a text request, a search request, and an image request separately and record `pass`, `fail`, or `deferred` with the HTTP class.

## Security boundary

This document deliberately excludes API secrets, Cookie values, Storage State, screenshots containing private session data, and Authorization headers. Rotate session state only through the Space secret manager when a live session is actually expired or exposed.
