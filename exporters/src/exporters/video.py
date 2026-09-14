"""Audio (+ slides) → MP4 with FFmpeg.

The W1 skeleton renders narration over a plain ink background so the whole pipeline
produces a real, playable file in FAKE_ADAPTERS mode. Slides land in W5.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080)}


class FFmpegNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedVideo:
    data: bytes
    duration_seconds: float


def assemble_mp4(audio: bytes, *, resolution: str = "720p", background: str = "0x0B0B0A") -> RenderedVideo:
    """TODO(W5, Zain): add title and content slides (images from the Image agent) timed to the narration."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise FFmpegNotFound("ffmpeg and ffprobe must be installed (the worker image includes them)")
    width, height = RESOLUTIONS[resolution]

    with tempfile.TemporaryDirectory() as tmp:
        audio_path, video_path = Path(tmp, "narration"), Path(tmp, "video.mp4")
        audio_path.write_bytes(audio)
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={background}:s={width}x{height}:r=25",
                "-i",
                str(audio_path),
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(video_path),
            ],
            check=True,
            capture_output=True,
        )
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        return RenderedVideo(data=video_path.read_bytes(), duration_seconds=duration)
