from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from pathlib import Path

from pydantic import ConfigDict, ValidationError, create_model

from contracts.agent import BaseAgent
from contracts.agent_io import WriteConfig, WriteInput, WriteOutput
from contracts.errors import AgentError, NonRetryableAgentError
from contracts.ports import Ports
from exporters import MissingDependencyError, to_docx, to_pdf

LENGTH_WORDS = {"short": 400, "medium": 800, "long": 1500}
# Sections the prompt asks for: a structure a model keeps to more reliably than a word count.
LENGTH_SECTIONS = {"short": 2, "medium": 4, "long": 6}
SYSTEM = "You are a careful writer. You only state what the notes support. You always answer with valid JSON."
EXPAND = (
    "The article below is {words} words; it should be about {target}. Rewrite it to about {target} words "
    "by explaining each point more fully: what it means, why it matters and how the points connect. Add "
    "no facts, numbers, dates, names, places or claims that the research notes don't contain, and keep "
    "the citations [n]. Return the same JSON object (title, summary, article_md).\n\n"
    "Research notes:\n{notes}\n\nArticle:\n{answer}"
)
# Below this share of the target, the Writer asks once for a fuller version.
SHORT_OF_TARGET = 0.75
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
            sections=LENGTH_SECTIONS[input_data.length],
            notes="\n".join(f"- {n}" for n in input_data.notes),
            sources="\n".join(f"[{i + 1}] {s.title} — {s.url}" for i, s in enumerate(input_data.sources)) or "(none)",
        )
        # The schema lets a provider that supports it (LM Studio, Ollama, OpenAI) constrain the answer
        # to this shape; the answer is still validated here either way.
        try:
            answer = await ports.llm.complete(prompt, system=SYSTEM, json_mode=True, json_schema=OUTPUT_SCHEMA)
        except AgentError as exc:
            if exc.code != "llm_truncated":
                raise
            # A local model can run away — under constrained decoding, endless whitespace between JSON
            # tokens — until the output cap. A second attempt usually doesn't; a second cut-off is
            # reported as it is (it names LLM_MAX_OUTPUT_TOKENS).
            answer = await ports.llm.complete(prompt, system=SYSTEM, json_mode=True, json_schema=OUTPUT_SCHEMA)
        article = await self._first_valid(answer, ports)
        article = await self._to_length(article, input_data, ports)
        return await self._save_files(article, input_data, ports)

    async def _save_files(self, article: WriteOutput, input_data: WriteInput, ports: Ports) -> WriteOutput:
        """FR-04: the finished article as PDF and Word files, next to the run's other outputs."""
        folder = f"artifacts/articles/{uuid.uuid4().hex[:8]}"
        name = _file_stem(article.title)
        files: dict[str, str] = {}
        for switch, key, render, suffix, mime in EXPORTS:
            if getattr(input_data, switch):
                data = await _render(render, switch, key, article)
                files[key] = await ports.storage.put(f"{folder}/{name}.{suffix}", data, mime)
        return article.model_copy(update=files)

    async def _to_length(self, article: WriteOutput, input_data: WriteInput, ports: Ports) -> WriteOutput:
        """One fuller rewrite when the article is well short of its target — kept only if it is valid,
        longer, and states no figure that neither the notes nor the first draft contain. Otherwise
        the first draft stands: being short is never a reason to fail the step, or to invent."""
        target = LENGTH_WORDS[input_data.length]
        words = len(article.article_md.split())
        if words >= SHORT_OF_TARGET * target:
            return article
        notes = "\n".join(f"- {n}" for n in input_data.notes)
        try:
            answer = await ports.llm.complete(
                EXPAND.format(words=words, target=target, notes=notes, answer=article.model_dump_json()),
                system=SYSTEM,
                json_mode=True,
                json_schema=OUTPUT_SCHEMA,
            )
            fuller = _parse(answer)
        except (AgentError, ValueError, ValidationError):
            return article
        known = figures(notes) | figures(article.article_md)
        if len(fuller.article_md.split()) <= words or figures(fuller.article_md) - known:
            return article
        return fuller

    async def _first_valid(self, answer: str, ports: Ports) -> WriteOutput:
        try:
            return _parse(answer)
        except (ValueError, ValidationError) as first:
            # One reformat attempt inside the agent (risk R5) before the orchestrator's retry counter moves.
            retry = await ports.llm.complete(
                REFORMAT.format(problem=_short(first), answer=answer),
                system=SYSTEM,
                json_mode=True,
                json_schema=OUTPUT_SCHEMA,
            )
            try:
                return _parse(retry)
            except (ValueError, ValidationError) as second:
                raise AgentError(
                    f"Writer returned content in an unexpected shape ({_short(second)}).", code="invalid_model_output"
                ) from second


# What the model writes: WriteOutput's text, nothing else. The files' paths are the Writer's own —
# taken from a model's answer, a prompt-injected one could name another user's file.
WRITTEN = ("title", "summary", "article_md")
Draft = create_model(
    "WriteOutput",
    __config__=ConfigDict(extra="forbid"),
    **{name: (WriteOutput.model_fields[name].annotation, WriteOutput.model_fields[name]) for name in WRITTEN},
)
OUTPUT_SCHEMA = Draft.model_json_schema()
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# The Writer step's switch, the output it fills, and how: FR-04.
EXPORTS = (
    ("save_pdf", "pdf_path", to_pdf, "pdf", "application/pdf"),
    ("save_docx", "docx_path", to_docx, "docx", DOCX_MIME),
)
_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$", re.S | re.I)


# What isn't a stated figure: citations ([1], [2, 3]), URLs, and Markdown list numbering.
_NOT_FIGURES = re.compile(r"\[\d+(?:\s*[,–-]\s*\d+)*\]|https?://\S+|^\s*\d+\.\s", re.M)
_FIGURE = re.compile(r"\d+(?:[.,]\d+)*")


def figures(text: str) -> set[str]:
    """Numbers stated as facts. Counting words written as digits (2–9: "3 challenges") are left out."""
    found = _FIGURE.findall(_NOT_FIGURES.sub(" ", text))
    return {f for f in found if "." in f or "," in f or int(f) >= 10}


def _parse(answer: str) -> WriteOutput:
    data = json.loads(_json_text(answer))
    if isinstance(data, dict) and "article_md" in data:
        data["article_md"] = _unescape_twice_escaped(data["article_md"])
    return WriteOutput.model_validate(Draft.model_validate(data).model_dump())


async def _render(render: Callable[..., bytes], switch: str, key: str, article: WriteOutput) -> bytes:
    """One export, off the event loop (WeasyPrint takes about a second). Neither failure is retried:
    the same article on the same server fails the same way."""
    kind = WriteOutput.model_fields[key].title
    try:
        return await asyncio.to_thread(render, article.article_md, title=article.title)
    except MissingDependencyError as exc:
        raise NonRetryableAgentError(
            f"This server can't save the article as a {kind}: {exc}. Install it on the worker, or turn off "
            f"“{WriteConfig.model_fields[switch].title}” in the Writer step.",
            code="export_unavailable",
        ) from exc
    except ValueError as exc:
        raise NonRetryableAgentError(f"The article couldn't be saved as a {kind}: {exc}", code="export_failed") from exc


def _file_stem(title: str) -> str:
    """The files' name, from the title: "Solar energy in KSA" → solar-energy-in-ksa."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-") or "article"


def _unescape_twice_escaped(value: object) -> object:
    """Text whose line breaks arrived as the two characters `\\n`.

    Under constrained decoding some local models (Qwen3 on LM Studio, seen live) escape a newline
    twice inside the JSON string, so the article parses as one line with literal backslash-n in it
    and the Markdown renders as a single paragraph. A text with no real line break but literal ones
    can only be that, so they are turned back into line breaks.
    """
    if isinstance(value, str) and "\n" not in value and "\\n" in value:
        return value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    return value


def _json_text(answer: str) -> str:
    """The JSON object in `answer`. Without constrained decoding, models often wrap it in a ```json
    fence or put a sentence before it; that is unwrapped here rather than costing a reformat call."""
    fenced = _FENCE.match(answer)
    if fenced:
        return fenced.group(1)
    start, end = answer.find("{"), answer.rfind("}")
    if start > 0 and end > start and not answer[:start].strip().startswith(("[", '"')):
        return answer[start : end + 1]
    return answer


def _short(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'value'}: {e['msg']}" for e in exc.errors()[:3])
    return str(exc)[:200]
