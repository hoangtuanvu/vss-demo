# vss-demo — Warehouse Safety Monitor

Agentic app on VSS `warehouse` blueprint + LangGraph.
Watches warehouse video for 5 hazards, triages/dedupes, auto-escalates
critical incidents, drafts reports, answers chat questions about footage.

Design: `docs/superpowers/specs/2026-06-19-warehouse-safety-monitor-design.md`
Plans (chronological, some implemented, some pending — check code before
trusting a plan doc): `docs/superpowers/plans/*.md`

## Architecture

```
[Video upload] -> Frontend (Next.js) -> POST /upload -> Agent (FastAPI)
                                            |  ffmpeg loopback -> mediamtx RTSP
                                            v
                         VSS warehouse profile (real, on Brev GPU —
                         dense-captioning + 5 alert rules) OR a stdlib
                         mock server (infra/mock_vss.py, local dev only)
                                            |  polled every POLL_INTERVAL_SECONDS
                                            v
                         Agent: triage graph (classify severity, dedupe,
                         persist, escalate) -> SQLite/Postgres incident
                         store -> SSE -> Frontend live feed
```

The agent owns its own incident store and all triage/escalation/report/chat
logic; it calls VSS only for alert ingestion, `/chat` (ask-video /
generate-report), and alert-rule registration. VSS's own
Elasticsearch/analytics stack is intentionally not used.

## Repo layout

- `agent/` — FastAPI + LangGraph backend (Python). Source in `agent/app/`,
  tests in `agent/tests/` (pytest, mirrors `app/` module names).
- `frontend/` — Next.js 14 + Tailwind dashboard (TypeScript). Components in
  `frontend/components/`, tests in `frontend/tests/` (vitest +
  testing-library).
- `infra/` — `mediamtx.yml` (RTSP server config), `mock_vss.py` (local stand-in
  for VSS, no GPU/key needed), `alert_rules.md`.
- `docs/superpowers/specs/` and `docs/superpowers/plans/` — design docs and
  TDD implementation plans, one pair per feature, dated. **Plans describe
  intended work, not necessarily merged work** — verify against the actual
  code (e.g. `agent/app/config.py` has no `vss_mode` field yet even though a
  plan describes adding one).
- `sample-videos/` — one short clip per hazard type for manual testing.

## Backend (`agent/`)

Key modules in `agent/app/`:
- `config.py` — `Settings` (pydantic-settings, reads `.env`). All runtime
  config lives here; no other module reads env vars directly.
- `wiring.py` — `build_app(settings)` constructs the DB engine, LLM, VSS
  client, both LangGraph graphs, and `AppDependencies`. This is the one
  place that wires concrete implementations together — `main.py` and the
  graphs take dependencies as plain constructor args, never importing
  `wiring` or `config` themselves, so they stay unit-testable in isolation.
- `main.py` — `create_app(deps: AppDependencies)` defines all FastAPI
  routes (`/upload`, `/incidents`, `/incidents/{id}`, `/chat`,
  `/alerts/stream`). Routes only call into `deps`, `store`, and `models`.
- `vss_client.py` — `VSSClient`, the only HTTP boundary to VSS. Two base
  URLs: `agent_base_url` (the agent-facing `/chat` endpoint) and
  `alert_bridge_base_url` (`/api/v1/realtime*` alert rules + incidents).
  Retries transport/5xx errors with exponential backoff
  (`_request_with_retry`). `CATEGORY_MAP` translates VSS's raw alert-bridge
  category strings (e.g. `"PPE Violation"`) to this app's `HazardType`
  enum values — alert categories not in the map pass through unmapped and
  get skipped by the poller.
- `poller.py` — `poll_loop` runs as an asyncio background task
  (started in `main.py`'s lifespan), calling `get_new_alerts` on an
  interval and invoking the triage graph once per new alert.
- `graphs/triage.py` — `build_triage_graph`: classify_severity (LLM) ->
  dedupe (same hazard+zone within `DEDUPE_WINDOW_SECONDS`) ->
  persist_incident -> [critical only] generate_report -> escalate_notify
  (Slack/generic webhook). Severity classification failures or invalid
  LLM output fall back to `warning`, never raise.
- `graphs/chat.py` — `build_chat_graph`: single node, calls
  `vss_client.chat()`, catches all exceptions and returns a fixed fallback
  string rather than erroring to the user.
- `chat_format.py` — strips `<agent-think>`/`<incidents>` noise tags VSS's
  chat responses sometimes include, before they reach the frontend.
- `models.py` / `store.py` — SQLAlchemy `Incident` model + plain-function
  data access (no repository class). `HazardType`, `Severity`,
  `IncidentStatus` are the three enums everything keys off of.
- `streaming.py` — `start_rtsp_loopback` shells out to `ffmpeg` to replay an
  uploaded file into mediamtx as a simulated live RTSP camera.

Error-handling convention used throughout: best-effort operations (alert
rule registration/cleanup, report generation, escalation, chat) catch and
log/fallback rather than raising, so one failure never blocks the
upload/triage/chat pipeline. The raw alert payload is always persisted even
if triage misclassifies it.

### Running / testing backend

```bash
cd agent
python -m pytest                 # full suite
python -m pytest tests/test_X.py -v   # one file
uvicorn app.asgi:app --reload    # run locally (needs .env, see .env.example)
```

Tests mock `VSSClient` and the LLM — no network calls in the unit suite.
`agent/tests/conftest.py` has the shared `session_factory` fixture
(in-memory SQLite via `StaticPool`).

## Frontend (`frontend/`)

- `app/page.tsx` — main dashboard: upload bar, incident feed (SSE-driven),
  chat panel, stats summary.
- `app/incidents/[id]/page.tsx` — incident detail page.
- `components/` — `UploadBar`, `IncidentFeed`, `ChatPanel`, `StatsSummary`.
- `lib/api.ts` — every backend call goes through here (`uploadVideo`,
  `fetchIncidents`, `fetchIncident`, `sendChatMessage`,
  `subscribeToAlerts` via `EventSource`). Don't `fetch()` directly from
  components.
- Reads `NEXT_PUBLIC_API_BASE_URL` (build-time, see `.env.local.example`).

```bash
cd frontend
npm run dev      # localhost:3000
npm test         # vitest run
npm run build
```

## Local dev / docker-compose

`docker-compose.yml` runs `mediamtx` + `agent` (`:8000`) + `frontend`
(`:3001`). The agent's `VSS_AGENT_BASE_URL`/`VSS_ALERT_BRIDGE_BASE_URL`
default to `http://localhost:8000`/`:9080`, which is nothing without a real
VSS deployment or `infra/mock_vss.py` running and the env vars pointed at
it — see `docs/local-testing.md` for the exact steps (note: that doc
references a `VSS_MODE` mock toggle from a pending plan that isn't merged
into `config.py`/`docker-compose.yml` yet; today swapping mock vs. real is
manual env-var editing, not a one-flag toggle).

## Conventions

- Settings/env vars: add new config only to `config.py`'s `Settings`, never
  read `os.environ` ad hoc elsewhere.
- Dependency wiring: add new collaborators to `wiring.build_app`, pass them
  into `AppDependencies`/graph builders as args — don't have deeper modules
  import `config` or `wiring` directly.
- LangGraph nodes are built via `make_X_node(...)` factories that close over
  their dependencies and return a plain `state -> dict` function; keep new
  nodes in this shape for testability.
- Tests: pytest for backend, vitest + testing-library for frontend; mirror
  existing file naming (`test_<module>.py`, `<component>.test.tsx`).
- TDD plan docs under `docs/superpowers/plans/` use checkbox steps
  (write failing test -> verify fail -> implement -> verify pass -> commit).
  When implementing one, follow it task-by-task and check off steps as
  completed; don't assume an unchecked plan was already done.
