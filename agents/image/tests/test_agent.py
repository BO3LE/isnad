import json
from pathlib import Path

import pytest

from adapters.factory import AdapterSettings, build_ports
from agents.image.agent import ImageAgent

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "input.json").read_text())


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


async def test_stores_one_png_per_image(ports, tmp_path):
    agent = ImageAgent()
    out = await agent.execute(agent.input_model.model_validate(FIXTURE), ports)
    assert len(out.image_paths) == 2
    assert (tmp_path / out.image_paths[0]).read_bytes().startswith(b"\x89PNG")
