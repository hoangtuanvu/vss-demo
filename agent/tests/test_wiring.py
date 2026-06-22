from app.config import Settings
from app.wiring import build_app


def test_build_app_uses_real_urls_when_vss_mode_real():
    settings = Settings(
        vss_mode="real",
        vss_agent_base_url="http://real-agent.test",
        vss_alert_bridge_base_url="http://real-bridge.test",
        database_url="sqlite:///:memory:",
    )
    _, deps = build_app(settings)
    assert deps.vss_client.agent_base_url == "http://real-agent.test"
    assert deps.vss_client.alert_bridge_base_url == "http://real-bridge.test"


def test_build_app_overrides_both_urls_when_vss_mode_mock():
    settings = Settings(
        vss_mode="mock",
        vss_agent_base_url="http://real-agent.test",
        vss_alert_bridge_base_url="http://real-bridge.test",
        mock_vss_base_url="http://mock-vss.test:9000",
        database_url="sqlite:///:memory:",
    )
    _, deps = build_app(settings)
    assert deps.vss_client.agent_base_url == "http://mock-vss.test:9000"
    assert deps.vss_client.alert_bridge_base_url == "http://mock-vss.test:9000"
