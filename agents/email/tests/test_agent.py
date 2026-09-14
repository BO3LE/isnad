import json
from pathlib import Path

import pytest

from adapters.factory import AdapterSettings, build_ports
from agents.email.agent import EmailAgent

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "input.json").read_text())


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


async def test_sends_links(ports):
    agent = EmailAgent()
    out = await agent.execute(agent.input_model.model_validate(FIXTURE), ports)
    to, _subject, body = ports.email.sent[0]
    assert to == ["demo@gp.local"] and "https://youtu.be/abc" in body and out.message_id


def test_requires_approval():
    assert EmailAgent.manifest.requires_approval is True
