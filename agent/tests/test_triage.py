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
