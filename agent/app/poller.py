import asyncio

from app import store
from app.models import HazardType


def run_poll_iteration(vss_client, compiled_graph, cursor, session_factory) -> str | None:
    alerts = vss_client.get_new_alerts(cursor)
    new_cursor = cursor
    for alert in alerts:
        with session_factory() as session:
            history = [
                {"caption": i.caption, "severity": i.severity.value, "created_at": i.created_at.isoformat()}
                for i in store.list_recent_incidents_by_hazard(session, HazardType(alert["hazard_type"]))
            ]
        initial_state = {
            "alert": alert,
            "hazard_type": alert["hazard_type"],
            "zone": alert["zone"],
            "caption": alert["caption"],
            "history": history,
            "severity": None,
            "dedupe_key": None,
            "incident_id": None,
            "is_new": None,
            "report_text": None,
            "escalated": False,
        }
        compiled_graph.invoke(initial_state)
        new_cursor = alert["cursor"]
    return new_cursor


async def poll_loop(vss_client, compiled_graph, session_factory, interval_seconds: int, stop_event: asyncio.Event):
    cursor = None
    while not stop_event.is_set():
        cursor = run_poll_iteration(vss_client, compiled_graph, cursor, session_factory)
        await asyncio.sleep(interval_seconds)
