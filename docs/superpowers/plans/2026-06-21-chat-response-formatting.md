# Chat Response Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip VSS's internal agent-think/incidents-JSON noise out of `/chat` responses server-side, and render the resulting prose as markdown in the chat UI.

**Architecture:** A new pure function `clean_chat_response()` in a new module `agent/app/chat_format.py` regex-strips known noise wrapper tags. `VSSClient.chat()` applies it to the raw VSS response before returning. `ChatPanel.tsx` renders assistant messages through `react-markdown` instead of raw string interpolation.

**Tech Stack:** Python (pytest, respx) for backend; TypeScript/React (vitest, @testing-library/react) for frontend. New frontend dependency: `react-markdown`.

## Global Constraints

- Stripping must be best-effort against an undocumented, model-generated format: if removing the known tags would leave an empty/whitespace string, return the original raw string unchanged instead (never blank a real answer).
- Strip these tag pairs (regex, case-sensitive, `re.DOTALL` so they match across newlines): `<agent-think>...</agent-think>` and `<incidents>...</incidents>`.
- No changes to `chat.py` (LangGraph chat graph) or its `ChatState` shape — cleaning happens inside `VSSClient.chat()`, below the graph.
- User-typed chat messages are never markdown-rendered — only assistant messages.

---

### Task 1: `clean_chat_response()` noise-stripping function

**Files:**
- Create: `agent/app/chat_format.py`
- Test: `agent/tests/test_chat_format.py` (new)

**Interfaces:**
- Produces: `clean_chat_response(raw: str) -> str` — pure function, no I/O, no exceptions on unexpected input. Consumed by Task 2's `VSSClient.chat()`.

- [ ] **Step 1: Write the failing tests**

```python
# agent/tests/test_chat_format.py
from app.chat_format import clean_chat_response


def test_strips_agent_think_block():
    raw = (
        "<agent-think>lots of internal tool-call trace, plan steps, "
        "sub-agent calls</agent-think>\n"
        "The sensor 'forklift_proximity' has no alerts or incidents "
        "recorded in the system for the last 24 hours."
    )
    assert clean_chat_response(raw) == (
        "The sensor 'forklift_proximity' has no alerts or incidents "
        "recorded in the system for the last 24 hours."
    )


def test_strips_incidents_block():
    raw = (
        "Found 2 incidents matching your query.\n"
        "<incidents>\n"
        '{ "incidents": [{"id": "i1"}, {"id": "i2"}] }\n'
        "</incidents>"
    )
    assert clean_chat_response(raw) == "Found 2 incidents matching your query."


def test_strips_both_blocks_together():
    raw = (
        "<agent-think>plan: call multi_report_agent</agent-think>\n"
        "Two PPE violations were recorded today.\n"
        "<incidents>\n"
        '{ "incidents": [] }\n'
        "</incidents>"
    )
    assert clean_chat_response(raw) == "Two PPE violations were recorded today."


def test_no_tags_returns_unchanged():
    raw = "Two people are visible in the frame."
    assert clean_chat_response(raw) == raw


def test_empty_after_strip_returns_original():
    raw = "<agent-think>only internal trace, no prose at all</agent-think>"
    assert clean_chat_response(raw) == raw
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd agent && .venv/bin/pytest tests/test_chat_format.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.chat_format'`

- [ ] **Step 3: Write the implementation**

```python
# agent/app/chat_format.py
import re

_NOISE_TAG_PATTERN = re.compile(
    r"<agent-think>.*?</agent-think>|<incidents>.*?</incidents>",
    re.DOTALL,
)


def clean_chat_response(raw: str) -> str:
    stripped = _NOISE_TAG_PATTERN.sub("", raw)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return stripped if stripped else raw
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd agent && .venv/bin/pytest tests/test_chat_format.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add agent/app/chat_format.py agent/tests/test_chat_format.py
git commit -m "feat: strip VSS agent-think/incidents noise from chat responses"
```

---

### Task 2: Wire `clean_chat_response()` into `VSSClient.chat()`

**Files:**
- Modify: `agent/app/vss_client.py:68-75` (the `chat` method)
- Test: `agent/tests/test_vss_client.py`

**Interfaces:**
- Consumes: `clean_chat_response(raw: str) -> str` from Task 1 (`agent/app/chat_format.py`).
- Produces: `VSSClient.chat(message: str) -> str` now returns cleaned text (signature unchanged, behavior changed). Used as-is by `chat.py`'s `make_chat_node` and by `generate_report()` — no changes needed there.

- [ ] **Step 1: Write the failing test**

Add to `agent/tests/test_vss_client.py` (after `test_chat_sends_openai_style_messages_and_parses_content`):

```python
@respx.mock
def test_chat_strips_agent_think_and_incidents_noise():
    respx.post("http://agent.test/chat").mock(
        return_value=Response(200, json={
            "choices": [{"message": {
                "content": (
                    "<agent-think>plan: call multi_report_agent</agent-think>\n"
                    "Two PPE violations were recorded today.\n"
                    "<incidents>\n"
                    '{ "incidents": [] }\n'
                    "</incidents>"
                ),
                "role": "assistant",
            }}],
        })
    )
    client = make_client()
    answer = client.chat("how many ppe violations today?")
    assert answer == "Two PPE violations were recorded today."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent && .venv/bin/pytest tests/test_vss_client.py::test_chat_strips_agent_think_and_incidents_noise -v`
Expected: FAIL — `answer` still contains the raw `<agent-think>`/`<incidents>` tags.

- [ ] **Step 3: Implement**

In `agent/app/vss_client.py`, add the import and update `chat()`:

```python
from app.chat_format import clean_chat_response
```

```python
    def chat(self, message: str) -> str:
        response = self._request_with_retry(
            "POST",
            self.agent_base_url,
            "/chat",
            json={"messages": [{"role": "user", "content": message}]},
        )
        content = response.json()["choices"][0]["message"]["content"]
        return clean_chat_response(content)
```

- [ ] **Step 4: Run full vss_client test file to verify pass and no regressions**

Run: `cd agent && .venv/bin/pytest tests/test_vss_client.py -v`
Expected: PASS (all tests, including the existing `test_chat_sends_openai_style_messages_and_parses_content` and `test_generate_report_builds_prompt_from_incident_and_calls_chat`, which use plain content with no tags — unaffected by the no-op pass-through).

- [ ] **Step 5: Commit**

```bash
git add agent/app/vss_client.py agent/tests/test_vss_client.py
git commit -m "feat: apply chat-response cleaning in VSSClient.chat()"
```

---

### Task 3: Render assistant chat messages as markdown

**Files:**
- Modify: `frontend/package.json` (add dependency)
- Modify: `frontend/components/ChatPanel.tsx`
- Test: `frontend/tests/chat-panel.test.tsx`

**Interfaces:**
- Consumes: `react-markdown`'s default export `ReactMarkdown` (component, `children: string` prop renders markdown).
- Produces: no new exports — `ChatPanel` default export signature unchanged.

- [ ] **Step 1: Add the dependency**

```bash
cd frontend && npm install react-markdown
```

- [ ] **Step 2: Write the failing test**

Add to `frontend/tests/chat-panel.test.tsx`:

```tsx
  it("renders markdown in assistant replies", async () => {
    (sendChatMessage as any).mockResolvedValue({ answer: "**Two** PPE violations today." });
    render(<ChatPanel />);

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "how many ppe violations today?" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => {
      const history = screen.getByTestId("chat-history");
      expect(history.querySelector("strong")?.textContent).toBe("Two");
    });
  });

  it("does not markdown-render the user's own message", async () => {
    (sendChatMessage as any).mockResolvedValue({ answer: "ok" });
    render(<ChatPanel />);

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "**not markdown**" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => {
      const history = screen.getByTestId("chat-history");
      expect(history.textContent).toContain("**not markdown**");
      expect(history.querySelector("strong")).toBeNull();
    });
  });
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `cd frontend && npm test -- chat-panel`
Expected: FAIL — `**Two**` shows as literal text, no `<strong>` element exists.

- [ ] **Step 4: Implement**

In `frontend/components/ChatPanel.tsx`, add the import:

```tsx
import ReactMarkdown from "react-markdown";
```

Replace the message-rendering block (the `{messages.map(...)}` body):

```tsx
        {messages.map((message, index) => (
          <li
            key={index}
            className={message.role === "user" ? "text-paper" : "border-l-2 border-signal pl-2 text-paper/80"}
          >
            <span className="font-mono text-xs uppercase tracking-widest text-paper/40">{message.role}</span>
            <br />
            {message.role === "assistant" ? (
              <ReactMarkdown>{message.text}</ReactMarkdown>
            ) : (
              message.text
            )}
          </li>
        ))}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- chat-panel`
Expected: PASS (all 3 tests: original reply test + 2 new ones).

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/components/ChatPanel.tsx frontend/tests/chat-panel.test.tsx
git commit -m "feat: render assistant chat replies as markdown"
```

---

## Self-Review Notes

- **Spec coverage:** Task 1 = stripping logic + fallback safety net. Task 2 = wiring into `VSSClient.chat()`. Task 3 = markdown rendering, user messages excluded. All three spec components covered; `<incidents>`-as-cards explicitly out of scope per spec, not attempted here.
- **Placeholder scan:** none — every step has runnable code and exact commands.
- **Type/signature consistency:** `clean_chat_response(raw: str) -> str` matches between Task 1's definition and Task 2's import/usage. `ChatPanel`'s `Message` interface (`role`, `text`) unchanged across Task 3.
