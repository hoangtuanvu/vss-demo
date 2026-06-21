# Chat Camera-Context Injection — Design

**Date:** 2026-06-21
**Status:** Approved for planning
**Repo:** `git@github.com:hoangtuanvu/vss-demo.git` (public)

## Purpose

The chat path was verified live against the real NVIDIA VSS warehouse-blueprint
instance for the first time after fixing the LLM deployment (see
`docs/superpowers/specs/2026-06-21-real-vss-integration-design.md` and the
LLM-mode-local redeploy — the prior `LLM_MODE=remote` setup was silently
broken end-to-end by an API-key entitlement problem, unrelated to anything in
this repo's code, now fixed by redeploying with `LLM_MODE=local`).

With a working LLM, real VSS's `/chat` behaves like a genuine agent: it plans,
calls real tools (`multi_report_agent`, object-count analytics with chart
URLs), and reasons over actual incident data. The one rough edge: when a
question doesn't name a camera/sensor, VSS correctly asks a clarifying
question ("Please provide a specific sensor ID...") instead of guessing. For
this demo's single-active-stream model (one upload at a time, per
`docs/superpowers/specs/2026-06-21-real-vss-integration-design.md` decision
4), we always know which sensor the user almost certainly means — the one
they just uploaded — so we can supply it automatically instead of making the
user name it every time.

Confirmed live: prefixing a chat message with `For camera/sensor 'X': ` makes
VSS resolve the sensor immediately and answer directly, rather than asking a
clarifying question.

## Decision

Track the active upload's sensor id and inject it as natural-language
context into every chat message, server-side, before forwarding to VSS's
real `/chat`. No graph or `VSSClient` changes — the injection happens once,
in the `/chat` HTTP route, by editing the message string itself (VSS already
parses sensor identification out of natural language, as confirmed by the
live test above).

If no clip has been uploaded yet in the current session, the message passes
through unmodified — VSS's own clarifying-question behavior is the correct
fallback, not a regression to paper over.

## Components

| File | Change |
|---|---|
| `agent/app/main.py` | `AppDependencies` gains `active_sensor_id: str \| None = None`. `/upload` sets it (same value already computed for `register_alert_rules`'s `sensor_id` param — `dest.stem`). `/chat` route prepends `f"For camera/sensor '{deps.active_sensor_id}': "` to `payload["message"]` before invoking the chat graph, only when `active_sensor_id` is set. |

## Data flow

```
POST /upload  →  dest.stem  →  deps.active_sensor_id = dest.stem
                                          │
POST /chat    →  if deps.active_sensor_id:
                      message = f"For camera/sensor '{deps.active_sensor_id}': {payload['message']}"
                  else:
                      message = payload["message"]
                  chat_graph.invoke({"message": message, "answer": None})
```

## Error handling

No new failure modes — this only edits a string before the existing,
already-tested `chat_graph.invoke` call. The existing fallback behavior in
`make_chat_node` (catch-all → `FALLBACK_ANSWER`) is unchanged.

## Testing

- `agent/tests/test_api.py`: new test — upload a clip (sets
  `active_sensor_id`), then POST `/chat`, assert the underlying
  `chat_graph`/`vss_client` received the message with the sensor-id prefix.
- Existing chat test (no upload first in that test's app instance) continues
  to assert the message passes through unmodified — proves the no-context
  fallback path still works.

## Out of scope (this pass)

- Multi-sensor / multi-stream tracking (this demo is single-active-stream by
  design, per the real-VSS-integration spec).
- Handling VSS's own internal tool-validation errors (e.g. the
  `source_type` missing-field error observed once) — these are bugs in VSS's
  own bundled tool layer, not something this repo's code can fix, and didn't
  recur once a sensor id was supplied directly.
- Any change to `VSSClient`, `chat.py`, or the chat graph's structure.
