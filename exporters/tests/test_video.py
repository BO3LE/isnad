"""assemble_lesson: a lesson and its narration → an MP4 whose slides follow the voice.

The render tests need FFmpeg (the worker image and CI have it) and Pillow (gp-exporters[video]).
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import wave
from itertools import pairwise
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from exporters import assemble_lesson
from exporters.lesson import (
    PAUSE_AFTER_HEADING,
    PAUSE_AFTER_LINE,
    PAUSE_AFTER_PART,
    PAUSE_AFTER_TITLE,
    RECAP_SECONDS,
    lesson_from_markdown,
)

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")

SCRIPT = "# Solar\n\nThe sun is strong here.\n\n## Panels\n\nA panel turns light into power. Dust lowers its output."


def _tone(seconds: float, rate: int = 24000) -> bytes:
    """A clip that isn't silence, at gTTS's rate — so the AAC track has something in it."""
    frames = int(rate * seconds)
    pcm = b"".join(((3000 if (i // 40) % 2 else -3000) & 0xFFFF).to_bytes(2, "little") for i in range(frames))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as track:
        track.setnchannels(1)
        track.setsampwidth(2)
        track.setframerate(rate)
        track.writeframes(pcm)
    return buffer.getvalue()


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)


def _frame(path: Path, at: float) -> Image.Image:
    png = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{at:.2f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-c:v",
            "png",
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    return Image.open(io.BytesIO(png)).convert("RGB")


def test_it_needs_one_clip_per_line_the_voice_reads():
    lesson = lesson_from_markdown(SCRIPT)

    with pytest.raises(ValueError, match=f"expected {len(lesson.narration())} narration clips, got 1"):
        assemble_lesson(lesson, [b"one"])


def test_every_ffmpeg_call_shares_one_time_budget(monkeypatch):
    """subprocess.run kills the child when `timeout` runs out, then raises TimeoutExpired."""
    seen = []

    def run(args, **kwargs):
        seen.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(subprocess, "run", run)
    lesson = lesson_from_markdown(SCRIPT)

    with pytest.raises(subprocess.TimeoutExpired):
        assemble_lesson(lesson, [b"clip"] * len(lesson.narration()), timeout_s=42)
    assert len(seen) == 1 and 41 < seen[0] <= 42


@needs_ffmpeg
def test_a_lesson_renders_as_a_playable_video_timed_to_its_narration(tmp_path):
    lesson = lesson_from_markdown(SCRIPT)  # cover, "Introduction" (not read), "Panels" (read), recap
    clips = [_tone(1.0) for _ in lesson.narration()]
    assert lesson.narration() == [
        "Solar.",
        "The sun is strong here.",
        "Panels.",
        "A panel turns light into power.",
        "Dust lowers its output.",
    ]

    video = assemble_lesson(lesson, clips)
    path = tmp_path / "video.mp4"
    path.write_bytes(video.data)
    probe = _probe(path)

    streams = {s["codec_type"]: s for s in probe["streams"]}
    assert streams["video"]["codec_name"] == "h264"
    assert (streams["video"]["width"], streams["video"]["height"]) == (1280, 720)
    assert streams["video"]["pix_fmt"] == "yuv420p"
    assert streams["audio"]["codec_name"] == "aac"
    # Five one-second clips, the pause after each, then the silent recap.
    pauses = PAUSE_AFTER_TITLE + PAUSE_AFTER_PART + PAUSE_AFTER_HEADING + PAUSE_AFTER_LINE + PAUSE_AFTER_PART
    expected = 5 * 1.0 + pauses + RECAP_SECONDS
    assert video.duration_seconds == pytest.approx(expected, abs=0.15)
    # The MP4's index is at the front, so a browser can start playing before it has the whole file.
    assert video.data.index(b"moov") < video.data.index(b"mdat")


@needs_ffmpeg
def test_the_picture_changes_with_the_voice_and_ends_on_ink(tmp_path):
    lesson = lesson_from_markdown(SCRIPT)
    clips = [_tone(1.0) for _ in lesson.narration()]
    path = tmp_path / "video.mp4"
    path.write_bytes(assemble_lesson(lesson, clips).data)

    # The beats: cover 0–1.8 s, the Introduction's line 1.8–3.7, "Panels." 3.7–5.2, its lines 5.2–6.55
    # and 6.55–8.45, the recap 8.45–13.45, fading to ink over its last 0.8 s.
    cover = _frame(path, 0.5)
    first_line = _frame(path, 2.5)
    second_part = _frame(path, 6.0)
    recap = _frame(path, 10.5)
    end = _frame(path, 13.4)

    frames = [cover, first_line, second_part, recap]
    for a, b in pairwise(frames):
        assert ImageChops.difference(a, b).getbbox() is not None
    assert first_line.getpixel((4, 4))[0] > 200  # the part slides are on paper
    assert max(end.resize((1, 1)).getpixel((0, 0))) < 30  # the last frames fade to ink


@needs_ffmpeg
def test_1080p_is_drawn_at_1080p(tmp_path):
    lesson = lesson_from_markdown("# T\n\nOne short line here.")
    video = assemble_lesson(lesson, [_tone(0.5), _tone(0.5)], resolution="1080p")
    path = tmp_path / "video.mp4"
    path.write_bytes(video.data)

    stream = next(s for s in _probe(path)["streams"] if s["codec_type"] == "video")
    assert (stream["width"], stream["height"]) == (1920, 1080)
