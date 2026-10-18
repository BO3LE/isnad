"""Video: a script → a narrated lesson video with slides (`exporters.video.assemble_lesson`).

The lesson's shape — title, parts, the lines the voice reads — comes from the script itself
(`exporters.lesson`). The key point each line adds to its slide is written by the model when it
answers with a usable list, and by a plain rule otherwise: a model that is down or answers badly
never fails the step, it only makes the notes plainer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import uuid

from contracts.agent import BaseAgent
from contracts.agent_io import VideoConfig, VideoInput, VideoOutput
from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import LLMPort, Ports, TTSPort
from exporters.lesson import Lesson, key_point, lesson_from_markdown
from exporters.video import FFmpegNotFound, assemble_lesson

log = logging.getLogger(__name__)

TTS_CONCURRENCY = 4
MAX_MODEL_POINT_WORDS = 12
AGENDA_INTRO = "In this lesson"  # English: read only when the voice is (exporters.lesson.Lesson.agenda_intro)

POINTS_SYSTEM = (
    "You write the short notes shown on lesson slides while a narrator reads the script. Answer with JSON only."
)


class VideoAgent(BaseAgent[VideoInput, VideoOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = VideoInput
    output_model = VideoOutput
    config_model = VideoConfig

    async def execute(self, input_data: VideoInput, ports: Ports) -> VideoOutput:
        english = input_data.voice.lower().startswith("en")
        lesson = lesson_from_markdown(
            input_data.script, title=input_data.title, agenda_intro=AGENDA_INTRO if english else None
        )
        if not lesson.parts:
            raise NonRetryableAgentError("The script has no sentences to narrate.", code="empty_script")
        lesson = await with_model_points(lesson, ports.llm)
        narration = await speak_all(lesson.narration(), ports.tts, input_data.voice)
        try:
            rendered = await asyncio.to_thread(assemble_lesson, lesson, narration, resolution=input_data.resolution)
        except FFmpegNotFound as exc:
            raise NonRetryableAgentError(
                "The video couldn't be assembled: FFmpeg is not installed.", code="ffmpeg_missing"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise NonRetryableAgentError(
                f"The video took longer than {exc.timeout:g} s to assemble and was stopped.", code="ffmpeg_timeout"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise AgentError("The video couldn't be assembled.", code="ffmpeg_failed") from exc
        path = await ports.storage.put(f"artifacts/videos/{uuid.uuid4().hex[:8]}/video.mp4", rendered.data, "video/mp4")
        return VideoOutput(video_path=path, duration_seconds=round(rendered.duration_seconds, 2))


async def speak_all(lines: list[str], tts: TTSPort, voice: str) -> list[bytes]:
    """One narration clip per line, in order — a few at a time."""
    gate = asyncio.Semaphore(TTS_CONCURRENCY)

    async def speak(text: str) -> bytes:
        async with gate:
            return await tts.speak(text, voice=voice)

    return list(await asyncio.gather(*(speak(line) for line in lines)))


def points_prompt(lesson: Lesson) -> str:
    numbered, n = [], 0
    for index, part in enumerate(lesson.parts, start=1):
        numbered.append(f"Part {index} — {part.heading}")
        for line in part.lines:
            n += 1
            numbered.append(f"{n}. {line.text}")
    body = "\n".join(numbered)
    return (
        f"Lesson: {lesson.title}\n\n"
        "Below is the narration, one numbered line per sentence, grouped by part. For each line write the key "
        "point a student would copy into their notes about that line: at most 8 words, plain words, no full stop "
        "at the end. Give every line a point unless it only repeats an earlier one.\n\n"
        f"{body}\n\n"
        f'Answer as {{"points": [{{"line": 1, "point": "..."}}, ...]}}, lines 1 to {n} in order.'
    )


def points_schema(count: int) -> dict:
    return {
        "type": "object",
        "properties": {
            "points": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "line": {"type": "integer", "minimum": 1, "maximum": count},
                        "point": {"type": "string"},
                    },
                    "required": ["line", "point"],
                    "additionalProperties": False,
                },
                "maxItems": count,
            }
        },
        "required": ["points"],
        "additionalProperties": False,
    }


async def with_model_points(lesson: Lesson, llm: LLMPort) -> Lesson:
    """The lesson with the model's key points, or unchanged (the plain rule's points) when the model
    can't be reached or its answer doesn't fit."""
    lines = lesson.lines()
    try:
        answer = await llm.complete(points_prompt(lesson), system=POINTS_SYSTEM, json_schema=points_schema(len(lines)))
        points = _parse_points(answer, len(lines))
    except (AgentError, ValueError, TypeError, KeyError) as exc:
        log.warning("video key points: using the plain rule (%s)", type(exc).__name__)
        return lesson
    cleaned = [_clean_point(point, line.text) for point, line in zip(points, lines, strict=True)]
    if not any(cleaned):
        return lesson
    return lesson.with_points(cleaned)


def _parse_points(answer: str, count: int) -> list[str]:
    """Each point by the line number the model wrote next to it — a list in order drifts when the model
    skips a line; a line it left out gets no point."""
    text = answer.strip()
    if "{" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    found = [""] * count
    for item in json.loads(text)["points"]:
        line, point = item["line"], item["point"]
        if not isinstance(line, int) or not isinstance(point, str) or not 1 <= line <= count:
            raise ValueError("a key point names a line that doesn't exist")
        found[line - 1] = point
    return found


def _clean_point(point: str, sentence: str) -> str:
    point = re.sub(r"\s+", " ", point).strip().strip("\"'“”‘’").rstrip(".").strip()
    if len(point.split()) > MAX_MODEL_POINT_WORDS:
        return key_point(sentence)
    return point[:1].upper() + point[1:]
