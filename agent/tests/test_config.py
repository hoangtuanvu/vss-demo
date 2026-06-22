from app.config import Settings


def test_settings_has_split_vss_backend_urls():
    settings = Settings(
        vss_agent_base_url="http://example.test:8000",
        vss_alert_bridge_base_url="http://example.test:9080",
    )
    assert settings.vss_agent_base_url == "http://example.test:8000"
    assert settings.vss_alert_bridge_base_url == "http://example.test:9080"


def test_settings_defaults_vss_mode_to_real():
    settings = Settings()
    assert settings.vss_mode == "real"


def test_settings_accepts_mock_vss_mode():
    settings = Settings(vss_mode="mock")
    assert settings.vss_mode == "mock"
