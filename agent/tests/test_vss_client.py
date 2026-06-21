import httpx
import respx
from httpx import Response

from app.vss_client import VSSClient


def make_client(max_retries=3):
    return VSSClient(
        agent_base_url="http://agent.test",
        alert_bridge_base_url="http://alertbridge.test",
        max_retries=max_retries,
    )


@respx.mock
def test_get_new_alerts_parses_and_sorts_by_timestamp():
    respx.get("http://alertbridge.test/api/v1/realtime/incidents").mock(
        return_value=Response(200, json={
            "status": "success",
            "count": 2,
            "total": 2,
            "timestamp": "2026-06-21T12:05:00Z",
            "incidents": [
                {"id": "i2", "category": "fall", "sensor_id": "cam1", "timestamp": "2026-06-21T12:01:00Z", "description": "person down"},
                {"id": "i1", "category": "ppe", "sensor_id": "cam1", "timestamp": "2026-06-21T12:00:00Z", "description": "no helmet"},
            ],
        })
    )
    client = make_client()
    alerts = client.get_new_alerts(None)
    assert [a["id"] for a in alerts] == ["i1", "i2"]


@respx.mock
def test_get_new_alerts_passes_start_time_param():
    route = respx.get("http://alertbridge.test/api/v1/realtime/incidents").mock(
        return_value=Response(200, json={"status": "success", "count": 0, "total": 0, "timestamp": "x", "incidents": []})
    )
    client = make_client()
    client.get_new_alerts("2026-06-21T12:00:00Z")
    assert route.calls.last.request.url.params["start_time"] == "2026-06-21T12:00:00Z"


@respx.mock
def test_get_new_alerts_retries_then_succeeds():
    route = respx.get("http://alertbridge.test/api/v1/realtime/incidents")
    route.side_effect = [
        httpx.TimeoutException("boom"),
        Response(200, json={"status": "success", "count": 0, "total": 0, "timestamp": "x", "incidents": []}),
    ]
    client = make_client()
    alerts = client.get_new_alerts(None)
    assert alerts == []
    assert route.call_count == 2


@respx.mock
def test_chat_sends_openai_style_messages_and_parses_content():
    route = respx.post("http://agent.test/chat").mock(
        return_value=Response(200, json={
            "id": "x", "object": "chat.completion", "model": "m", "created": 0,
            "choices": [{"finish_reason": "stop", "index": 0, "message": {"content": "two people", "role": "assistant"}}],
        })
    )
    client = make_client()
    answer = client.chat("how many people?")
    assert answer == "two people"
    sent_body = route.calls.last.request.content
    assert b'"role":"user"' in sent_body
    assert b'"content":"how many people?"' in sent_body


@respx.mock
def test_generate_report_builds_prompt_from_incident_and_calls_chat():
    route = respx.post("http://agent.test/chat").mock(
        return_value=Response(200, json={
            "choices": [{"message": {"content": "Person down in aisle-3.", "role": "assistant"}}],
        })
    )
    client = make_client()
    incident = {
        "id": 1, "hazard_type": "fall", "severity": "critical", "status": "open",
        "zone": "aisle-3", "caption": "person down", "report_text": None,
        "created_at": "2026-06-21T12:00:00", "updated_at": "2026-06-21T12:00:00",
    }
    report = client.generate_report(incident)
    assert report == "Person down in aisle-3."
    sent_body = route.calls.last.request.content
    assert b"aisle-3" in sent_body
    assert b"fall" in sent_body


@respx.mock
def test_register_alert_rules_posts_each_rule_and_returns_ids():
    respx.post("http://alertbridge.test/api/v1/realtime").mock(side_effect=[
        Response(200, json={"id": "rule-1", "status": "success", "message": "created"}),
        Response(200, json={"id": "rule-2", "status": "success", "message": "created"}),
    ])
    client = make_client()
    rules = [
        {"alert_type": "ppe", "prompt": "p1", "system_prompt": "s1"},
        {"alert_type": "fall", "prompt": "p2", "system_prompt": "s2"},
    ]
    ids = client.register_alert_rules("rtsp://localhost:8554/cam1", "cam1", rules)
    assert ids == ["rule-1", "rule-2"]


@respx.mock
def test_delete_alert_rules_deletes_each_id():
    route1 = respx.delete("http://alertbridge.test/api/v1/realtime/rule-1").mock(
        return_value=Response(200, json={"id": "rule-1", "status": "success", "message": "deleted"})
    )
    route2 = respx.delete("http://alertbridge.test/api/v1/realtime/rule-2").mock(
        return_value=Response(200, json={"id": "rule-2", "status": "success", "message": "deleted"})
    )
    client = make_client()
    client.delete_alert_rules(["rule-1", "rule-2"])
    assert route1.called
    assert route2.called


@respx.mock
def test_health_check_returns_true_when_both_backends_healthy():
    respx.get("http://agent.test/health").mock(return_value=Response(200, json={"value": {"isAlive": True}}))
    respx.get("http://alertbridge.test/health").mock(return_value=Response(200, json={"status": "ok"}))
    client = make_client()
    assert client.health_check() is True


@respx.mock
def test_health_check_returns_false_if_either_backend_fails():
    respx.get("http://agent.test/health").mock(return_value=Response(503))
    respx.get("http://alertbridge.test/health").mock(return_value=Response(200, json={"status": "ok"}))
    client = make_client(max_retries=1)
    assert client.health_check() is False
