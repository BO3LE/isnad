import json
from pathlib import Path

import pytest

from adapters.factory import AdapterSettings, build_ports
from agents.publisher.agent import PublisherAgent

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "input.json").read_text())


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


async def test_publishes_through_the_injected_port(ports):
    agent = PublisherAgent()
    out = await agent.execute(agent.input_model.model_validate(FIXTURE), ports)
    assert out.remote_url.startswith("https://youtu.be/")
    assert ports.publishers["youtube"].published[0][1].privacy == "unlisted"


def test_requires_approval():
    assert PublisherAgent.manifest.requires_approval is True
