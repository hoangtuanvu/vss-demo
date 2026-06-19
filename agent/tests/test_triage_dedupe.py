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
