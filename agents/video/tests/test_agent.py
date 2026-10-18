import dataclasses
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from adapters.factory import AdapterSettings, build_ports
from adapters.llm.fake import FakeLLM
from agents.video import agent as video
from agents.video.agent import VideoAgent, points_prompt, points_schema
from contracts.errors import AgentError
from exporters.lesson import key_point, lesson_from_markdown
from exporters.video import FFmpegNotFound, RenderedVideo

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "input.json").read_text())

SCRIPT = """# Solar in Riyadh

Saudi Arabia gets strong sunlight all year [1]. That makes solar power cheap.

## Panels

A panel turns light into electricity [2, 3]. Dust lowers its output.

## Sources

1. https://example.org/irena
"""


class RecordingTTS:
    def __init__(self):
        self.read: list[str] = []

    async def speak(self, text: str, *, voice: str) -> bytes:
        self.read.append(text)
        return b"clip"


class BrokenLLM:
    async def complete(self, prompt, **kwargs):
        raise AgentError("The model is not loaded.", code="llm_unavailable")


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


@pytest.fixture()
def rendered(monkeypatch):
    """Stands in for the FFmpeg render and keeps what the agent handed it."""
    seen = {}

    def assemble(lesson, narration, **kwargs):
        seen.update(lesson=lesson, narration=narration, **kwargs)
        return RenderedVideo(data=b"\x00\x00\x00\x18ftypmp42", duration_seconds=12.345)

    monkeypatch.setattr(video, "assemble_lesson", assemble)
    return seen


async def run(ports, **given):
    agent = VideoAgent()
    return await agent.execute(agent.input_model.model_validate({"script": SCRIPT} | given), ports)


def answer(*points: tuple[int, str]) -> str:
    return json.dumps({"points": [{"line": line, "point": point} for line, point in points]})


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
async def test_renders_a_playable_mp4(ports, tmp_path):
    agent = VideoAgent()
    out = await agent.execute(agent.input_model.model_validate(FIXTURE), ports)
    assert (tmp_path / out.video_path).read_bytes()[4:8] == b"ftyp"
    assert out.duration_seconds > 0


async def test_the_video_is_stored_and_its_length_reported(ports, rendered, tmp_path):
    out = await run(ports, resolution="1080p")

    assert out.video_path.startswith("artifacts/videos/") and out.video_path.endswith("/video.mp4")
    assert (tmp_path / out.video_path).read_bytes()[4:8] == b"ftyp"
    assert out.duration_seconds == 12.35
    assert rendered["resolution"] == "1080p"


async def test_the_voice_reads_the_lesson_without_citation_markers_or_sources(ports, rendered):
    tts = RecordingTTS()

    await run(dataclasses.replace(ports, tts=tts))

    assert tts.read == [
        "Solar in Riyadh.",
        "In this lesson: Introduction and Panels.",
        "Saudi Arabia gets strong sunlight all year.",
        "That makes solar power cheap.",
        "Panels.",
        "A panel turns light into electricity.",
        "Dust lowers its output.",
    ]
    assert rendered["narration"] == [b"clip"] * len(tts.read)


async def test_the_agenda_is_read_only_in_english(ports, rendered):
    tts = RecordingTTS()

    await run(dataclasses.replace(ports, tts=tts), voice="ar")

    assert not any(line.startswith("In this lesson") for line in tts.read)


async def test_the_models_key_points_go_on_the_slides_by_line_number(ports, rendered):
    llm = FakeLLM(
        "Here you go:\n"
        + answer(
            (4, "dust lowers output."),  # out of order and lower-case: matched by number, tidied
            (1, "“Strong sun all year”"),
            (3, "Panels turn light into power"),
        )
    )

    await run(dataclasses.replace(ports, llm=llm))

    lesson = rendered["lesson"]
    assert [line.point for line in lesson.lines()] == [
        "Strong sun all year",
        "",  # the model gave line 2 no point
        "Panels turn light into power",
        "Dust lowers output",
    ]
    call = llm.calls[0]
    assert call["json_schema"] == points_schema(4)
    assert "1. Saudi Arabia gets strong sunlight all year." in call["prompt"]
    assert "[1]" not in call["prompt"] and "example.org" not in call["prompt"]


async def test_a_point_too_long_for_a_slide_is_made_by_the_plain_rule(ports, rendered):
    llm = FakeLLM(answer((1, " ".join(["word"] * 20)), (2, "Cheap power")))

    await run(dataclasses.replace(ports, llm=llm))

    points = [line.point for line in rendered["lesson"].lines()]
    assert points[:2] == [key_point("Saudi Arabia gets strong sunlight all year."), "Cheap power"]


@pytest.mark.parametrize(
    "llm",
    [
        BrokenLLM(),
        FakeLLM("not JSON at all"),
        FakeLLM(json.dumps({"title": "an answer to some other question"})),
        FakeLLM(answer((9, "a line that doesn't exist"))),
        FakeLLM(json.dumps({"points": ["not", "objects"]})),
        FakeLLM(answer((1, ""), (2, "  "))),
    ],
    ids=["model-down", "not-json", "wrong-shape", "unknown-line", "not-objects", "all-empty"],
)
async def test_a_model_that_cant_help_only_makes_the_points_plainer(ports, rendered, llm):
    await run(dataclasses.replace(ports, llm=llm))

    expected = lesson_from_markdown(SCRIPT).lines()
    assert [line.point for line in rendered["lesson"].lines()] == [line.point for line in expected]
    assert all(line.point for line in rendered["lesson"].lines())


def test_the_prompt_numbers_every_line_under_its_part():
    prompt = points_prompt(lesson_from_markdown(SCRIPT))

    assert "Part 1 — Introduction\n1. Saudi Arabia gets strong sunlight all year.\n2. That makes" in prompt
    assert "Part 2 — Panels\n3. A panel turns light into electricity.\n4. Dust lowers its output." in prompt
    assert "lines 1 to 4" in prompt


async def test_a_script_with_nothing_to_read_fails_without_retrying(ports, rendered):
    with pytest.raises(AgentError) as caught:
        await run(ports, script="# Title\n\n## Sources\n\n- https://example.org")

    assert (caught.value.code, caught.value.retryable) == ("empty_script", False)


async def test_a_render_past_its_time_is_stopped_and_not_retried(ports, monkeypatch):
    def too_slow(lesson, narration, **kwargs):
        raise subprocess.TimeoutExpired(["ffmpeg"], 600)

    monkeypatch.setattr(video, "assemble_lesson", too_slow)
    agent = VideoAgent()

    with pytest.raises(AgentError) as caught:
        await agent.execute(agent.input_model.model_validate(FIXTURE), ports)

    assert (caught.value.code, caught.value.retryable) == ("ffmpeg_timeout", False)
    assert "longer than 600 s" in caught.value.message


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (FFmpegNotFound("no ffmpeg"), "ffmpeg_missing", False),
        (subprocess.CalledProcessError(1, ["ffmpeg"]), "ffmpeg_failed", True),
    ],
)
async def test_ffmpeg_failures_are_reported_plainly(ports, monkeypatch, error, code, retryable):
    def fails(lesson, narration, **kwargs):
        raise error

    monkeypatch.setattr(video, "assemble_lesson", fails)

    with pytest.raises(AgentError) as caught:
        await run(ports)

    assert (caught.value.code, caught.value.retryable) == (code, retryable)
