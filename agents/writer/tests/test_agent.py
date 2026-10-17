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


async def test_the_writer_asks_for_its_output_schema(ports):
    """So LM Studio, Ollama or OpenAI can constrain decoding to exactly this shape."""
    from dataclasses import replace

    from contracts.agent_io import WriteOutput

    llm = FakeLLM()
    agent = WriterAgent()
    await agent.execute(agent.input_model.model_validate(FIXTURE), replace(ports, llm=llm))
    (call,) = llm.calls
    assert call["json_schema"] == WriteOutput.model_json_schema()
    assert call["json_mode"] is True


@pytest.mark.parametrize(
    "answer",
    [
        '```json\n{"title": "T", "summary": "S.", "article_md": "# T\\n\\nBody."}\n```',
        'Here is the article:\n{"title": "T", "summary": "S.", "article_md": "# T\\n\\nBody."}',
        '\n  {"title": "T", "summary": "S.", "article_md": "# T\\n\\nBody."}  \n',
    ],
    ids=["fenced", "preamble", "whitespace"],
)
async def test_json_wrapped_the_way_unconstrained_models_wrap_it_needs_no_reformat_call(ports, answer):
    from dataclasses import replace

    llm = FakeLLM(response=answer)
    agent = WriterAgent()
    out = await agent.execute(agent.input_model.model_validate(FIXTURE), replace(ports, llm=llm))
    assert out.title == "T"
    assert len(llm.prompts) == 1
