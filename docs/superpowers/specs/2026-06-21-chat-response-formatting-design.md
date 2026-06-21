# Chat Response Formatting (strip agent-think noise + markdown render) — Design

**Date:** 2026-06-21
**Status:** Approved for planning

## Purpose

With the real NVIDIA VSS instance live (see
`docs/superpowers/specs/2026-06-21-chat-context-injection-design.md`), the
`/chat` endpoint behaves like a genuine agent and its raw text response mixes
three things in one string:

1. An internal agent-think / tool-call trace (e.g. `<agent-think>...
   </agent-think>`, sub-agent calls, plan steps).
2. The model's actual prose answer to the user's question.
3. A redundant `<incidents>` JSON block, duplicating data the underlying
   tool already surfaced separately.

`vss_client.chat()` (agent/app/vss_client.py:68) returns this raw string
verbatim, and `ChatPanel.tsx` renders it as plain text. The user sees the
full internal trace and a duplicate JSON dump, and markdown the model
produces (bold, headers, bullet lists) shows as literal `**`/`#` characters.

Example observed for "show me alerts" with no incidents found:

```
<agent-think>...lots of internal tool-call trace...</agent-think>
The sensor 'forklift_proximity' has no alerts or incidents recorded in the
system for the last 24 hours. No visualizations or reports can be generated
due to the absence of data.
<incidents>
{ "incidents": [] }
</incidents>
```

Only the middle sentence is meant for the user.

## Decision

Strip known VSS noise wrapper tags from the response server-side, keep only
the model's prose, and render that prose as markdown in the frontend. Do
**not** attempt to parse the `<incidents>` JSON block into structured
data/cards — its schema is undocumented and VSS-internal, and depending on
it would couple this repo to a format that can change upstream without
notice. The tool already shows incidents to the user through its own
existing path; the chat bubble only needs the prose.

## Components

| File | Change |
|---|---|
| `agent/app/chat_format.py` (new) | `clean_chat_response(raw: str) -> str`. Pure function, no I/O. Strips `<agent-think>...</agent-think>` and `<incidents>...</incidents>` blocks (regex, `re.DOTALL`), collapses resulting multi-blank-lines, `.strip()`. If the result is empty/whitespace, returns the original `raw` unmodified (never blank a real answer because the stripping pattern didn't match VSS's current format). |
| `agent/app/vss_client.py` | `chat()` pipes `response.json()["choices"][0]["message"]["content"]` through `clean_chat_response()` before returning. `generate_report()` is unaffected in behavior (it calls `chat()` too, but its prompts don't trigger agent-think/incidents tags in practice — cleaning is a no-op pass-through for them). |
| `frontend/package.json` | Add `react-markdown` dependency. |
| `frontend/components/ChatPanel.tsx` | Assistant messages (`message.role === "assistant"`) render `message.text` through `<ReactMarkdown>` instead of raw string interpolation. User messages keep current plain-text rendering (no reason to markdown-render the user's own typed input). |

## Data flow

```
VSS POST /chat response.choices[0].message.content (raw, noisy)
        │
        ▼
clean_chat_response(raw)   — strip <agent-think>, <incidents> blocks
        │
        ▼
vss_client.chat() returns clean prose
        │
        ▼
chat_graph "answer" field (unchanged shape)
        │
        ▼
ChatPanel.tsx — assistant bubble rendered via ReactMarkdown
```

## Error handling

- Regex stripping is best-effort against an undocumented, model-generated
  format. The empty-after-strip fallback (return original `raw`) is the only
  safety net needed — it guarantees cleaning can never turn a real answer
  into a blank bubble.
- No new failure modes in `vss_client.chat()` — `clean_chat_response` is a
  pure string transform with no exceptions raised on unexpected input (no
  match ⇒ no-op).
- Existing `make_chat_node` fallback (`FALLBACK_ANSWER` on exception) is
  unchanged.

## Testing

- `agent/tests/test_chat_format.py` (new):
  - Feed the two real pasted examples (with-trace/no-incidents case, and a
    case with only an `<incidents>` block and no `<agent-think>`) → assert
    only the clean prose sentence remains.
  - Feed a string with no tags at all → assert returned unchanged.
  - Feed a string where stripping would remove everything → assert original
    `raw` returned (fallback case).
- `agent/tests/test_vss_client.py`: assert `chat()` applies
  `clean_chat_response` to the HTTP response content before returning.
- `frontend/tests/chat-panel.test.tsx`: assert an assistant message
  containing `**bold**` renders as a `<strong>` element, not literal
  asterisks; assert a user message is unaffected.

## Out of scope (this pass)

- Parsing `<incidents>` JSON into structured incident cards in the chat UI.
- Any change to `chat.py` / the LangGraph chat graph structure (cleaning
  lives in `vss_client.py`, below the graph).
- Handling VSS's own internal tool-validation errors (separately tracked,
  per the chat-context-injection design's out-of-scope section).
