import asyncio

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


async def test_alerts_stream_endpoint_returns_event_stream_headers(session_factory, tmp_path):
    # The SSE endpoint streams forever, so it can't be driven through TestClient
    # or httpx's ASGITransport — both await the whole ASGI call before returning
    # a response. Drive the ASGI callable directly and stop once headers land.
    app = make_test_app(session_factory, tmp_path)
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "path": "/alerts/stream", "raw_path": b"/alerts/stream", "query_string": b"",
        "headers": [], "client": ("testclient", 123), "server": ("testserver", 80), "scheme": "http",
    }
    sent = []
    response_started = asyncio.Event()

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.start":
            response_started.set()

    task = asyncio.create_task(app(scope, receive, send))
    try:
        await asyncio.wait_for(response_started.wait(), timeout=2)
        start_message = next(m for m in sent if m["type"] == "http.response.start")
        headers = {k.decode(): v.decode() for k, v in start_message["headers"]}
        assert start_message["status"] == 200
        assert "text/event-stream" in headers["content-type"]
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
