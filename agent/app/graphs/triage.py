from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Callable, TypedDict

from app import store
from app.models import HazardType, Severity, incident_to_dict

CLASSIFY_SEVERITY_TIMEOUT_SECONDS = 15.0


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
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(llm.invoke, prompt)
            text = future.result(timeout=CLASSIFY_SEVERITY_TIMEOUT_SECONDS).content.strip().lower()
        except (Exception, FutureTimeoutError):
            return {"severity": Severity.WARNING.value}
        finally:
            executor.shutdown(wait=False)
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


def make_persist_incident_node(session_factory, broadcaster, upload_state) -> Callable[[dict], dict]:
    def persist_incident(state: dict) -> dict:
        video_offset_seconds = None
        if upload_state.stream_start_at is not None and upload_state.duration_seconds:
            elapsed = (datetime.utcnow() - upload_state.stream_start_at).total_seconds()
            video_offset_seconds = elapsed % upload_state.duration_seconds

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
                    video_offset_seconds=video_offset_seconds,
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

REPORT_PROMPT = (
    "Write a concise warehouse safety incident report.\n"
    "Hazard type: {hazard_type}\nSeverity: {severity}\nZone: {zone}\n"
    "Description: {caption}\nDetected at: {created_at}\n"
    "Report:"
)


def make_generate_report_node(llm, session_factory) -> Callable[[dict], dict]:
    def generate_report(state: dict) -> dict:
        with session_factory() as session:
            incident = store.get_incident(session, state["incident_id"])
            incident_dict = incident_to_dict(incident)
        try:
            report_text = llm.invoke(REPORT_PROMPT.format(**incident_dict)).content.strip()
        except Exception:
            report_text = (
                f"Incident report: {incident_dict['hazard_type']} detected in "
                f"{incident_dict['zone']} at {incident_dict['created_at']}."
            )
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


from typing import Literal

from langgraph.graph import END, StateGraph


def route_by_severity(state: dict) -> Literal["critical", "end"]:
    return "critical" if state["severity"] == Severity.CRITICAL.value else "end"


def build_triage_graph(llm, session_factory, webhook_url: str, dedupe_window_seconds: int, broadcaster, upload_state):
    graph = StateGraph(TriageState)
    graph.add_node("classify_severity", make_classify_severity_node(llm))
    graph.add_node("dedupe", make_dedupe_node(session_factory, dedupe_window_seconds))
    graph.add_node("persist_incident", make_persist_incident_node(session_factory, broadcaster, upload_state))
    graph.add_node("generate_report", make_generate_report_node(llm, session_factory))
    graph.add_node("escalate_notify", make_escalate_notify_node(webhook_url, session_factory))
    graph.set_entry_point("classify_severity")
    graph.add_edge("classify_severity", "dedupe")
    graph.add_edge("dedupe", "persist_incident")
    graph.add_conditional_edges("persist_incident", route_by_severity, {"critical": "generate_report", "end": END})
    graph.add_edge("generate_report", "escalate_notify")
    graph.add_edge("escalate_notify", END)
    return graph.compile()
