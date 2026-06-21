from app.config import Settings


def test_settings_has_split_vss_backend_urls():
    settings = Settings(
        vss_agent_base_url="http://example.test:8000",
        vss_alert_bridge_base_url="http://example.test:9080",
    )
    assert settings.vss_agent_base_url == "http://example.test:8000"
    assert settings.vss_alert_bridge_base_url == "http://example.test:9080"
