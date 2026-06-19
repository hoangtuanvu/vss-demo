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
