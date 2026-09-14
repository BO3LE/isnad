from __future__ import annotations

import asyncio
import re
import subprocess
import uuid

from contracts.agent import BaseAgent
from contracts.agent_io import VideoConfig, VideoInput, VideoOutput
from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import Ports
from exporters.video import FFmpegNotFound, assemble_mp4


class VideoAgent(BaseAgent[VideoInput, VideoOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = VideoInput
    output_model = VideoOutput
    config_model = VideoConfig

    async def execute(self, input_data: VideoInput, ports: Ports) -> VideoOutput:
        narration = _plain_text(input_data.script)
        audio = await ports.tts.speak(narration, voice=input_data.voice)
        try:
            rendered = await asyncio.to_thread(assemble_mp4, audio, resolution=input_data.resolution)
        except FFmpegNotFound as exc:
            raise NonRetryableAgentError(
                "The video couldn't be assembled: FFmpeg is not installed.", code="ffmpeg_missing"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise AgentError("The video couldn't be assembled.", code="ffmpeg_failed") from exc
        path = await ports.storage.put(f"artifacts/videos/{uuid.uuid4().hex[:8]}/video.mp4", rendered.data, "video/mp4")
        return VideoOutput(video_path=path, duration_seconds=round(rendered.duration_seconds, 2))


def _plain_text(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#>*_`]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
