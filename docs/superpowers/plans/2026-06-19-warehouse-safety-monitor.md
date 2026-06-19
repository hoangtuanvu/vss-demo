# Warehouse Safety Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an agentic Warehouse Safety Monitor: a LangGraph backend that triages safety hazards detected by an NVIDIA VSS `warehouse` deployment, escalates and reports on critical incidents, answers natural-language questions about footage, and exposes all of this through a standalone Next.js dashboard.

**Architecture:** Uploaded video is replayed through an ffmpeg→mediamtx RTSP loopback into a VSS `warehouse` profile deployment (Brev GPU), which runs dense-captioning and 5 hazard alert rules. A FastAPI/LangGraph backend polls VSS's alert endpoint, triages each event (severity classify → dedupe → persist), escalates and auto-reports critical incidents, and serves a chat graph for Q&A. A Next.js frontend drives uploads, shows a live alert feed over SSE, incident detail, chat, and stats.

**Tech Stack:** Python, FastAPI, LangGraph, `langchain-nvidia-ai-endpoints` (ChatNVIDIA), SQLAlchemy, httpx, respx (test mocking), sse-starlette, pytest; Next.js (TypeScript) + Tailwind CSS, Vitest + React Testing Library.

## Global Constraints

- All LLM calls go through `ChatNVIDIA` against NIM models on `build.nvidia.com` using the NGC API key — no other LLM vendor anywhere in the agent loop.
- All 5 hazard types ship: PPE compliance, restricted-zone intrusion, forklift–pedestrian proximity, fall/man-down, spill/obstruction. No scope cut.
- Frontend is a standalone Next.js app — it must not embed or extend VSS's own built-in frontend.
- Video input is file upload only; "live" behavior comes from replaying the upload through an RTSP loopback, not a real camera.
- The agent owns its own incident store (Postgres in deployment, SQLite in tests) — VSS's own Elasticsearch/video-analytics-api stack is explicitly out of scope.
- Automated tests must mock VSS and NIM network calls. The one true end-to-end path (real VLM, real Brev deployment) is a manual/integration check, not CI — do not fabricate an automated test for it.
- Deploying VSS to Brev is a real, billed cloud GPU action — get explicit user confirmation before running the launch command.

---

### Task 1: Repo scaffolding

**Files:**
- Create: `agent/app/__init__.py`
- Create: `agent/requirements.txt`
- Create: `agent/pytest.ini`
- Create: `agent/tests/__init__.py`
- Create: `agent/tests/test_sanity.py`
- Create: `infra/.gitkeep`
- Create: `sample-videos/.gitkeep`
- Create: `.gitignore` (root)
- Modify: `README.md` (root)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: an importable `app` package at `agent/app/`, rooted so `python -m pytest` run from `agent/` resolves `import app`. All later backend tasks add modules under `agent/app/` and tests under `agent/tests/`.

- [ ] **Step 1: Write the failing sanity test**

```python
# agent/tests/test_sanity.py
def test_package_importable():
    import app  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_sanity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create the package and project files**

```python
# agent/app/__init__.py
```

```text
# agent/requirements.txt
fastapi
uvicorn[standard]
pydantic-settings
sqlalchemy
httpx
respx
sse-starlette
langgraph
langchain-nvidia-ai-endpoints
pytest
pytest-asyncio
```

```ini
# agent/pytest.ini
[pytest]
testpaths = tests
pythonpath = .
asyncio_mode = auto
```

```python
# agent/tests/__init__.py
```

```text
# infra/.gitkeep
```

```text
# sample-videos/.gitkeep
```

```text
# .gitignore (root)
agent/.venv/
agent/.env
agent/uploads/
agent/*.db
frontend/node_modules/
frontend/.next/
__pycache__/
*.pyc
.DS_Store
```

Modify root `README.md` — append after the existing `# vss-demo` line:

```markdown

Warehouse Safety Monitor: agentic app on NVIDIA VSS (`warehouse` profile)
+ LangGraph. See `docs/superpowers/specs/2026-06-19-warehouse-safety-monitor-design.md`
for the design and `docs/superpowers/plans/2026-06-19-warehouse-safety-monitor.md`
for the implementation plan.
```

- [ ] **Step 4: Install dependencies and run test to verify it passes**

Run: `cd agent && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m pytest tests/test_sanity.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/__init__.py agent/requirements.txt agent/pytest.ini agent/tests/__init__.py agent/tests/test_sanity.py infra/.gitkeep sample-videos/.gitkeep .gitignore README.md
git commit -m "chore: scaffold agent package and repo layout"
```

---

### Task 2: Deploy VSS `warehouse` profile to Brev

**Files:**
- Create: `infra/brev_deploy.md`
- Create: `agent/.env.example`
- Create: `agent/.env` (untracked — gitignored by Task 1)

**Interfaces:**
- Consumes: nothing
- Produces: a live VSS base URL + NGC API key recorded in `agent/.env`, documented (with placeholders) in `agent/.env.example`. Task 5's `Settings` class reads these env vars: `VSS_BASE_URL`, `NVIDIA_API_KEY`.

This task launches real, billed cloud GPU compute. It has no automated test — verification is a manual health check against the live endpoint.

- [ ] **Step 1: Confirm with the user before launching**

Stop and get explicit confirmation: "About to launch a Brev GPU instance running VSS's `warehouse` profile — this is billed compute. Proceed?" Do not run Step 2 without a yes.

- [ ] **Step 2: Deploy via the `vss-deploy-profile` skill**

Follow `github.com/NVIDIA-AI-Blueprints/video-search-and-summarization/skills/vss-deploy-profile/SKILL.md` in Claude Code, selecting the `warehouse` profile and an NGC API key for NIM access. Record every command actually run (Brev launchable URL or CLI invocation) into `infra/brev_deploy.md`.

- [ ] **Step 3: Record credentials**

```text
# agent/.env.example
NVIDIA_API_KEY=
NIM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL_NAME=nvidia/nemotron-nano-9b-v2
VSS_BASE_URL=
DATABASE_URL=sqlite:///./warehouse.db
SLACK_WEBHOOK_URL=
POLL_INTERVAL_SECONDS=8
DEDUPE_WINDOW_SECONDS=300
MEDIAMTX_RTSP_URL=rtsp://localhost:8554
```

Copy this to `agent/.env` and fill in the real `NVIDIA_API_KEY` and `VSS_BASE_URL` from the deployment.

- [ ] **Step 4: Verify (manual)**

Run: `curl -s "$VSS_BASE_URL/health"` (substitute the real URL)
Expected: a 2xx response indicating the VSS service is up.

- [ ] **Step 5: Commit documentation only**

```bash
git add infra/brev_deploy.md agent/.env.example
git commit -m "docs: record VSS warehouse profile Brev deployment steps"
```

(`agent/.env` stays untracked — it holds real credentials.)

---

### Task 3: Configure the 5 hazard alert rules

**Files:**
- Create: `infra/alert_rules.md`

**Interfaces:**
- Consumes: the live VSS deployment from Task 2.
- Produces: 5 active alert rules on the VSS deployment, each emitting an event with a `hazard_type` tag matching the `HazardType` enum values Task 6 defines: `ppe`, `zone_intrusion`, `forklift_proximity`, `fall`, `spill`. Task 7's `vss_client.get_new_alerts` assumes alert payloads carry this `hazard_type` field.

No automated test — verification is a manual query confirming all 5 rules are registered.

- [ ] **Step 1: Write the 5 natural-language alert rules**

```markdown
# infra/alert_rules.md

| hazard_type | Rule text |
|---|---|
| ppe | "Alert if a person is visible without a hard hat or hi-vis vest in a designated PPE-required zone." |
| zone_intrusion | "Alert if a person enters a marked restricted or no-go zone." |
| forklift_proximity | "Alert if a forklift and a pedestrian are within close proximity (less than approximately 2 meters) of each other." |
| fall | "Alert if a person is on the ground and not moving for more than a few seconds." |
| spill | "Alert if there is a liquid spill, dropped pallet, or other obstruction blocking a walkway." |
```

- [ ] **Step 2: Apply each rule via the VSS alert-management skill**

Follow `vss-manage-alerts` / `vss-deploy-dense-captioning` (per the VSS blueprint repo's `skills/` directory) in Claude Code, once per row above, tagging each rule's emitted events with the matching `hazard_type` value so Task 7's client can read it directly off the alert payload. Record the exact commands run, appended to `infra/alert_rules.md` under a "Commands run" section.

- [ ] **Step 3: Verify (manual)**

Run: `curl -s "$VSS_BASE_URL/alert-rules"` (or the equivalent `vss-manage-alerts` list/query command)
Expected: response lists exactly 5 active rules, one per hazard type above.

- [ ] **Step 4: Commit**

```bash
git add infra/alert_rules.md
git commit -m "docs: configure 5 warehouse hazard alert rules on VSS"
```

---

### Task 4: RTSP loopback utility

**Files:**
- Create: `agent/app/streaming.py`
- Create: `agent/tests/test_streaming.py`
- Create: `infra/mediamtx.yml`

**Interfaces:**
- Consumes: nothing
- Produces: `start_rtsp_loopback(video_path: Path, stream_name: str, mediamtx_rtsp_url: str) -> str`, used by Task 17's `/upload` endpoint to turn an uploaded file into a stream URL VSS can ingest.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_streaming.py
from pathlib import Path
from unittest.mock import patch

from app.streaming import start_rtsp_loopback


def test_start_rtsp_loopback_returns_url_and_invokes_ffmpeg(tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake-video-bytes")

    with patch("app.streaming.subprocess.Popen") as mock_popen:
        url = start_rtsp_loopback(video_path, "cam1", "rtsp://localhost:8554")

    assert url == "rtsp://localhost:8554/cam1"
    args = mock_popen.call_args.args[0]
    assert args[0] == "ffmpeg"
    assert str(video_path) in args
    assert "rtsp://localhost:8554/cam1" in args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_streaming.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.streaming'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/streaming.py
import subprocess
from pathlib import Path


def start_rtsp_loopback(video_path: Path, stream_name: str, mediamtx_rtsp_url: str) -> str:
    rtsp_url = f"{mediamtx_rtsp_url}/{stream_name}"
    subprocess.Popen(
        [
            "ffmpeg", "-re", "-stream_loop", "-1", "-i", str(video_path),
            "-c", "copy", "-f", "rtsp", rtsp_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return rtsp_url
```

```yaml
# infra/mediamtx.yml
paths:
  all:
    source: publisher
rtspAddress: :8554
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_streaming.py -v`
Expected: PASS

- [ ] **Step 5: Verify (manual, real ffmpeg/mediamtx)**

Run mediamtx (`mediamtx infra/mediamtx.yml`) in one terminal, then `python -c "from pathlib import Path; from app.streaming import start_rtsp_loopback; print(start_rtsp_loopback(Path('sample-videos/ppe.mp4'), 'cam1', 'rtsp://localhost:8554'))"` in another, then confirm with `ffprobe rtsp://localhost:8554/cam1` that the stream is live.

- [ ] **Step 6: Commit**

```bash
git add agent/app/streaming.py agent/tests/test_streaming.py infra/mediamtx.yml
git commit -m "feat: add RTSP loopback utility for simulated live camera input"
```

---

### Task 5: FastAPI skeleton, settings, `/health`

**Files:**
- Create: `agent/app/config.py`
- Create: `agent/app/main.py`
- Create: `agent/tests/test_main.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Settings` (pydantic-settings model) and `get_settings() -> Settings`, reused by every later task that needs config. `app` FastAPI instance with `/health`, extended by Task 17 with the real routes.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_main.py
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    nvidia_api_key: str = ""
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model_name: str = "nvidia/nemotron-nano-9b-v2"
    vss_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./warehouse.db"
    slack_webhook_url: str = ""
    poll_interval_seconds: int = 8
    dedupe_window_seconds: int = 300
    mediamtx_rtsp_url: str = "rtsp://localhost:8554"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

```python
# agent/app/main.py
from fastapi import FastAPI

app = FastAPI(title="Warehouse Safety Monitor Agent")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/config.py agent/app/main.py agent/tests/test_main.py
git commit -m "feat: add FastAPI skeleton with settings and health endpoint"
```

---

### Task 6: Incident store (db, models, CRUD)

**Files:**
- Create: `agent/app/db.py`
- Create: `agent/app/models.py`
- Create: `agent/app/store.py`
- Create: `agent/tests/conftest.py`
- Create: `agent/tests/test_store.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `HazardType`, `Severity`, `IncidentStatus` enums (values: `ppe`/`zone_intrusion`/`forklift_proximity`/`fall`/`spill`; `critical`/`warning`/`info`; `open`/`escalated`/`resolved`).
  - `Incident` ORM model and `incident_to_dict(incident: Incident) -> dict`.
  - `make_engine(database_url: str)`, `make_session_factory(engine) -> sessionmaker`.
  - `store.create_incident(session, *, hazard_type, severity, zone, caption, raw_alert_payload, dedupe_key) -> Incident`
  - `store.get_open_incident_by_dedupe_key(session, dedupe_key, window_seconds) -> Incident | None`
  - `store.update_incident(session, incident_id, **fields) -> Incident`
  - `store.list_incidents(session, limit=100) -> list[Incident]`
  - `store.get_incident(session, incident_id) -> Incident | None`
  - `store.list_recent_incidents_by_hazard(session, hazard_type, limit=5) -> list[Incident]`
  - `tests/conftest.py` fixture `session_factory`, reused by every later backend test that touches the store.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/conftest.py
import pytest

from app.db import make_engine, make_session_factory
from app.models import Base


@pytest.fixture
def session_factory():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)
```

```python
# agent/tests/test_store.py
from datetime import datetime, timedelta

from app import store
from app.models import HazardType, Severity, IncidentStatus


def test_create_and_get_incident(session_factory):
    with session_factory() as session:
        incident = store.create_incident(
            session,
            hazard_type=HazardType.PPE,
            severity=Severity.WARNING,
            zone="dock-1",
            caption="no hard hat",
            raw_alert_payload={"hazard_type": "ppe"},
            dedupe_key="ppe:dock-1",
        )
        fetched = store.get_incident(session, incident.id)
        assert fetched.caption == "no hard hat"
        assert fetched.status == IncidentStatus.OPEN


def test_get_open_incident_by_dedupe_key_within_window(session_factory):
    with session_factory() as session:
        created = store.create_incident(
            session,
            hazard_type=HazardType.FALL,
            severity=Severity.CRITICAL,
            zone="aisle-3",
            caption="person down",
            raw_alert_payload={},
            dedupe_key="fall:aisle-3",
        )
        found = store.get_open_incident_by_dedupe_key(session, "fall:aisle-3", window_seconds=300)
        assert found.id == created.id


def test_get_open_incident_by_dedupe_key_outside_window_returns_none(session_factory):
    with session_factory() as session:
        incident = store.create_incident(
            session,
            hazard_type=HazardType.SPILL,
            severity=Severity.WARNING,
            zone="aisle-1",
            caption="spill",
            raw_alert_payload={},
            dedupe_key="spill:aisle-1",
        )
        incident.updated_at = datetime.utcnow() - timedelta(seconds=600)
        session.commit()
        found = store.get_open_incident_by_dedupe_key(session, "spill:aisle-1", window_seconds=300)
        assert found is None


def test_update_incident(session_factory):
    with session_factory() as session:
        incident = store.create_incident(
            session,
            hazard_type=HazardType.ZONE_INTRUSION,
            severity=Severity.WARNING,
            zone="restricted-a",
            caption="person entered",
            raw_alert_payload={},
            dedupe_key="zone_intrusion:restricted-a",
        )
        updated = store.update_incident(session, incident.id, severity=Severity.CRITICAL)
        assert updated.severity == Severity.CRITICAL


def test_list_recent_incidents_by_hazard(session_factory):
    with session_factory() as session:
        store.create_incident(
            session, hazard_type=HazardType.FORKLIFT_PROXIMITY, severity=Severity.WARNING,
            zone="aisle-2", caption="forklift near person", raw_alert_payload={},
            dedupe_key="forklift_proximity:aisle-2",
        )
        recent = store.list_recent_incidents_by_hazard(session, HazardType.FORKLIFT_PROXIMITY)
        assert len(recent) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def make_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

```python
# agent/app/models.py
import datetime
import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, Integer, JSON, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class HazardType(str, enum.Enum):
    PPE = "ppe"
    ZONE_INTRUSION = "zone_intrusion"
    FORKLIFT_PROXIMITY = "forklift_proximity"
    FALL = "fall"
    SPILL = "spill"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    hazard_type = Column(SAEnum(HazardType), nullable=False)
    severity = Column(SAEnum(Severity), nullable=False)
    status = Column(SAEnum(IncidentStatus), nullable=False, default=IncidentStatus.OPEN)
    zone = Column(String, nullable=False)
    caption = Column(String, nullable=False)
    raw_alert_payload = Column(JSON, nullable=False)
    report_text = Column(String, nullable=True)
    dedupe_key = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False
    )


def incident_to_dict(incident: Incident) -> dict:
    return {
        "id": incident.id,
        "hazard_type": incident.hazard_type.value,
        "severity": incident.severity.value,
        "status": incident.status.value,
        "zone": incident.zone,
        "caption": incident.caption,
        "report_text": incident.report_text,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
    }
```

```python
# agent/app/store.py
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HazardType, Incident


def create_incident(
    session: Session, *, hazard_type, severity, zone: str, caption: str,
    raw_alert_payload: dict, dedupe_key: str,
) -> Incident:
    incident = Incident(
        hazard_type=hazard_type, severity=severity, zone=zone, caption=caption,
        raw_alert_payload=raw_alert_payload, dedupe_key=dedupe_key,
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident


def get_open_incident_by_dedupe_key(session: Session, dedupe_key: str, window_seconds: int) -> Incident | None:
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    stmt = (
        select(Incident)
        .where(Incident.dedupe_key == dedupe_key, Incident.updated_at >= cutoff)
        .order_by(Incident.updated_at.desc())
    )
    return session.execute(stmt).scalars().first()


def update_incident(session: Session, incident_id: int, **fields) -> Incident:
    incident = session.get(Incident, incident_id)
    for key, value in fields.items():
        setattr(incident, key, value)
    incident.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(incident)
    return incident


def list_incidents(session: Session, limit: int = 100) -> list[Incident]:
    stmt = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


def get_incident(session: Session, incident_id: int) -> Incident | None:
    return session.get(Incident, incident_id)


def list_recent_incidents_by_hazard(session: Session, hazard_type: HazardType, limit: int = 5) -> list[Incident]:
    stmt = (
        select(Incident)
        .where(Incident.hazard_type == hazard_type)
        .order_by(Incident.created_at.desc())
        .limit(limit)
    )
    return list(session.execute(stmt).scalars().all())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/db.py agent/app/models.py agent/app/store.py agent/tests/conftest.py agent/tests/test_store.py
git commit -m "feat: add incident store (SQLAlchemy models + CRUD)"
```

---

### Task 7: VSS tool client

**Files:**
- Create: `agent/app/vss_client.py`
- Create: `agent/tests/test_vss_client.py`

**Interfaces:**
- Consumes: nothing
- Produces: `VSSClient(base_url, client=None, max_retries=3)` with methods `get_new_alerts(since_cursor) -> list[dict]`, `ask_video(question, clip_ref) -> str`, `query_analytics(query) -> dict`, `search_archive(query) -> list[dict]`, `generate_report(incident_id) -> str`, `health_check() -> bool`. Alert dicts are assumed to carry `hazard_type`, `zone`, `caption`, `cursor` keys (set up by Task 3's alert rules). Used by Tasks 12, 14, 16, 17. `health_check` backs Task 17's pre-upload VSS reachability check (design doc's "VSS unreachable" error-handling requirement).

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_vss_client.py
import httpx
import respx
from httpx import Response

from app.vss_client import VSSClient


@respx.mock
def test_get_new_alerts_parses_payload():
    respx.get("http://vss.test/alerts").mock(
        return_value=Response(200, json={"alerts": [
            {"hazard_type": "ppe", "zone": "dock-1", "caption": "no helmet", "cursor": "c1"}
        ]})
    )
    client = VSSClient(base_url="http://vss.test")
    alerts = client.get_new_alerts(None)
    assert alerts[0]["hazard_type"] == "ppe"


@respx.mock
def test_get_new_alerts_retries_then_succeeds():
    route = respx.get("http://vss.test/alerts")
    route.side_effect = [httpx.TimeoutException("boom"), Response(200, json={"alerts": []})]
    client = VSSClient(base_url="http://vss.test", max_retries=3)
    alerts = client.get_new_alerts(None)
    assert alerts == []
    assert route.call_count == 2


@respx.mock
def test_ask_video_returns_answer():
    respx.post("http://vss.test/ask-video").mock(return_value=Response(200, json={"answer": "two people"}))
    client = VSSClient(base_url="http://vss.test")
    assert client.ask_video("how many people?", "clip-1") == "two people"


@respx.mock
def test_generate_report_returns_text():
    respx.post("http://vss.test/generate-report").mock(return_value=Response(200, json={"report_text": "Incident #1..."}))
    client = VSSClient(base_url="http://vss.test")
    assert client.generate_report(1) == "Incident #1..."


@respx.mock
def test_health_check_returns_true_on_2xx():
    respx.get("http://vss.test/health").mock(return_value=Response(200, json={"status": "ok"}))
    client = VSSClient(base_url="http://vss.test")
    assert client.health_check() is True


@respx.mock
def test_health_check_returns_false_on_failure():
    respx.get("http://vss.test/health").mock(return_value=Response(503))
    client = VSSClient(base_url="http://vss.test", max_retries=1)
    assert client.health_check() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_vss_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.vss_client'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/vss_client.py
import time

import httpx


class VSSClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=10.0)
        self.max_retries = max_retries

    def _request_with_retry(self, method: str, path: str, **kwargs) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.request(method, f"{self.base_url}{path}", **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt * 0.1)
        raise last_exc

    def get_new_alerts(self, since_cursor: str | None) -> list[dict]:
        params = {"since": since_cursor} if since_cursor else {}
        response = self._request_with_retry("GET", "/alerts", params=params)
        return response.json()["alerts"]

    def ask_video(self, question: str, clip_ref: str) -> str:
        response = self._request_with_retry(
            "POST", "/ask-video", json={"question": question, "clip_ref": clip_ref}
        )
        return response.json()["answer"]

    def query_analytics(self, query: str) -> dict:
        response = self._request_with_retry("POST", "/query-analytics", json={"query": query})
        return response.json()

    def search_archive(self, query: str) -> list[dict]:
        response = self._request_with_retry("POST", "/search-archive", json={"query": query})
        return response.json()["results"]

    def generate_report(self, incident_id: int) -> str:
        response = self._request_with_retry(
            "POST", "/generate-report", json={"incident_id": incident_id}
        )
        return response.json()["report_text"]

    def health_check(self) -> bool:
        try:
            self._request_with_retry("GET", "/health")
        except (httpx.TimeoutException, httpx.HTTPStatusError):
            return False
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_vss_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/vss_client.py agent/tests/test_vss_client.py
git commit -m "feat: add VSS REST client with retry/backoff"
```

---

### Task 8: NIM LLM client

**Files:**
- Create: `agent/app/llm.py`
- Create: `agent/tests/test_llm.py`

**Interfaces:**
- Consumes: `Settings` from Task 5.
- Produces: `get_chat_model(settings: Settings) -> ChatNVIDIA`, used by Tasks 9, 15, 16.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_llm.py
from app import llm
from app.config import Settings


def test_get_chat_model_uses_settings(monkeypatch):
    captured = {}

    class FakeChatNVIDIA:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm, "ChatNVIDIA", FakeChatNVIDIA)
    settings = Settings(
        nvidia_api_key="key123", nim_base_url="https://x", llm_model_name="nvidia/nemotron-nano-9b-v2"
    )
    model = llm.get_chat_model(settings)
    assert isinstance(model, FakeChatNVIDIA)
    assert captured["api_key"] == "key123"
    assert captured["base_url"] == "https://x"
    assert captured["model"] == "nvidia/nemotron-nano-9b-v2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/llm.py
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from app.config import Settings


def get_chat_model(settings: Settings) -> ChatNVIDIA:
    return ChatNVIDIA(
        model=settings.llm_model_name,
        api_key=settings.nvidia_api_key,
        base_url=settings.nim_base_url,
        temperature=0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/llm.py agent/tests/test_llm.py
git commit -m "feat: add NIM ChatNVIDIA client wrapper"
```

---

### Task 9: Triage graph — `classify_severity` node

**Files:**
- Create: `agent/app/graphs/__init__.py`
- Create: `agent/app/graphs/triage.py`
- Create: `agent/tests/test_triage_classify.py`

**Interfaces:**
- Consumes: an LLM object with `.invoke(prompt: str) -> object` where the return has a `.content: str` attribute (matches `ChatNVIDIA` from Task 8).
- Produces: `TriageState` TypedDict (fields: `alert: dict`, `hazard_type: str`, `zone: str`, `caption: str`, `history: list[dict]`, `severity: str | None`, `dedupe_key: str | None`, `incident_id: int | None`, `is_new: bool | None`, `report_text: str | None`, `escalated: bool`) and `make_classify_severity_node(llm) -> Callable[[dict], dict]`. Returns `{"severity": "critical"|"warning"|"info"}`, defaulting to `"warning"` on any parse failure or LLM error. Used by Task 13's graph assembly.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_triage_classify.py
from app.graphs.triage import make_classify_severity_node


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def invoke(self, prompt):
        return FakeResponse(self.reply)


class ErrorLLM:
    def invoke(self, prompt):
        raise RuntimeError("boom")


BASE_STATE = {"hazard_type": "fall", "zone": "dock-1", "caption": "person down", "history": []}


def test_classify_severity_parses_valid_reply():
    node = make_classify_severity_node(FakeLLM("critical"))
    assert node(BASE_STATE) == {"severity": "critical"}


def test_classify_severity_falls_back_on_malformed_reply():
    node = make_classify_severity_node(FakeLLM("not-a-severity"))
    assert node(BASE_STATE) == {"severity": "warning"}


def test_classify_severity_falls_back_on_llm_error():
    node = make_classify_severity_node(ErrorLLM())
    assert node(BASE_STATE) == {"severity": "warning"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_triage_classify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.graphs'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/graphs/__init__.py
```

```python
# agent/app/graphs/triage.py
from typing import Callable, TypedDict

from app.models import Severity


class TriageState(TypedDict):
    alert: dict
    hazard_type: str
    zone: str
    caption: str
    history: list[dict]
    severity: str | None
    dedupe_key: str | None
    incident_id: int | None
    is_new: bool | None
    report_text: str | None
    escalated: bool


SEVERITY_PROMPT = """You are a warehouse safety triage assistant.
Hazard type: {hazard_type}
Zone: {zone}
Detected caption: {caption}
Recent history for this hazard/zone: {history}

Classify this event's severity as exactly one of: critical, warning, info.
Reply with only the single word."""

VALID_SEVERITIES = {s.value for s in Severity}


def make_classify_severity_node(llm) -> Callable[[dict], dict]:
    def classify_severity(state: dict) -> dict:
        prompt = SEVERITY_PROMPT.format(
            hazard_type=state["hazard_type"],
            zone=state["zone"],
            caption=state["caption"],
            history=state["history"],
        )
        try:
            text = llm.invoke(prompt).content.strip().lower()
        except Exception:
            return {"severity": Severity.WARNING.value}
        if text not in VALID_SEVERITIES:
            return {"severity": Severity.WARNING.value}
        return {"severity": text}

    return classify_severity
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_triage_classify.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/graphs/__init__.py agent/app/graphs/triage.py agent/tests/test_triage_classify.py
git commit -m "feat: add triage graph severity classification node"
```

---

### Task 10: Triage graph — `dedupe` node

**Files:**
- Modify: `agent/app/graphs/triage.py`
- Create: `agent/tests/test_triage_dedupe.py`

**Interfaces:**
- Consumes: `store.get_open_incident_by_dedupe_key` from Task 6.
- Produces: `make_dedupe_node(session_factory, window_seconds: int) -> Callable[[dict], dict]`. Returns `{"dedupe_key": str, "incident_id": int | None, "is_new": bool}` — `incident_id` is the existing open incident's id when a match is found within the window, else `None` with `is_new=True`. Used by Task 13's graph assembly.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_triage_dedupe.py
from datetime import datetime, timedelta

from app import store
from app.graphs.triage import make_dedupe_node
from app.models import HazardType, Severity


def test_dedupe_merges_into_open_incident_within_window(session_factory):
    with session_factory() as session:
        existing = store.create_incident(
            session, hazard_type=HazardType.FALL, severity=Severity.WARNING,
            zone="aisle-3", caption="person down", raw_alert_payload={},
            dedupe_key="fall:aisle-3",
        )
        existing_id = existing.id

    node = make_dedupe_node(session_factory, window_seconds=300)
    result = node({"hazard_type": "fall", "zone": "aisle-3"})
    assert result == {"dedupe_key": "fall:aisle-3", "incident_id": existing_id, "is_new": False}


def test_dedupe_creates_new_outside_window(session_factory):
    with session_factory() as session:
        existing = store.create_incident(
            session, hazard_type=HazardType.SPILL, severity=Severity.WARNING,
            zone="aisle-1", caption="spill", raw_alert_payload={},
            dedupe_key="spill:aisle-1",
        )
        existing.updated_at = datetime.utcnow() - timedelta(seconds=600)
        session.commit()

    node = make_dedupe_node(session_factory, window_seconds=300)
    result = node({"hazard_type": "spill", "zone": "aisle-1"})
    assert result == {"dedupe_key": "spill:aisle-1", "incident_id": None, "is_new": True}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_triage_dedupe.py -v`
Expected: FAIL with `ImportError: cannot import name 'make_dedupe_node' from 'app.graphs.triage'`

- [ ] **Step 3: Write the implementation**

Append to `agent/app/graphs/triage.py`:

```python
from app import store


def make_dedupe_node(session_factory, window_seconds: int) -> Callable[[dict], dict]:
    def dedupe(state: dict) -> dict:
        dedupe_key = f"{state['hazard_type']}:{state['zone']}"
        with session_factory() as session:
            existing = store.get_open_incident_by_dedupe_key(session, dedupe_key, window_seconds)
            if existing is not None:
                return {"dedupe_key": dedupe_key, "incident_id": existing.id, "is_new": False}
        return {"dedupe_key": dedupe_key, "incident_id": None, "is_new": True}

    return dedupe
```

(`from app import store` joins the existing imports at the top of the file alongside the Task 9 imports.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_triage_dedupe.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/graphs/triage.py agent/tests/test_triage_dedupe.py
git commit -m "feat: add triage graph dedupe node"
```

---

### Task 11: Triage graph — `persist_incident` node + incident broadcaster

**Files:**
- Create: `agent/app/events.py`
- Modify: `agent/app/graphs/triage.py`
- Create: `agent/tests/test_events.py`
- Create: `agent/tests/test_triage_persist.py`

**Interfaces:**
- Consumes: `store.create_incident`/`store.update_incident` from Task 6, `incident_to_dict` from Task 6.
- Produces:
  - `IncidentBroadcaster` with `subscribe() -> asyncio.Queue`, `unsubscribe(queue) -> None`, `publish(incident: dict) -> None`. A module-level `broadcaster = IncidentBroadcaster()` singleton. Used by Task 17's SSE endpoint.
  - `make_persist_incident_node(session_factory, broadcaster) -> Callable[[dict], dict]`. Returns `{"incident_id": int}`, and calls `broadcaster.publish(incident_to_dict(incident))` as a side effect. Used by Task 13's graph assembly.

- [ ] **Step 1: Write the failing tests**

```python
# agent/tests/test_events.py
import asyncio

from app.events import IncidentBroadcaster


def test_publish_delivers_to_subscribed_queue():
    broadcaster = IncidentBroadcaster()
    queue = broadcaster.subscribe()
    broadcaster.publish({"id": 1})
    assert queue.get_nowait() == {"id": 1}


def test_unsubscribe_stops_delivery():
    broadcaster = IncidentBroadcaster()
    queue = broadcaster.subscribe()
    broadcaster.unsubscribe(queue)
    broadcaster.publish({"id": 1})
    assert queue.empty()
```

```python
# agent/tests/test_triage_persist.py
from app.events import IncidentBroadcaster
from app.graphs.triage import make_persist_incident_node
from app.models import HazardType, Severity


def test_persist_incident_creates_new_and_publishes(session_factory):
    broadcaster = IncidentBroadcaster()
    queue = broadcaster.subscribe()
    node = make_persist_incident_node(session_factory, broadcaster)

    result = node({
        "is_new": True, "incident_id": None, "hazard_type": "ppe", "zone": "dock-1",
        "caption": "no hard hat", "severity": "warning", "alert": {"raw": True}, "dedupe_key": "ppe:dock-1",
    })

    assert isinstance(result["incident_id"], int)
    published = queue.get_nowait()
    assert published["id"] == result["incident_id"]
    assert published["caption"] == "no hard hat"


def test_persist_incident_updates_existing(session_factory):
    from app import store
    with session_factory() as session:
        existing = store.create_incident(
            session, hazard_type=HazardType.PPE, severity=Severity.WARNING,
            zone="dock-1", caption="old caption", raw_alert_payload={}, dedupe_key="ppe:dock-1",
        )
        existing_id = existing.id

    broadcaster = IncidentBroadcaster()
    node = make_persist_incident_node(session_factory, broadcaster)
    result = node({
        "is_new": False, "incident_id": existing_id, "hazard_type": "ppe", "zone": "dock-1",
        "caption": "still no hard hat", "severity": "critical", "alert": {}, "dedupe_key": "ppe:dock-1",
    })

    assert result["incident_id"] == existing_id
    with session_factory() as session:
        from app import store
        updated = store.get_incident(session, existing_id)
        assert updated.caption == "still no hard hat"
        assert updated.severity == Severity.CRITICAL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agent && python -m pytest tests/test_events.py tests/test_triage_persist.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.events'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/events.py
import asyncio


class IncidentBroadcaster:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.remove(queue)

    def publish(self, incident: dict) -> None:
        for queue in self._subscribers:
            queue.put_nowait(incident)


broadcaster = IncidentBroadcaster()
```

Append to `agent/app/graphs/triage.py`:

```python
from app.models import HazardType, incident_to_dict


def make_persist_incident_node(session_factory, broadcaster) -> Callable[[dict], dict]:
    def persist_incident(state: dict) -> dict:
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agent && python -m pytest tests/test_events.py tests/test_triage_persist.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/events.py agent/app/graphs/triage.py agent/tests/test_events.py agent/tests/test_triage_persist.py
git commit -m "feat: add incident broadcaster and triage graph persist node"
```

---

### Task 12: Triage graph — `generate_report` and `escalate_notify` nodes

**Files:**
- Modify: `agent/app/graphs/triage.py`
- Create: `agent/tests/test_triage_report_escalate.py`

**Interfaces:**
- Consumes: `vss_client.generate_report` from Task 7, `store.update_incident` from Task 6.
- Produces: `make_generate_report_node(vss_client, session_factory) -> Callable[[dict], dict]` (returns `{"report_text": str}`) and `make_escalate_notify_node(webhook_url, session_factory) -> Callable[[dict], dict]` (returns `{"escalated": bool}`, no-ops with a logged warning if `webhook_url` is empty). Used by Task 13's graph assembly, on the critical-severity branch only.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_triage_report_escalate.py
from app import store
from app.graphs.triage import make_escalate_notify_node, make_generate_report_node
from app.models import HazardType, Severity


class FakeVSSClient:
    def __init__(self, report_text="Incident report"):
        self.report_text = report_text
        self.calls = []

    def generate_report(self, incident_id):
        self.calls.append(incident_id)
        return self.report_text


def _seed_incident(session_factory):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.FALL, severity=Severity.CRITICAL,
            zone="aisle-3", caption="person down", raw_alert_payload={}, dedupe_key="fall:aisle-3",
        )
        return incident.id


def test_generate_report_calls_vss_client_and_persists(session_factory):
    incident_id = _seed_incident(session_factory)
    vss_client = FakeVSSClient(report_text="Person down in aisle-3 at 10:02.")
    node = make_generate_report_node(vss_client, session_factory)

    result = node({"incident_id": incident_id})

    assert result == {"report_text": "Person down in aisle-3 at 10:02."}
    assert vss_client.calls == [incident_id]
    with session_factory() as session:
        assert store.get_incident(session, incident_id).report_text == "Person down in aisle-3 at 10:02."


def test_escalate_notify_posts_webhook_and_updates_status(session_factory, monkeypatch):
    incident_id = _seed_incident(session_factory)
    posted = {}

    def fake_post(url, json, timeout):
        posted["url"] = url
        posted["json"] = json

    monkeypatch.setattr("app.graphs.triage.httpx.post", fake_post)
    node = make_escalate_notify_node("https://hooks.example/webhook", session_factory)

    result = node({
        "incident_id": incident_id, "hazard_type": "fall", "zone": "aisle-3",
        "caption": "person down", "report_text": "report",
    })

    assert result == {"escalated": True}
    assert posted["url"] == "https://hooks.example/webhook"
    assert posted["json"]["incident_id"] == incident_id
    with session_factory() as session:
        from app.models import IncidentStatus
        assert store.get_incident(session, incident_id).status == IncidentStatus.ESCALATED


def test_escalate_notify_skips_when_no_webhook_configured(session_factory):
    incident_id = _seed_incident(session_factory)
    node = make_escalate_notify_node("", session_factory)

    result = node({"incident_id": incident_id, "hazard_type": "fall", "zone": "aisle-3", "caption": "x", "report_text": None})

    assert result == {"escalated": False}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_triage_report_escalate.py -v`
Expected: FAIL with `ImportError: cannot import name 'make_generate_report_node' from 'app.graphs.triage'`

- [ ] **Step 3: Write the implementation**

Append to `agent/app/graphs/triage.py`:

```python
import logging

import httpx

from app.models import IncidentStatus

logger = logging.getLogger(__name__)


def make_generate_report_node(vss_client, session_factory) -> Callable[[dict], dict]:
    def generate_report(state: dict) -> dict:
        report_text = vss_client.generate_report(state["incident_id"])
        with session_factory() as session:
            store.update_incident(session, state["incident_id"], report_text=report_text)
        return {"report_text": report_text}

    return generate_report


def make_escalate_notify_node(webhook_url: str, session_factory) -> Callable[[dict], dict]:
    def escalate_notify(state: dict) -> dict:
        if not webhook_url:
            logger.warning("No webhook URL configured, skipping escalation for incident %s", state["incident_id"])
            return {"escalated": False}
        httpx.post(
            webhook_url,
            json={
                "incident_id": state["incident_id"],
                "hazard_type": state["hazard_type"],
                "zone": state["zone"],
                "caption": state["caption"],
                "report_text": state.get("report_text"),
            },
            timeout=5.0,
        )
        with session_factory() as session:
            store.update_incident(session, state["incident_id"], status=IncidentStatus.ESCALATED)
        return {"escalated": True}

    return escalate_notify
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_triage_report_escalate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/graphs/triage.py agent/tests/test_triage_report_escalate.py
git commit -m "feat: add triage graph report-generation and escalation nodes"
```

---

### Task 13: Assemble the full triage `StateGraph`

**Files:**
- Modify: `agent/app/graphs/triage.py`
- Create: `agent/tests/test_triage_graph.py`

**Interfaces:**
- Consumes: all five node factories from Tasks 9–12.
- Produces: `build_triage_graph(llm, vss_client, session_factory, webhook_url, dedupe_window_seconds, broadcaster) -> CompiledGraph` with `.invoke(initial_state: dict) -> dict`. Used by Task 14's poller and Task 17's app wiring.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_triage_graph.py
from app.events import IncidentBroadcaster
from app.graphs.triage import build_triage_graph
from app import store


class FakeLLM:
    def __init__(self, severities):
        self._severities = iter(severities)

    def invoke(self, prompt):
        class R:
            content = next(self._severities)
        return R()


class FakeVSSClient:
    def generate_report(self, incident_id):
        return f"report for {incident_id}"


def make_initial_state(hazard_type, zone, caption):
    return {
        "alert": {"hazard_type": hazard_type, "zone": zone, "caption": caption},
        "hazard_type": hazard_type, "zone": zone, "caption": caption, "history": [],
        "severity": None, "dedupe_key": None, "incident_id": None, "is_new": None,
        "report_text": None, "escalated": False,
    }


def test_triage_graph_handles_one_fixture_per_hazard(session_factory, monkeypatch):
    monkeypatch.setattr("app.graphs.triage.httpx.post", lambda *a, **k: None)
    fixtures = [
        ("ppe", "dock-1", "no hard hat", "warning"),
        ("zone_intrusion", "restricted-a", "person in restricted zone", "warning"),
        ("forklift_proximity", "aisle-2", "forklift near person", "critical"),
        ("fall", "aisle-3", "person down", "critical"),
        ("spill", "aisle-1", "liquid spill", "info"),
    ]
    llm = FakeLLM([severity for *_rest, severity in fixtures])
    graph = build_triage_graph(
        llm, FakeVSSClient(), session_factory, "https://hooks.example/webhook",
        dedupe_window_seconds=300, broadcaster=IncidentBroadcaster(),
    )

    for hazard_type, zone, caption, expected_severity in fixtures:
        graph.invoke(make_initial_state(hazard_type, zone, caption))

    with session_factory() as session:
        incidents = store.list_incidents(session)
    assert len(incidents) == 5
    by_hazard = {i.hazard_type.value: i for i in incidents}
    assert by_hazard["forklift_proximity"].severity.value == "critical"
    assert by_hazard["forklift_proximity"].report_text == f"report for {by_hazard['forklift_proximity'].id}"
    assert by_hazard["ppe"].severity.value == "warning"
    assert by_hazard["ppe"].report_text is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_triage_graph.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_triage_graph' from 'app.graphs.triage'`

- [ ] **Step 3: Write the implementation**

Append to `agent/app/graphs/triage.py`:

```python
from typing import Literal

from langgraph.graph import END, StateGraph


def route_by_severity(state: dict) -> Literal["critical", "end"]:
    return "critical" if state["severity"] == Severity.CRITICAL.value else "end"


def build_triage_graph(llm, vss_client, session_factory, webhook_url: str, dedupe_window_seconds: int, broadcaster):
    graph = StateGraph(TriageState)
    graph.add_node("classify_severity", make_classify_severity_node(llm))
    graph.add_node("dedupe", make_dedupe_node(session_factory, dedupe_window_seconds))
    graph.add_node("persist_incident", make_persist_incident_node(session_factory, broadcaster))
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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_triage_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/graphs/triage.py agent/tests/test_triage_graph.py
git commit -m "feat: assemble full triage StateGraph"
```

---

### Task 14: Background poll loop

**Files:**
- Create: `agent/app/poller.py`
- Create: `agent/tests/test_poller.py`

**Interfaces:**
- Consumes: `vss_client.get_new_alerts`, a compiled triage graph's `.invoke`, `store.list_recent_incidents_by_hazard`.
- Produces: `run_poll_iteration(vss_client, compiled_graph, cursor, session_factory) -> str | None` (processes one batch, returns the new cursor) and `async def poll_loop(vss_client, compiled_graph, session_factory, interval_seconds, stop_event)`. Used by Task 17's app wiring. Alert dicts are assumed to carry a `cursor` field (per Task 7's interface note).

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_poller.py
from app.poller import run_poll_iteration


class FakeVSSClient:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    def get_new_alerts(self, since_cursor):
        self.calls.append(since_cursor)
        return self._batches.pop(0) if self._batches else []


class FakeGraph:
    def __init__(self):
        self.invocations = []

    def invoke(self, state):
        self.invocations.append(state)
        return state


def test_run_poll_iteration_advances_cursor_and_processes_each_alert_once(session_factory):
    batch1 = [
        {"hazard_type": "ppe", "zone": "dock-1", "caption": "no helmet", "cursor": "c1"},
        {"hazard_type": "fall", "zone": "aisle-3", "caption": "person down", "cursor": "c2"},
    ]
    batch2 = [
        {"hazard_type": "spill", "zone": "aisle-1", "caption": "spill", "cursor": "c3"},
    ]
    vss_client = FakeVSSClient([batch1, batch2])
    graph = FakeGraph()

    cursor_after_first = run_poll_iteration(vss_client, graph, None, session_factory)
    cursor_after_second = run_poll_iteration(vss_client, graph, cursor_after_first, session_factory)

    assert cursor_after_first == "c2"
    assert cursor_after_second == "c3"
    assert vss_client.calls == [None, "c2"]
    assert len(graph.invocations) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_poller.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.poller'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/poller.py
import asyncio

from app import store
from app.models import HazardType


def run_poll_iteration(vss_client, compiled_graph, cursor, session_factory) -> str | None:
    alerts = vss_client.get_new_alerts(cursor)
    new_cursor = cursor
    for alert in alerts:
        with session_factory() as session:
            history = [
                {"caption": i.caption, "severity": i.severity.value, "created_at": i.created_at.isoformat()}
                for i in store.list_recent_incidents_by_hazard(session, HazardType(alert["hazard_type"]))
            ]
        initial_state = {
            "alert": alert,
            "hazard_type": alert["hazard_type"],
            "zone": alert["zone"],
            "caption": alert["caption"],
            "history": history,
            "severity": None,
            "dedupe_key": None,
            "incident_id": None,
            "is_new": None,
            "report_text": None,
            "escalated": False,
        }
        compiled_graph.invoke(initial_state)
        new_cursor = alert["cursor"]
    return new_cursor


async def poll_loop(vss_client, compiled_graph, session_factory, interval_seconds: int, stop_event: asyncio.Event):
    cursor = None
    while not stop_event.is_set():
        cursor = run_poll_iteration(vss_client, compiled_graph, cursor, session_factory)
        await asyncio.sleep(interval_seconds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_poller.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/poller.py agent/tests/test_poller.py
git commit -m "feat: add background alert poll loop"
```

---

### Task 15: Chat graph — `parse_intent` node

**Files:**
- Create: `agent/app/graphs/chat.py`
- Create: `agent/tests/test_chat_classify.py`

**Interfaces:**
- Consumes: same LLM interface as Task 9 (`.invoke(prompt) -> object` with `.content`).
- Produces: `ChatState` TypedDict (`message: str`, `intent: str | None`, `answer: str | None`) and `make_parse_intent_node(llm) -> Callable[[dict], dict]`. Returns `{"intent": "clip_question"|"stats_question"|"archive_search"|"sop_suggestion"}`, defaulting to `"stats_question"` on any parse failure or LLM error. Used by Task 16's graph assembly.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_chat_classify.py
from app.graphs.chat import make_parse_intent_node


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def invoke(self, prompt):
        class R:
            content = self.reply
        return R()


def test_parse_intent_recognizes_each_category():
    for intent in ("clip_question", "stats_question", "archive_search", "sop_suggestion"):
        node = make_parse_intent_node(FakeLLM(intent))
        assert node({"message": "anything"}) == {"intent": intent}


def test_parse_intent_falls_back_on_malformed_reply():
    node = make_parse_intent_node(FakeLLM("nonsense"))
    assert node({"message": "anything"}) == {"intent": "stats_question"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_chat_classify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.graphs.chat'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/graphs/chat.py
from typing import Callable, TypedDict


class ChatState(TypedDict):
    message: str
    intent: str | None
    answer: str | None


INTENT_PROMPT = """Classify the user's question into exactly one category:
clip_question, stats_question, archive_search, sop_suggestion.
Question: {message}
Reply with only the category name."""

VALID_INTENTS = {"clip_question", "stats_question", "archive_search", "sop_suggestion"}


def make_parse_intent_node(llm) -> Callable[[dict], dict]:
    def parse_intent(state: dict) -> dict:
        try:
            intent = llm.invoke(INTENT_PROMPT.format(message=state["message"])).content.strip().lower()
        except Exception:
            intent = "stats_question"
        if intent not in VALID_INTENTS:
            intent = "stats_question"
        return {"intent": intent}

    return parse_intent
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_chat_classify.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/graphs/chat.py agent/tests/test_chat_classify.py
git commit -m "feat: add chat graph intent classification node"
```

---

### Task 16: Chat graph — per-intent handlers and assembly

**Files:**
- Modify: `agent/app/graphs/chat.py`
- Create: `agent/tests/test_chat_graph.py`

**Interfaces:**
- Consumes: `vss_client.ask_video`/`query_analytics`/`search_archive` from Task 7, `store.list_incidents` from Task 6, `make_parse_intent_node` from Task 15.
- Produces: `build_chat_graph(llm, vss_client, session_factory) -> CompiledGraph` with `.invoke({"message": str, "intent": None, "answer": None}) -> dict` returning `{"message", "intent", "answer"}`. Used by Task 17's app wiring. Every handler returns `FALLBACK_ANSWER` instead of raising if its VSS call fails.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_chat_graph.py
from app.graphs.chat import build_chat_graph


class FakeLLMIntent:
    def __init__(self, intent):
        self.intent = intent

    def invoke(self, prompt):
        class R:
            content = self.intent
        return R()


class FakeVSSClient:
    def __init__(self):
        self.ask_video_called = False
        self.query_analytics_called = False
        self.search_archive_called = False

    def ask_video(self, question, clip_ref):
        self.ask_video_called = True
        return "two people in frame"

    def query_analytics(self, query):
        self.query_analytics_called = True
        return {"count": 3}

    def search_archive(self, query):
        self.search_archive_called = True
        return [{"clip": "c1"}]


def test_clip_question_routes_to_ask_video(session_factory):
    vss_client = FakeVSSClient()
    graph = build_chat_graph(FakeLLMIntent("clip_question"), vss_client, session_factory)
    result = graph.invoke({"message": "who is in this clip?", "intent": None, "answer": None})
    assert vss_client.ask_video_called
    assert result["answer"]


def test_stats_question_routes_to_query_analytics(session_factory):
    vss_client = FakeVSSClient()
    graph = build_chat_graph(FakeLLMIntent("stats_question"), vss_client, session_factory)
    result = graph.invoke({"message": "how many ppe violations today?", "intent": None, "answer": None})
    assert vss_client.query_analytics_called
    assert result["answer"]


def test_archive_search_routes_to_search_archive(session_factory):
    vss_client = FakeVSSClient()
    graph = build_chat_graph(FakeLLMIntent("archive_search"), vss_client, session_factory)
    result = graph.invoke({"message": "find clips with a forklift", "intent": None, "answer": None})
    assert vss_client.search_archive_called
    assert result["answer"]


def test_clip_question_falls_back_gracefully_on_tool_error(session_factory):
    class ErrorVSSClient:
        def ask_video(self, question, clip_ref):
            raise RuntimeError("boom")

    graph = build_chat_graph(FakeLLMIntent("clip_question"), ErrorVSSClient(), session_factory)
    result = graph.invoke({"message": "who is in this clip?", "intent": None, "answer": None})
    assert "couldn't fetch" in result["answer"]


def test_sop_suggestion_drafts_from_history(session_factory):
    graph = build_chat_graph(FakeLLMIntent("sop_suggestion"), FakeVSSClient(), session_factory)
    result = graph.invoke({"message": "how do we prevent forklift incidents?", "intent": None, "answer": None})
    assert result["answer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_chat_graph.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_chat_graph' from 'app.graphs.chat'`

- [ ] **Step 3: Write the implementation**

Append to `agent/app/graphs/chat.py`:

```python
from langgraph.graph import END, StateGraph

from app import store

FALLBACK_ANSWER = "Sorry, I couldn't fetch that from the footage right now. Try rephrasing your question."


def make_clip_question_node(vss_client) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        try:
            answer = vss_client.ask_video(state["message"], "latest")
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": answer}

    return handle


def make_stats_question_node(vss_client) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        try:
            result = vss_client.query_analytics(state["message"])
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": str(result)}

    return handle


def make_archive_search_node(vss_client) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        try:
            results = vss_client.search_archive(state["message"])
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": str(results)}

    return handle


SOP_PROMPT = """Recent incident history: {history}
The user asked how to prevent this kind of incident: {message}
Draft a short, concrete SOP improvement suggestion."""


def make_sop_suggestion_node(llm, session_factory) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        with session_factory() as session:
            recent = store.list_incidents(session, limit=5)
        history = [{"hazard_type": i.hazard_type.value, "caption": i.caption} for i in recent]
        try:
            answer = llm.invoke(SOP_PROMPT.format(history=history, message=state["message"])).content.strip()
        except Exception:
            answer = FALLBACK_ANSWER
        return {"answer": answer}

    return handle


def build_chat_graph(llm, vss_client, session_factory):
    graph = StateGraph(ChatState)
    graph.add_node("parse_intent", make_parse_intent_node(llm))
    graph.add_node("clip_question", make_clip_question_node(vss_client))
    graph.add_node("stats_question", make_stats_question_node(vss_client))
    graph.add_node("archive_search", make_archive_search_node(vss_client))
    graph.add_node("sop_suggestion", make_sop_suggestion_node(llm, session_factory))
    graph.set_entry_point("parse_intent")
    graph.add_conditional_edges(
        "parse_intent",
        lambda state: state["intent"],
        {
            "clip_question": "clip_question",
            "stats_question": "stats_question",
            "archive_search": "archive_search",
            "sop_suggestion": "sop_suggestion",
        },
    )
    for node in ("clip_question", "stats_question", "archive_search", "sop_suggestion"):
        graph.add_edge(node, END)
    return graph.compile()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_chat_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/graphs/chat.py agent/tests/test_chat_graph.py
git commit -m "feat: add chat graph per-intent handlers and assembly"
```

---

### Task 17: HTTP API, app wiring, and SSE alert stream

**Files:**
- Modify: `agent/app/main.py` (replaces Task 5's version)
- Create: `agent/app/wiring.py`
- Create: `agent/app/asgi.py`
- Create: `agent/tests/test_api.py`
- Create: `agent/tests/test_sse.py`

**Interfaces:**
- Consumes: everything from Tasks 6–16 (`store`, `VSSClient` incl. `health_check`, `get_chat_model`, `build_triage_graph`, `build_chat_graph`, `poll_loop`, `broadcaster`, `incident_to_dict`, `start_rtsp_loopback`).
- Produces: `AppDependencies` dataclass, `create_app(deps: AppDependencies) -> FastAPI`, `build_app(settings: Settings) -> tuple[FastAPI, AppDependencies]`, and the real `app` object in `agent/app/asgi.py` used by `uvicorn app.asgi:app`. Routes: `GET /health`, `POST /upload`, `GET /incidents`, `GET /incidents/{id}`, `POST /chat`, `GET /alerts/stream`. `/upload` returns 503 if VSS is unreachable and 502 if the RTSP loopback fails to start — per the design doc's error-handling requirements, neither case is an unhandled crash.

- [ ] **Step 1: Write the failing tests**

```python
# agent/tests/test_api.py
from fastapi.testclient import TestClient

from app import store
from app.events import IncidentBroadcaster
from app.main import AppDependencies, create_app
from app.models import HazardType, Severity


class FakeVSSClient:
    def get_new_alerts(self, since_cursor):
        return []

    def generate_report(self, incident_id):
        return "generated report"

    def health_check(self):
        return True


class FakeChatGraph:
    def invoke(self, state):
        return {"answer": "the chat answer"}


def make_test_app(session_factory, tmp_path, broadcaster=None):
    deps = AppDependencies(
        session_factory=session_factory,
        triage_graph=None,
        chat_graph=FakeChatGraph(),
        vss_client=FakeVSSClient(),
        broadcaster=broadcaster or IncidentBroadcaster(),
        upload_dir=tmp_path,
        mediamtx_rtsp_url="rtsp://localhost:8554",
        poll_interval_seconds=9999,
    )
    return create_app(deps)


def test_health(session_factory, tmp_path):
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_list_and_get_incident(session_factory, tmp_path):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.PPE, severity=Severity.WARNING,
            zone="dock-1", caption="no hard hat", raw_alert_payload={}, dedupe_key="ppe:dock-1",
        )
        incident_id = incident.id

    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        listed = client.get("/incidents")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        detail = client.get(f"/incidents/{incident_id}")
        assert detail.status_code == 200
        assert detail.json()["caption"] == "no hard hat"


def test_incident_detail_generates_report_for_critical_without_one(session_factory, tmp_path):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.FALL, severity=Severity.CRITICAL,
            zone="aisle-3", caption="person down", raw_alert_payload={}, dedupe_key="fall:aisle-3",
        )
        incident_id = incident.id

    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        detail = client.get(f"/incidents/{incident_id}")
    assert detail.json()["report_text"] == "generated report"


def test_incident_detail_404_for_missing_incident(session_factory, tmp_path):
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.get("/incidents/999")
    assert response.status_code == 404


def test_chat_endpoint_returns_answer(session_factory, tmp_path):
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "how many ppe violations today?"})
    assert response.json() == {"answer": "the chat answer"}


def test_upload_starts_rtsp_loopback(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.json() == {"stream_url": "rtsp://localhost:8554/clip"}


def test_upload_returns_503_when_vss_unreachable(session_factory, tmp_path):
    class UnreachableVSSClient(FakeVSSClient):
        def health_check(self):
            return False

    deps = AppDependencies(
        session_factory=session_factory, triage_graph=None, chat_graph=FakeChatGraph(),
        vss_client=UnreachableVSSClient(), broadcaster=IncidentBroadcaster(), upload_dir=tmp_path,
        mediamtx_rtsp_url="rtsp://localhost:8554", poll_interval_seconds=9999,
    )
    app = create_app(deps)
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.status_code == 503


def test_upload_returns_502_when_rtsp_loopback_fails(session_factory, tmp_path, monkeypatch):
    def boom(path, name, url):
        raise RuntimeError("ffmpeg not found")

    monkeypatch.setattr("app.main.start_rtsp_loopback", boom)
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.status_code == 502


def test_alerts_stream_endpoint_returns_event_stream_headers(session_factory, tmp_path):
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        with client.stream("GET", "/alerts/stream") as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
```

```python
# agent/tests/test_sse.py
import asyncio
import json

from app.events import IncidentBroadcaster
from app.main import _alert_event_generator


def test_alert_event_generator_yields_published_incident():
    async def run():
        broadcaster = IncidentBroadcaster()
        gen = _alert_event_generator(broadcaster)
        task = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0)
        broadcaster.publish({"id": 1, "caption": "test"})
        return await task

    event = asyncio.run(run())
    assert json.loads(event["data"]) == {"id": 1, "caption": "test"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agent && python -m pytest tests/test_api.py tests/test_sse.py -v`
Expected: FAIL — `AppDependencies`/`create_app` don't accept these fields yet (Task 5's `main.py` only has a bare `app`/`/health`).

- [ ] **Step 3: Write the implementation**

```python
# agent/app/main.py
import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from sse_starlette.sse import EventSourceResponse

from app import store
from app.events import IncidentBroadcaster
from app.models import Severity, incident_to_dict
from app.poller import poll_loop
from app.streaming import start_rtsp_loopback


@dataclass
class AppDependencies:
    session_factory: object
    triage_graph: object
    chat_graph: object
    vss_client: object
    broadcaster: IncidentBroadcaster
    upload_dir: Path
    mediamtx_rtsp_url: str
    poll_interval_seconds: int = 8


async def _alert_event_generator(broadcaster: IncidentBroadcaster):
    queue = broadcaster.subscribe()
    try:
        while True:
            incident = await queue.get()
            yield {"event": "incident", "data": json.dumps(incident)}
    finally:
        broadcaster.unsubscribe(queue)


def create_app(deps: AppDependencies) -> FastAPI:
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        poll_task = None
        if deps.triage_graph is not None:
            poll_task = asyncio.create_task(
                poll_loop(deps.vss_client, deps.triage_graph, deps.session_factory, deps.poll_interval_seconds, stop_event)
            )
        yield
        stop_event.set()
        if poll_task is not None:
            poll_task.cancel()

    app = FastAPI(title="Warehouse Safety Monitor Agent", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok"}

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
        return {"stream_url": stream_url}

    @app.get("/incidents")
    def list_incidents_route():
        with deps.session_factory() as session:
            return [incident_to_dict(i) for i in store.list_incidents(session)]

    @app.get("/incidents/{incident_id}")
    def incident_detail(incident_id: int):
        with deps.session_factory() as session:
            incident = store.get_incident(session, incident_id)
            if incident is None:
                raise HTTPException(status_code=404, detail="incident not found")
            if incident.report_text is None and incident.severity == Severity.CRITICAL:
                report_text = deps.vss_client.generate_report(incident.id)
                incident = store.update_incident(session, incident.id, report_text=report_text)
            return incident_to_dict(incident)

    @app.post("/chat")
    def chat(payload: dict):
        result = deps.chat_graph.invoke({"message": payload["message"], "intent": None, "answer": None})
        return {"answer": result["answer"]}

    @app.get("/alerts/stream")
    async def alerts_stream():
        return EventSourceResponse(_alert_event_generator(deps.broadcaster))

    return app
```

```python
# agent/app/wiring.py
from pathlib import Path

from fastapi import FastAPI

from app.config import Settings
from app.db import make_engine, make_session_factory
from app.events import broadcaster
from app.graphs.chat import build_chat_graph
from app.graphs.triage import build_triage_graph
from app.llm import get_chat_model
from app.main import AppDependencies, create_app
from app.models import Base
from app.vss_client import VSSClient


def build_app(settings: Settings) -> tuple[FastAPI, AppDependencies]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    llm = get_chat_model(settings)
    vss_client = VSSClient(settings.vss_base_url)
    triage_graph = build_triage_graph(
        llm, vss_client, session_factory, settings.slack_webhook_url,
        settings.dedupe_window_seconds, broadcaster,
    )
    chat_graph = build_chat_graph(llm, vss_client, session_factory)
    deps = AppDependencies(
        session_factory=session_factory,
        triage_graph=triage_graph,
        chat_graph=chat_graph,
        vss_client=vss_client,
        broadcaster=broadcaster,
        upload_dir=Path("uploads"),
        mediamtx_rtsp_url=settings.mediamtx_rtsp_url,
        poll_interval_seconds=settings.poll_interval_seconds,
    )
    return create_app(deps), deps
```

```python
# agent/app/asgi.py
from app.config import get_settings
from app.wiring import build_app

app, _deps = build_app(get_settings())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agent && python -m pytest tests/test_api.py tests/test_sse.py -v`
Expected: PASS

- [ ] **Step 5: Verify (manual)**

Run: `cd agent && uvicorn app.asgi:app --reload`
Expected: server starts, `curl localhost:8000/health` returns `{"status": "ok"}`.

- [ ] **Step 6: Commit**

```bash
git add agent/app/main.py agent/app/wiring.py agent/app/asgi.py agent/tests/test_api.py agent/tests/test_sse.py
git commit -m "feat: add HTTP API, app wiring, and SSE alert stream"
```

---

### Task 18: Next.js + Tailwind frontend scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.mjs`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/tests/setup.ts`
- Create: `frontend/tests/page.test.tsx`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/globals.css`
- Create: `frontend/app/page.tsx`
- Create: `frontend/lib/api.ts`
- Create: `frontend/.env.local.example`

**Interfaces:**
- Consumes: backend routes from Task 17 (`/upload`, `/incidents`, `/incidents/{id}`, `/chat`, `/alerts/stream`).
- Produces: `lib/api.ts` exports — `Incident` interface, `uploadVideo(file)`, `fetchIncidents()`, `fetchIncident(id)`, `sendChatMessage(message)`, `subscribeToAlerts(onIncident)` — used by every page task that follows.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/page.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "../app/page";

describe("Home", () => {
  it("renders navigation links", () => {
    render(<Home />);
    expect(screen.getByText("Upload")).toBeTruthy();
    expect(screen.getByText("Live Monitor")).toBeTruthy();
    expect(screen.getByText("Stats")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm install && npm test`
Expected: FAIL — `app/page.tsx` / vitest config don't exist yet.

- [ ] **Step 3: Write the implementation**

```json
// frontend/package.json
{
  "name": "warehouse-safety-monitor-frontend",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "test": "vitest run"
  },
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "typescript": "^5.4.0",
    "@types/react": "^18.3.0",
    "@types/node": "^20.12.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "vitest": "^1.6.0",
    "@testing-library/react": "^15.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "jsdom": "^24.0.0",
    "@vitejs/plugin-react": "^4.2.0"
  }
}
```

```json
// frontend/tsconfig.json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

```js
// frontend/next.config.mjs
/** @type {import('next').NextConfig} */
const nextConfig = {};
export default nextConfig;
```

```ts
// frontend/tailwind.config.ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
export default config;
```

```js
// frontend/postcss.config.js
module.exports = {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

```ts
// frontend/vitest.config.ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
  },
});
```

```ts
// frontend/tests/setup.ts
import "@testing-library/jest-dom";
```

```css
/* frontend/app/globals.css */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

```tsx
// frontend/app/layout.tsx
import "./globals.css";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
```

```tsx
// frontend/app/page.tsx
import Link from "next/link";

export default function Home() {
  return (
    <main>
      <h1>Warehouse Safety Monitor</h1>
      <nav>
        <Link href="/upload">Upload</Link>
        <Link href="/monitor">Live Monitor</Link>
        <Link href="/stats">Stats</Link>
      </nav>
    </main>
  );
}
```

```ts
// frontend/lib/api.ts
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface Incident {
  id: number;
  hazard_type: string;
  severity: string;
  status: string;
  zone: string;
  caption: string;
  report_text: string | null;
  created_at: string;
  updated_at: string;
}

export async function uploadVideo(file: File): Promise<{ stream_url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE_URL}/upload`, { method: "POST", body: formData });
  if (!res.ok) throw new Error("upload failed");
  return res.json();
}

export async function fetchIncidents(): Promise<Incident[]> {
  const res = await fetch(`${API_BASE_URL}/incidents`);
  if (!res.ok) throw new Error("failed to fetch incidents");
  return res.json();
}

export async function fetchIncident(id: number): Promise<Incident> {
  const res = await fetch(`${API_BASE_URL}/incidents/${id}`);
  if (!res.ok) throw new Error("failed to fetch incident");
  return res.json();
}

export async function sendChatMessage(message: string): Promise<{ answer: string }> {
  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("chat failed");
  return res.json();
}

export function subscribeToAlerts(onIncident: (incident: Incident) => void): EventSource {
  const source = new EventSource(`${API_BASE_URL}/alerts/stream`);
  source.addEventListener("incident", (event) => {
    onIncident(JSON.parse((event as MessageEvent).data));
  });
  return source;
}
```

```text
# frontend/.env.local.example
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS

- [ ] **Step 5: Verify build (manual)**

Run: `cd frontend && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/tsconfig.json frontend/next.config.mjs frontend/tailwind.config.ts frontend/postcss.config.js frontend/vitest.config.ts frontend/tests/setup.ts frontend/tests/page.test.tsx frontend/app/layout.tsx frontend/app/globals.css frontend/app/page.tsx frontend/lib/api.ts frontend/.env.local.example
git commit -m "chore: scaffold Next.js + Tailwind frontend"
```

---

### Task 19: Upload page

**Files:**
- Create: `frontend/app/upload/page.tsx`
- Create: `frontend/tests/upload-page.test.tsx`

**Interfaces:**
- Consumes: `uploadVideo` from `lib/api.ts` (Task 18).
- Produces: the `/upload` route, the first stop in the end-to-end data flow.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/upload-page.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ uploadVideo: vi.fn() }));

import UploadPage from "../app/upload/page";
import { uploadVideo } from "../lib/api";

describe("UploadPage", () => {
  it("shows the stream status after a successful upload", async () => {
    (uploadVideo as any).mockResolvedValue({ stream_url: "rtsp://localhost:8554/cam1" });
    render(<UploadPage />);

    const file = new File(["fake"], "clip.mp4", { type: "video/mp4" });
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(screen.getByTestId("upload-status").textContent).toContain("rtsp://localhost:8554/cam1");
    });
  });

  it("shows an error message when the upload fails", async () => {
    (uploadVideo as any).mockRejectedValue(new Error("boom"));
    render(<UploadPage />);

    const file = new File(["fake"], "clip.mp4", { type: "video/mp4" });
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(screen.getByTestId("upload-error")).toBeTruthy();
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- upload-page`
Expected: FAIL — `app/upload/page.tsx` doesn't exist.

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/app/upload/page.tsx
"use client";
import { useState } from "react";

import { uploadVideo } from "../../lib/api";

export default function UploadPage() {
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
    } catch {
      setError("Upload failed. Try again.");
      setStatus(null);
    }
  }

  return (
    <main>
      <h1>Upload Video</h1>
      <form onSubmit={handleSubmit}>
        <input type="file" name="file" accept="video/*" data-testid="file-input" />
        <button type="submit">Upload</button>
      </form>
      {status && <p data-testid="upload-status">{status}</p>}
      {error && <p data-testid="upload-error">{error}</p>}
    </main>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- upload-page`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/app/upload/page.tsx frontend/tests/upload-page.test.tsx
git commit -m "feat: add video upload page"
```

---

### Task 20: Live Monitor page (SSE)

**Files:**
- Create: `frontend/app/monitor/page.tsx`
- Create: `frontend/tests/monitor-page.test.tsx`

**Interfaces:**
- Consumes: `subscribeToAlerts` from `lib/api.ts` (Task 18).
- Produces: the `/monitor` route showing a live, severity-colored incident feed.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/monitor-page.test.tsx
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ subscribeToAlerts: vi.fn() }));

import MonitorPage from "../app/monitor/page";
import { subscribeToAlerts } from "../lib/api";

describe("MonitorPage", () => {
  it("renders an incident pushed over the alert subscription", () => {
    let pushIncident: (incident: any) => void = () => {};
    (subscribeToAlerts as any).mockImplementation((onIncident: any) => {
      pushIncident = onIncident;
      return { close: vi.fn() };
    });

    render(<MonitorPage />);
    act(() => {
      pushIncident({ id: 1, hazard_type: "ppe", severity: "warning", caption: "no hard hat" });
    });

    expect(screen.getByTestId("incident-list").textContent).toContain("no hard hat");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- monitor-page`
Expected: FAIL — `app/monitor/page.tsx` doesn't exist.

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/app/monitor/page.tsx
"use client";
import { useEffect, useState } from "react";

import { Incident, subscribeToAlerts } from "../../lib/api";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "red",
  warning: "orange",
  info: "gray",
};

export default function MonitorPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    const source = subscribeToAlerts((incident) => {
      setIncidents((prev) => [incident, ...prev.filter((i) => i.id !== incident.id)]);
    });
    return () => source.close();
  }, []);

  return (
    <main>
      <h1>Live Monitor</h1>
      <ul data-testid="incident-list">
        {incidents.map((incident) => (
          <li key={incident.id} style={{ color: SEVERITY_COLORS[incident.severity] }}>
            {incident.hazard_type}: {incident.caption}
          </li>
        ))}
      </ul>
    </main>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- monitor-page`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/app/monitor/page.tsx frontend/tests/monitor-page.test.tsx
git commit -m "feat: add live monitor page with SSE alert feed"
```

---

### Task 21: Incident detail page

**Files:**
- Create: `frontend/app/incidents/[id]/page.tsx`
- Create: `frontend/tests/incident-detail-page.test.tsx`

**Interfaces:**
- Consumes: `fetchIncident` from `lib/api.ts` (Task 18).
- Produces: the `/incidents/[id]` route.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/incident-detail-page.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ fetchIncident: vi.fn() }));

import IncidentDetailPage from "../app/incidents/[id]/page";
import { fetchIncident } from "../lib/api";

describe("IncidentDetailPage", () => {
  it("renders incident detail once fetched", async () => {
    (fetchIncident as any).mockResolvedValue({
      id: 1, hazard_type: "fall", severity: "critical", status: "escalated",
      zone: "aisle-3", caption: "person down", report_text: "Incident report text",
      created_at: "2026-06-19T10:00:00", updated_at: "2026-06-19T10:01:00",
    });

    render(<IncidentDetailPage params={{ id: "1" }} />);

    await waitFor(() => {
      expect(screen.getByTestId("incident-caption").textContent).toBe("person down");
    });
    expect(screen.getByTestId("incident-severity").textContent).toBe("critical");
    expect(screen.getByTestId("incident-report").textContent).toBe("Incident report text");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- incident-detail-page`
Expected: FAIL — `app/incidents/[id]/page.tsx` doesn't exist.

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/app/incidents/[id]/page.tsx
"use client";
import { useEffect, useState } from "react";

import { Incident, fetchIncident } from "../../../lib/api";

export default function IncidentDetailPage({ params }: { params: { id: string } }) {
  const [incident, setIncident] = useState<Incident | null>(null);

  useEffect(() => {
    fetchIncident(Number(params.id)).then(setIncident);
  }, [params.id]);

  if (!incident) return <p>Loading...</p>;

  return (
    <main>
      <h1>Incident #{incident.id}</h1>
      <p data-testid="incident-caption">{incident.caption}</p>
      <p data-testid="incident-severity">{incident.severity}</p>
      <p data-testid="incident-status">{incident.status}</p>
      {incident.report_text && <p data-testid="incident-report">{incident.report_text}</p>}
    </main>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- incident-detail-page`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add "frontend/app/incidents/[id]/page.tsx" frontend/tests/incident-detail-page.test.tsx
git commit -m "feat: add incident detail page"
```

---

### Task 22: Chat panel component

**Files:**
- Create: `frontend/components/ChatPanel.tsx`
- Create: `frontend/tests/chat-panel.test.tsx`

**Interfaces:**
- Consumes: `sendChatMessage` from `lib/api.ts` (Task 18).
- Produces: `<ChatPanel />`, mounted on the Live Monitor page (wired in this task) for "ask the footage" Q&A and SOP suggestions.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/chat-panel.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ sendChatMessage: vi.fn() }));

import ChatPanel from "../components/ChatPanel";
import { sendChatMessage } from "../lib/api";

describe("ChatPanel", () => {
  it("sends a message and renders the reply", async () => {
    (sendChatMessage as any).mockResolvedValue({ answer: "Two PPE violations today." });
    render(<ChatPanel />);

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "how many ppe violations today?" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-history").textContent).toContain("Two PPE violations today.");
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- chat-panel`
Expected: FAIL — `components/ChatPanel.tsx` doesn't exist.

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/components/ChatPanel.tsx
"use client";
import { useState } from "react";

import { sendChatMessage } from "../lib/api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  async function handleSend() {
    if (!input.trim()) return;
    const userMessage: Message = { role: "user", text: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    const result = await sendChatMessage(userMessage.text);
    setMessages((prev) => [...prev, { role: "assistant", text: result.answer }]);
  }

  return (
    <div>
      <ul data-testid="chat-history">
        {messages.map((message, index) => (
          <li key={index}>
            {message.role}: {message.text}
          </li>
        ))}
      </ul>
      <input data-testid="chat-input" value={input} onChange={(event) => setInput(event.target.value)} />
      <button onClick={handleSend}>Send</button>
    </div>
  );
}
```

Mount it on the Live Monitor page from Task 20 — append to `frontend/app/monitor/page.tsx`'s returned JSX, just inside `</main>`:

```tsx
      <ChatPanel />
```

and add the import:

```tsx
import ChatPanel from "../../components/ChatPanel";
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- chat-panel`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/components/ChatPanel.tsx frontend/tests/chat-panel.test.tsx frontend/app/monitor/page.tsx
git commit -m "feat: add chat panel and mount it on the live monitor page"
```

---

### Task 23: Stats page

**Files:**
- Create: `frontend/app/stats/page.tsx`
- Create: `frontend/tests/stats-page.test.tsx`

**Interfaces:**
- Consumes: `fetchIncidents` from `lib/api.ts` (Task 18).
- Produces: the `/stats` route.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/stats-page.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ fetchIncidents: vi.fn() }));

import StatsPage from "../app/stats/page";
import { fetchIncidents } from "../lib/api";

describe("StatsPage", () => {
  it("renders incident counts by hazard type and severity", async () => {
    (fetchIncidents as any).mockResolvedValue([
      { id: 1, hazard_type: "ppe", severity: "warning" },
      { id: 2, hazard_type: "ppe", severity: "warning" },
      { id: 3, hazard_type: "fall", severity: "critical" },
    ]);

    render(<StatsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("stats-table").textContent).toContain("ppe:warning");
    });
    expect(screen.getByTestId("stats-table").textContent).toContain("2");
    expect(screen.getByTestId("stats-table").textContent).toContain("fall:critical");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- stats-page`
Expected: FAIL — `app/stats/page.tsx` doesn't exist.

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/app/stats/page.tsx
"use client";
import { useEffect, useState } from "react";

import { Incident, fetchIncidents } from "../../lib/api";

export default function StatsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    fetchIncidents().then(setIncidents);
  }, []);

  const counts: Record<string, number> = {};
  for (const incident of incidents) {
    const key = `${incident.hazard_type}:${incident.severity}`;
    counts[key] = (counts[key] || 0) + 1;
  }

  return (
    <main>
      <h1>Stats</h1>
      <table data-testid="stats-table">
        <tbody>
          {Object.entries(counts).map(([key, count]) => (
            <tr key={key}>
              <td>{key}</td>
              <td>{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- stats-page`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/app/stats/page.tsx frontend/tests/stats-page.test.tsx
git commit -m "feat: add stats page"
```

---

### Task 24: Sample hazard video clips

**Files:**
- Create: `sample-videos/README.md`

**Interfaces:**
- Consumes: nothing
- Produces: 5 short clips (one per hazard) at the exact filenames Task 25's demo script uploads. No automated test — this is sourcing reference material, not code.

- [ ] **Step 1: Document sourcing and expected filenames**

```markdown
# sample-videos/README.md

Each clip should be short (15-30s), clearly depict one hazard, and be
license-safe to keep in a public repo (Creative Commons / public domain, or
self-recorded). Source from Pexels/Pixabay (CC0 warehouse/forklift footage)
or self-record a short clip with a phone, trimmed with:

    ffmpeg -i raw.mp4 -t 20 -c copy clip.mp4

Expected filenames (referenced by `docs/superpowers/demo-script.md`):

| File | Hazard depicted |
|---|---|
| `ppe.mp4` | Person without hard hat / hi-vis vest in a PPE zone |
| `zone_intrusion.mp4` | Person entering a marked restricted zone |
| `forklift_proximity.mp4` | Forklift and pedestrian in close proximity |
| `fall.mp4` | Person falling / lying on the ground, not moving |
| `spill.mp4` | Liquid spill or obstruction blocking a walkway |
```

- [ ] **Step 2: Add the 5 clips to `sample-videos/` matching those filenames** (manual sourcing — not a code step)

- [ ] **Step 3: Commit**

```bash
git add sample-videos/README.md sample-videos/ppe.mp4 sample-videos/zone_intrusion.mp4 sample-videos/forklift_proximity.mp4 sample-videos/fall.mp4 sample-videos/spill.mp4
git commit -m "docs: add sample hazard video clips for the demo"
```

---

### Task 25: Demo script (manual integration pass)

**Files:**
- Create: `docs/superpowers/demo-script.md`

**Interfaces:**
- Consumes: every component built in Tasks 1–24, plus the live VSS deployment from Tasks 2–3.
- Produces: the walkthrough used both as the project's one true end-to-end verification and as the interview demo.

This task's "test" is explicitly manual — running it live against the real Brev VSS deployment and the real VLM. Do not invent an automated test for it; per the spec's Testing strategy, this path cannot be meaningfully mocked.

- [ ] **Step 1: Write the demo script**

```markdown
# docs/superpowers/demo-script.md

## Prerequisites

- VSS `warehouse` profile deployed on Brev (Task 2), 5 alert rules configured (Task 3).
- `agent/.env` filled in with the real `VSS_BASE_URL` and `NVIDIA_API_KEY`.
- mediamtx running: `mediamtx infra/mediamtx.yml`.

## Start the stack

1. `cd agent && source .venv/bin/activate && uvicorn app.asgi:app --reload`
2. `cd frontend && npm run dev`
3. Open `http://localhost:3000`.

## Walkthrough

1. Go to **Upload**, upload `sample-videos/ppe.mp4`. Confirm a `stream_url` status appears.
2. Go to **Live Monitor**. Within ~10-20s (one poll interval), confirm a `ppe` incident appears in the feed.
3. Repeat step 1-2 for `zone_intrusion.mp4`, `forklift_proximity.mp4`, `fall.mp4`, `spill.mp4` — confirm one incident per hazard type appears, each tagged correctly.
4. Click into the `forklift_proximity` or `fall` incident (expected critical severity) — confirm an auto-generated report is shown and the configured Slack/webhook received a notification.
5. Click into the `ppe` incident (expected warning severity) — confirm no report/escalation was triggered.
6. In the chat panel, ask one question per intent:
   - "What's happening in the latest clip?" (clip_question)
   - "How many PPE violations today?" (stats_question)
   - "Find clips with a forklift" (archive_search)
   - "How do we prevent fall incidents like this?" (sop_suggestion)
   Confirm each returns a relevant, non-generic answer.
7. Go to **Stats**, confirm counts by hazard type/severity match what was triggered in steps 2-3.

## Known limitations to mention in the interview

- Dedupe window (5 min) and poll interval (8s) are tuned for a short demo, not production.
- VSS's own analytics stack (Elasticsearch/video-analytics-api) is intentionally not deployed — the agent owns its own incident store instead.
```

- [ ] **Step 2: Run the walkthrough once, live, before the interview** (manual — not a code step)

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/demo-script.md
git commit -m "docs: add end-to-end demo script for interview walkthrough"
```
