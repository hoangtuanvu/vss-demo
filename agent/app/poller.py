import asyncio
import logging

from app import store
from app.models import HazardType

logger = logging.getLogger(__name__)


def run_poll_iteration(vss_client, compiled_graph, since_timestamp, session_factory) -> str | None:
    alerts = vss_client.get_new_alerts(since_timestamp)
    new_since_timestamp = since_timestamp
    for alert in alerts:
        try:
            hazard_type = HazardType(alert["category"])
        except ValueError:
            logger.warning("Skipping alert with unrecognized category: %s", alert.get("category"))
            new_since_timestamp = alert["timestamp"]
            continue
        with session_factory() as session:
            history = [
                {"caption": i.caption, "severity": i.severity.value, "created_at": i.created_at.isoformat()}
                for i in store.list_recent_incidents_by_hazard(session, hazard_type)
            ]
        initial_state = {
            "alert": alert,
            "hazard_type": alert["category"],
            "zone": vss_client.resolve_sensor_id(alert["sensor_id"]),
            "caption": alert.get("description", ""),
            "history": history,
            "severity": None,
            "dedupe_key": None,
            "incident_id": None,
            "is_new": None,
            "report_text": None,
            "escalated": False,
        }
        compiled_graph.invoke(initial_state)
        new_since_timestamp = alert["timestamp"]
    return new_since_timestamp


async def poll_loop(vss_client, compiled_graph, session_factory, interval_seconds: int, stop_event: asyncio.Event):
    since_timestamp = None
    while not stop_event.is_set():
        try:
            since_timestamp = await asyncio.to_thread(
                run_poll_iteration, vss_client, compiled_graph, since_timestamp, session_factory
            )
        except Exception:
            logger.exception("Poll iteration failed, will retry next interval")
        await asyncio.sleep(interval_seconds)
