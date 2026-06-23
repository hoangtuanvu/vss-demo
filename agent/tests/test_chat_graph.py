from app.graphs.chat import build_chat_graph
from app.models import HazardType, Severity
from app.store import create_incident


class FakeLLMIntent:
    def __init__(self, intent):
        self.intent = intent

    def invoke(self, prompt):
        class R:
            content = self.intent

        return R()


class FakeVSSClient:
    def __init__(self, answer="two people in frame"):
        self.answer = answer
        self.messages_received = []

    def chat(self, message):
        self.messages_received.append(message)
        return self.answer


def test_chat_graph_forwards_general_question_and_returns_answer(session_factory):
    vss_client = FakeVSSClient(answer="two people in frame")
    graph = build_chat_graph(FakeLLMIntent("general"), vss_client, session_factory)
    result = graph.invoke({"message": "who is in this clip?", "intent": None, "answer": None})
    assert vss_client.messages_received == ["who is in this clip?"]
    assert result["answer"] == "two people in frame"


def test_chat_graph_falls_back_gracefully_on_vss_client_error(session_factory):
    class ErrorVSSClient:
        def chat(self, message):
            raise RuntimeError("boom")

    graph = build_chat_graph(FakeLLMIntent("general"), ErrorVSSClient(), session_factory)
    result = graph.invoke({"message": "who is in this clip?", "intent": None, "answer": None})
    assert "couldn't fetch" in result["answer"]


def test_sop_suggestion_drafts_from_incident_history(session_factory):
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

    vss_client = FakeVSSClient(answer="Add a marked pedestrian lane near dock-1.")
    graph = build_chat_graph(FakeLLMIntent("sop_suggestion"), vss_client, session_factory)
    result = graph.invoke(
        {"message": "how do we prevent forklift incidents?", "intent": None, "answer": None}
    )

    assert result["answer"] == "Add a marked pedestrian lane near dock-1."
    assert len(vss_client.messages_received) == 1
    assert "forklift passed within 1m of a pedestrian" in vss_client.messages_received[0]
    assert "how do we prevent forklift incidents?" in vss_client.messages_received[0]


def test_sop_suggestion_falls_back_gracefully_on_vss_client_error(session_factory):
    class ErrorVSSClient:
        def chat(self, message):
            raise RuntimeError("boom")

    graph = build_chat_graph(FakeLLMIntent("sop_suggestion"), ErrorVSSClient(), session_factory)
    result = graph.invoke(
        {"message": "how do we prevent forklift incidents?", "intent": None, "answer": None}
    )
    assert "couldn't fetch" in result["answer"]


def test_parse_intent_falls_back_to_general_on_malformed_reply(session_factory):
    vss_client = FakeVSSClient(answer="fine")
    graph = build_chat_graph(FakeLLMIntent("nonsense"), vss_client, session_factory)
    result = graph.invoke({"message": "anything", "intent": None, "answer": None})
    assert vss_client.messages_received == ["anything"]
    assert result["answer"] == "fine"
