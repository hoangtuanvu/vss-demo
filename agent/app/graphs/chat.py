from typing import Callable, TypedDict


class ChatState(TypedDict):
    message: str
    intent: str | None
    answer: str | None


INTENT_PROMPT = """Classify the user's question into exactly one category:
clip_question, stats_question, archive_search, sop_suggestion.
Question: {message}
Reply with only the category name."""

VALID_INTENTS = {"clip_question", "stats_question", "archive_search", "sop_suggestion"}


def make_parse_intent_node(llm) -> Callable[[dict], dict]:
    def parse_intent(state: dict) -> dict:
        try:
            intent = llm.invoke(INTENT_PROMPT.format(message=state["message"])).content.strip().lower()
        except Exception:
            intent = "stats_question"
        if intent not in VALID_INTENTS:
            intent = "stats_question"
        return {"intent": intent}

    return parse_intent


from langgraph.graph import END, StateGraph

from app import store

FALLBACK_ANSWER = "Sorry, I couldn't fetch that from the footage right now. Try rephrasing your question."


def make_clip_question_node(vss_client) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        try:
            answer = vss_client.ask_video(state["message"], "latest")
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": answer}

    return handle


def make_stats_question_node(vss_client) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        try:
            result = vss_client.query_analytics(state["message"])
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": str(result)}

    return handle


def make_archive_search_node(vss_client) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        try:
            results = vss_client.search_archive(state["message"])
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": str(results)}

    return handle


SOP_PROMPT = """Recent incident history: {history}
The user asked how to prevent this kind of incident: {message}
Draft a short, concrete SOP improvement suggestion."""


def make_sop_suggestion_node(llm, session_factory) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        with session_factory() as session:
            recent = store.list_incidents(session, limit=5)
        history = [{"hazard_type": i.hazard_type.value, "caption": i.caption} for i in recent]
        try:
            answer = llm.invoke(SOP_PROMPT.format(history=history, message=state["message"])).content.strip()
        except Exception:
            answer = FALLBACK_ANSWER
        return {"answer": answer}

    return handle


def build_chat_graph(llm, vss_client, session_factory):
    graph = StateGraph(ChatState)
    graph.add_node("parse_intent", make_parse_intent_node(llm))
    graph.add_node("clip_question", make_clip_question_node(vss_client))
    graph.add_node("stats_question", make_stats_question_node(vss_client))
    graph.add_node("archive_search", make_archive_search_node(vss_client))
    graph.add_node("sop_suggestion", make_sop_suggestion_node(llm, session_factory))
    graph.set_entry_point("parse_intent")
    graph.add_conditional_edges(
        "parse_intent",
        lambda state: state["intent"],
        {
            "clip_question": "clip_question",
            "stats_question": "stats_question",
            "archive_search": "archive_search",
            "sop_suggestion": "sop_suggestion",
        },
    )
    for node in ("clip_question", "stats_question", "archive_search", "sop_suggestion"):
        graph.add_edge(node, END)
    return graph.compile()
