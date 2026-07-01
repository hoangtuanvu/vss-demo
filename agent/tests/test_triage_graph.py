from app.events import IncidentBroadcaster
from app.graphs.triage import build_triage_graph
from app.upload_state import ActiveUploadState
from app import store


class FakeLLM:
    def __init__(self, severities):
        self._severities = iter(severities)

    def invoke(self, prompt):
        class R:
            content = next(self._severities)
        return R()


class FakeLLMWithReport:
    """Routes classify-severity calls to the severities iterator; report calls return fixed text."""
    def __init__(self, severities):
        self._severities = iter(severities)

    def invoke(self, prompt):
        class R:
            pass
        r = R()
        if prompt.startswith("Write a concise"):
            r.content = "Mock incident report."
        else:
            r.content = next(self._severities)
        return r


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
    llm = FakeLLMWithReport([severity for *_rest, severity in fixtures])
    graph = build_triage_graph(
        llm, session_factory, "https://hooks.example/webhook",
        dedupe_window_seconds=300, broadcaster=IncidentBroadcaster(),
        upload_state=ActiveUploadState(),
    )

    for hazard_type, zone, caption, expected_severity in fixtures:
        graph.invoke(make_initial_state(hazard_type, zone, caption))

    with session_factory() as session:
        incidents = store.list_incidents(session)
    assert len(incidents) == 5
    by_hazard = {i.hazard_type.value: i for i in incidents}
    assert by_hazard["forklift_proximity"].severity.value == "critical"
    assert by_hazard["forklift_proximity"].report_text is not None
    assert by_hazard["ppe"].severity.value == "warning"
    assert by_hazard["ppe"].report_text is None
