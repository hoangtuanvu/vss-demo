from app.graphs.chat import build_chat_graph


class FakeLLMIntent:
    def __init__(self, intent):
        self.intent = intent

    def invoke(self, prompt):
        class R:
            content = self.intent
        return R()


class FakeVSSClient:
    def __init__(self):
        self.ask_video_called = False
        self.query_analytics_called = False
        self.search_archive_called = False

    def ask_video(self, question, clip_ref):
        self.ask_video_called = True
        return "two people in frame"

    def query_analytics(self, query):
        self.query_analytics_called = True
        return {"count": 3}

    def search_archive(self, query):
        self.search_archive_called = True
        return [{"clip": "c1"}]


def test_clip_question_routes_to_ask_video(session_factory):
    vss_client = FakeVSSClient()
    graph = build_chat_graph(FakeLLMIntent("clip_question"), vss_client, session_factory)
    result = graph.invoke({"message": "who is in this clip?", "intent": None, "answer": None})
    assert vss_client.ask_video_called
    assert result["answer"]


def test_stats_question_routes_to_query_analytics(session_factory):
    vss_client = FakeVSSClient()
    graph = build_chat_graph(FakeLLMIntent("stats_question"), vss_client, session_factory)
    result = graph.invoke({"message": "how many ppe violations today?", "intent": None, "answer": None})
    assert vss_client.query_analytics_called
    assert result["answer"]


def test_archive_search_routes_to_search_archive(session_factory):
    vss_client = FakeVSSClient()
    graph = build_chat_graph(FakeLLMIntent("archive_search"), vss_client, session_factory)
    result = graph.invoke({"message": "find clips with a forklift", "intent": None, "answer": None})
    assert vss_client.search_archive_called
    assert result["answer"]


def test_clip_question_falls_back_gracefully_on_tool_error(session_factory):
    class ErrorVSSClient:
        def ask_video(self, question, clip_ref):
            raise RuntimeError("boom")

    graph = build_chat_graph(FakeLLMIntent("clip_question"), ErrorVSSClient(), session_factory)
    result = graph.invoke({"message": "who is in this clip?", "intent": None, "answer": None})
    assert "couldn't fetch" in result["answer"]


def test_sop_suggestion_drafts_from_history(session_factory):
    graph = build_chat_graph(FakeLLMIntent("sop_suggestion"), FakeVSSClient(), session_factory)
    result = graph.invoke({"message": "how do we prevent forklift incidents?", "intent": None, "answer": None})
    assert result["answer"]
