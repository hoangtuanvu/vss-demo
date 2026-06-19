from typing import Callable, TypedDict

from app import store
from app.models import HazardType, Severity, incident_to_dict


class TriageState(TypedDict):
    alert: dict
    hazard_type: str
    zone: str
    caption: str
    history: list[dict]
    severity: str | None
    dedupe_key: str | None
    incident_id: int | None
    is_new: bool | None
    report_text: str | None
    escalated: bool


SEVERITY_PROMPT = """You are a warehouse safety triage assistant.
Hazard type: {hazard_type}
Zone: {zone}
Detected caption: {caption}
Recent history for this hazard/zone: {history}

Classify this event's severity as exactly one of: critical, warning, info.
Reply with only the single word."""

VALID_SEVERITIES = {s.value for s in Severity}


def make_classify_severity_node(llm) -> Callable[[dict], dict]:
    def classify_severity(state: dict) -> dict:
        prompt = SEVERITY_PROMPT.format(
            hazard_type=state["hazard_type"],
            zone=state["zone"],
            caption=state["caption"],
            history=state["history"],
        )
        try:
            text = llm.invoke(prompt).content.strip().lower()
        except Exception:
            return {"severity": Severity.WARNING.value}
        if text not in VALID_SEVERITIES:
            return {"severity": Severity.WARNING.value}
        return {"severity": text}

    return classify_severity


def make_dedupe_node(session_factory, window_seconds: int) -> Callable[[dict], dict]:
    def dedupe(state: dict) -> dict:
        dedupe_key = f"{state['hazard_type']}:{state['zone']}"
        with session_factory() as session:
            existing = store.get_open_incident_by_dedupe_key(session, dedupe_key, window_seconds)
            if existing is not None:
                return {"dedupe_key": dedupe_key, "incident_id": existing.id, "is_new": False}
        return {"dedupe_key": dedupe_key, "incident_id": None, "is_new": True}

    return dedupe


def make_persist_incident_node(session_factory, broadcaster) -> Callable[[dict], dict]:
    def persist_incident(state: dict) -> dict:
        with session_factory() as session:
            if state["is_new"]:
                incident = store.create_incident(
                    session,
                    hazard_type=HazardType(state["hazard_type"]),
                    severity=Severity(state["severity"]),
                    zone=state["zone"],
                    caption=state["caption"],
                    raw_alert_payload=state["alert"],
                    dedupe_key=state["dedupe_key"],
                )
            else:
                incident = store.update_incident(
                    session,
                    state["incident_id"],
                    caption=state["caption"],
                    severity=Severity(state["severity"]),
                    raw_alert_payload=state["alert"],
                )
            broadcaster.publish(incident_to_dict(incident))
        return {"incident_id": incident.id}

    return persist_incident


import logging

import httpx

from app.models import IncidentStatus

logger = logging.getLogger(__name__)


def make_generate_report_node(vss_client, session_factory) -> Callable[[dict], dict]:
    def generate_report(state: dict) -> dict:
        report_text = vss_client.generate_report(state["incident_id"])
        with session_factory() as session:
            store.update_incident(session, state["incident_id"], report_text=report_text)
        return {"report_text": report_text}

    return generate_report


def make_escalate_notify_node(webhook_url: str, session_factory) -> Callable[[dict], dict]:
    def escalate_notify(state: dict) -> dict:
        if not webhook_url:
            logger.warning("No webhook URL configured, skipping escalation for incident %s", state["incident_id"])
            return {"escalated": False}
        httpx.post(
            webhook_url,
            json={
                "incident_id": state["incident_id"],
                "hazard_type": state["hazard_type"],
                "zone": state["zone"],
                "caption": state["caption"],
                "report_text": state.get("report_text"),
            },
            timeout=5.0,
        )
        with session_factory() as session:
            store.update_incident(session, state["incident_id"], status=IncidentStatus.ESCALATED)
        return {"escalated": True}

    return escalate_notify
