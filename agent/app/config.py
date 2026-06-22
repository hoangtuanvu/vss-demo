from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    nvidia_api_key: str = ""
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model_name: str = "nvidia/nvidia-nemotron-nano-9b-v2"
    vss_mode: Literal["real", "mock"] = "real"
    vss_agent_base_url: str = "http://localhost:8000"
    vss_alert_bridge_base_url: str = "http://localhost:9080"
    mock_vss_base_url: str = "http://localhost:9000"
    database_url: str = "sqlite:///./warehouse.db"
    slack_webhook_url: str = ""
    poll_interval_seconds: int = 8
    dedupe_window_seconds: int = 300
    mediamtx_rtsp_url: str = "rtsp://localhost:8554"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
