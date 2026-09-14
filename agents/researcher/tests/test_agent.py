import json
from pathlib import Path

import pytest

from adapters.factory import AdapterSettings, build_ports
from agents.researcher.agent import ResearcherAgent

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "input.json").read_text())


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


async def test_returns_notes_and_sources(ports):
    agent = ResearcherAgent()
    out = await agent.execute(agent.input_model.model_validate(FIXTURE), ports)
    assert len(out.sources) == 3 and len(out.notes) == 3


def test_manifest_matches_folder():
    assert ResearcherAgent.manifest.name == "researcher"
    assert "topic" in ResearcherAgent.catalog_entry().config_schema["required"]
