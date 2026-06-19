from app.graphs.chat import make_parse_intent_node


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def invoke(self, prompt):
        class R:
            content = self.reply
        return R()


def test_parse_intent_recognizes_each_category():
    for intent in ("clip_question", "stats_question", "archive_search", "sop_suggestion"):
        node = make_parse_intent_node(FakeLLM(intent))
        assert node({"message": "anything"}) == {"intent": intent}


def test_parse_intent_falls_back_on_malformed_reply():
    node = make_parse_intent_node(FakeLLM("nonsense"))
    assert node({"message": "anything"}) == {"intent": "stats_question"}
