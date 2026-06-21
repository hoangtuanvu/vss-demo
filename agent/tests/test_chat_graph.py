from app.graphs.chat import build_chat_graph


class FakeVSSClient:
    def __init__(self, answer="two people in frame"):
        self.answer = answer
        self.messages_received = []

    def chat(self, message):
        self.messages_received.append(message)
        return self.answer


def test_chat_graph_forwards_message_and_returns_answer():
    vss_client = FakeVSSClient(answer="two people in frame")
    graph = build_chat_graph(vss_client)
    result = graph.invoke({"message": "who is in this clip?", "answer": None})
    assert vss_client.messages_received == ["who is in this clip?"]
    assert result["answer"] == "two people in frame"


def test_chat_graph_falls_back_gracefully_on_vss_client_error():
    class ErrorVSSClient:
        def chat(self, message):
            raise RuntimeError("boom")

    graph = build_chat_graph(ErrorVSSClient())
    result = graph.invoke({"message": "who is in this clip?", "answer": None})
    assert "couldn't fetch" in result["answer"]
