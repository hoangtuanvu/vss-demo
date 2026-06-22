from dataclasses import dataclass
from datetime import datetime


@dataclass
class ActiveUploadState:
    filename: str | None = None
    stream_start_at: datetime | None = None
    duration_seconds: float | None = None
