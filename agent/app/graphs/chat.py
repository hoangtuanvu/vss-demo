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
