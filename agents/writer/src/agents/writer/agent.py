from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from contracts.agent import BaseAgent
from contracts.agent_io import WriteConfig, WriteInput, WriteOutput
from contracts.errors import AgentError
from contracts.ports import Ports

LENGTH_WORDS = {"short": 400, "medium": 800, "long": 1500}
SYSTEM = "You are a careful writer. You only state what the notes support. You always answer with valid JSON."
REFORMAT = (
    "Your previous answer was not valid JSON with the keys title, summary and article_md. "
    "Problem: {problem}\n\nReturn only the corrected JSON object.\n\nPrevious answer:\n{answer}"
)


class WriterAgent(BaseAgent[WriteInput, WriteOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = WriteInput
    output_model = WriteOutput
    config_model = WriteConfig

    async def execute(self, input_data: WriteInput, ports: Ports) -> WriteOutput:
        template = Path(__file__).with_name("prompts").joinpath("write.md").read_text(encoding="utf-8")
        prompt = template.format(
            format=input_data.format.replace("_", " "),
            style=input_data.style,
            length_words=LENGTH_WORDS[input_data.length],
            notes="\n".join(f"- {n}" for n in input_data.notes),
            sources="\n".join(f"[{i + 1}] {s.title} — {s.url}" for i, s in enumerate(input_data.sources)) or "(none)",
        )
        answer = await ports.llm.complete(prompt, system=SYSTEM, json_mode=True)
        try:
            return _parse(answer)
        except (ValueError, ValidationError) as first:
            # One reformat attempt inside the agent (risk R5) before the orchestrator's retry counter moves.
            retry = await ports.llm.complete(
                REFORMAT.format(problem=_short(first), answer=answer), system=SYSTEM, json_mode=True
            )
            try:
                return _parse(retry)
            except (ValueError, ValidationError) as second:
                raise AgentError(
                    f"Writer returned content in an unexpected shape ({_short(second)}).", code="invalid_model_output"
                ) from second


def _parse(answer: str) -> WriteOutput:
    return WriteOutput.model_validate(json.loads(answer))


def _short(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'value'}: {e['msg']}" for e in exc.errors()[:3])
    return str(exc)[:200]
