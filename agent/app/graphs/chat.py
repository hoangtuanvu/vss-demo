from typing import Callable, TypedDict

from langgraph.graph import END, StateGraph

from app import store


class ChatState(TypedDict):
    message: str
    intent: str | None
    answer: str | None
    sensor_id: str | None


FALLBACK_ANSWER = "Sorry, I couldn't fetch that right now. Try rephrasing your question."

_VIDEO_KEYWORDS = {
    "happening", "what's in", "whats in", "see in", "live", "stream",
    "footage", "feed", "currently", "right now", "camera", "recording",
    "what do you see", "describe the video", "describe the feed",
}

_SOP_KEYWORDS = {
    "prevent", "avoid", "improve", "sop", "procedure", "protocol",
    "how can we", "how do we", "what should we", "recommendation",
    "best practice", "mitigation",
}


def _classify_intent(message: str) -> str:
    lower = message.lower()
    if any(kw in lower for kw in _SOP_KEYWORDS):
        return "sop_suggestion"
    if any(kw in lower for kw in _VIDEO_KEYWORDS):
        return "video_question"
    return "incidents_query"

INCIDENTS_CONTEXT_PROMPT = """You are a warehouse safety assistant. You have access to the following incident log:

{incidents_json}

Answer the user's question based on this data. Be concise and specific.
If there are no incidents matching the query, say so clearly.

Question: {message}"""

SOP_PROMPT = """You are a warehouse safety expert. Recent incident history:
{history}

The user asked: {message}

Draft a short, concrete SOP improvement suggestion (3-5 bullet points max)."""


def _format_incidents(incidents) -> str:
    if not incidents:
        return "[]"
    rows = []
    for i in incidents:
        rows.append(
            f"- ID {i.id} | {i.created_at.strftime('%Y-%m-%d %H:%M')} | "
            f"{i.hazard_type.value} | {i.severity.value} | zone={i.zone} | {i.caption[:120]}"
        )
    return "\n".join(rows)


def make_parse_intent_node(llm) -> Callable[[dict], dict]:
    def parse_intent(state: dict) -> dict:
        return {"intent": _classify_intent(state["message"])}

    return parse_intent


def make_incidents_query_node(llm, session_factory) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        with session_factory() as session:
            incidents = store.list_incidents(session, limit=100)
        context = _format_incidents(incidents)
        prompt = INCIDENTS_CONTEXT_PROMPT.format(
            incidents_json=context,
            message=state["message"],
        )
        try:
            answer = llm.invoke(prompt).content.strip()
        except Exception:
            answer = FALLBACK_ANSWER
        return {"answer": answer}

    return handle


def make_video_question_node(vss_client) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        message = state["message"]
        if state.get("sensor_id"):
            message = f"For camera/sensor '{state['sensor_id']}': {message}"
        try:
            answer = vss_client.chat(message)
            if "sorry" in answer.lower() and "wasn't able" in answer.lower():
                answer = (
                    "No active video stream to query. Upload a video first, "
                    "then ask again once processing starts."
                )
        except Exception:
            answer = "No active video stream. Upload a video to enable live footage queries."
        return {"answer": answer}

    return handle


def make_sop_suggestion_node(llm, session_factory) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        with session_factory() as session:
            recent = store.list_incidents(session, limit=10)
        history = _format_incidents(recent)
        prompt = SOP_PROMPT.format(history=history, message=state["message"])
        try:
            answer = llm.invoke(prompt).content.strip()
        except Exception:
            answer = FALLBACK_ANSWER
        return {"answer": answer}

    return handle


def build_chat_graph(llm, vss_client, session_factory):
    graph = StateGraph(ChatState)
    graph.add_node("parse_intent", make_parse_intent_node(llm))
    graph.add_node("incidents_query", make_incidents_query_node(llm, session_factory))
    graph.add_node("video_question", make_video_question_node(vss_client))
    graph.add_node("sop_suggestion", make_sop_suggestion_node(llm, session_factory))
    graph.set_entry_point("parse_intent")
    graph.add_conditional_edges(
        "parse_intent",
        lambda state: state["intent"],
        {
            "incidents_query": "incidents_query",
            "video_question": "video_question",
            "sop_suggestion": "sop_suggestion",
        },
    )
    graph.add_edge("incidents_query", END)
    graph.add_edge("video_question", END)
    graph.add_edge("sop_suggestion", END)
    return graph.compile()
