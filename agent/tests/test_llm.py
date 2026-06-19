from app import llm
from app.config import Settings


def test_get_chat_model_uses_settings(monkeypatch):
    captured = {}

    class FakeChatNVIDIA:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm, "ChatNVIDIA", FakeChatNVIDIA)
    settings = Settings(
        nvidia_api_key="key123", nim_base_url="https://x", llm_model_name="nvidia/nemotron-nano-9b-v2"
    )
    model = llm.get_chat_model(settings)
    assert isinstance(model, FakeChatNVIDIA)
    assert captured["api_key"] == "key123"
    assert captured["base_url"] == "https://x"
    assert captured["model"] == "nvidia/nemotron-nano-9b-v2"
