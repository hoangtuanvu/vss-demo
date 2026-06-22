from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HazardType, Incident


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
