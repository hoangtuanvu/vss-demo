from app.graphs.triage import make_classify_severity_node


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def invoke(self, prompt):
        return FakeResponse(self.reply)


class ErrorLLM:
    def invoke(self, prompt):
        raise RuntimeError("boom")


BASE_STATE = {"hazard_type": "fall", "zone": "dock-1", "caption": "person down", "history": []}


def test_classify_severity_parses_valid_reply():
    node = make_classify_severity_node(FakeLLM("critical"))
    assert node(BASE_STATE) == {"severity": "critical"}


def test_classify_severity_falls_back_on_malformed_reply():
    node = make_classify_severity_node(FakeLLM("not-a-severity"))
    assert node(BASE_STATE) == {"severity": "warning"}


def test_classify_severity_falls_back_on_llm_error():
    node = make_classify_severity_node(ErrorLLM())
    assert node(BASE_STATE) == {"severity": "warning"}
