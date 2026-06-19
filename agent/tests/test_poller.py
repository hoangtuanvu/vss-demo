from app.poller import run_poll_iteration


class FakeVSSClient:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    def get_new_alerts(self, since_cursor):
        self.calls.append(since_cursor)
        return self._batches.pop(0) if self._batches else []


class FakeGraph:
    def __init__(self):
        self.invocations = []

    def invoke(self, state):
        self.invocations.append(state)
        return state


def test_run_poll_iteration_advances_cursor_and_processes_each_alert_once(session_factory):
    batch1 = [
        {"hazard_type": "ppe", "zone": "dock-1", "caption": "no helmet", "cursor": "c1"},
        {"hazard_type": "fall", "zone": "aisle-3", "caption": "person down", "cursor": "c2"},
    ]
    batch2 = [
        {"hazard_type": "spill", "zone": "aisle-1", "caption": "spill", "cursor": "c3"},
    ]
    vss_client = FakeVSSClient([batch1, batch2])
    graph = FakeGraph()

    cursor_after_first = run_poll_iteration(vss_client, graph, None, session_factory)
    cursor_after_second = run_poll_iteration(vss_client, graph, cursor_after_first, session_factory)

    assert cursor_after_first == "c2"
    assert cursor_after_second == "c3"
    assert vss_client.calls == [None, "c2"]
    assert len(graph.invocations) == 3
