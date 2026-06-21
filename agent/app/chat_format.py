import re

_NOISE_TAG_PATTERN = re.compile(
    r"<agent-think>.*?</agent-think>|<incidents>.*?</incidents>",
    re.DOTALL,
)


def clean_chat_response(raw: str) -> str:
    stripped = _NOISE_TAG_PATTERN.sub("", raw)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return stripped if stripped else raw
