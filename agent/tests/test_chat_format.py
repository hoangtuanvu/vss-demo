from app.chat_format import clean_chat_response


def test_strips_agent_think_block():
    raw = (
        "<agent-think>lots of internal tool-call trace, plan steps, "
        "sub-agent calls</agent-think>\n"
        "The sensor 'forklift_proximity' has no alerts or incidents "
        "recorded in the system for the last 24 hours."
    )
    assert clean_chat_response(raw) == (
        "The sensor 'forklift_proximity' has no alerts or incidents "
        "recorded in the system for the last 24 hours."
    )


def test_strips_incidents_block():
    raw = (
        "Found 2 incidents matching your query.\n"
        "<incidents>\n"
        '{ "incidents": [{"id": "i1"}, {"id": "i2"}] }\n'
        "</incidents>"
    )
    assert clean_chat_response(raw) == "Found 2 incidents matching your query."


def test_strips_both_blocks_together():
    raw = (
        "<agent-think>plan: call multi_report_agent</agent-think>\n"
        "Two PPE violations were recorded today.\n"
        "<incidents>\n"
        '{ "incidents": [] }\n'
        "</incidents>"
    )
    assert clean_chat_response(raw) == "Two PPE violations were recorded today."


def test_no_tags_returns_unchanged():
    raw = "Two people are visible in the frame."
    assert clean_chat_response(raw) == raw


def test_empty_after_strip_returns_original():
    raw = "<agent-think>only internal trace, no prose at all</agent-think>"
    assert clean_chat_response(raw) == raw
