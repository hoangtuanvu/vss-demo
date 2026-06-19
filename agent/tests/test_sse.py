import asyncio
import json

from app.events import IncidentBroadcaster
from app.main import _alert_event_generator


def test_alert_event_generator_yields_published_incident():
    async def run():
        broadcaster = IncidentBroadcaster()
        gen = _alert_event_generator(broadcaster)
        task = asyncio.ensure_future(gen.__anext__())
        await asyncio.sleep(0)
        broadcaster.publish({"id": 1, "caption": "test"})
        return await task

    event = asyncio.run(run())
    assert json.loads(event["data"]) == {"id": 1, "caption": "test"}
