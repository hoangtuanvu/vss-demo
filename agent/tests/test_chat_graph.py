from app.graphs.chat import build_chat_graph
from app.models import HazardType, Severity
from app.store import create_incident


class FakeLLM:
    """Returns responses from a queue; last entry is repeated if exhausted."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self._index = 0

    def invoke(self, prompt):
        idx = min(self._index, len(self._responses) - 1)
        self._index += 1
        content = self._responses[idx]

        class R:
            pass

        r = R()
        r.content = content
        return r


class FakeVSSClient:
    def __init__(self, answer="two people in frame"):
        self.answer = answer
        self.messages_received = []

    def chat(self, message):
        self.messages_received.append(message)
        return self.answer


class ErrorVSSClient:
    def chat(self, message):
        raise RuntimeError("boom")


def test_incidents_query_uses_llm_not_vss(session_factory):
    with session_factory() as session:
        create_incident(
            session,
            hazard_type=HazardType.SPILL,
            severity=Severity.WARNING,
            zone="aisle-3",
            caption="liquid spill near shelf",
            raw_alert_payload={},
            dedupe_key="spill:aisle-3:1",
        )

    vss_client = FakeVSSClient()
    llm = FakeLLM("1 spill in aisle-3")
    graph = build_chat_graph(llm, vss_client, session_factory)
    result = graph.invoke({"message": "list all spill incidents", "intent": None, "answer": None})

    assert result["answer"] == "1 spill in aisle-3"
    assert vss_client.messages_received == []  # VSS never called


def test_video_question_calls_vss(session_factory):
    vss_client = FakeVSSClient(answer="forklift moving near loading dock")
    llm = FakeLLM("video_question")
    graph = build_chat_graph(llm, vss_client, session_factory)
    result = graph.invoke({"message": "what is happening?", "intent": None, "answer": None})

    assert vss_client.messages_received == ["what is happening?"]
    assert result["answer"] == "forklift moving near loading dock"


def test_video_question_vss_error_returns_helpful_message(session_factory):
    llm = FakeLLM("video_question")
    graph = build_chat_graph(llm, ErrorVSSClient(), session_factory)
    result = graph.invoke({"message": "what is happening?", "intent": None, "answer": None})

    assert "upload" in result["answer"].lower() or "stream" in result["answer"].lower()


def test_video_question_vss_sorry_response_is_replaced(session_factory):
    vss_client = FakeVSSClient(
        answer="Sorry, I wasn't able to complete your request. Please try again."
    )
    llm = FakeLLM("video_question")
    graph = build_chat_graph(llm, vss_client, session_factory)
    result = graph.invoke({"message": "what is in the video?", "intent": None, "answer": None})

    assert "sorry" not in result["answer"].lower() or "upload" in result["answer"].lower()


def test_sop_suggestion_uses_llm_with_incident_history(session_factory):
    with session_factory() as session:
        create_incident(
            session,
            hazard_type=HazardType.FORKLIFT_PROXIMITY,
            severity=Severity.CRITICAL,
            zone="dock-1",
            caption="forklift passed within 1m of a pedestrian",
            raw_alert_payload={},
            dedupe_key="forklift_proximity:dock-1:1",
        )

    vss_client = FakeVSSClient()
    llm = FakeLLM("Add pedestrian lanes near dock-1.")
    graph = build_chat_graph(llm, vss_client, session_factory)
    result = graph.invoke(
        {"message": "how do we prevent forklift incidents?", "intent": None, "answer": None}
    )

    assert result["answer"] == "Add pedestrian lanes near dock-1."
    assert vss_client.messages_received == []  # VSS never called


def test_generic_message_routes_to_incidents_query(session_factory):
    vss_client = FakeVSSClient()
    llm = FakeLLM("No incidents found.")
    graph = build_chat_graph(llm, vss_client, session_factory)
    result = graph.invoke({"message": "anything", "intent": None, "answer": None})

    assert result["answer"] == "No incidents found."
    assert vss_client.messages_received == []


def test_video_keywords_route_to_video_question(session_factory):
    vss_client = FakeVSSClient(answer="forklift visible")
    llm = FakeLLM()
    graph = build_chat_graph(llm, vss_client, session_factory)
    result = graph.invoke({"message": "what is happening in the footage?", "intent": None, "answer": None})
    assert vss_client.messages_received != []
    assert result["answer"] == "forklift visible"


def test_sop_keywords_route_to_sop_suggestion(session_factory):
    vss_client = FakeVSSClient()
    llm = FakeLLM("Add safety barriers.")
    graph = build_chat_graph(llm, vss_client, session_factory)
    result = graph.invoke({"message": "how can we prevent accidents?", "intent": None, "answer": None})
    assert vss_client.messages_received == []
    assert result["answer"] == "Add safety barriers."
