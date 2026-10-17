import json
import shutil
import subprocess
from pathlib import Path

import pytest

from adapters.factory import AdapterSettings, build_ports
from agents.video import agent as video
from agents.video.agent import VideoAgent, _plain_text
from contracts.errors import AgentError

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "input.json").read_text())


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


def test_markdown_is_flattened_for_narration():
    assert _plain_text("# Title\n\nSee [IRENA](https://x.org).") == "Title See IRENA."


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
async def test_renders_a_playable_mp4(ports, tmp_path):
    agent = VideoAgent()
    out = await agent.execute(agent.input_model.model_validate(FIXTURE), ports)
    assert (tmp_path / out.video_path).read_bytes()[4:8] == b"ftyp"
    assert out.duration_seconds > 0


async def test_a_render_past_its_time_is_stopped_and_not_retried(ports, monkeypatch):
    def too_slow(audio, **kwargs):
        raise subprocess.TimeoutExpired(["ffmpeg"], 600)

    monkeypatch.setattr(video, "assemble_mp4", too_slow)
    agent = VideoAgent()

    with pytest.raises(AgentError) as caught:
        await agent.execute(agent.input_model.model_validate(FIXTURE), ports)

    assert (caught.value.code, caught.value.retryable) == ("ffmpeg_timeout", False)
    assert "longer than 600 s" in caught.value.message
