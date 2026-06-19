import httpx
import respx
from httpx import Response

from app.vss_client import VSSClient


@respx.mock
def test_get_new_alerts_parses_payload():
    respx.get("http://vss.test/alerts").mock(
        return_value=Response(200, json={"alerts": [
            {"hazard_type": "ppe", "zone": "dock-1", "caption": "no helmet", "cursor": "c1"}
        ]})
    )
    client = VSSClient(base_url="http://vss.test")
    alerts = client.get_new_alerts(None)
    assert alerts[0]["hazard_type"] == "ppe"


@respx.mock
def test_get_new_alerts_retries_then_succeeds():
    route = respx.get("http://vss.test/alerts")
    route.side_effect = [httpx.TimeoutException("boom"), Response(200, json={"alerts": []})]
    client = VSSClient(base_url="http://vss.test", max_retries=3)
    alerts = client.get_new_alerts(None)
    assert alerts == []
    assert route.call_count == 2


@respx.mock
def test_ask_video_returns_answer():
    respx.post("http://vss.test/ask-video").mock(return_value=Response(200, json={"answer": "two people"}))
    client = VSSClient(base_url="http://vss.test")
    assert client.ask_video("how many people?", "clip-1") == "two people"


@respx.mock
def test_generate_report_returns_text():
    respx.post("http://vss.test/generate-report").mock(return_value=Response(200, json={"report_text": "Incident #1..."}))
    client = VSSClient(base_url="http://vss.test")
    assert client.generate_report(1) == "Incident #1..."


@respx.mock
def test_health_check_returns_true_on_2xx():
    respx.get("http://vss.test/health").mock(return_value=Response(200, json={"status": "ok"}))
    client = VSSClient(base_url="http://vss.test")
    assert client.health_check() is True


@respx.mock
def test_health_check_returns_false_on_failure():
    respx.get("http://vss.test/health").mock(return_value=Response(503))
    client = VSSClient(base_url="http://vss.test", max_retries=1)
    assert client.health_check() is False
