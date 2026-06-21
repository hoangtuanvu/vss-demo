# Real VSS Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fictional VSS REST client (`/alerts`, `/ask-video`, `/query-analytics`, `/search-archive`, `/generate-report`) with one that matches the real NVIDIA VSS warehouse blueprint API, now live on a Brev GPU instance, and update every downstream consumer (poller, chat graph, upload flow, tests) accordingly.

**Architecture:** `VSSClient` talks to two real backends — vss-agent (port 8000, `/chat`) and alert-bridge (port 9080, `/api/v1/realtime*`) — instead of one fictional host. The poller switches from opaque cursors to last-seen-timestamp filtering. The chat graph collapses from a 4-way intent router to a single passthrough node, since the real agent already does intent routing server-side. `/upload` now also registers the 5 hazard alert rules against the new stream's RTSP URL.

**Tech Stack:** Python, FastAPI, LangGraph, httpx, respx (test mocking), pytest — same stack as the rest of `agent/`.

## Global Constraints

- All real network calls in tests must stay `respx`-mocked — no live network access from CI.
- `vss-agent` reachable at `http://216.81.245.166:8000`, `alert-bridge` at `http://216.81.245.166:9080` (Brev instance `vss-warehouse`, UFW-opened for both ports).
- The 5 hazard types and their exact rule prompts are fixed (from `infra/alert_rules.md` / the original implementation plan): `ppe`, `zone_intrusion`, `forklift_proximity`, `fall`, `spill`.
- Don't touch `agent/app/graphs/triage.py`'s severity classification, dedupe, or escalation logic — only the `generate_report` node's call into `vss_client`.

---

### Task 1: Settings — split `VSS_BASE_URL` into two real backend URLs

**Files:**
- Modify: `agent/app/config.py:10`
- Create: `agent/.env.example`
- Modify: `docker-compose.yml:17`
- Create: `agent/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.vss_agent_base_url: str`, `Settings.vss_alert_bridge_base_url: str` (replacing `Settings.vss_base_url`). Consumed by Task 3's `VSSClient` and Task 7's `wiring.py`.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_config.py
from app.config import Settings


def test_settings_has_split_vss_backend_urls():
    settings = Settings(
        vss_agent_base_url="http://example.test:8000",
        vss_alert_bridge_base_url="http://example.test:9080",
    )
    assert settings.vss_agent_base_url == "http://example.test:8000"
    assert settings.vss_alert_bridge_base_url == "http://example.test:9080"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_config.py -v`
Expected: FAIL with `pydantic_core._pydantic_core.ValidationError` (unexpected keyword arguments) or `AttributeError: 'Settings' object has no attribute 'vss_agent_base_url'`

- [ ] **Step 3: Replace the field in `Settings`**

In `agent/app/config.py`, replace line 10:

```python
    vss_base_url: str = "http://localhost:8000"
```

with:

```python
    vss_agent_base_url: str = "http://localhost:8000"
    vss_alert_bridge_base_url: str = "http://localhost:9080"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Create `agent/.env.example`**

```text
# agent/.env.example
NVIDIA_API_KEY=
NIM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL_NAME=nvidia/nemotron-nano-9b-v2
VSS_AGENT_BASE_URL=http://216.81.245.166:8000
VSS_ALERT_BRIDGE_BASE_URL=http://216.81.245.166:9080
DATABASE_URL=sqlite:///./warehouse.db
SLACK_WEBHOOK_URL=
POLL_INTERVAL_SECONDS=8
DEDUPE_WINDOW_SECONDS=300
MEDIAMTX_RTSP_URL=rtsp://localhost:8554
```

- [ ] **Step 6: Update `docker-compose.yml`**

Replace line 17 (`VSS_BASE_URL: ${VSS_BASE_URL:-http://localhost:8001}`) with:

```yaml
      VSS_AGENT_BASE_URL: ${VSS_AGENT_BASE_URL:-http://localhost:8000}
      VSS_ALERT_BRIDGE_BASE_URL: ${VSS_ALERT_BRIDGE_BASE_URL:-http://localhost:9080}
```

- [ ] **Step 7: Commit**

```bash
git add agent/app/config.py agent/.env.example docker-compose.yml agent/tests/test_config.py
git commit -m "feat: split VSS_BASE_URL into agent + alert-bridge backend URLs"
```

---

### Task 2: Hazard alert rule definitions

**Files:**
- Create: `agent/app/alert_rules.py`
- Create: `infra/alert_rules.md`
- Create: `agent/tests/test_alert_rules.py`

**Interfaces:**
- Produces: `HAZARD_ALERT_RULES: list[dict]` — 5 entries, each `{"alert_type": str, "prompt": str, "system_prompt": str}`. Consumed by Task 8's `/upload` handler via `VSSClient.register_alert_rules`.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_alert_rules.py
from app.alert_rules import HAZARD_ALERT_RULES


def test_hazard_alert_rules_covers_all_five_types():
    alert_types = {rule["alert_type"] for rule in HAZARD_ALERT_RULES}
    assert alert_types == {"ppe", "zone_intrusion", "forklift_proximity", "fall", "spill"}


def test_every_rule_has_prompt_and_system_prompt():
    for rule in HAZARD_ALERT_RULES:
        assert rule["prompt"]
        assert rule["system_prompt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_alert_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.alert_rules'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/alert_rules.py
SYSTEM_PROMPT = (
    "You are a warehouse safety monitoring system watching a live video feed. "
    "Analyze each frame for the specific hazard described and alert only when "
    "it is clearly present."
)

HAZARD_ALERT_RULES: list[dict] = [
    {
        "alert_type": "ppe",
        "prompt": "Alert if a person is visible without a hard hat or hi-vis vest in a designated PPE-required zone.",
        "system_prompt": SYSTEM_PROMPT,
    },
    {
        "alert_type": "zone_intrusion",
        "prompt": "Alert if a person enters a marked restricted or no-go zone.",
        "system_prompt": SYSTEM_PROMPT,
    },
    {
        "alert_type": "forklift_proximity",
        "prompt": "Alert if a forklift and a pedestrian are within close proximity (less than approximately 2 meters) of each other.",
        "system_prompt": SYSTEM_PROMPT,
    },
    {
        "alert_type": "fall",
        "prompt": "Alert if a person is on the ground and not moving for more than a few seconds.",
        "system_prompt": SYSTEM_PROMPT,
    },
    {
        "alert_type": "spill",
        "prompt": "Alert if there is a liquid spill, dropped pallet, or other obstruction blocking a walkway.",
        "system_prompt": SYSTEM_PROMPT,
    },
]
```

```markdown
# infra/alert_rules.md

The 5 hazard alert rules registered against each uploaded clip's RTSP stream
via `alert-bridge`'s `POST /api/v1/realtime` (see `agent/app/alert_rules.py`
for the source of truth — this table documents the same data).

| alert_type | prompt |
|---|---|
| ppe | "Alert if a person is visible without a hard hat or hi-vis vest in a designated PPE-required zone." |
| zone_intrusion | "Alert if a person enters a marked restricted or no-go zone." |
| forklift_proximity | "Alert if a forklift and a pedestrian are within close proximity (less than approximately 2 meters) of each other." |
| fall | "Alert if a person is on the ground and not moving for more than a few seconds." |
| spill | "Alert if there is a liquid spill, dropped pallet, or other obstruction blocking a walkway." |

All 5 rules share the same `system_prompt` (see `SYSTEM_PROMPT` in
`agent/app/alert_rules.py`). Rules are registered per upload (see Task 8 of
`docs/superpowers/plans/2026-06-21-real-vss-integration.md`) against that
clip's RTSP loopback URL, and the previous upload's rules are deleted first
— this is a single-active-stream demo, not multi-tenant.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_alert_rules.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/alert_rules.py infra/alert_rules.md agent/tests/test_alert_rules.py
git commit -m "feat: define the 5 hazard alert rules for real VSS alert-bridge"
```

---

### Task 3: Rewrite `VSSClient` for the real API

**Files:**
- Modify: `agent/app/vss_client.py` (full rewrite)
- Modify: `agent/tests/test_vss_client.py` (full rewrite)

**Interfaces:**
- Consumes: nothing new.
- Produces: `VSSClient(agent_base_url, alert_bridge_base_url, client=None, max_retries=3)` with:
  - `get_new_alerts(since_timestamp: str | None) -> list[dict]` — each dict has `id`, `category`, `sensor_id`, `timestamp`, `description` (real alert-bridge incident shape), sorted ascending by `timestamp`.
  - `chat(message: str) -> str` — posts OpenAI-style `messages` to vss-agent `/chat`, returns `choices[0].message.content`.
  - `generate_report(incident: dict) -> str` — `incident` is an `incident_to_dict(...)`-shaped dict (`id`, `hazard_type`, `severity`, `zone`, `caption`, `created_at`, ...); builds a prompt from it and calls `chat()`.
  - `register_alert_rules(stream_url: str, sensor_id: str, rules: list[dict]) -> list[str]` — POSTs each rule (`alert_type`/`prompt`/`system_prompt`) to alert-bridge, returns the created rule ids.
  - `delete_alert_rules(rule_ids: list[str]) -> None` — DELETEs each rule id.
  - `health_check() -> bool` — True only if both vss-agent `/health` and alert-bridge `/health` succeed.
  Used by Tasks 4 (poller), 5 (chat graph), 6 (triage `generate_report` node), 8 (`/upload`).

- [ ] **Step 1: Write the failing tests**

```python
# agent/tests/test_vss_client.py
import httpx
import respx
from httpx import Response

from app.vss_client import VSSClient


def make_client(max_retries=3):
    return VSSClient(
        agent_base_url="http://agent.test",
        alert_bridge_base_url="http://alertbridge.test",
        max_retries=max_retries,
    )


@respx.mock
def test_get_new_alerts_parses_and_sorts_by_timestamp():
    respx.get("http://alertbridge.test/api/v1/realtime/incidents").mock(
        return_value=Response(200, json={
            "status": "success",
            "count": 2,
            "total": 2,
            "timestamp": "2026-06-21T12:05:00Z",
            "incidents": [
                {"id": "i2", "category": "fall", "sensor_id": "cam1", "timestamp": "2026-06-21T12:01:00Z", "description": "person down"},
                {"id": "i1", "category": "ppe", "sensor_id": "cam1", "timestamp": "2026-06-21T12:00:00Z", "description": "no helmet"},
            ],
        })
    )
    client = make_client()
    alerts = client.get_new_alerts(None)
    assert [a["id"] for a in alerts] == ["i1", "i2"]


@respx.mock
def test_get_new_alerts_passes_start_time_param():
    route = respx.get("http://alertbridge.test/api/v1/realtime/incidents").mock(
        return_value=Response(200, json={"status": "success", "count": 0, "total": 0, "timestamp": "x", "incidents": []})
    )
    client = make_client()
    client.get_new_alerts("2026-06-21T12:00:00Z")
    assert route.calls.last.request.url.params["start_time"] == "2026-06-21T12:00:00Z"


@respx.mock
def test_get_new_alerts_retries_then_succeeds():
    route = respx.get("http://alertbridge.test/api/v1/realtime/incidents")
    route.side_effect = [
        httpx.TimeoutException("boom"),
        Response(200, json={"status": "success", "count": 0, "total": 0, "timestamp": "x", "incidents": []}),
    ]
    client = make_client()
    alerts = client.get_new_alerts(None)
    assert alerts == []
    assert route.call_count == 2


@respx.mock
def test_chat_sends_openai_style_messages_and_parses_content():
    route = respx.post("http://agent.test/chat").mock(
        return_value=Response(200, json={
            "id": "x", "object": "chat.completion", "model": "m", "created": 0,
            "choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "two people", "role": "assistant"}}],
        })
    )
    client = make_client()
    answer = client.chat("how many people?")
    assert answer == "two people"
    sent_body = route.calls.last.request.content
    assert b'"role":"user"' in sent_body
    assert b'"content":"how many people?"' in sent_body


@respx.mock
def test_generate_report_builds_prompt_from_incident_and_calls_chat():
    route = respx.post("http://agent.test/chat").mock(
        return_value=Response(200, json={
            "choices": [{"message": {"content": "Person down in aisle-3.", "role": "assistant"}}],
        })
    )
    client = make_client()
    incident = {
        "id": 1, "hazard_type": "fall", "severity": "critical", "status": "open",
        "zone": "aisle-3", "caption": "person down", "report_text": None,
        "created_at": "2026-06-21T12:00:00", "updated_at": "2026-06-21T12:00:00",
    }
    report = client.generate_report(incident)
    assert report == "Person down in aisle-3."
    sent_body = route.calls.last.request.content
    assert b"aisle-3" in sent_body
    assert b"fall" in sent_body


@respx.mock
def test_register_alert_rules_posts_each_rule_and_returns_ids():
    respx.post("http://alertbridge.test/api/v1/realtime").mock(side_effect=[
        Response(200, json={"id": "rule-1", "status": "success", "message": "created"}),
        Response(200, json={"id": "rule-2", "status": "success", "message": "created"}),
    ])
    client = make_client()
    rules = [
        {"alert_type": "ppe", "prompt": "p1", "system_prompt": "s1"},
        {"alert_type": "fall", "prompt": "p2", "system_prompt": "s2"},
    ]
    ids = client.register_alert_rules("rtsp://localhost:8554/cam1", "cam1", rules)
    assert ids == ["rule-1", "rule-2"]


@respx.mock
def test_delete_alert_rules_deletes_each_id():
    route1 = respx.delete("http://alertbridge.test/api/v1/realtime/rule-1").mock(
        return_value=Response(200, json={"id": "rule-1", "status": "success", "message": "deleted"})
    )
    route2 = respx.delete("http://alertbridge.test/api/v1/realtime/rule-2").mock(
        return_value=Response(200, json={"id": "rule-2", "status": "success", "message": "deleted"})
    )
    client = make_client()
    client.delete_alert_rules(["rule-1", "rule-2"])
    assert route1.called
    assert route2.called


@respx.mock
def test_health_check_returns_true_when_both_backends_healthy():
    respx.get("http://agent.test/health").mock(return_value=Response(200, json={"value": {"isAlive": True}}))
    respx.get("http://alertbridge.test/health").mock(return_value=Response(200, json={"status": "ok"}))
    client = make_client()
    assert client.health_check() is True


@respx.mock
def test_health_check_returns_false_if_either_backend_fails():
    respx.get("http://agent.test/health").mock(return_value=Response(503))
    respx.get("http://alertbridge.test/health").mock(return_value=Response(200, json={"status": "ok"}))
    client = make_client(max_retries=1)
    assert client.health_check() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agent && python -m pytest tests/test_vss_client.py -v`
Expected: FAIL — `TypeError: VSSClient.__init__() got an unexpected keyword argument 'agent_base_url'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/vss_client.py
import time

import httpx


class VSSClient:
    def __init__(
        self,
        agent_base_url: str,
        alert_bridge_base_url: str,
        client: httpx.Client | None = None,
        max_retries: int = 3,
    ):
        self.agent_base_url = agent_base_url.rstrip("/")
        self.alert_bridge_base_url = alert_bridge_base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=10.0)
        self.max_retries = max_retries

    def _request_with_retry(self, method: str, base_url: str, path: str, **kwargs) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.request(method, f"{base_url}{path}", **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(2 ** attempt * 0.1)
        raise last_exc

    def get_new_alerts(self, since_timestamp: str | None) -> list[dict]:
        params = {"limit": 100}
        if since_timestamp:
            params["start_time"] = since_timestamp
        response = self._request_with_retry(
            "GET", self.alert_bridge_base_url, "/api/v1/realtime/incidents", params=params
        )
        incidents = response.json()["incidents"]
        incidents.sort(key=lambda incident: incident["timestamp"])
        return incidents

    def chat(self, message: str) -> str:
        response = self._request_with_retry(
            "POST",
            self.agent_base_url,
            "/chat",
            json={"messages": [{"role": "user", "content": message}]},
        )
        return response.json()["choices"][0]["message"]["content"]

    def generate_report(self, incident: dict) -> str:
        prompt = (
            "Write a short incident report for this warehouse safety incident.\n"
            f"Hazard type: {incident['hazard_type']}\n"
            f"Severity: {incident['severity']}\n"
            f"Zone: {incident['zone']}\n"
            f"Description: {incident['caption']}\n"
            f"Detected at: {incident['created_at']}\n"
        )
        return self.chat(prompt)

    def register_alert_rules(self, stream_url: str, sensor_id: str, rules: list[dict]) -> list[str]:
        rule_ids = []
        for rule in rules:
            response = self._request_with_retry(
                "POST",
                self.alert_bridge_base_url,
                "/api/v1/realtime",
                json={
                    "live_stream_url": stream_url,
                    "sensor_id": sensor_id,
                    "alert_type": rule["alert_type"],
                    "prompt": rule["prompt"],
                    "system_prompt": rule["system_prompt"],
                },
            )
            rule_ids.append(response.json()["id"])
        return rule_ids

    def delete_alert_rules(self, rule_ids: list[str]) -> None:
        for rule_id in rule_ids:
            self._request_with_retry(
                "DELETE", self.alert_bridge_base_url, f"/api/v1/realtime/{rule_id}"
            )

    def health_check(self) -> bool:
        try:
            self._request_with_retry("GET", self.agent_base_url, "/health")
            self._request_with_retry("GET", self.alert_bridge_base_url, "/health")
        except (httpx.TransportError, httpx.HTTPStatusError):
            return False
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agent && python -m pytest tests/test_vss_client.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/app/vss_client.py agent/tests/test_vss_client.py
git commit -m "feat: rewrite VSSClient to match real vss-agent + alert-bridge API"
```

---

### Task 4: Poller — timestamp-based cursoring + real alert fields

**Files:**
- Modify: `agent/app/poller.py` (full rewrite)
- Modify: `agent/tests/test_poller.py` (full rewrite)

**Interfaces:**
- Consumes: `VSSClient.get_new_alerts(since_timestamp)` from Task 3.
- Produces: `run_poll_iteration(vss_client, compiled_graph, since_timestamp, session_factory) -> str | None` (returns the latest alert's `timestamp`, or the input unchanged if no alerts), `poll_loop(...)` unchanged signature. Used by Task 7's `wiring.py` (already wired) — no signature change there, only field-mapping changes inside.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_poller.py
from app.poller import run_poll_iteration


class FakeVSSClient:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    def get_new_alerts(self, since_timestamp):
        self.calls.append(since_timestamp)
        return self._batches.pop(0) if self._batches else []


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_poller.py -v`
Expected: FAIL — `KeyError: 'hazard_type'` (FakeGraph stores raw state, which still has old field names from the alert dict, not yet mapped)

- [ ] **Step 3: Write the implementation**

```python
# agent/app/poller.py
import asyncio

from app import store
from app.models import HazardType


def run_poll_iteration(vss_client, compiled_graph, since_timestamp, session_factory) -> str | None:
    alerts = vss_client.get_new_alerts(since_timestamp)
    new_since_timestamp = since_timestamp
    for alert in alerts:
        with session_factory() as session:
            history = [
                {"caption": i.caption, "severity": i.severity.value, "created_at": i.created_at.isoformat()}
                for i in store.list_recent_incidents_by_hazard(session, HazardType(alert["category"]))
            ]
        initial_state = {
            "alert": alert,
            "hazard_type": alert["category"],
            "zone": alert["sensor_id"],
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
        since_timestamp = run_poll_iteration(vss_client, compiled_graph, since_timestamp, session_factory)
        await asyncio.sleep(interval_seconds)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_poller.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/poller.py agent/tests/test_poller.py
git commit -m "feat: switch poller from opaque cursor to last-seen-timestamp filtering"
```

---

### Task 5: Chat graph — collapse to single passthrough node

**Files:**
- Modify: `agent/app/graphs/chat.py` (full rewrite)
- Modify: `agent/tests/test_chat_graph.py` (full rewrite)
- Delete: `agent/tests/test_chat_classify.py`

**Interfaces:**
- Consumes: `VSSClient.chat(message)` from Task 3.
- Produces: `ChatState` TypedDict (`message: str`, `answer: str | None` — `intent` field removed), `build_chat_graph(vss_client) -> CompiledGraph` (no more `llm`/`session_factory` params). Used by Task 7's `wiring.py` and Task 8's `/chat` route.

- [ ] **Step 1: Delete the obsolete intent-classification test**

```bash
rm agent/tests/test_chat_classify.py
```

- [ ] **Step 2: Write the failing test**

```python
# agent/tests/test_chat_graph.py
from app.graphs.chat import build_chat_graph


class FakeVSSClient:
    def __init__(self, answer="two people in frame"):
        self.answer = answer
        self.messages_received = []

    def chat(self, message):
        self.messages_received.append(message)
        return self.answer


def test_chat_graph_forwards_message_and_returns_answer():
    vss_client = FakeVSSClient(answer="two people in frame")
    graph = build_chat_graph(vss_client)
    result = graph.invoke({"message": "who is in this clip?", "answer": None})
    assert vss_client.messages_received == ["who is in this clip?"]
    assert result["answer"] == "two people in frame"


def test_chat_graph_falls_back_gracefully_on_vss_client_error():
    class ErrorVSSClient:
        def chat(self, message):
            raise RuntimeError("boom")

    graph = build_chat_graph(ErrorVSSClient())
    result = graph.invoke({"message": "who is in this clip?", "answer": None})
    assert "couldn't fetch" in result["answer"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd agent && python -m pytest tests/test_chat_graph.py -v`
Expected: FAIL — `TypeError: build_chat_graph() missing 1 required positional argument` (old signature was `(llm, vss_client, session_factory)`)

- [ ] **Step 4: Write the implementation**

```python
# agent/app/graphs/chat.py
from typing import Callable, TypedDict

from langgraph.graph import END, StateGraph


class ChatState(TypedDict):
    message: str
    answer: str | None


FALLBACK_ANSWER = "Sorry, I couldn't fetch that from the footage right now. Try rephrasing your question."


def make_chat_node(vss_client) -> Callable[[dict], dict]:
    def chat(state: dict) -> dict:
        try:
            answer = vss_client.chat(state["message"])
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": answer}

    return chat


def build_chat_graph(vss_client):
    graph = StateGraph(ChatState)
    graph.add_node("chat", make_chat_node(vss_client))
    graph.set_entry_point("chat")
    graph.add_edge("chat", END)
    return graph.compile()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd agent && python -m pytest tests/test_chat_graph.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agent/app/graphs/chat.py agent/tests/test_chat_graph.py
git rm agent/tests/test_chat_classify.py
git commit -m "feat: collapse chat graph to single passthrough node against real vss-agent /chat"
```

---

### Task 6: Triage graph — `generate_report` node uses the incident record

**Files:**
- Modify: `agent/app/graphs/triage.py:100-107`
- Modify: `agent/tests/test_triage_report_escalate.py:1-35`
- Modify: `agent/tests/test_triage_graph.py:16-18`

**Interfaces:**
- Consumes: `VSSClient.generate_report(incident: dict)` from Task 3, `store.get_incident` + `incident_to_dict` from Task 6 of the original plan (already in `app.models`/`app.store`).
- Produces: `make_generate_report_node(vss_client, session_factory)` — same factory signature as before, but now fetches the full incident record and passes `incident_to_dict(incident)` to `vss_client.generate_report` instead of just the id. Used by Task 13's `build_triage_graph` (unchanged call site).

- [ ] **Step 1: Update the failing test**

Replace `agent/tests/test_triage_report_escalate.py` lines 1-35 (the `FakeVSSClient` and `test_generate_report_calls_vss_client_and_persists`) with:

```python
from app import store
from app.graphs.triage import make_escalate_notify_node, make_generate_report_node
from app.models import HazardType, Severity


class FakeVSSClient:
    def __init__(self, report_text="Incident report"):
        self.report_text = report_text
        self.calls = []

    def generate_report(self, incident):
        self.calls.append(incident)
        return self.report_text


def _seed_incident(session_factory):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.FALL, severity=Severity.CRITICAL,
            zone="aisle-3", caption="person down", raw_alert_payload={}, dedupe_key="fall:aisle-3",
        )
        return incident.id


def test_generate_report_calls_vss_client_with_incident_dict_and_persists(session_factory):
    incident_id = _seed_incident(session_factory)
    vss_client = FakeVSSClient(report_text="Person down in aisle-3 at 10:02.")
    node = make_generate_report_node(vss_client, session_factory)

    result = node({"incident_id": incident_id})

    assert result == {"report_text": "Person down in aisle-3 at 10:02."}
    assert vss_client.calls[0]["id"] == incident_id
    assert vss_client.calls[0]["hazard_type"] == "fall"
    assert vss_client.calls[0]["zone"] == "aisle-3"
    assert vss_client.calls[0]["caption"] == "person down"
    with session_factory() as session:
        assert store.get_incident(session, incident_id).report_text == "Person down in aisle-3 at 10:02."
```

Leave the rest of the file (the two `escalate_notify` tests) unchanged.

In `agent/tests/test_triage_graph.py`, replace lines 16-18:

```python
class FakeVSSClient:
    def generate_report(self, incident_id):
        return f"report for {incident_id}"
```

with:

```python
class FakeVSSClient:
    def generate_report(self, incident):
        return f"report for {incident['id']}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agent && python -m pytest tests/test_triage_report_escalate.py tests/test_triage_graph.py -v`
Expected: FAIL — `assert vss_client.calls[0]["id"] == incident_id` raises `TypeError: 'int' object is not subscriptable` (old node still passes the bare id)

- [ ] **Step 3: Update the implementation**

In `agent/app/graphs/triage.py`, replace lines 100-107:

```python
def make_generate_report_node(vss_client, session_factory) -> Callable[[dict], dict]:
    def generate_report(state: dict) -> dict:
        report_text = vss_client.generate_report(state["incident_id"])
        with session_factory() as session:
            store.update_incident(session, state["incident_id"], report_text=report_text)
        return {"report_text": report_text}

    return generate_report
```

with:

```python
def make_generate_report_node(vss_client, session_factory) -> Callable[[dict], dict]:
    def generate_report(state: dict) -> dict:
        with session_factory() as session:
            incident = store.get_incident(session, state["incident_id"])
            incident_dict = incident_to_dict(incident)
        report_text = vss_client.generate_report(incident_dict)
        with session_factory() as session:
            store.update_incident(session, state["incident_id"], report_text=report_text)
        return {"report_text": report_text}

    return generate_report
```

(`incident_to_dict` is already imported at the top of the file — line 4: `from app.models import HazardType, Severity, incident_to_dict`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agent && python -m pytest tests/test_triage_report_escalate.py tests/test_triage_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/app/graphs/triage.py agent/tests/test_triage_report_escalate.py agent/tests/test_triage_graph.py
git commit -m "feat: generate_report node passes full incident record to VSSClient"
```

---

### Task 7: Wire `VSSClient` and `build_chat_graph`'s new signatures into `wiring.py`

**Files:**
- Modify: `agent/app/wiring.py:16-26`

**Interfaces:**
- Consumes: `VSSClient(agent_base_url, alert_bridge_base_url)` from Task 3, `build_chat_graph(vss_client)` from Task 5, `Settings.vss_agent_base_url` / `Settings.vss_alert_bridge_base_url` from Task 1.
- Produces: same `build_app(settings) -> tuple[FastAPI, AppDependencies]` signature as before — no change visible to callers.

No new automated test for this task — it's pure wiring, already covered end-to-end by Task 8's `test_api.py` (which constructs `AppDependencies` directly, bypassing `wiring.py`) and by the manual smoke test in Task 10. Verify by reading the diff and running the full suite at the end of Task 8.

- [ ] **Step 1: Update `build_app`**

In `agent/app/wiring.py`, replace lines 16-26:

```python
def build_app(settings: Settings) -> tuple[FastAPI, AppDependencies]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    llm = get_chat_model(settings)
    vss_client = VSSClient(settings.vss_base_url)
    triage_graph = build_triage_graph(
        llm, vss_client, session_factory, settings.slack_webhook_url,
        settings.dedupe_window_seconds, broadcaster,
    )
    chat_graph = build_chat_graph(llm, vss_client, session_factory)
```

with:

```python
def build_app(settings: Settings) -> tuple[FastAPI, AppDependencies]:
    engine = make_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    llm = get_chat_model(settings)
    vss_client = VSSClient(settings.vss_agent_base_url, settings.vss_alert_bridge_base_url)
    triage_graph = build_triage_graph(
        llm, vss_client, session_factory, settings.slack_webhook_url,
        settings.dedupe_window_seconds, broadcaster,
    )
    chat_graph = build_chat_graph(vss_client)
```

- [ ] **Step 2: Verify by import**

Run: `cd agent && python -c "from app.wiring import build_app; from app.config import Settings; build_app(Settings())"`
Expected: no traceback (constructs the app without starting a server; `VSSClient`'s `httpx.Client` is created lazily and doesn't make network calls at construction time)

- [ ] **Step 3: Commit**

```bash
git add agent/app/wiring.py
git commit -m "feat: wire VSSClient's split URLs and build_chat_graph's new signature"
```

---

### Task 8: `/upload` registers + replaces alert rules

**Files:**
- Modify: `agent/app/main.py` (full file — `AppDependencies` dataclass, `/upload`, `/chat` routes)
- Modify: `agent/tests/test_api.py` (full rewrite)

**Interfaces:**
- Consumes: `HAZARD_ALERT_RULES` from Task 2, `VSSClient.register_alert_rules`/`delete_alert_rules` from Task 3.
- Produces: `AppDependencies` gains `active_rule_ids: list[str]` (mutable, default `[]`). `/upload` now also registers the 5 hazard rules against the new stream and deletes the previous upload's rules first. `/chat` route drops the now-removed `intent` field from the graph invocation. No change to `/health`, `/incidents`, `/incidents/{id}`, `/alerts/stream`.

- [ ] **Step 1: Write the failing tests**

Replace `agent/tests/test_api.py`'s `FakeVSSClient` (lines 11-19) and add new assertions. Full new file:

```python
# agent/tests/test_api.py
import asyncio

from fastapi.testclient import TestClient

from app import store
from app.events import IncidentBroadcaster
from app.main import AppDependencies, create_app
from app.models import HazardType, Severity


class FakeVSSClient:
    def __init__(self):
        self.registered_calls = []
        self.deleted_calls = []

    def get_new_alerts(self, since_timestamp):
        return []

    def generate_report(self, incident):
        return "generated report"

    def health_check(self):
        return True

    def register_alert_rules(self, stream_url, sensor_id, rules):
        self.registered_calls.append((stream_url, sensor_id, rules))
        return [f"rule-{i}" for i in range(len(rules))]

    def delete_alert_rules(self, rule_ids):
        self.deleted_calls.append(rule_ids)


class FakeChatGraph:
    def invoke(self, state):
        return {"answer": "the chat answer"}


def make_test_app(session_factory, tmp_path, broadcaster=None, vss_client=None):
    deps = AppDependencies(
        session_factory=session_factory,
        triage_graph=None,
        chat_graph=FakeChatGraph(),
        vss_client=vss_client or FakeVSSClient(),
        broadcaster=broadcaster or IncidentBroadcaster(),
        upload_dir=tmp_path,
        mediamtx_rtsp_url="rtsp://localhost:8554",
        poll_interval_seconds=9999,
    )
    return create_app(deps)


def test_health(session_factory, tmp_path):
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200


def test_list_and_get_incident(session_factory, tmp_path):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.PPE, severity=Severity.WARNING,
            zone="dock-1", caption="no hard hat", raw_alert_payload={}, dedupe_key="ppe:dock-1",
        )
        incident_id = incident.id

    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        listed = client.get("/incidents")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        detail = client.get(f"/incidents/{incident_id}")
        assert detail.status_code == 200
        assert detail.json()["caption"] == "no hard hat"


def test_incident_detail_generates_report_for_critical_without_one(session_factory, tmp_path):
    with session_factory() as session:
        incident = store.create_incident(
            session, hazard_type=HazardType.FALL, severity=Severity.CRITICAL,
            zone="aisle-3", caption="person down", raw_alert_payload={}, dedupe_key="fall:aisle-3",
        )
        incident_id = incident.id

    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        detail = client.get(f"/incidents/{incident_id}")
    assert detail.json()["report_text"] == "generated report"


def test_incident_detail_404_for_missing_incident(session_factory, tmp_path):
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.get("/incidents/999")
    assert response.status_code == 404


def test_chat_endpoint_returns_answer(session_factory, tmp_path):
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "how many ppe violations today?"})
    assert response.json() == {"answer": "the chat answer"}


def test_upload_starts_rtsp_loopback_and_registers_alert_rules(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    vss_client = FakeVSSClient()
    app = make_test_app(session_factory, tmp_path, vss_client=vss_client)
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.json() == {"stream_url": "rtsp://localhost:8554/clip"}
    assert len(vss_client.registered_calls) == 1
    stream_url, sensor_id, rules = vss_client.registered_calls[0]
    assert stream_url == "rtsp://localhost:8554/clip"
    assert sensor_id == "clip"
    assert len(rules) == 5


def test_upload_deletes_previous_rules_before_registering_new_ones(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    vss_client = FakeVSSClient()
    app = make_test_app(session_factory, tmp_path, vss_client=vss_client)
    with TestClient(app) as client:
        client.post("/upload", files={"file": ("clip1.mp4", b"fake-bytes", "video/mp4")})
        client.post("/upload", files={"file": ("clip2.mp4", b"fake-bytes", "video/mp4")})
    assert len(vss_client.deleted_calls) == 1
    assert vss_client.deleted_calls[0] == ["rule-0", "rule-1", "rule-2", "rule-3", "rule-4"]


def test_upload_returns_503_when_vss_unreachable(session_factory, tmp_path):
    class UnreachableVSSClient(FakeVSSClient):
        def health_check(self):
            return False

    app = make_test_app(session_factory, tmp_path, vss_client=UnreachableVSSClient())
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.status_code == 503


def test_upload_returns_502_when_rtsp_loopback_fails(session_factory, tmp_path, monkeypatch):
    def boom(path, name, url):
        raise RuntimeError("ffmpeg not found")

    monkeypatch.setattr("app.main.start_rtsp_loopback", boom)
    app = make_test_app(session_factory, tmp_path)
    with TestClient(app) as client:
        response = client.post("/upload", files={"file": ("clip.mp4", b"fake-bytes", "video/mp4")})
    assert response.status_code == 502


async def test_alerts_stream_endpoint_returns_event_stream_headers(session_factory, tmp_path):
    # The SSE endpoint streams forever, so it can't be driven through TestClient
    # or httpx's ASGITransport — both await the whole ASGI call before returning
    # a response. Drive the ASGI callable directly and stop once headers land.
    app = make_test_app(session_factory, tmp_path)
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "path": "/alerts/stream", "raw_path": b"/alerts/stream", "query_string": b"",
        "headers": [], "client": ("testclient", 123), "server": ("testserver", 80), "scheme": "http",
    }
    sent = []
    response_started = asyncio.Event()

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.start":
            response_started.set()

    task = asyncio.create_task(app(scope, receive, send))
    try:
        await asyncio.wait_for(response_started.wait(), timeout=2)
        start_message = next(m for m in sent if m["type"] == "http.response.start")
        headers = {k.decode(): v.decode() for k, v in start_message["headers"]}
        assert start_message["status"] == 200
        assert "text/event-stream" in headers["content-type"]
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agent && python -m pytest tests/test_api.py -v`
Expected: FAIL — `TypeError: AppDependencies.__init__() got an unexpected keyword argument` is NOT expected (existing fields still accepted); instead expect `AttributeError`/assertion failures on `vss_client.registered_calls` since `/upload` doesn't call `register_alert_rules` yet.

- [ ] **Step 3: Write the implementation**

Replace the full contents of `agent/app/main.py`:

```python
# agent/app/main.py
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from app import store
from app.alert_rules import HAZARD_ALERT_RULES
from app.events import IncidentBroadcaster
from app.models import Severity, incident_to_dict
from app.poller import poll_loop
from app.streaming import start_rtsp_loopback

logger = logging.getLogger(__name__)


@dataclass
class AppDependencies:
    session_factory: object
    triage_graph: object
    chat_graph: object
    vss_client: object
    broadcaster: IncidentBroadcaster
    upload_dir: Path
    mediamtx_rtsp_url: str
    poll_interval_seconds: int = 8
    active_rule_ids: list[str] = field(default_factory=list)


async def _alert_event_generator(broadcaster: IncidentBroadcaster):
    queue = broadcaster.subscribe()
    try:
        while True:
            incident = await queue.get()
            yield {"event": "incident", "data": json.dumps(incident)}
    finally:
        broadcaster.unsubscribe(queue)


def create_app(deps: AppDependencies) -> FastAPI:
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        poll_task = None
        if deps.triage_graph is not None:
            poll_task = asyncio.create_task(
                poll_loop(deps.vss_client, deps.triage_graph, deps.session_factory, deps.poll_interval_seconds, stop_event)
            )
        yield
        stop_event.set()
        if poll_task is not None:
            poll_task.cancel()

    app = FastAPI(title="Warehouse Safety Monitor Agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/upload")
    def upload(file: UploadFile = File(...)):
        if not deps.vss_client.health_check():
            raise HTTPException(status_code=503, detail="VSS is unreachable")
        deps.upload_dir.mkdir(parents=True, exist_ok=True)
        dest = deps.upload_dir / file.filename
        dest.write_bytes(file.file.read())
        try:
            stream_url = start_rtsp_loopback(dest, dest.stem, deps.mediamtx_rtsp_url)
        except Exception:
            raise HTTPException(status_code=502, detail="Failed to start video stream ingestion")

        if deps.active_rule_ids:
            try:
                deps.vss_client.delete_alert_rules(deps.active_rule_ids)
            except Exception:
                logger.warning("Failed to delete previous alert rules: %s", deps.active_rule_ids)
            deps.active_rule_ids = []
        try:
            deps.active_rule_ids = deps.vss_client.register_alert_rules(
                stream_url, dest.stem, HAZARD_ALERT_RULES
            )
        except Exception:
            logger.warning("Failed to register alert rules for stream %s", stream_url)

        return {"stream_url": stream_url}

    @app.get("/incidents")
    def list_incidents_route():
        with deps.session_factory() as session:
            return [incident_to_dict(i) for i in store.list_incidents(session)]

    @app.get("/incidents/{incident_id}")
    def incident_detail(incident_id: int):
        with deps.session_factory() as session:
            incident = store.get_incident(session, incident_id)
            if incident is None:
                raise HTTPException(status_code=404, detail="incident not found")
            if incident.report_text is None and incident.severity == Severity.CRITICAL:
                report_text = deps.vss_client.generate_report(incident_to_dict(incident))
                incident = store.update_incident(session, incident.id, report_text=report_text)
            return incident_to_dict(incident)

    @app.post("/chat")
    def chat(payload: dict):
        result = deps.chat_graph.invoke({"message": payload["message"], "answer": None})
        return {"answer": result["answer"]}

    @app.get("/alerts/stream")
    async def alerts_stream():
        return EventSourceResponse(_alert_event_generator(deps.broadcaster))

    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agent && python -m pytest tests/test_api.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add agent/app/main.py agent/tests/test_api.py
git commit -m "feat: /upload registers and rotates real VSS alert rules per stream"
```

---

### Task 9: Full test suite + manual smoke test against the real Brev instance

**Files:** none (verification only)

**Interfaces:** none — this task only verifies Tasks 1-8 together.

- [ ] **Step 1: Run the full automated suite**

Run: `cd agent && python -m pytest -v`
Expected: PASS, no failures, no leftover references to `ask_video`/`query_analytics`/`search_archive`/`vss_base_url`/`"cursor"` anywhere in `agent/`. Verify with:

```bash
grep -rn "vss_base_url\|ask_video\|query_analytics\|search_archive" agent/ || echo "clean"
```

Expected output: `clean`

- [ ] **Step 2: Open the firewall ports on the Brev instance**

Run (against the live `vss-warehouse` instance):

```bash
brev exec vss-warehouse -- "sudo ufw allow 8000/tcp && sudo ufw allow 9080/tcp && sudo ufw status"
```

Expected: `8000/tcp` and `9080/tcp` listed as `ALLOW`.

- [ ] **Step 3: Manual smoke test — start the agent against the real instance**

```bash
cd agent
cp .env.example .env
# edit .env: set NVIDIA_API_KEY, VSS_AGENT_BASE_URL=http://216.81.245.166:8000, VSS_ALERT_BRIDGE_BASE_URL=http://216.81.245.166:9080
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn app.asgi:app --reload
```

In another terminal:

```bash
curl -s localhost:8000/health
# expect {"status": "ok"}
curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' -d '{"message": "how many cameras are streaming?"}'
# expect a JSON {"answer": "..."} with a real, non-fallback answer
```

- [ ] **Step 4: Manual smoke test — upload a sample clip and confirm rule registration**

```bash
curl -s -i -X POST localhost:8000/upload -F "file=@../sample-videos/ppe.mp4;filename=ppe.mp4;type=video/mp4"
```

Expected: `200` + a `stream_url`. Then confirm the 5 rules landed on the real instance:

```bash
curl -s "http://216.81.245.166:9080/api/v1/realtime" | python3 -m json.tool
```

Expected: 5 rules listed, `live_stream_url` matching the returned `stream_url`, `sensor_id` = `ppe`.

No commit for this task — verification only. If any step fails, return to the relevant task above and fix before proceeding.
