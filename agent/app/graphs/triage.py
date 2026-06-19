from typing import Callable, TypedDict

from app.models import Severity


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
