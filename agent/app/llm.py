from langchain_nvidia_ai_endpoints import ChatNVIDIA

from app.config import Settings


def get_chat_model(settings: Settings) -> ChatNVIDIA:
    return ChatNVIDIA(
        model=settings.llm_model_name,
        api_key=settings.nvidia_api_key,
        base_url=settings.nim_base_url,
        temperature=0,
    )
