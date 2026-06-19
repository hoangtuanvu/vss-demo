import subprocess
from pathlib import Path


def start_rtsp_loopback(video_path: Path, stream_name: str, mediamtx_rtsp_url: str) -> str:
    rtsp_url = f"{mediamtx_rtsp_url}/{stream_name}"
    subprocess.Popen(
        [
            "ffmpeg", "-re", "-stream_loop", "-1", "-i", str(video_path),
            "-c", "copy", "-f", "rtsp", rtsp_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return rtsp_url
