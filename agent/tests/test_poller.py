from app.poller import run_poll_iteration


class FakeVSSClient:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    def get_new_alerts(self, since_timestamp):
        self.calls.append(since_timestamp)
        return self._batches.pop(0) if self._batches else []

    def resolve_sensor_id(self, raw_sensor_id):
        return raw_sensor_id


class FakeGraph:
    def __init__(self):
        self.invocations = []

    def invoke(self, state):
        self.invocations.append(state)
        return state


def test_run_poll_iteration_advances_timestamp_and_processes_each_alert_once(session_factory):
    batch1 = [
        {"id": "i1", "category": "ppe", "sensor_id": "dock-1", "timestamp": "2026-06-21T12:00:00Z", "description": "no helmet"},
        {"id": "i2", "category": "fall", "sensor_id": "aisle-3", "timestamp": "2026-06-21T12:01:00Z", "description": "person down"},
    ]
    batch2 = [
        {"id": "i3", "category": "spill", "sensor_id": "aisle-1", "timestamp": "2026-06-21T12:02:00Z", "description": "spill"},
    ]
    vss_client = FakeVSSClient([batch1, batch2])
    graph = FakeGraph()

    ts_after_first = run_poll_iteration(vss_client, graph, None, session_factory)
    ts_after_second = run_poll_iteration(vss_client, graph, ts_after_first, session_factory)

    assert ts_after_first == "2026-06-21T12:01:00Z"
    assert ts_after_second == "2026-06-21T12:02:00Z"
    assert vss_client.calls == [None, "2026-06-21T12:01:00Z"]
    assert len(graph.invocations) == 3
    assert graph.invocations[0]["hazard_type"] == "ppe"
    assert graph.invocations[0]["zone"] == "dock-1"
    assert graph.invocations[0]["caption"] == "no helmet"


def test_run_poll_iteration_returns_unchanged_timestamp_when_no_alerts(session_factory):
    vss_client = FakeVSSClient([[]])
    graph = FakeGraph()
    result = run_poll_iteration(vss_client, graph, "2026-06-21T12:00:00Z", session_factory)
    assert result == "2026-06-21T12:00:00Z"


def test_run_poll_iteration_skips_unrecognized_category_without_crashing(session_factory):
    batch = [
        {"id": "i1", "category": "robot_malfunction", "sensor_id": "dock-1", "timestamp": "2026-06-21T12:00:00Z", "description": "unknown hazard"},
        {"id": "i2", "category": "fall", "sensor_id": "aisle-3", "timestamp": "2026-06-21T12:01:00Z", "description": "person down"},
    ]
    vss_client = FakeVSSClient([batch])
    graph = FakeGraph()

    result = run_poll_iteration(vss_client, graph, None, session_factory)

    assert result == "2026-06-21T12:01:00Z"
    assert len(graph.invocations) == 1
    assert graph.invocations[0]["hazard_type"] == "fall"
