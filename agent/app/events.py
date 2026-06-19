import asyncio


class IncidentBroadcaster:
    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.remove(queue)

    def publish(self, incident: dict) -> None:
        for queue in self._subscribers:
            queue.put_nowait(incident)


broadcaster = IncidentBroadcaster()
