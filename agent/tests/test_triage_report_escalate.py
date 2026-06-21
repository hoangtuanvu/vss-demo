from app import store
from app.graphs.triage import make_escalate_notify_node, make_generate_report_node
from app.models import HazardType, Severity


class FakeVSSClient:
    def __init__(self, report_text="Incident report"):
        self.report_text = report_text
        self.calls = []

    def generate_report(self, incident):
        self.calls.append(incident)
        return self.report_text


def _seed_incident(session_factory):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.FALL, severity=Severity.CRITICAL,
            zone="aisle-3", caption="person down", raw_alert_payload={}, dedupe_key="fall:aisle-3",
        )
        return incident.id


def test_generate_report_calls_vss_client_with_incident_dict_and_persists(session_factory):
    incident_id = _seed_incident(session_factory)
    vss_client = FakeVSSClient(report_text="Person down in aisle-3 at 10:02.")
    node = make_generate_report_node(vss_client, session_factory)

    result = node({"incident_id": incident_id})

    assert result == {"report_text": "Person down in aisle-3 at 10:02."}
    assert vss_client.calls[0]["id"] == incident_id
    assert vss_client.calls[0]["hazard_type"] == "fall"
    assert vss_client.calls[0]["zone"] == "aisle-3"
    assert vss_client.calls[0]["caption"] == "person down"
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
