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
