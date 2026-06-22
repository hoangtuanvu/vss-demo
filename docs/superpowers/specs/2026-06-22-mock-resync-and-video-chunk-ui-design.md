# Mock VSS resync + video chunk preview UI

## Problem

Real VSS deployment is currently turned off for demo purposes. Two gaps block running/demoing the full pipeline locally:

1. `infra/mock_vss.py` implements a stale API contract (`/alerts`, `/ask-video`, `/query-analytics`, `/search-archive`, `/generate-report`) that predates the real-VSS integration work (see `docs/superpowers/specs/2026-06-21-real-vss-integration-design.md`). It no longer matches what `agent/app/vss_client.py` actually calls, so nothing in the app currently works against it.
2. The frontend has no way to preview the uploaded video or jump to the moment an incident was detected — every walkthrough pain point ("don't make me scrub footage, just tell me / show me the moment") has no UI surface today.

## Goals

- Make the app fully runnable against a mock backend with one config flag, no manual URL juggling.
- Resync the mock to the real `VSSClient` contract (health, chat, alert-rule register/delete, incident polling).
- Add a video preview player on the dashboard that seeks to the right moment when an incident is clicked.
- Make search/summarization discoverable as one-click affordances on top of the existing `/chat` path (real VSS already does archive search + summarization server-side via its NAT+MCP layer — no new backend endpoint needed for this).

## Non-goals

- Building our own VLM/CV pipeline — frame analysis stays server-side on the real VSS deployment; the mock only fakes its responses.
- Exact-frame-accurate seeking — offsets are best-effort (computed from wall-clock elapsed time modulo video duration), good enough for a demo, not frame-perfect.

## Design

### 1. Mock API resync (`infra/mock_vss.py`)

Single process serving both the "agent" and "alert-bridge" roles (real deployments can colocate these too — this just makes local config simpler). Endpoints, matching `vss_client.py` exactly:

- `GET /health` → `{"status": "ok"}`
- `POST /chat` → OpenAI-style response shape (`choices[0].message.content`). Canned routing by keyword in the incoming message:
  - contains "summar" → canned summary text
  - contains "search" / "find" → canned list-style answer referencing the 5 canned incidents
  - contains a hazard keyword (ppe/forklift/spill/fall/zone) → canned per-hazard answer
  - matches the `generate_report` prompt template (mentions "Hazard type:" and "Severity:") → canned incident report text
  - else → generic fallback acknowledging the question
- `POST /api/v1/realtime` → register a rule, returns `{"id": "<generated>"}`
- `DELETE /api/v1/realtime/{id}` → no-op 200
- `GET /api/v1/realtime/incidents?start_time=&limit=` → `{"incidents": [...]}`, 5 canned incidents with **raw category strings** matching `CATEGORY_MAP` keys (e.g. `"PPE Violation"`, `"Spillover Violation"`), paged out incrementally via `start_time` cursor (same incremental-reveal behavior as before, just on the new shape)

### 2. Mock/real toggle

`config.py`: add `vss_mode: Literal["real", "mock"] = "real"` (env `VSS_MODE`).

`wiring.py`: when `vss_mode == "mock"`, override both `agent_base_url` and `alert_bridge_base_url` to point at the mock service (`http://mock-vss:9000` in compose, `http://localhost:9000` for bare-metal local runs) — regardless of whatever `VSS_AGENT_BASE_URL`/`VSS_ALERT_BRIDGE_BASE_URL` happen to be set to. This means flipping one var switches the whole pipeline; no need to also remember to repoint two URL envs.

`docker-compose.yml`: add a `mock-vss` service under `profiles: ["mock"]`, running `infra/mock_vss.py`. Started only via `docker compose --profile mock up`. Switching back to real VSS = `VSS_MODE=real`, drop the `--profile mock` flag, point `VSS_AGENT_BASE_URL`/`VSS_ALERT_BRIDGE_BASE_URL` at the real deployment as today.

### 3. Video preview + chunk-seek

**Serving the file back:** add `GET /uploads/{filename}` (FastAPI `FileResponse`) to `agent/app/main.py`. Sanitize `filename` to `Path(filename).name` only (reject path traversal); 404 if missing.

**Offset tracking:** at upload time (`/upload` handler), run `ffprobe` on the saved file to get `duration_seconds`. Store `(stream_start_at: datetime, duration_seconds: float | None, filename: str)` on `AppDependencies`, mirroring the existing `active_sensor_id` field. If `ffprobe` fails (missing binary, corrupt file), log a warning and leave `duration_seconds=None` — upload still succeeds, streaming still starts; offset computation is just skipped downstream.

**Incident offset:** add nullable `video_offset_seconds: Column(Float, nullable=True)` to `Incident` (`models.py`), included in `incident_to_dict`. Computed where incidents are created (triage graph / `store.create_incident` call site) as:

```
offset = (incident_created_at - stream_start_at).total_seconds() % duration_seconds
```

If `duration_seconds` is `None` (probe failed) or there's no active upload, `video_offset_seconds` stays `None`.

**Frontend:**
- New `VideoPreview` component: `<video>` pointed at `/uploads/{filename}`, exposes its ref to the parent (`page.tsx`) via callback prop.
- `page.tsx` holds the video ref; passes a `onSelectIncident(offset)` handler down to `IncidentFeed`.
- `IncidentFeed` row click → if `video_offset_seconds` is non-null, `videoRef.currentTime = offset; videoRef.play()`. If null, row is still clickable but shows "clip unavailable" (no-op on the player).

### 4. Search & summarization UX

No new backend endpoint — real VSS already resolves archive search and summarization through `/chat`'s server-side NAT+MCP workflow; mock fakes the same shape (see section 1).

Add quick-action chips above the `ChatPanel` input: "Summarize today", "Search: forklift", "Search: spill", etc. Clicking fills + sends a canned prompt through the existing `sendChatMessage`/`handleSend` path. Purely additive to `ChatPanel.tsx` — no new API client functions needed.

## Error handling

- `ffprobe` failure → warn-log, `duration_seconds=None`, offsets skipped, upload still succeeds.
- `VSS_MODE=mock` but `mock-vss` container not started → existing `health_check()` gate on `/upload` already returns 503 "VSS is unreachable." No new handling needed.
- `GET /uploads/{filename}` → reject path traversal (`Path(filename).name` only), 404 on missing file.

## Testing

- `config.py` / `wiring.py`: unit test that `VSS_MODE=mock` overrides both base URLs regardless of explicit env vars.
- Upload route: test `ffprobe` failure path leaves `duration_seconds=None` and doesn't 500.
- Offset math: unit test `(created_at - stream_start) % duration`, including wraparound past one loop of the video.
- `GET /uploads/{filename}`: test path-traversal rejected, valid file streams back with correct content type.
- `mock_vss.py`: manual smoke test only (matches existing `docs/local-testing.md` pattern), not pytest — it's a dev tool, not shipped code.
- Frontend: `VideoPreview` seek-on-click behavior, mirroring existing `IncidentFeed`/`ChatPanel` test patterns in `frontend/tests`.
