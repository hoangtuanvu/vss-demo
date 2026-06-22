from app.events import IncidentBroadcaster
from app.graphs.triage import make_persist_incident_node
from app.models import HazardType, Severity
from app.upload_state import ActiveUploadState


def test_persist_incident_creates_new_and_publishes(session_factory):
    broadcaster = IncidentBroadcaster()
    queue = broadcaster.subscribe()
    node = make_persist_incident_node(session_factory, broadcaster, ActiveUploadState())

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
    node = make_persist_incident_node(session_factory, broadcaster, ActiveUploadState())
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
