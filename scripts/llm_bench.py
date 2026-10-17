#!/usr/bin/env python3
"""Benchmark local models as ISNAD's Writer — the real agent, prompt and validation — before choosing one.

Opt-in and never run in CI: it needs a running model server. For each model × structured-output
mode × article length it runs the Writer `--runs` times on fixed research notes and records:

    ok              a valid WriteOutput came back (after at most the Writer's one reformat call)
    first_try       valid on the first call: no reformat, no second attempt after a cut-off answer
    expanded        the Writer asked once for a fuller version (first draft under 75% of the target)
    words           article length, and whether it is within ±25% of the target
    cited           the article cites a source as [n]
    invented        figures in the article that the notes don't contain (the notes hold one: 2030)
    seconds         wall time; first-token time; completion tokens per second when reported
    mode_used       the structured mode the server actually accepted (the adapter falls back)

and, per model, how reliably it calls a tool when it should (`contracts.tools.run_tools`).

A model passes when, in json_schema mode, 100% of runs are first-try valid, at least 90% are within
the length target, no run invents a figure, and the median long article takes under 3 minutes. The
fastest passing model wins — and a person confirms the choice.

    # LM Studio's server running with the model loaded (see SETUP.md → "Local LLM"):
    python scripts/llm_bench.py --models qwen3-30b-a3b-instruct-2507
    python scripts/llm_bench.py --models a,b --modes json_schema,none --lengths long --runs 5 \\
        --out docs/metrics/data/llm-bench.json
    python scripts/llm_bench.py --models qwen/qwen3.8-27b --reasoning-effort none   # a thinking model

Prints no prompt or article text, only measurements. For a hosted provider pass --provider and set
its key in the environment (OPENAI_API_KEY / OPENROUTER_API_KEY); the key is never printed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from adapters.factory import AdapterSettings, build_ports
from adapters.llm.openai_compatible import LLMConfig, OpenAICompatibleLLM
from agents.writer.agent import EXPAND, LENGTH_WORDS, REFORMAT, WriterAgent, figures
from contracts.agent_io import WriteInput
from contracts.errors import AgentError
from contracts.ports import Tool
from contracts.tools import run_tools

DEFAULT_URLS = {
    "local": "http://localhost:1234/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
}
KEY_ENV = {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}

# Fixed benchmark input, shaped like the Researcher's output. Placeholder sources, not citations.
NOTES = [
    "Saudi Arabia has some of the highest solar irradiance in the world, with clear skies most of the year.",
    "The national renewable energy programme aims for a large share of electricity from renewables by 2030.",
    "Several utility-scale solar plants are operating or under construction, some among the largest single sites.",
    "Desert dust reduces panel output; operators use robotic and waterless cleaning to recover efficiency.",
    "Falling module prices have made solar one of the cheapest sources of new generation in the region.",
    "High summer temperatures lower photovoltaic efficiency, which affects plant design and panel choice.",
    "Storage and grid upgrades are needed to use solar power after sunset and to balance demand peaks.",
    "Local manufacturing and training programmes aim to build a domestic solar industry and jobs.",
]
SOURCES = [
    {"title": f"Benchmark source {i}", "url": f"https://example.org/source-{i}", "snippet": ""} for i in range(1, 6)
]
CITATION = re.compile(r"\[\d+\]")
ALLOWED_FIGURES = figures(" ".join(NOTES))

LOOKUP = Tool(
    name="capacity_lookup",
    description="Installed solar capacity of a country, in gigawatts.",
    parameters={
        "type": "object",
        "properties": {"country": {"type": "string", "description": "Country name in English"}},
        "required": ["country"],
    },
)


class Counting:
    """Wraps the adapter to count the Writer's calls: the first, a reformat attempt, a fuller rewrite."""

    def __init__(self, inner: OpenAICompatibleLLM):
        self.inner, self.calls, self.reformats, self.expansions, self.cutoffs = inner, 0, 0, 0, 0

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        self.calls += 1
        self.reformats += prompt.startswith(REFORMAT.split("{", 1)[0])
        self.expansions += prompt.startswith(EXPAND.split("{", 1)[0])
        try:
            return await self.inner.complete(prompt, **kwargs)
        except AgentError as exc:
            self.cutoffs += exc.code == "llm_truncated"  # the Writer tries a cut-off answer once more
            raise


@dataclass
class Result:
    model: str
    mode: str
    length: str
    run: int
    ok: bool
    first_try: bool
    error: str | None
    words: int
    target: int
    within: bool
    cited: bool
    invented: list[str]
    expanded: bool
    seconds: float
    first_token_seconds: float | None
    completion_tokens: int | None
    tokens_per_second: float | None
    mode_used: str | None


async def write_once(llm: OpenAICompatibleLLM, model: str, mode: str, length: str, run: int) -> Result:
    counting = Counting(llm)
    ports = replace(build_ports(AdapterSettings(fake=True, storage_root="/tmp/isnad-llm-bench")), llm=counting)
    data = WriteInput(notes=NOTES, sources=SOURCES, length=length, style="informative", format="blog_post")
    target = LENGTH_WORDS[length]
    started = time.monotonic()
    error, article = None, ""
    try:
        out = await WriterAgent().execute(data, ports)
        article = out.article_md
    except AgentError as exc:
        error = exc.code
    seconds = time.monotonic() - started
    usage = llm.last_usage
    words = len(article.split())
    tokens = usage.completion_tokens or (usage.chunks or None)
    gen_seconds = usage.seconds - (usage.first_token_seconds or 0)
    return Result(
        model=model,
        mode=mode,
        length=length,
        run=run,
        ok=error is None,
        first_try=error is None and counting.reformats == 0 and counting.cutoffs == 0,
        expanded=counting.expansions > 0,
        error=error,
        words=words,
        target=target,
        within=error is None and abs(words - target) <= 0.25 * target,
        cited=bool(CITATION.search(article)),
        invented=sorted(figures(article) - ALLOWED_FIGURES),
        seconds=round(seconds, 2),
        first_token_seconds=round(usage.first_token_seconds, 2) if usage.first_token_seconds else None,
        completion_tokens=usage.completion_tokens,
        tokens_per_second=round(tokens / gen_seconds, 1) if tokens and gen_seconds > 0 else None,
        mode_used=usage.structured,
    )


async def tool_call_once(llm: OpenAICompatibleLLM) -> bool:
    asked: list[str] = []

    async def lookup(arguments: dict[str, Any]) -> dict[str, Any]:
        asked.append(str(arguments.get("country", "")))
        return {"country": arguments.get("country"), "installed_gw": 12.3}

    try:
        reply, _ = await run_tools(
            llm,
            [{"role": "user", "content": "Use the tool to find Saudi Arabia's installed solar capacity, then answer."}],
            {LOOKUP.name: (LOOKUP, lookup)},
            max_rounds=3,
        )
    except AgentError:
        return False
    return any("saudi" in c.lower() for c in asked) and "12.3" in reply.content


def summarise(results: list[Result], tool_rates: dict[str, float]) -> list[dict[str, Any]]:
    rows = []
    keys = sorted(
        {(r.model, r.mode, r.length) for r in results}, key=lambda k: (k[0], k[1], list(LENGTH_WORDS).index(k[2]))
    )
    for model, mode, length in keys:
        group = [r for r in results if (r.model, r.mode, r.length) == (model, mode, length)]
        times = sorted(r.seconds for r in group)
        speeds = [r.tokens_per_second for r in group if r.tokens_per_second]
        rows.append(
            {
                "model": model,
                "mode": mode,
                "length": length,
                "runs": len(group),
                "ok": f"{sum(r.ok for r in group)}/{len(group)}",
                "first_try": f"{sum(r.first_try for r in group)}/{len(group)}",
                "within_25pct": f"{sum(r.within for r in group)}/{len(group)}",
                "cited": f"{sum(r.cited for r in group)}/{len(group)}",
                "invented": f"{sum(bool(r.invented) for r in group)}/{len(group)}",
                "expanded": f"{sum(r.expanded for r in group)}/{len(group)}",
                "median_s": round(statistics.median(times), 1),
                "p95_s": round(times[min(len(times) - 1, int(0.95 * len(times)))], 1),
                "median_tok_s": round(statistics.median(speeds), 1) if speeds else None,
                "mode_used": sorted({r.mode_used or "-" for r in group}),
                "errors": sorted({r.error for r in group if r.error}),
                "tool_calls": f"{tool_rates.get(model, 0):.0%}" if model in tool_rates else "-",
            }
        )
    return rows


def verdict(model: str, results: list[Result]) -> tuple[bool, str]:
    schema = [r for r in results if r.model == model and r.mode == "json_schema"]
    if not schema:
        return False, "not run in json_schema mode"
    first_try = sum(r.first_try for r in schema) / len(schema)
    within = sum(r.within for r in schema) / len(schema)
    long_times = [r.seconds for r in schema if r.length == "long"]
    median_long = statistics.median(long_times) if long_times else None
    reasons = []
    if first_try < 1:
        reasons.append(f"first-try valid {first_try:.0%} < 100%")
    if within < 0.9:
        reasons.append(f"within length {within:.0%} < 90%")
    inventing = sum(bool(r.invented) for r in schema)
    if inventing:
        reasons.append(f"invented figures in {inventing}/{len(schema)} runs")
    if median_long is None:
        reasons.append("no long runs")
    elif median_long >= 180:
        reasons.append(f"median long {median_long:.0f}s ≥ 180s")
    return not reasons, "; ".join(reasons) or f"median long {median_long:.0f}s"


def print_table(rows: list[dict[str, Any]]) -> None:
    columns = [
        "model",
        "mode",
        "length",
        "ok",
        "first_try",
        "within_25pct",
        "cited",
        "invented",
        "expanded",
        "median_s",
        "p95_s",
        "median_tok_s",
        "tool_calls",
        "errors",
    ]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in columns}
    print("  ".join(c.ljust(widths[c]) for c in columns))
    for row in rows:
        print("  ".join(str(row[c]).ljust(widths[c]) for c in columns))


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", choices=sorted(DEFAULT_URLS), default="local")
    parser.add_argument("--base-url", default=None, help="default: LM Studio on this machine")
    parser.add_argument("--models", default=os.environ.get("LLM_MODEL", ""), help="comma-separated model ids")
    parser.add_argument("--modes", default="json_schema", help="json_schema,json_object,none")
    parser.add_argument("--lengths", default="short,medium,long")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--tool-runs", type=int, default=5, help="tool-calling attempts per model (0 to skip)")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high"],
        default=os.environ.get("LLM_REASONING_EFFORT") or None,
        help="sent as reasoning_effort; none turns a thinking model's reasoning off (default: LLM_REASONING_EFFORT)",
    )
    parser.add_argument("--out", type=Path, help="write every measurement as JSON here")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        parser.error("--models (or LLM_MODEL) is required: the ids `lms ls` or GET /v1/models show")
    base_url = (args.base_url or DEFAULT_URLS[args.provider]).rstrip("/")
    api_key = os.environ.get(KEY_ENV[args.provider]) if args.provider in KEY_ENV else None
    if args.provider in KEY_ENV and not api_key:
        parser.error(f"--provider {args.provider} needs {KEY_ENV[args.provider]} in the environment")

    def adapter(model: str, mode: str) -> OpenAICompatibleLLM:
        return OpenAICompatibleLLM(
            LLMConfig(
                provider=args.provider,
                base_url=base_url,
                model=model,
                api_key=api_key,
                structured=mode,
                timeout_s=args.timeout,
                max_output_tokens=args.max_output_tokens,
                reasoning_effort=args.reasoning_effort,
            )
        )

    results: list[Result] = []
    tool_rates: dict[str, float] = {}
    for model in models:
        probe = await adapter(model, "json_schema").probe()
        if not probe["reachable"]:
            print(
                f"✗ {base_url} is not reachable ({probe.get('error')}). Start the server: lms server start",
                file=sys.stderr,
            )
            return 2
        if not probe["model_listed"]:
            print(f"✗ {model!r} isn't offered at {base_url}. It lists: {probe.get('models')}", file=sys.stderr)
            return 2
        effort = f", reasoning_effort={args.reasoning_effort}" if args.reasoning_effort else ""
        print(f"== {model} at {base_url}{effort}", flush=True)
        for mode in args.modes.split(","):
            llm = adapter(model, mode)  # one adapter per mode, so a fallback is visible in mode_used
            for length in args.lengths.split(","):
                for run in range(1, args.runs + 1):
                    result = await write_once(llm, model, mode, length, run)
                    results.append(result)
                    status = "ok" if result.ok else f"✗ {result.error}"
                    print(
                        f"   {mode:<11} {length:<6} run {run}: {status:<24} {result.words:>5} words "
                        f"{result.seconds:>6.1f}s  tok/s {result.tokens_per_second or '-'}"
                        + (f"  invented: {', '.join(result.invented)}" if result.invented else ""),
                        flush=True,
                    )
        if args.tool_runs:
            llm = adapter(model, "json_schema")
            wins = [await tool_call_once(llm) for _ in range(args.tool_runs)]
            tool_rates[model] = sum(wins) / len(wins)
            print(f"   tool calling: {sum(wins)}/{len(wins)}", flush=True)

    rows = summarise(results, tool_rates)
    print()
    print_table(rows)
    print()
    for model in models:
        passed, why = verdict(model, results)
        print(f"{'PASS' if passed else 'FAIL'}  {model}: {why}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "provider": args.provider,
                    "base_url": base_url,
                    "reasoning_effort": args.reasoning_effort,
                    "summary": rows,
                    "runs": [asdict(r) for r in results],
                },
                indent=2,
            )
            + "\n"
        )
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
