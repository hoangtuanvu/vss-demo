# Chat Camera-Context Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-inject the active upload's camera/sensor id into every chat message before forwarding to real VSS's `/chat`, so users don't have to name the camera themselves.

**Architecture:** `AppDependencies` tracks the most recent upload's sensor id (`dest.stem`, the same value already used for `register_alert_rules`). The `/chat` route prepends `For camera/sensor '<id>': ` to the user's message when a sensor id is known, before invoking the chat graph — a one-line string edit in the HTTP layer, no changes to `VSSClient` or the chat graph itself.

**Tech Stack:** Python, FastAPI — same stack as the rest of `agent/`.

## Global Constraints

- No changes to `agent/app/vss_client.py`, `agent/app/graphs/chat.py`, or the chat graph's structure — the spec confirms VSS already parses sensor identification out of natural language, so the fix lives entirely in how the message string is built before `chat_graph.invoke(...)`.
- When no clip has been uploaded yet, the message passes through unmodified — VSS's own clarifying-question behavior in that case is correct, not a bug to suppress.
- Test runner: `cd agent && python -m pytest`.

---

### Task 1: Track and inject the active sensor id

**Files:**
- Modify: `agent/app/main.py:22-33` (`AppDependencies`), `:72-97` (`/upload`), `:115-118` (`/chat`)
- Modify: `agent/tests/test_api.py` (add one fake-state-capturing capability to `FakeChatGraph`, add one new test, strengthen one existing test)

**Interfaces:**
- Consumes: nothing new — `dest.stem` is already computed in `/upload` (used for `register_alert_rules`'s `sensor_id` param).
- Produces: `AppDependencies.active_sensor_id: str | None = None`. Nothing later depends on this beyond the app itself.

- [ ] **Step 1: Write the failing tests**

In `agent/tests/test_api.py`, replace the `FakeChatGraph` class (lines 33-35):

```python
class FakeChatGraph:
    def __init__(self):
        self.invocations = []

    def invoke(self, state):
        self.invocations.append(state)
        return {"answer": "the chat answer"}
```

`make_test_app` (lines 38-49) constructs `FakeChatGraph()` inline inside `AppDependencies(...)` — change it to accept the chat graph as a parameter so tests can hold a reference to inspect `.invocations`:

```python
def make_test_app(session_factory, tmp_path, broadcaster=None, vss_client=None, chat_graph=None):
    deps = AppDependencies(
        session_factory=session_factory,
        triage_graph=None,
        chat_graph=chat_graph or FakeChatGraph(),
        vss_client=vss_client or FakeVSSClient(),
        broadcaster=broadcaster or IncidentBroadcaster(),
        upload_dir=tmp_path,
        mediamtx_rtsp_url="rtsp://localhost:8554",
        poll_interval_seconds=9999,
    )
    return create_app(deps)
```

Replace `test_chat_endpoint_returns_answer` (lines 99-103) with a version that also asserts the message passed through unmodified when nothing has been uploaded yet:

```python
def test_chat_endpoint_returns_answer(session_factory, tmp_path):
    chat_graph = FakeChatGraph()
    app = make_test_app(session_factory, tmp_path, chat_graph=chat_graph)
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "how many ppe violations today?"})
    assert response.json() == {"answer": "the chat answer"}
    assert chat_graph.invocations[0]["message"] == "how many ppe violations today?"
```

Add a new test, after `test_upload_deletes_previous_rules_before_registering_new_ones` (after line 128):

```python
def test_chat_includes_active_sensor_context_after_upload(session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.start_rtsp_loopback", lambda path, name, url: f"{url}/{name}")
    chat_graph = FakeChatGraph()
    app = make_test_app(session_factory, tmp_path, chat_graph=chat_graph)
    with TestClient(app) as client:
        client.post("/upload", files={"file": ("forklift_proximity.mp4", b"fake-bytes", "video/mp4")})
        client.post("/chat", json={"message": "how many incidents today?"})
    assert chat_graph.invocations[0]["message"] == (
        "For camera/sensor 'forklift_proximity': how many incidents today?"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agent && python -m pytest tests/test_api.py -v`
Expected: FAIL — `test_chat_includes_active_sensor_context_after_upload` fails because `chat_graph.invocations[0]["message"] == "how many incidents today?"` (no prefix yet); `test_chat_endpoint_returns_answer` fails with `IndexError` or similar if `FakeChatGraph.invocations` isn't being populated by the current `chat_graph.invoke` call shape — confirm both failures reference the missing prefix / missing tracking, not a typo.

- [ ] **Step 3: Write the implementation**

In `agent/app/main.py`, add `active_sensor_id` to `AppDependencies` (after line 32's `active_rule_ids` field):

```python
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
    active_sensor_id: str | None = None
```

In the `/upload` route, set `deps.active_sensor_id` right after computing `stream_url` (insert after line 82's `except Exception:` block, before the `if deps.active_rule_ids:` line):

```python
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

        deps.active_sensor_id = dest.stem

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
```

Replace the `/chat` route (lines 115-118):

```python
    @app.post("/chat")
    def chat(payload: dict):
        message = payload["message"]
        if deps.active_sensor_id:
            message = f"For camera/sensor '{deps.active_sensor_id}': {message}"
        result = deps.chat_graph.invoke({"message": message, "answer": None})
        return {"answer": result["answer"]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agent && python -m pytest tests/test_api.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Run the full suite**

Run: `cd agent && python -m pytest -q`
Expected: PASS, no regressions in other test files (`make_test_app`'s new `chat_graph` parameter is optional with a default, so no other test file needs changes)

- [ ] **Step 6: Commit**

```bash
git add agent/app/main.py agent/tests/test_api.py
git commit -m "feat: auto-inject active upload's sensor id into chat messages"
```
