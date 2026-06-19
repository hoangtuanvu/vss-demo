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
