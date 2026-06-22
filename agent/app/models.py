import datetime
import enum

from sqlalchemy import Column, DateTime, Enum as SAEnum, Float, Integer, JSON, String
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
    video_offset_seconds = Column(Float, nullable=True)
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
        "video_offset_seconds": incident.video_offset_seconds,
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
    }
