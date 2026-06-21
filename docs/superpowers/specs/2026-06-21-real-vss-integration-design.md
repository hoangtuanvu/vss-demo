# Real VSS Integration — Design

**Date:** 2026-06-21
**Status:** Approved for planning
**Repo:** `git@github.com:hoangtuanvu/vss-demo.git` (public)

## Purpose

The original `agent/app/vss_client.py` was built against a fictional VSS REST
shape (`/alerts`, `/ask-video`, `/query-analytics`, `/search-archive`,
`/generate-report`) — convenient for `respx`-mocked tests, but never
validated against a real NVIDIA VSS warehouse blueprint deployment. A real
`bp_wh` instance is now live on Brev (2×A6000, `LLM_MODE=remote`), and its
actual API surface was inspected directly via each service's
`/openapi.json`. This spec replaces the fictional client with one that
matches the real API, and updates everything downstream that assumed the old
shape (poller, chat graph, upload flow, tests).

## Real VSS API surface (as deployed)

Two backends our agent talks to, neither behind the Brev HAProxy secure link
(only `/`, `/api`, `/chat`, `/alert-bridge`, etc. as *paths on the proxy* are
routed there — but our agent calls these ports directly over the network,
not through the browser-facing proxy):

- **vss-agent**, port 8000 — `POST /chat`. Request: OpenAI-style
  `{"messages": [{"role": "user", "content": "<text>"}]}`. Response: OpenAI
  `chat.completion` shape — answer at `choices[0].message.content`.
  Confirmed live against the deployed instance.
- **alert-bridge**, port 9080 — realtime alert rule CRUD and the incident
  feed:
  - `POST /api/v1/realtime` — create a rule. Body: `live_stream_url`,
    `sensor_id`, `alert_type`, `prompt`, `system_prompt` (+ optional
    `sensor_name`, `place_name`, etc). Returns the created rule's `id`.
  - `DELETE /api/v1/realtime/{alert_rule_id}` — remove a rule.
  - `GET /api/v1/realtime/incidents` — list incidents. Query params:
    `sensor_id`, `category`, `start_time`, `end_time`, `limit`, `offset`.
    **No cursor field exists.** Each incident document has (at minimum)
    `id`, `category`, `sensor_id`, `timestamp`, `description`.
  - `GET /health` — liveness.

## Decisions

1. **Chat: fully delegate, no local intent layer.** Real `vss-agent`'s
   `/chat` already runs its own NAT workflow + MCP tools (clip Q&A, stats,
   archive search) server-side. Our `graphs/chat.py` collapses to a single
   passthrough node — no `parse_intent`, no four handler nodes. The
   SOP-suggestion node (drafted from our own incident history) has no
   real-VSS equivalent and is dropped in this pass.
2. **Polling: last-seen timestamp, not cursor.** The real incident feed
   filters by `start_time`/`end_time`, not an opaque cursor. The poller
   tracks the max `timestamp` seen and passes it as `start_time` on the next
   call.
3. **Report generation: build the prompt from our own incident record.**
   No dedicated "generate report for incident X" endpoint exists on real
   VSS. `generate_report(incident_dict)` constructs an `input_message` from
   our own stored fields (`hazard_type`, `zone`, `caption`, `severity`,
   timestamps) and sends it through `chat()`. Keeps report content
   independent of VSS's own `incident_report_template.md`.
4. **Alert rules: register per upload, not once.** Each alert rule binds to
   one `live_stream_url`. Our `/upload` endpoint creates a fresh RTSP
   loopback per clip, so `/upload` also registers the 5 hazard rules
   (`ppe`/`zone_intrusion`/`forklift_proximity`/`fall`/`spill`, texts from
   `infra/alert_rules.md`) against that stream's URL, and deletes the
   previous upload's rule ids first (single active rule set — this is a
   demo app, not a multi-tenant one).
5. **Network access: open UFW, two new base-URL settings.** vss-agent
   (8000) and alert-bridge (9080) aren't on the Brev HAProxy route table, so
   `VSS_BASE_URL` (singular) no longer fits. Split into
   `VSS_AGENT_BASE_URL` and `VSS_ALERT_BRIDGE_BASE_URL`, both pointed at the
   instance's public IP (`http://216.81.245.166:8000` /
   `http://216.81.245.166:9080`). Ports opened directly via
   `sudo ufw allow 8000/tcp` / `9080/tcp` on the instance — no auth in front
   by default, acceptable for a time-boxed demo box, not for anything
   long-lived.

## Components touched

| File | Change |
|---|---|
| `agent/app/config.py` | `vss_base_url` → `vss_agent_base_url` + `vss_alert_bridge_base_url` |
| `agent/app/vss_client.py` | Rewritten: `get_new_alerts(since_timestamp)`, `chat(message)`, `generate_report(incident_dict)`, `register_alert_rules(stream_url, sensor_id)`, `delete_alert_rules(ids)`, `health_check()` (checks both backends) |
| `agent/app/poller.py` | Cursor is now an ISO timestamp; alert field mapping `category→hazard_type`, `sensor_id→zone`, `description→caption` |
| `agent/app/graphs/chat.py` | Collapsed to one passthrough node; `parse_intent` and the 4 handler nodes removed |
| `agent/app/wiring.py` / `main.py` | `/upload` calls `register_alert_rules` after starting the loopback; deletes prior rule ids first |
| `infra/alert_rules.md` | Reshaped from prose rules into `alert_type`/`prompt`/`system_prompt` fields |
| `docker-compose.yml`, `agent/.env.example` | `VSS_BASE_URL` replaced by the two new settings |
| Brev instance (`vss-warehouse`) | `ufw allow 8000/tcp`, `ufw allow 9080/tcp` |

## Data flow (upload → incident)

Upload → mediamtx RTSP loopback starts → `register_alert_rules` POSTs 5
rules against that RTSP URL → RTVI VLM watches the stream → alert-bridge
writes incidents to Elasticsearch → poller's `get_new_alerts(since_timestamp)`
time-range-queries them → existing triage graph (severity classify → dedupe
→ persist → escalate/report on critical) runs unchanged.

## Error handling

Same `VSSClient` retry/backoff wrapper (`httpx.TransportError` /
`HTTPStatusError`, exponential backoff, raises after `max_retries`).
`chat()` failures still fall back to `FALLBACK_ANSWER` in the chat graph.
`register_alert_rules` failures during `/upload` are logged but don't fail
the upload — the stream still starts, hazard monitoring is just degraded
rather than the whole demo 502ing.

## Testing

All `respx`-mocked, no real network calls in CI:

- Rewrite `agent/tests/test_vss_client.py` for the new method signatures and
  real response shapes.
- Rewrite `agent/tests/test_poller.py` for timestamp-based cursoring.
- Rewrite `agent/tests/test_chat_graph.py` for the single passthrough node;
  delete `agent/tests/test_chat_classify.py` (intent classification no
  longer exists).
- Update `agent/tests/test_triage_report_escalate.py`'s `generate_report`
  test for the new prompt-from-incident-record path.
- Update `agent/tests/test_api.py`'s upload test to assert
  `register_alert_rules` is called with the new stream URL.

## Out of scope (this pass)

- SOP-suggestion node (no real-VSS equivalent; revisit separately if wanted).
- Auth/TLS in front of the opened 8000/9080 ports (acceptable for this
  time-boxed demo instance only).
- 3D/MV3DT modes, multi-tenant rule management, anything beyond the single
  active upload this demo already assumed.
