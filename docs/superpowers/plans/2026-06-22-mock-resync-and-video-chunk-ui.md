# Mock VSS resync + video chunk preview UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resync `infra/mock_vss.py` to the real `VSSClient` API contract behind a `VSS_MODE` toggle, and add a video preview player to the dashboard that seeks to the moment an incident was detected.

**Architecture:** Backend: a `VSS_MODE` setting picks mock vs. real base URLs in `wiring.py`; the mock server fakes the same `/chat`, `/api/v1/realtime*`, `/health` endpoints the real `VSSClient` already calls. A shared mutable `ActiveUploadState` object (created once in `wiring.py`) is threaded through both the `/upload` route (writes `stream_start_at`/`duration_seconds`) and the triage graph's persist node (reads them to compute each incident's `video_offset_seconds`). Frontend: a new `VideoPreview` component plays the uploaded file back via a new `GET /uploads/{filename}` route; clicking an incident seeks that player.

**Tech Stack:** FastAPI, SQLAlchemy, LangGraph (backend, Python/pytest); Next.js, React, vitest + testing-library (frontend).

## Global Constraints

- Real `VSSClient` contract (do not change): `GET /health`, `POST /chat` (OpenAI-style), `POST /api/v1/realtime`, `DELETE /api/v1/realtime/{id}`, `GET /api/v1/realtime/incidents?start_time=&limit=`.
- `CATEGORY_MAP` in `agent/app/vss_client.py` expects raw category strings like `"PPE Violation"`, `"Spillover Violation"`, `"Pathway Obstruction Violation"`, `"Near Miss Violation"` (case-insensitive match).
- Mock and real `VSSClient` configuration must be switchable via one setting (`VSS_MODE`), not by hand-editing multiple URL envs.
- `video_offset_seconds` must be `None`/`null` (never raise) when duration probing fails or no upload is active — offset is best-effort only.

---

## Task 1: `VSS_MODE` config toggle

**Files:**
- Modify: `agent/app/config.py:4-16`
- Test: `agent/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.vss_mode: Literal["real", "mock"]` (default `"real"`), env var `VSS_MODE`.

- [ ] **Step 1: Write the failing test**

Append to `agent/tests/test_config.py`:

```python
def test_settings_defaults_vss_mode_to_real():
    settings = Settings()
    assert settings.vss_mode == "real"


def test_settings_accepts_mock_vss_mode():
    settings = Settings(vss_mode="mock")
    assert settings.vss_mode == "mock"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError` or pydantic validation error — `vss_mode` not defined.

- [ ] **Step 3: Implement**

In `agent/app/config.py`, add the import and field:

```python
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    nvidia_api_key: str = ""
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model_name: str = "nvidia/nvidia-nemotron-nano-9b-v2"
    vss_mode: Literal["real", "mock"] = "real"
    vss_agent_base_url: str = "http://localhost:8000"
    vss_alert_bridge_base_url: str = "http://localhost:9080"
    mock_vss_base_url: str = "http://localhost:9000"
    database_url: str = "sqlite:///./warehouse.db"
    slack_webhook_url: str = ""
    poll_interval_seconds: int = 8
    dedupe_window_seconds: int = 300
    mediamtx_rtsp_url: str = "rtsp://localhost:8554"
```

(`mock_vss_base_url` added now since Task 2 needs it — default matches the port `infra/mock_vss.py` listens on.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_config.py -v`
Expected: PASS, all tests including pre-existing `test_settings_has_split_vss_backend_urls`.

- [ ] **Step 5: Commit**

```bash
cd agent && git add app/config.py tests/test_config.py
git commit -m "feat: add VSS_MODE config toggle for mock vs real VSS"
```

---

## Task 2: Wire `VSS_MODE` into `wiring.py`

**Files:**
- Modify: `agent/app/wiring.py:16-21`
- Test: `agent/tests/test_wiring.py` (new)

**Interfaces:**
- Consumes: `Settings.vss_mode`, `Settings.mock_vss_base_url` (Task 1).
- Produces: `build_app(settings)` still returns `tuple[FastAPI, AppDependencies]`; when `vss_mode == "mock"`, the `VSSClient` passed to both graphs uses `mock_vss_base_url` for *both* its `agent_base_url` and `alert_bridge_base_url` args, regardless of `vss_agent_base_url`/`vss_alert_bridge_base_url`.

- [ ] **Step 1: Write the failing test**

Create `agent/tests/test_wiring.py`:

```python
from app.config import Settings
from app.wiring import build_app


def test_build_app_uses_real_urls_when_vss_mode_real():
    settings = Settings(
        vss_mode="real",
        vss_agent_base_url="http://real-agent.test",
        vss_alert_bridge_base_url="http://real-bridge.test",
        database_url="sqlite:///:memory:",
    )
    _, deps = build_app(settings)
    assert deps.vss_client.agent_base_url == "http://real-agent.test"
    assert deps.vss_client.alert_bridge_base_url == "http://real-bridge.test"


def test_build_app_overrides_both_urls_when_vss_mode_mock():
    settings = Settings(
        vss_mode="mock",
        vss_agent_base_url="http://real-agent.test",
        vss_alert_bridge_base_url="http://real-bridge.test",
        mock_vss_base_url="http://mock-vss.test:9000",
        database_url="sqlite:///:memory:",
    )
    _, deps = build_app(settings)
    assert deps.vss_client.agent_base_url == "http://mock-vss.test:9000"
    assert deps.vss_client.alert_bridge_base_url == "http://mock-vss.test:9000"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_wiring.py -v`
Expected: FAIL on the mock-mode test — URLs come back as `http://real-agent.test`/`http://real-bridge.test` either way (no override exists yet).

- [ ] **Step 3: Implement**

In `agent/app/wiring.py`, replace the `vss_client = VSSClient(...)` line:

```python
def build_app(settings: Settings) -> tuple[FastAPI, AppDependencies]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    llm = get_chat_model(settings)
    if settings.vss_mode == "mock":
        agent_base_url = settings.mock_vss_base_url
        alert_bridge_base_url = settings.mock_vss_base_url
    else:
        agent_base_url = settings.vss_agent_base_url
        alert_bridge_base_url = settings.vss_alert_bridge_base_url
    vss_client = VSSClient(agent_base_url, alert_bridge_base_url)
```

(rest of the function is unchanged).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd agent && git add app/wiring.py tests/test_wiring.py
git commit -m "feat: override VSS base URLs with mock_vss_base_url when VSS_MODE=mock"
```

---

## Task 3: Resync `infra/mock_vss.py` to the real contract

**Files:**
- Modify: `infra/mock_vss.py` (full rewrite)
- Modify: `docs/local-testing.md` (update mock section — see Step 4)

**Interfaces:**
- Produces: an HTTP server on `:9000` implementing `GET /health`, `POST /chat`, `POST /api/v1/realtime`, `DELETE /api/v1/realtime/{id}`, `GET /api/v1/realtime/incidents?start_time=&limit=` — the exact shapes `agent/app/vss_client.py` parses (see `agent/tests/test_vss_client.py` for the response shapes it expects).

This file has no pytest coverage (dev tool, matches existing pattern) — verify by manual smoke test instead of a unit test step.

- [ ] **Step 1: Rewrite the file**

```python
# Local-testing stand-in for a real VSS deployment. Implements the same
# endpoints app.vss_client.VSSClient calls — health, chat, realtime alert
# rules, realtime incidents — with canned hazard incidents and canned chat
# answers, so the full pipeline (poll -> triage -> persist -> SSE -> chat)
# can be exercised without a real Brev GPU instance. See docs/local-testing.md.
import json
import uuid
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

BASE_TIME = datetime(2026, 1, 1, 0, 0, 0)

INCIDENTS = [
    {"id": "c1", "category": "PPE Violation", "sensor_id": "dock-1", "timestamp": (BASE_TIME).isoformat() + "Z", "description": "Worker without a hard hat near the loading dock"},
    {"id": "c2", "category": "Near Miss Violation", "sensor_id": "aisle-2", "timestamp": (BASE_TIME + timedelta(seconds=10)).isoformat() + "Z", "description": "Forklift within 2m of a pedestrian"},
    {"id": "c3", "category": "Pathway Obstruction Violation", "sensor_id": "aisle-1", "timestamp": (BASE_TIME + timedelta(seconds=20)).isoformat() + "Z", "description": "Liquid spill blocking the walkway"},
    {"id": "c4", "category": "Spillover Violation", "sensor_id": "aisle-3", "timestamp": (BASE_TIME + timedelta(seconds=30)).isoformat() + "Z", "description": "Dropped pallet blocking the walkway"},
    {"id": "c5", "category": "PPE Violation", "sensor_id": "restricted-a", "timestamp": (BASE_TIME + timedelta(seconds=40)).isoformat() + "Z", "description": "Person entered the marked restricted zone without a vest"},
]


def incidents_after(start_time):
    if not start_time:
        return INCIDENTS
    return [i for i in INCIDENTS if i["timestamp"] > start_time]


def chat_reply(message: str) -> str:
    lowered = message.lower()
    if "hazard type:" in lowered and "severity:" in lowered:
        return "Mock incident report: hazard observed and logged for follow-up; no further action required at this time."
    if "summar" in lowered:
        return "Mock summary: 5 hazards detected today across PPE, near-miss, and spill categories. No critical escalations."
    if "search" in lowered or "find" in lowered:
        return "Mock search results: 5 matching incidents found — PPE violation (dock-1), near-miss (aisle-2), pathway obstruction (aisle-1), spillover (aisle-3), PPE violation (restricted-a)."
    for keyword in ("ppe", "forklift", "spill", "fall", "zone"):
        if keyword in lowered:
            return f"Mock answer about {keyword}: this hazard type has been observed today, see the incident feed for details."
    return f"Mock answer to: {message}"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except ValueError:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
        elif parsed.path == "/api/v1/realtime/incidents":
            query = parse_qs(parsed.query)
            start_time = query.get("start_time", [None])[0]
            limit = int(query.get("limit", [100])[0])
            incidents = incidents_after(start_time)[:limit]
            self._send_json({
                "status": "success", "count": len(incidents), "total": len(INCIDENTS),
                "timestamp": datetime.utcnow().isoformat() + "Z", "incidents": incidents,
            })
        else:
            self._send_json({"detail": "not found"}, status=404)

    def do_POST(self):
        body = self._read_json_body()
        if self.path == "/chat":
            messages = body.get("messages", [])
            last_user_message = messages[-1]["content"] if messages else ""
            self._send_json({
                "id": "mock", "object": "chat.completion", "model": "mock", "created": 0,
                "choices": [{"finish_reason": "stop", "index": 0, "message": {
                    "role": "assistant", "content": chat_reply(last_user_message),
                }}],
            })
        elif self.path == "/api/v1/realtime":
            self._send_json({"id": str(uuid.uuid4()), "status": "success", "message": "created"})
        else:
            self._send_json({"detail": "not found"}, status=404)

    def do_DELETE(self):
        if self.path.startswith("/api/v1/realtime/"):
            rule_id = self.path.rsplit("/", 1)[-1]
            self._send_json({"id": rule_id, "status": "success", "message": "deleted"})
        else:
            self._send_json({"detail": "not found"}, status=404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
```

- [ ] **Step 2: Manual smoke test**

Run: `python3 infra/mock_vss.py &` then:

```bash
curl -s localhost:9000/health
curl -s localhost:9000/api/v1/realtime/incidents
curl -s -X POST localhost:9000/chat -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"summarize today"}]}'
curl -s -X POST localhost:9000/api/v1/realtime -d '{}'
curl -s -X DELETE localhost:9000/api/v1/realtime/abc
```

Expected: `{"status": "ok"}`; incidents JSON with 5 entries; chat JSON whose `choices[0].message.content` starts with "Mock summary:"; realtime POST returns a JSON `id`; DELETE returns `{"id": "abc", ...}`. Kill the background process after (`kill %1`).

- [ ] **Step 3: Verify against the real client's parsing**

Run: `cd agent && python -m pytest tests/test_vss_client.py -v`
Expected: PASS (unaffected — this task only changes the mock server, not `VSSClient`; confirms no regression).

- [ ] **Step 4: Update `docs/local-testing.md`**

Read the file first, then replace the "1a. Test against the mock VSS" section's endpoint list and env-var instructions to match the new contract: list the new endpoints (`/health`, `/chat`, `/api/v1/realtime`, `/api/v1/realtime/incidents`), and replace `VSS_BASE_URL=http://host.docker.internal:9000` with the two new variables: `VSS_MODE=mock` plus `MOCK_VSS_BASE_URL=http://host.docker.internal:9000` (when mock runs on the host) or `http://mock-vss:9000` (when mock runs via the compose profile from Task 4).

- [ ] **Step 5: Commit**

```bash
git add infra/mock_vss.py docs/local-testing.md
git commit -m "fix: resync mock_vss.py to the current VSSClient API contract"
```

---

## Task 4: `mock-vss` compose service behind a profile

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:** none (infra-only; no code consumes this beyond what Tasks 1-3 already established).

- [ ] **Step 1: Add the service**

Read `docker-compose.yml`, then add this service block (alongside `mediamtx`/`agent`/`frontend`), and add `MOCK_VSS_BASE_URL`/`VSS_MODE` to `agent`'s environment:

```yaml
  mock-vss:
    image: python:3.12-slim
    profiles: ["mock"]
    working_dir: /app
    volumes:
      - ./infra:/app/infra:ro
    command: ["python3", "infra/mock_vss.py"]
    ports:
      - "9000:9000"
```

In the `agent` service's `environment:` block, add:

```yaml
      VSS_MODE: ${VSS_MODE:-real}
      MOCK_VSS_BASE_URL: ${MOCK_VSS_BASE_URL:-http://mock-vss:9000}
```

- [ ] **Step 2: Manual verification**

Run: `docker compose --profile mock up -d --build`
Expected: `mock-vss`, `mediamtx`, `agent`, `frontend` all start; `curl localhost:9000/health` returns `{"status": "ok"}` from the host.

Run: `docker compose down`
Run: `docker compose up -d --build` (no `--profile mock`)
Expected: `mock-vss` does NOT start (profile-gated); `agent` defaults to `VSS_MODE=real` and 503s on `/upload` until pointed at a real deployment (existing, documented behavior).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add mock-vss compose service behind --profile mock"
```

---

## Task 5: `video_offset_seconds` on the `Incident` model

**Files:**
- Modify: `agent/app/models.py:30-59`
- Modify: `agent/app/store.py:9-20`
- Test: `agent/tests/test_store.py` (new, or append if it exists — check first)

**Interfaces:**
- Produces: `Incident.video_offset_seconds: float | None` column; `store.create_incident(..., video_offset_seconds: float | None = None)`; `incident_to_dict(incident)["video_offset_seconds"]`.

- [ ] **Step 1: Check for an existing store test file**

Run: `ls agent/tests/test_store.py 2>/dev/null || echo "none"`

If it exists, read it first and append the test below in its existing style. If not, create it fresh with the imports shown.

- [ ] **Step 2: Write the failing test**

```python
from app.models import HazardType, Severity
from app import store


def test_create_incident_stores_video_offset_seconds(session_factory):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.PPE, severity=Severity.WARNING,
            zone="dock-1", caption="no hard hat", raw_alert_payload={},
            dedupe_key="ppe:dock-1", video_offset_seconds=12.5,
        )
        assert incident.video_offset_seconds == 12.5


def test_create_incident_defaults_video_offset_seconds_to_none(session_factory):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.PPE, severity=Severity.WARNING,
            zone="dock-1", caption="no hard hat", raw_alert_payload={},
            dedupe_key="ppe:dock-1",
        )
        assert incident.video_offset_seconds is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_store.py -v`
Expected: FAIL — `create_incident()` raises `TypeError: unexpected keyword argument 'video_offset_seconds'`.

- [ ] **Step 4: Implement**

In `agent/app/models.py`, add the import and column (line 4 and inside the `Incident` class after `dedupe_key`):

```python
from sqlalchemy import Column, DateTime, Enum as SAEnum, Float, Integer, JSON, String
```

```python
    dedupe_key = Column(String, nullable=False, index=True)
    video_offset_seconds = Column(Float, nullable=True)
```

In `incident_to_dict`, add the field:

```python
def incident_to_dict(incident: Incident) -> dict:
    return {
        "id": incident.id,
        "hazard_type": incident.hazard_type.value,
        "severity": incident.severity.value,
        "status": incident.status.value,
        "zone": incident.zone,
        "caption": incident.caption,
        "report_text": incident.report_text,
        "video_offset_seconds": incident.video_offset_seconds,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
    }
```

In `agent/app/store.py`, update `create_incident`:

```python
def create_incident(
    session: Session, *, hazard_type, severity, zone: str, caption: str,
    raw_alert_payload: dict, dedupe_key: str, video_offset_seconds: float | None = None,
) -> Incident:
    incident = Incident(
        hazard_type=hazard_type, severity=severity, zone=zone, caption=caption,
        raw_alert_payload=raw_alert_payload, dedupe_key=dedupe_key,
        video_offset_seconds=video_offset_seconds,
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_store.py tests/test_api.py -v`
Expected: PASS for new tests; `test_api.py` still passes (it doesn't assert on the dict's exact key set, only specific fields).

- [ ] **Step 6: Commit**

```bash
cd agent && git add app/models.py app/store.py tests/test_store.py
git commit -m "feat: add nullable video_offset_seconds to Incident"
```

---

## Task 6: `ActiveUploadState` + ffprobe duration helper

**Files:**
- Create: `agent/app/upload_state.py`
- Modify: `agent/app/streaming.py`
- Test: `agent/tests/test_streaming.py`

**Interfaces:**
- Produces: `class ActiveUploadState` with attributes `filename: str | None`, `stream_start_at: datetime | None`, `duration_seconds: float | None` (all default `None`).
- Produces: `get_video_duration_seconds(video_path: Path) -> float | None` in `streaming.py` — returns `None` (never raises) on any `ffprobe` failure.

- [ ] **Step 1: Write the failing test**

Read `agent/tests/test_streaming.py` first, then append in its existing style:

```python
def test_get_video_duration_seconds_returns_none_on_ffprobe_failure(tmp_path, monkeypatch):
    import subprocess

    from app.streaming import get_video_duration_seconds

    def boom(*args, **kwargs):
        raise FileNotFoundError("ffprobe not found")

    monkeypatch.setattr(subprocess, "run", boom)
    missing = tmp_path / "clip.mp4"
    missing.write_bytes(b"not a real video")
    assert get_video_duration_seconds(missing) is None


def test_get_video_duration_seconds_parses_ffprobe_output(tmp_path, monkeypatch):
    import subprocess

    from app.streaming import get_video_duration_seconds

    class FakeResult:
        stdout = "12.5\n"
        returncode = 0

    def fake_run(*args, **kwargs):
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fake")
    assert get_video_duration_seconds(path) == 12.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_streaming.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_video_duration_seconds'`.

- [ ] **Step 3: Implement**

Create `agent/app/upload_state.py`:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ActiveUploadState:
    filename: str | None = None
    stream_start_at: datetime | None = None
    duration_seconds: float | None = None
```

In `agent/app/streaming.py`, append:

```python
def get_video_duration_seconds(video_path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
            ],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, OSError):
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_streaming.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd agent && git add app/upload_state.py app/streaming.py tests/test_streaming.py
git commit -m "feat: add ActiveUploadState and ffprobe-based duration helper"
```

---

## Task 7: Compute `video_offset_seconds` in the triage graph

**Files:**
- Modify: `agent/app/graphs/triage.py:64-88, 145-158`
- Modify: `agent/app/wiring.py` (pass `upload_state` through)
- Test: `agent/tests/test_chat_graph.py` or new `agent/tests/test_triage.py` — check first

**Interfaces:**
- Consumes: `ActiveUploadState` (Task 6).
- Produces: `build_triage_graph(llm, vss_client, session_factory, webhook_url, dedupe_window_seconds, broadcaster, upload_state)` — note the added trailing parameter; `make_persist_incident_node(session_factory, broadcaster, upload_state)`.

- [ ] **Step 1: Check for existing triage tests**

Run: `ls agent/tests/test_triage.py 2>/dev/null || grep -rl "build_triage_graph\|make_persist_incident_node" agent/tests/`

Read whatever file(s) come back to match existing fixture/mocking style before writing new tests. If nothing covers `triage.py` directly, create `agent/tests/test_triage.py`.

- [ ] **Step 2: Write the failing test**

```python
from datetime import datetime, timedelta

from app.events import IncidentBroadcaster
from app.graphs.triage import make_persist_incident_node
from app.upload_state import ActiveUploadState


def test_persist_incident_computes_video_offset_from_upload_state(session_factory):
    upload_state = ActiveUploadState(
        filename="clip.mp4",
        stream_start_at=datetime.utcnow() - timedelta(seconds=5),
        duration_seconds=20.0,
    )
    node = make_persist_incident_node(session_factory, IncidentBroadcaster(), upload_state)
    state = {
        "is_new": True, "hazard_type": "ppe", "severity": "warning", "zone": "dock-1",
        "caption": "no hard hat", "alert": {}, "dedupe_key": "ppe:dock-1",
    }
    result = node(state)
    with session_factory() as session:
        from app import store
        incident = store.get_incident(session, result["incident_id"])
    assert incident.video_offset_seconds is not None
    assert 0 <= incident.video_offset_seconds < 20.0


def test_persist_incident_leaves_video_offset_none_without_active_upload(session_factory):
    upload_state = ActiveUploadState()
    node = make_persist_incident_node(session_factory, IncidentBroadcaster(), upload_state)
    state = {
        "is_new": True, "hazard_type": "ppe", "severity": "warning", "zone": "dock-1",
        "caption": "no hard hat", "alert": {}, "dedupe_key": "ppe:dock-1",
    }
    result = node(state)
    with session_factory() as session:
        from app import store
        incident = store.get_incident(session, result["incident_id"])
    assert incident.video_offset_seconds is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_triage.py -v`
Expected: FAIL — `make_persist_incident_node()` takes 2 positional arguments but 3 were given.

- [ ] **Step 4: Implement**

In `agent/app/graphs/triage.py`, replace `make_persist_incident_node` and `build_triage_graph`:

```python
from datetime import datetime


def make_persist_incident_node(session_factory, broadcaster, upload_state) -> Callable[[dict], dict]:
    def persist_incident(state: dict) -> dict:
        video_offset_seconds = None
        if upload_state.stream_start_at is not None and upload_state.duration_seconds:
            elapsed = (datetime.utcnow() - upload_state.stream_start_at).total_seconds()
            video_offset_seconds = elapsed % upload_state.duration_seconds

        with session_factory() as session:
            if state["is_new"]:
                incident = store.create_incident(
                    session,
                    hazard_type=HazardType(state["hazard_type"]),
                    severity=Severity(state["severity"]),
                    zone=state["zone"],
                    caption=state["caption"],
                    raw_alert_payload=state["alert"],
                    dedupe_key=state["dedupe_key"],
                    video_offset_seconds=video_offset_seconds,
                )
            else:
                incident = store.update_incident(
                    session,
                    state["incident_id"],
                    caption=state["caption"],
                    severity=Severity(state["severity"]),
                    raw_alert_payload=state["alert"],
                )
            broadcaster.publish(incident_to_dict(incident))
        return {"incident_id": incident.id}

    return persist_incident
```

```python
def build_triage_graph(llm, vss_client, session_factory, webhook_url: str, dedupe_window_seconds: int, broadcaster, upload_state):
    graph = StateGraph(TriageState)
    graph.add_node("classify_severity", make_classify_severity_node(llm))
    graph.add_node("dedupe", make_dedupe_node(session_factory, dedupe_window_seconds))
    graph.add_node("persist_incident", make_persist_incident_node(session_factory, broadcaster, upload_state))
    graph.add_node("generate_report", make_generate_report_node(vss_client, session_factory))
    graph.add_node("escalate_notify", make_escalate_notify_node(webhook_url, session_factory))
    graph.set_entry_point("classify_severity")
    graph.add_edge("classify_severity", "dedupe")
    graph.add_edge("dedupe", "persist_incident")
    graph.add_conditional_edges("persist_incident", route_by_severity, {"critical": "generate_report", "end": END})
    graph.add_edge("generate_report", "escalate_notify")
    graph.add_edge("escalate_notify", END)
    return graph.compile()
```

In `agent/app/wiring.py`, create the shared state and pass it to `build_triage_graph`, and add it to `AppDependencies`:

```python
from app.upload_state import ActiveUploadState
```

```python
    upload_state = ActiveUploadState()
    triage_graph = build_triage_graph(
        llm, vss_client, session_factory, settings.slack_webhook_url,
        settings.dedupe_window_seconds, broadcaster, upload_state,
    )
    chat_graph = build_chat_graph(vss_client)
    deps = AppDependencies(
        session_factory=session_factory,
        triage_graph=triage_graph,
        chat_graph=chat_graph,
        vss_client=vss_client,
        broadcaster=broadcaster,
        upload_dir=Path("uploads"),
        mediamtx_rtsp_url=settings.mediamtx_rtsp_url,
        poll_interval_seconds=settings.poll_interval_seconds,
        upload_state=upload_state,
    )
```

(Task 8 adds the `upload_state` field to `AppDependencies` itself — if executed out of order, add it now: `upload_state: object = None` is NOT acceptable since it must always exist; add `upload_state: ActiveUploadState` as a required field in `agent/app/main.py`'s `AppDependencies` dataclass and import `ActiveUploadState` there too.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_triage.py tests/test_wiring.py tests/test_api.py -v`
Expected: PASS. `test_api.py`'s `make_test_app` helper builds `AppDependencies` directly without `triage_graph`-related upload_state usage — if it now fails because `AppDependencies` requires `upload_state`, update `make_test_app` in `agent/tests/test_api.py` to pass `upload_state=ActiveUploadState()` (import `from app.upload_state import ActiveUploadState` at the top of that test file).

- [ ] **Step 6: Commit**

```bash
cd agent && git add app/graphs/triage.py app/wiring.py app/main.py tests/test_triage.py tests/test_api.py
git commit -m "feat: compute incident video_offset_seconds from ActiveUploadState"
```

---

## Task 8: `/upload` populates `ActiveUploadState`; new `GET /uploads/{filename}`

**Files:**
- Modify: `agent/app/main.py:1-100`
- Test: `agent/tests/test_api.py`

**Interfaces:**
- Consumes: `ActiveUploadState` (Task 6), `get_video_duration_seconds` (Task 6).
- Produces: `AppDependencies.upload_state: ActiveUploadState` (required field); `POST /upload` response gains `"filename"` key; new `GET /uploads/{filename}` route.

- [ ] **Step 1: Write the failing tests**

Append to `agent/tests/test_api.py` (add the import at top: `from app.upload_state import ActiveUploadState`):

```python
def test_upload_response_includes_filename(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    monkeypatch.setattr("app.main.get_video_duration_seconds", lambda path: 15.0)
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.json()["filename"] == "clip.mp4"


def test_upload_populates_active_upload_state(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    monkeypatch.setattr("app.main.get_video_duration_seconds", lambda path: 15.0)
    deps = AppDependencies(
        session_factory=session_factory, triage_graph=None, chat_graph=FakeChatGraph(),
        vss_client=FakeVSSClient(), broadcaster=IncidentBroadcaster(), upload_dir=tmp_path,
        mediamtx_rtsp_url="rtsp://localhost:8554", poll_interval_seconds=9999,
        upload_state=ActiveUploadState(),
    )
    app = create_app(deps)
    with TestClient(app) as client:
        client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert deps.upload_state.filename == "clip.mp4"
    assert deps.upload_state.duration_seconds == 15.0
    assert deps.upload_state.stream_start_at is not None


def test_get_uploaded_file_returns_bytes(session_factory, tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"fake-video-bytes")
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.get("/uploads/clip.mp4")
    assert response.status_code == 200
    assert response.content == b"fake-video-bytes"


def test_get_uploaded_file_404_for_missing_file(session_factory, tmp_path):
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.get("/uploads/missing.mp4")
    assert response.status_code == 404


def test_get_uploaded_file_rejects_path_traversal(session_factory, tmp_path):
    (tmp_path / "secret.txt").write_bytes(b"top secret")
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.get("/uploads/..%2F..%2Fsecret.txt")
    assert response.status_code == 404
```

Also update `make_test_app` in the same file to pass `upload_state=ActiveUploadState()` to `AppDependencies(...)` (required field added below), and update the existing `test_upload_starts_rtsp_loopback_and_registers_alert_rules` test's assertion from:

```python
    assert response.json() == {"stream_url": "rtsp://localhost:8554/clip"}
```

to:

```python
    assert response.json() == {"stream_url": "rtsp://localhost:8554/clip", "filename": "clip.mp4"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_api.py -v`
Expected: FAIL — `AppDependencies` has no `upload_state` field; `/uploads/{filename}` route doesn't exist (404 on a route that doesn't 404 for the right reason vs. just unmatched).

- [ ] **Step 3: Implement**

In `agent/app/main.py`, update imports and the dataclass:

```python
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app import store
from app.alert_rules import HAZARD_ALERT_RULES
from app.events import IncidentBroadcaster
from app.models import Severity, incident_to_dict
from app.poller import poll_loop
from app.streaming import get_video_duration_seconds, start_rtsp_loopback
from app.upload_state import ActiveUploadState
```

```python
@dataclass
class AppDependencies:
    session_factory: object
    triage_graph: object
    chat_graph: object
    vss_client: object
    broadcaster: IncidentBroadcaster
    upload_dir: Path
    mediamtx_rtsp_url: str
    upload_state: ActiveUploadState
    poll_interval_seconds: int = 8
    active_rule_ids: list[str] = field(default_factory=list)
    active_sensor_id: str | None = None
```

Update the `/upload` route body (after `dest.write_bytes(...)`, before the `return`):

```python
    @app.post("/upload")
    def upload(file: UploadFile = File(...)):
        if not deps.vss_client.health_check():
            raise HTTPException(status_code=503, detail="VSS is unreachable")
        deps.upload_dir.mkdir(parents=True, exist_ok=True)
        dest = deps.upload_dir / file.filename
        dest.write_bytes(file.file.read())
        try:
            stream_url = start_rtsp_loopback(dest, dest.stem, deps.mediamtx_rtsp_url)
        except Exception:
            raise HTTPException(status_code=502, detail="Failed to start video stream ingestion")

        deps.active_sensor_id = dest.stem
        deps.upload_state.filename = dest.name
        deps.upload_state.stream_start_at = datetime.utcnow()
        deps.upload_state.duration_seconds = get_video_duration_seconds(dest)

        if deps.active_rule_ids:
            try:
                deps.vss_client.delete_alert_rules(deps.active_rule_ids)
            except Exception:
                logger.warning("Failed to delete previous alert rules: %s", deps.active_rule_ids)
            deps.active_rule_ids = []
        try:
            deps.active_rule_ids = deps.vss_client.register_alert_rules(
                stream_url, dest.stem, HAZARD_ALERT_RULES
            )
        except Exception:
            logger.warning("Failed to register alert rules for stream %s", stream_url)

        return {"stream_url": stream_url, "filename": dest.name}
```

Add `import datetime`'s `datetime` (top of file already has `import asyncio, json, logging` — add `from datetime import datetime` alongside them).

Add the new route (after `/upload`, before `/incidents`):

```python
    @app.get("/uploads/{filename}")
    def get_uploaded_file(filename: str):
        safe_name = Path(filename).name
        path = deps.upload_dir / safe_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        return FileResponse(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_api.py tests/test_wiring.py -v`
Expected: PASS, full file.

- [ ] **Step 5: Run the full backend suite**

Run: `cd agent && python -m pytest -v`
Expected: PASS, no regressions across all backend tests.

- [ ] **Step 6: Commit**

```bash
cd agent && git add app/main.py tests/test_api.py
git commit -m "feat: populate ActiveUploadState on /upload, add GET /uploads/{filename}"
```

---

## Task 9: Frontend `Incident` type + `VideoPreview` component

**Files:**
- Modify: `frontend/lib/api.ts:1-13`
- Create: `frontend/components/VideoPreview.tsx`
- Test: `frontend/tests/video-preview.test.tsx` (new)

**Interfaces:**
- Produces: `Incident.video_offset_seconds: number | null` and `Incident.filename` is NOT on `Incident` — filename comes only from the upload response, not incidents (incidents don't carry filenames in this design; see Task 10 for how `page.tsx` tracks the active filename separately).
- Produces: `uploadVideo()` return type gains `filename: string`.
- Produces: `VideoPreview` component, `forwardRef<HTMLVideoElement, { src: string }>`.

- [ ] **Step 1: Write the failing test**

Create `frontend/tests/video-preview.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import VideoPreview from "../components/VideoPreview";

describe("VideoPreview", () => {
  it("renders a video element pointed at the given src", () => {
    render(<VideoPreview src="http://localhost:8000/uploads/clip.mp4" />);
    const video = screen.getByTestId("video-preview") as HTMLVideoElement;
    expect(video.querySelector("source")?.getAttribute("src")).toBe(
      "http://localhost:8000/uploads/clip.mp4"
    );
  });

  it("forwards the ref to the underlying video element", () => {
    const ref = createRef<HTMLVideoElement>();
    render(<VideoPreview src="http://localhost:8000/uploads/clip.mp4" ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLVideoElement);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/video-preview.test.tsx`
Expected: FAIL — `Cannot find module '../components/VideoPreview'`.

- [ ] **Step 3: Implement**

Create `frontend/components/VideoPreview.tsx`:

```tsx
import { forwardRef } from "react";

const VideoPreview = forwardRef<HTMLVideoElement, { src: string }>(function VideoPreview(
  { src },
  ref
) {
  return (
    <video
      ref={ref}
      data-testid="video-preview"
      controls
      className="w-full border border-paper/15 bg-ink"
    >
      <source src={src} type="video/mp4" />
    </video>
  );
});

export default VideoPreview;
```

In `frontend/lib/api.ts`, update `Incident` and `uploadVideo`:

```typescript
export interface Incident {
  id: number;
  hazard_type: string;
  severity: string;
  status: string;
  zone: string;
  caption: string;
  report_text: string | null;
  video_offset_seconds: number | null;
  created_at: string;
  updated_at: string;
}

export async function uploadVideo(file: File): Promise<{ stream_url: string; filename: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE_URL}/upload`, { method: "POST", body: formData });
  if (!res.ok) throw new Error("upload failed");
  return res.json();
}

export function videoUrl(filename: string): string {
  return `${API_BASE_URL}/uploads/${filename}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/video-preview.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd frontend && git add components/VideoPreview.tsx lib/api.ts tests/video-preview.test.tsx
git commit -m "feat: add VideoPreview component and video_offset_seconds/filename API types"
```

---

## Task 10: Wire upload → preview → incident-click-to-seek in `page.tsx` / `IncidentFeed`

**Files:**
- Modify: `frontend/components/UploadBar.tsx`
- Modify: `frontend/components/IncidentFeed.tsx`
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/tests/upload-bar.test.tsx`, `frontend/tests/incident-feed.test.tsx`, `frontend/tests/page.test.tsx`

**Interfaces:**
- Produces: `UploadBar` accepts optional prop `onUploaded?: (filename: string) => void`, calls it with `result.filename` after a successful upload.
- Produces: `IncidentFeed` accepts optional prop `onPlayClip?: (offsetSeconds: number) => void`; renders a "Play clip" button per incident row when `incident.video_offset_seconds != null`, calling `onPlayClip(incident.video_offset_seconds)` on click (`event.preventDefault()`/`stopPropagation()` so it doesn't trigger the row's `Link` navigation).
- Produces: `page.tsx` holds `videoRef = useRef<HTMLVideoElement>(null)` and `activeFilename` state; renders `<VideoPreview ref={videoRef} src={videoUrl(activeFilename)} />` when `activeFilename` is set; passes `onPlayClip` that sets `videoRef.current.currentTime = offsetSeconds` and calls `.play()`.

- [ ] **Step 1: Write the failing tests**

In `frontend/tests/upload-bar.test.tsx`, append:

```tsx
it("calls onUploaded with the returned filename", async () => {
  (uploadVideo as any).mockResolvedValue({ stream_url: "rtsp://localhost:8554/cam1", filename: "cam1.mp4" });
  const onUploaded = vi.fn();
  render(<UploadBar onUploaded={onUploaded} />);

  const file = new File(["fake"], "cam1.mp4", { type: "video/mp4" });
  const input = screen.getByTestId("file-input") as HTMLInputElement;
  fireEvent.change(input, { target: { files: [file] } });
  fireEvent.click(screen.getByText("Upload"));

  await waitFor(() => {
    expect(onUploaded).toHaveBeenCalledWith("cam1.mp4");
  });
});
```

In `frontend/tests/incident-feed.test.tsx`, append:

```tsx
it("shows a Play clip button when video_offset_seconds is set and calls onPlayClip with it", () => {
  const onPlayClip = vi.fn();
  render(
    <IncidentFeed
      incidents={[
        { id: 1, hazard_type: "ppe", severity: "warning", caption: "no hard hat", video_offset_seconds: 42.5 } as any,
      ]}
      onPlayClip={onPlayClip}
    />
  );
  fireEvent.click(screen.getByText("Play clip"));
  expect(onPlayClip).toHaveBeenCalledWith(42.5);
});

it("does not show a Play clip button when video_offset_seconds is null", () => {
  render(
    <IncidentFeed
      incidents={[
        { id: 1, hazard_type: "ppe", severity: "warning", caption: "no hard hat", video_offset_seconds: null } as any,
      ]}
    />
  );
  expect(screen.queryByText("Play clip")).toBeNull();
});
```

(add `fireEvent, vi` to that file's existing `vitest`/`@testing-library/react` imports if not already present.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run tests/upload-bar.test.tsx tests/incident-feed.test.tsx`
Expected: FAIL — `onUploaded` never called; no "Play clip" text found.

- [ ] **Step 3: Implement `UploadBar.tsx`**

```tsx
"use client";
import { useState } from "react";

import { uploadVideo } from "../lib/api";

export default function UploadBar({ onUploaded }: { onUploaded?: (filename: string) => void }) {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fileInput = event.currentTarget.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) return;
    try {
      const result = await uploadVideo(file);
      setStatus(`Streaming at ${result.stream_url}`);
      setError(null);
      onUploaded?.(result.filename);
    } catch {
      setError("Upload failed. Try again.");
      setStatus(null);
    }
  }

  return (
    <div className="border border-paper/15 bg-panel p-4">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-3">
        <label htmlFor="file" className="font-mono text-xs uppercase tracking-widest text-paper/50">
          New clip
        </label>
        <input
          id="file"
          type="file"
          name="file"
          accept="video/*"
          data-testid="file-input"
          className="block text-sm text-paper/80 file:mr-4 file:border file:border-paper/20 file:bg-ink file:px-3 file:py-1.5 file:text-sm file:text-paper file:transition-colors hover:file:border-caution"
        />
        <button
          type="submit"
          className="border border-caution bg-caution px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-ink transition-colors hover:bg-ink hover:text-caution"
        >
          Upload
        </button>
      </form>
      {status && (
        <p data-testid="upload-status" className="mt-3 border-l-2 border-signal pl-3 font-mono text-sm text-signal">
          {status}
        </p>
      )}
      {error && (
        <p data-testid="upload-error" className="mt-3 border-l-2 border-alarm pl-3 font-mono text-sm text-alarm">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Implement `IncidentFeed.tsx`**

```tsx
import Link from "next/link";

import { Incident } from "../lib/api";

const SEVERITY: Record<string, { label: string; border: string; text: string }> = {
  critical: { label: "Critical", border: "border-alarm", text: "text-alarm" },
  warning: { label: "Caution", border: "border-caution", text: "text-caution" },
  info: { label: "Clear", border: "border-signal", text: "text-signal" },
};

export default function IncidentFeed({
  incidents,
  onPlayClip,
}: {
  incidents: Incident[];
  onPlayClip?: (offsetSeconds: number) => void;
}) {
  return (
    <ul data-testid="incident-list" className="space-y-2">
      {incidents.length === 0 && (
        <li className="border border-paper/15 bg-panel p-4 text-sm text-paper/50">
          No alerts yet. The floor is clear.
        </li>
      )}
      {incidents.map((incident) => {
        const severity = SEVERITY[incident.severity] ?? SEVERITY.info;
        return (
          <li key={incident.id} className={`border-l-2 ${severity.border} bg-panel`}>
            <Link href={`/incidents/${incident.id}`} className="block p-4 hover:bg-ink/40">
              <span className={`font-mono text-xs uppercase tracking-widest ${severity.text}`}>
                {severity.label}
              </span>
              <p className="mt-1 text-sm">
                <span className="font-mono text-paper/50">{incident.hazard_type}</span>: {incident.caption}
              </p>
            </Link>
            {incident.video_offset_seconds != null && (
              <button
                type="button"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  onPlayClip?.(incident.video_offset_seconds as number);
                }}
                className="mb-3 ml-4 font-mono text-xs uppercase tracking-widest text-signal hover:underline"
              >
                Play clip
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 5: Implement `page.tsx`**

```tsx
"use client";
import { useEffect, useRef, useState } from "react";

import ChatPanel from "../components/ChatPanel";
import IncidentFeed from "../components/IncidentFeed";
import StatsSummary from "../components/StatsSummary";
import UploadBar from "../components/UploadBar";
import VideoPreview from "../components/VideoPreview";
import { Incident, fetchIncidents, subscribeToAlerts, videoUrl } from "../lib/api";

export default function Home() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [activeFilename, setActiveFilename] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    fetchIncidents().then(setIncidents);
  }, []);

  useEffect(() => {
    const source = subscribeToAlerts((incident) => {
      setIncidents((prev) => [incident, ...prev.filter((i) => i.id !== incident.id)]);
    });
    return () => source.close();
  }, []);

  function handlePlayClip(offsetSeconds: number) {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = offsetSeconds;
    video.play();
  }

  return (
    <main className="min-h-screen">
      <div className="hazard-tape h-2 w-full" aria-hidden="true" />
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-caution">Live ops console</p>
            <h1 className="mt-4 font-display text-3xl sm:text-4xl">Warehouse Safety Monitor</h1>
          </div>
          <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-alarm">
            <span className="h-2 w-2 rounded-full bg-alarm" aria-hidden="true" />
            Recording
          </span>
        </div>

        <div className="mt-6">
          <UploadBar onUploaded={setActiveFilename} />
        </div>

        {activeFilename && (
          <div className="mt-6">
            <VideoPreview ref={videoRef} src={videoUrl(activeFilename)} />
          </div>
        )}

        <div className="mt-8 grid gap-8 lg:grid-cols-[2fr_1fr]">
          <IncidentFeed incidents={incidents} onPlayClip={handlePlayClip} />
          <aside className="space-y-8">
            <div className="border border-paper/15 bg-panel p-4">
              <p className="font-mono text-xs uppercase tracking-widest text-paper/50">Ask the floor</p>
              <ChatPanel />
            </div>
            <StatsSummary incidents={incidents} />
          </aside>
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run tests/upload-bar.test.tsx tests/incident-feed.test.tsx tests/page.test.tsx`
Expected: PASS. If `page.test.tsx` fails because its mocked incidents lack `video_offset_seconds`, that's fine — the field being `undefined` behaves the same as `null` for the `!= null` check (no button rendered), so no test changes should be needed there; only adjust `page.test.tsx` if it explicitly fails.

- [ ] **Step 7: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
cd frontend && git add components/UploadBar.tsx components/IncidentFeed.tsx app/page.tsx tests/upload-bar.test.tsx tests/incident-feed.test.tsx
git commit -m "feat: wire video preview and click-to-seek on incident play-clip"
```

---

## Task 11: Quick-action search/summarize chips in `ChatPanel`

**Files:**
- Modify: `frontend/components/ChatPanel.tsx`
- Modify: `frontend/tests/chat-panel.test.tsx`

**Interfaces:** none new exported — purely internal to `ChatPanel`.

- [ ] **Step 1: Write the failing test**

Append to `frontend/tests/chat-panel.test.tsx`:

```tsx
it("sends a canned prompt when a quick-action chip is clicked", async () => {
  (sendChatMessage as any).mockResolvedValue({ answer: "Mock summary." });
  render(<ChatPanel />);

  fireEvent.click(screen.getByText("Summarize today"));

  await waitFor(() => {
    expect(sendChatMessage).toHaveBeenCalledWith("Summarize today's incidents.");
    expect(screen.getByTestId("chat-history").textContent).toContain("Mock summary.");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/chat-panel.test.tsx`
Expected: FAIL — `Unable to find an element with the text: Summarize today`.

- [ ] **Step 3: Implement**

```tsx
"use client";
import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { sendChatMessage } from "../lib/api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

const QUICK_ACTIONS: { label: string; prompt: string }[] = [
  { label: "Summarize today", prompt: "Summarize today's incidents." },
  { label: "Search: forklift", prompt: "Search the archive for forklift proximity incidents." },
  { label: "Search: spill", prompt: "Search the archive for spill incidents." },
];

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  async function sendMessage(text: string) {
    if (!text.trim()) return;
    const userMessage: Message = { role: "user", text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    const result = await sendChatMessage(text);
    setMessages((prev) => [...prev, { role: "assistant", text: result.answer }]);
  }

  return (
    <div className="mt-3 flex flex-col">
      <div className="mb-2 flex flex-wrap gap-2">
        {QUICK_ACTIONS.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => sendMessage(action.prompt)}
            className="border border-paper/20 px-2 py-1 font-mono text-xs uppercase tracking-widest text-paper/60 hover:border-caution hover:text-caution"
          >
            {action.label}
          </button>
        ))}
      </div>
      <ul data-testid="chat-history" className="flex max-h-64 flex-col gap-2 overflow-y-auto text-sm">
        {messages.length === 0 && (
          <li className="text-paper/40">Ask about a hazard, a zone, or how to prevent the next one.</li>
        )}
        {messages.map((message, index) => (
          <li
            key={index}
            className={message.role === "user" ? "text-paper" : "border-l-2 border-signal pl-2 text-paper/80"}
          >
            <span className="font-mono text-xs uppercase tracking-widest text-paper/40">{message.role}</span>
            <br />
            {message.role === "assistant" ? (
              <ReactMarkdown>{message.text}</ReactMarkdown>
            ) : (
              message.text
            )}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <input
          data-testid="chat-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the floor…"
          className="flex-1 border border-paper/20 bg-ink px-3 py-2 text-sm text-paper outline-none focus-visible:border-caution"
        />
        <button
          onClick={() => sendMessage(input)}
          className="border border-caution px-4 py-2 font-mono text-xs uppercase tracking-widest text-caution transition-colors hover:bg-caution hover:text-ink"
        >
          Send
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/chat-panel.test.tsx`
Expected: PASS, including the pre-existing 3 tests (`handleSend` behavior is now `sendMessage(input)` — same externally observable behavior, button text "Send" unchanged).

- [ ] **Step 5: Run the full frontend suite**

Run: `cd frontend && npx vitest run`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
cd frontend && git add components/ChatPanel.tsx tests/chat-panel.test.tsx
git commit -m "feat: add quick-action search/summarize chips to ChatPanel"
```

---

## Final verification

- [ ] Run full backend suite: `cd agent && python -m pytest -v` — expect all PASS.
- [ ] Run full frontend suite: `cd frontend && npx vitest run` — expect all PASS.
- [ ] Manual end-to-end smoke test per updated `docs/local-testing.md` mock section: start `infra/mock_vss.py`, set `VSS_MODE=mock`, run `docker compose --profile mock up -d --build`, upload a short test clip through the dashboard, confirm: incidents appear via SSE, video preview player renders, clicking "Play clip" seeks the player, ChatPanel quick-action chips return canned mock answers.
