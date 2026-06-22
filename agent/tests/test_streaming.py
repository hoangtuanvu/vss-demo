from pathlib import Path
from unittest.mock import patch

from app.streaming import start_rtsp_loopback


def test_start_rtsp_loopback_returns_url_and_invokes_ffmpeg(tmp_path):
    video_path = tmp_path / "sample.mp4"
    video_path.write_bytes(b"fake-video-bytes")

    with patch("app.streaming.subprocess.Popen") as mock_popen:
        url = start_rtsp_loopback(video_path, "cam1", "rtsp://localhost:8554")

    assert url == "rtsp://localhost:8554/cam1"
    args = mock_popen.call_args.args[0]
    assert args[0] == "ffmpeg"
    assert str(video_path) in args
    assert "rtsp://localhost:8554/cam1" in args
    assert "-rtsp_transport" in args
    assert args[args.index("-rtsp_transport") + 1] == "tcp"


def test_get_video_duration_seconds_returns_none_on_ffprobe_failure(tmp_path, monkeypatch):
    import subprocess

    from app.streaming import get_video_duration_seconds

    def boom(*args, **kwargs):
        raise FileNotFoundError("ffprobe not found")

    monkeypatch.setattr(subprocess, "run", boom)
    missing = tmp_path / "clip.mp4"
    missing.write_bytes(b"not a real video")
    assert get_video_duration_seconds(missing) is None


def test_get_video_duration_seconds_parses_ffprobe_output(tmp_path, monkeypatch):
    import subprocess

    from app.streaming import get_video_duration_seconds

    class FakeResult:
        stdout = "12.5\n"
        returncode = 0

    def fake_run(*args, **kwargs):
        return FakeResult()

    monkeypatch.setattr(subprocess, "run", fake_run)
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"fake")
    assert get_video_duration_seconds(path) == 12.5
