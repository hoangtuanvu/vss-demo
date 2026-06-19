import asyncio

from app.events import IncidentBroadcaster


def test_publish_delivers_to_subscribed_queue():
    broadcaster = IncidentBroadcaster()
    queue = broadcaster.subscribe()
    broadcaster.publish({"id": 1})
    assert queue.get_nowait() == {"id": 1}


def test_unsubscribe_stops_delivery():
    broadcaster = IncidentBroadcaster()
    queue = broadcaster.subscribe()
    broadcaster.unsubscribe(queue)
    broadcaster.publish({"id": 1})
    assert queue.empty()
