import asyncio

from fastapi.testclient import TestClient

from app import store
from app.events import IncidentBroadcaster
from app.main import AppDependencies, create_app
from app.models import HazardType, Severity
from app.upload_state import ActiveUploadState


class FakeVSSClient:
    def __init__(self):
        self.registered_calls = []
        self.deleted_calls = []

    def get_new_alerts(self, since_timestamp):
        return []

    def generate_report(self, incident):
        return "generated report"

    def health_check(self):
        return True

    def register_alert_rules(self, stream_url, sensor_id, rules):
        self.registered_calls.append((stream_url, sensor_id, rules))
        return [f"rule-{i}" for i in range(len(rules))]

    def delete_alert_rules(self, rule_ids):
        self.deleted_calls.append(rule_ids)


class FakeChatGraph:
    def __init__(self):
        self.invocations = []

    def invoke(self, state):
        self.invocations.append(state)
        return {"answer": "the chat answer"}


def make_test_app(session_factory, tmp_path, broadcaster=None, vss_client=None, chat_graph=None):
    deps = AppDependencies(
        session_factory=session_factory,
        triage_graph=None,
        chat_graph=chat_graph or FakeChatGraph(),
        vss_client=vss_client or FakeVSSClient(),
        broadcaster=broadcaster or IncidentBroadcaster(),
        upload_dir=tmp_path,
        mediamtx_rtsp_url="rtsp://localhost:8554",
        upload_state=ActiveUploadState(),
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
    chat_graph = FakeChatGraph()
    app = make_test_app(session_factory, tmp_path, chat_graph=chat_graph)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "how many ppe violations today?"})
    assert response.json() == {"answer": "the chat answer"}
    assert chat_graph.invocations[0]["message"] == "how many ppe violations today?"


def test_upload_starts_rtsp_loopback_and_registers_alert_rules(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    vss_client = FakeVSSClient()
    app = make_test_app(session_factory, tmp_path, vss_client=vss_client)
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.json() == {"stream_url": "rtsp://localhost:8554/clip", "filename": "clip.mp4"}
    assert len(vss_client.registered_calls) == 1
    stream_url, sensor_id, rules = vss_client.registered_calls[0]
    assert stream_url == "rtsp://localhost:8554/clip"
    assert sensor_id == "clip"
    assert len(rules) == 5


def test_upload_deletes_previous_rules_before_registering_new_ones(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    vss_client = FakeVSSClient()
    app = make_test_app(session_factory, tmp_path, vss_client=vss_client)
    with TestClient(app) as client:
        client.post("/upload", files={"file": ("clip1.mp4", b"fake-bytes", "video/mp4")})
        client.post("/upload", files={"file": ("clip2.mp4", b"fake-bytes", "video/mp4")})
    assert len(vss_client.deleted_calls) == 1
    assert vss_client.deleted_calls[0] == ["rule-0", "rule-1", "rule-2", "rule-3", "rule-4"]


def test_chat_includes_active_sensor_context_after_upload(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    chat_graph = FakeChatGraph()
    app = make_test_app(session_factory, tmp_path, chat_graph=chat_graph)
    with TestClient(app) as client:
        client.post("/upload", files={"file": ("forklift_proximity.mp4", b"fake-bytes", "video/mp4")})
        client.post("/chat", json={"message": "how many incidents today?"})
    assert chat_graph.invocations[0]["message"] == (
        "For camera/sensor 'forklift_proximity': how many incidents today?"
    )


def test_upload_succeeds_even_when_register_alert_rules_fails(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")

    class FailingRegisterVSSClient(FakeVSSClient):
        def register_alert_rules(self, stream_url, sensor_id, rules):
            raise RuntimeError("alert-bridge unreachable")

    vss_client = FailingRegisterVSSClient()
    app = make_test_app(session_factory, tmp_path, vss_client=vss_client)
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.status_code == 200
    assert response.json() == {"stream_url": "rtsp://localhost:8554/clip", "filename": "clip.mp4"}


def test_upload_returns_503_when_vss_unreachable(session_factory, tmp_path):
    class UnreachableVSSClient(FakeVSSClient):
        def health_check(self):
            return False

    app = make_test_app(session_factory, tmp_path, vss_client=UnreachableVSSClient())
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
