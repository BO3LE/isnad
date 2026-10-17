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
    assert llm.calls  # the first call, and a fuller rewrite since the fake's article is short
    for call in llm.calls:
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
    assert not any(p.startswith("Your previous answer was not valid JSON") for p in llm.prompts)


async def test_line_breaks_escaped_twice_become_line_breaks(ports):
    """Qwen3 under LM Studio's constrained decoding, seen live: `\\n` inside the JSON string arrived
    as `\\\\n`, so the article parsed as one line with literal backslash-n and rendered as one block."""
    from dataclasses import replace

    twice = json.dumps({"title": "T", "summary": "S.", "article_md": "# T\\n\\nFirst.\\n\\n## Part\\n\\nSecond."})
    agent = WriterAgent()

    out = await agent.execute(agent.input_model.model_validate(FIXTURE), replace(ports, llm=FakeLLM(response=twice)))

    assert out.article_md == "# T\n\nFirst.\n\n## Part\n\nSecond."


async def test_an_article_with_real_line_breaks_keeps_a_literal_backslash_n(ports):
    """In a code sample, `\\n` is meant literally — the article has real line breaks, so it is left alone."""
    from dataclasses import replace

    article = "# T\n\nIn Python, `print('a\\nb')` prints two lines."
    answer = json.dumps({"title": "Using \\n", "summary": "S.", "article_md": article})
    agent = WriterAgent()

    out = await agent.execute(agent.input_model.model_validate(FIXTURE), replace(ports, llm=FakeLLM(response=answer)))

    assert out.article_md == article
    assert out.title == "Using \\n"


async def test_the_prompt_asks_for_a_structure_and_forbids_facts_the_notes_lack(ports):
    from dataclasses import replace

    llm = FakeLLM()
    agent = WriterAgent()
    data = agent.input_model.model_validate({**FIXTURE, "length": "long"})

    await agent.execute(data, replace(ports, llm=llm))

    prompt = llm.calls[0]["prompt"]
    assert "about 1500 words" in prompt and "6 sections" in prompt
    assert "Do not add numbers, dates, names" in prompt


def _article(words: int, extra: str = "") -> str:
    body = " ".join(["word"] * words)
    return json.dumps({"title": "T", "summary": "S.", "article_md": f"# T\n\n{body}{extra}"})


async def test_an_article_well_short_of_its_target_is_rewritten_fuller_once(ports):
    from dataclasses import replace

    llm = FakeLLM()
    agent = WriterAgent()
    replies = iter([_article(100), _article(700)])  # medium is 800 words; 100 is far under 75% of it

    async def complete(prompt, **kwargs):
        llm.calls.append({"prompt": prompt, **kwargs})
        return next(replies)

    llm.complete = complete
    out = await agent.execute(
        agent.input_model.model_validate({**FIXTURE, "length": "medium"}), replace(ports, llm=llm)
    )

    assert len(out.article_md.split()) > 700
    assert len(llm.calls) == 2 and llm.calls[1]["prompt"].startswith("The article below is 102 words")


@pytest.mark.parametrize(
    ("rewrite", "why"),
    [
        (_article(700, " It reached 58.7 GW in 2041."), "states figures the notes don't contain"),
        (_article(50), "is shorter"),
        ("not json", "isn't valid"),
    ],
)
async def test_a_fuller_rewrite_is_kept_only_if_it_is_longer_and_invents_nothing(ports, rewrite, why):
    from dataclasses import replace

    llm = FakeLLM()
    replies = iter([_article(100), rewrite])

    async def complete(prompt, **kwargs):
        llm.calls.append({"prompt": prompt, **kwargs})
        return next(replies)

    llm.complete = complete
    agent = WriterAgent()
    out = await agent.execute(
        agent.input_model.model_validate({**FIXTURE, "length": "medium"}), replace(ports, llm=llm)
    )

    assert len(out.article_md.split()) == 102, f"kept a rewrite that {why}"


async def test_an_article_near_its_target_is_not_rewritten(ports):
    from dataclasses import replace

    llm = FakeLLM(response=_article(700))
    agent = WriterAgent()
    await agent.execute(agent.input_model.model_validate({**FIXTURE, "length": "medium"}), replace(ports, llm=llm))
    assert len(llm.calls) == 1


async def test_an_answer_cut_off_at_the_output_cap_gets_one_more_attempt(ports):
    """Seen live: Qwen3 ran to the 4096-token cap once in 45 runs; the same prompt again was fine."""
    from dataclasses import replace

    from contracts.errors import NonRetryableAgentError

    llm = FakeLLM()
    replies = iter([NonRetryableAgentError("cut off", code="llm_truncated"), _article(700)])

    async def complete(prompt, **kwargs):
        llm.calls.append({"prompt": prompt, **kwargs})
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    llm.complete = complete
    agent = WriterAgent()
    out = await agent.execute(
        agent.input_model.model_validate({**FIXTURE, "length": "medium"}), replace(ports, llm=llm)
    )

    assert len(out.article_md.split()) == 702 and len(llm.calls) == 2


async def test_cut_off_twice_is_reported_as_it_is(ports):
    from dataclasses import replace

    from contracts.errors import NonRetryableAgentError

    llm = FakeLLM()

    async def complete(prompt, **kwargs):
        llm.calls.append({"prompt": prompt})
        raise NonRetryableAgentError("cut off", code="llm_truncated")

    llm.complete = complete
    agent = WriterAgent()
    with pytest.raises(AgentError) as caught:
        await agent.execute(agent.input_model.model_validate(FIXTURE), replace(ports, llm=llm))
    assert caught.value.code == "llm_truncated" and len(llm.calls) == 2
