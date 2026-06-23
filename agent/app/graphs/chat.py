from typing import Callable, TypedDict

from langgraph.graph import END, StateGraph

from app import store


class ChatState(TypedDict):
    message: str
    intent: str | None
    answer: str | None


FALLBACK_ANSWER = "Sorry, I couldn't fetch that from the footage right now. Try rephrasing your question."

INTENT_PROMPT = """Classify the user's question into exactly one category:
general, sop_suggestion.
Use sop_suggestion only for questions asking how to prevent, fix, or improve
procedures around a type of safety incident (e.g. "how do we prevent X").
Question: {message}
Reply with only the category name."""

VALID_INTENTS = {"general", "sop_suggestion"}


def make_parse_intent_node(llm) -> Callable[[dict], dict]:
    def parse_intent(state: dict) -> dict:
        try:
            intent = llm.invoke(INTENT_PROMPT.format(message=state["message"])).content.strip().lower()
        except Exception:
            intent = "general"
        if intent not in VALID_INTENTS:
            intent = "general"
        return {"intent": intent}

    return parse_intent


def make_general_question_node(vss_client) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        try:
            answer = vss_client.chat(state["message"])
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": answer}

    return handle


SOP_PROMPT = """Recent incident history: {history}
The user asked how to prevent this kind of incident: {message}
Draft a short, concrete SOP improvement suggestion."""


def make_sop_suggestion_node(vss_client, session_factory) -> Callable[[dict], dict]:
    def handle(state: dict) -> dict:
        with session_factory() as session:
            recent = store.list_incidents(session, limit=5)
        history = [{"hazard_type": i.hazard_type.value, "caption": i.caption} for i in recent]
        prompt = SOP_PROMPT.format(history=history, message=state["message"])
        try:
            answer = vss_client.chat(prompt)
        except Exception:
            return {"answer": FALLBACK_ANSWER}
        return {"answer": answer}

    return handle


def build_chat_graph(llm, vss_client, session_factory):
    graph = StateGraph(ChatState)
    graph.add_node("parse_intent", make_parse_intent_node(llm))
    graph.add_node("general", make_general_question_node(vss_client))
    graph.add_node("sop_suggestion", make_sop_suggestion_node(vss_client, session_factory))
    graph.set_entry_point("parse_intent")
    graph.add_conditional_edges(
        "parse_intent",
        lambda state: state["intent"],
        {"general": "general", "sop_suggestion": "sop_suggestion"},
    )
    graph.add_edge("general", END)
    graph.add_edge("sop_suggestion", END)
    return graph.compile()
