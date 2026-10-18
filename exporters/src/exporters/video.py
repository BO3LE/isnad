"""Narration (+ slides) → MP4 with FFmpeg.

`assemble_lesson` is what the Video agent uses: one narration clip per line of the lesson, slides
timed to them (`exporters.lesson`, `exporters.slides`). `assemble_mp4` puts narration over a plain
ink background — the first skeleton, kept as the smallest real MP4 the pipeline can make.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import time
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exporters.lesson import Lesson

RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080)}

FPS = 25
SAMPLE_RATE = 24_000  # gTTS speaks at 24 kHz; the narration track is built at that rate, mono, 16-bit
SLIDE_FADE = 0.5  # seconds: a cross-fade when the slide changes
POINT_FADE = 0.25  # seconds: a new key point and caption fading in on the same slide
END_FADE = 0.8  # seconds: the last slide fading to ink


class FFmpegNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedVideo:
    data: bytes
    duration_seconds: float


def _tools() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise FFmpegNotFound("ffmpeg and ffprobe must be installed (the worker image includes them)")
    return ffmpeg, ffprobe


def _duration(ffprobe: str, path: Path) -> float:
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return float(json.loads(probe.stdout)["format"]["duration"])


def assemble_mp4(
    audio: bytes, *, resolution: str = "720p", background: str = "0x0B0B0A", timeout_s: float = 600.0
) -> RenderedVideo:
    ffmpeg, ffprobe = _tools()
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
            timeout=timeout_s,  # raises subprocess.TimeoutExpired after killing ffmpeg
        )
        return RenderedVideo(data=video_path.read_bytes(), duration_seconds=_duration(ffprobe, video_path))


class _Deadline:
    """One time budget for every FFmpeg call of a render: each gets what is left of it."""

    def __init__(self, seconds: float):
        self._seconds = seconds
        self._end = time.monotonic() + seconds

    def left(self, cmd: Sequence[str]) -> float:
        remaining = self._end - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(list(cmd), self._seconds)
        return remaining


def assemble_lesson(
    lesson: Lesson,
    narration: Sequence[bytes],
    *,
    resolution: str = "720p",
    timeout_s: float = 600.0,
) -> RenderedVideo:
    """A lesson video: `narration[i]` is the voice reading `lesson.narration()[i]` (any format FFmpeg
    reads — gTTS gives MP3). Each slide stays up for its line plus a pause; the parts' key points
    appear as they are read; the video ends on the recap. `timeout_s` bounds the whole render."""
    from PIL import Image  # Pillow, needed only here

    from exporters import slides

    size = RESOLUTIONS[resolution]
    beats = lesson.beats()
    spoken = [beat for beat in beats if beat.say]
    if len(narration) != len(spoken):
        raise ValueError(f"expected {len(spoken)} narration clips, got {len(narration)}")
    ffmpeg, ffprobe = _tools()
    deadline = _Deadline(timeout_s)

    # 1. The narration track: each clip decoded to PCM, the beat's pause after it, silence for silent beats.
    clips = iter(narration)
    pcm = io.BytesIO()
    durations: list[float] = []
    for beat in beats:
        samples = b""
        if beat.say:
            cmd = [ffmpeg, "-v", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "pipe:1"]
            samples = subprocess.run(
                cmd, input=next(clips), check=True, capture_output=True, timeout=deadline.left(cmd)
            ).stdout
        gap = beat.pause if beat.say else beat.hold
        pcm.write(samples + b"\x00\x00" * round(gap * SAMPLE_RATE))
        durations.append(len(samples) / 2 / SAMPLE_RATE + gap)
    total = sum(durations)

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        with wave.open(str(folder / "narration.wav"), "wb") as track:
            track.setnchannels(1)
            track.setsampwidth(2)
            track.setframerate(SAMPLE_RATE)
            track.writeframes(pcm.getvalue())

        # 2. The pictures: one slide per beat, held until the next beat starts — frame-exact, so the
        #    slides never drift from the voice — with a short cross-fade into each.
        entries: list[tuple[str, float]] = []
        count = 0

        def frame(image, frames: int) -> None:
            nonlocal count
            name = f"f{count:05d}.png"
            image.save(folder / name, compress_level=1)
            entries.append((name, frames / FPS))
            count += 1

        minutes = max(1, round(total / 60))
        start = 0.0
        previous = None
        previous_beat = None
        for index, (beat, seconds) in enumerate(zip(beats, durations, strict=True)):
            first, last = round(start * FPS), round((start + seconds) * FPS)
            span = max(1, last - first)
            start += seconds
            image = slides.render(lesson, beat, size, progress=(start - seconds) / total, minutes=minutes)
            fade = 0
            if previous is not None:
                changed = beat.slide != previous_beat.slide or beat.part != previous_beat.part
                fade = min(span - 1, round((SLIDE_FADE if changed else POINT_FADE) * FPS))
            for step in range(1, fade):
                frame(Image.blend(previous, image, step / fade), 1)
            ending = round(END_FADE * FPS) if index == len(beats) - 1 else 0
            hold = span - max(0, fade - 1) - ending
            frame(image, max(1, hold))
            if ending:
                ink = Image.new("RGB", size, slides.INK)
                for step in range(1, ending + 1):
                    frame(Image.blend(image, ink, step / ending), 1)
            previous, previous_beat = image, beat

        listing = "ffconcat version 1.0\n" + "".join(f"file '{name}'\nduration {d:.4f}\n" for name, d in entries)
        listing += f"file '{entries[-1][0]}'\n"  # the concat demuxer ignores the last entry's duration
        (folder / "frames.ffconcat").write_text(listing)

        # 3. Encode.
        video_path = folder / "video.mp4"
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(folder / "frames.ffconcat"),
            "-i",
            str(folder / "narration.wav"),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-vf",
            f"fps={FPS},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-tune",
            "stillimage",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-t",
            f"{total:.3f}",
            "-movflags",
            "+faststart",
            str(video_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=deadline.left(cmd))
        return RenderedVideo(data=video_path.read_bytes(), duration_seconds=_duration(ffprobe, video_path))
