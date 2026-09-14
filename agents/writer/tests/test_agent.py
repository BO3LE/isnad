import json
from pathlib import Path

import pytest

from adapters.factory import AdapterSettings, build_ports
from adapters.llm.fake import FakeLLM
from agents.writer.agent import WriterAgent
from contracts.errors import AgentError

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "input.json").read_text())


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


async def test_writes_an_article(ports):
    agent = WriterAgent()
    out = await agent.execute(agent.input_model.model_validate(FIXTURE), ports)
    assert out.article_md.startswith("#")


async def test_one_reformat_attempt_then_a_readable_error(ports):
    """RB-02: unparsable model output gets one in-agent reformat attempt, then fails with a named problem."""
    from dataclasses import replace

    llm = FakeLLM(response="this is not json")
    agent = WriterAgent()
    with pytest.raises(AgentError) as err:
        await agent.execute(agent.input_model.model_validate(FIXTURE), replace(ports, llm=llm))
    assert len(llm.prompts) == 2
    assert err.value.code == "invalid_model_output"
