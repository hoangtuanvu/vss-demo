import subprocess
from pathlib import Path


def start_rtsp_loopback(video_path: Path, stream_name: str, mediamtx_rtsp_url: str) -> str:
    rtsp_url = f"{mediamtx_rtsp_url}/{stream_name}"
    subprocess.Popen(
        [
            "ffmpeg", "-re", "-stream_loop", "-1", "-i", str(video_path),
            "-c", "copy", "-f", "rtsp", "-rtsp_transport", "tcp", rtsp_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return rtsp_url


def get_video_duration_seconds(video_path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(video_path),
            ],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError, ValueError, OSError):
        return None
