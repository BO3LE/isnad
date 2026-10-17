# The Writer on a local model — 2026-10-17

The Writer on **Qwen3-30B-A3B** (`qwen/qwen3-30b-a3b`, MLX 4-bit, 17.19 GB) running in LM Studio
on the demo Mac (M4 Pro, 48 GB). Context 16,384, 2 parallel slots, `LLM_STRUCTURED=json_schema`.
This is the original hybrid-thinking Qwen3-30B-A3B, not the Instruct-2507 variant the plan names.
See **Method** below to reproduce.

## Compatibility — `adapters/tests/test_live_llm.py`

| Check | Result |
|---|---|
| The server lists the model | pass |
| A `json_schema` answer is valid JSON of that shape, streamed and whole | pass, pass |
| The model calls a tool and uses its result | pass |

## The Writer — `scripts/llm_bench.py`, 5 runs per length, json_schema

| | Before | After |
|---|---|---|
| Valid on the first try | 15/15 | 14/15 (one long answer cut off at 4,096 tokens; the second attempt was valid) |
| Valid in the end | 15/15 | 15/15 |
| States a figure the notes don't contain | not measured | **0/15** |
| Cites its sources | 13/15 | 15/15 |
| Within ±25% of the target length | 0/15 | 2/15 (7/15 in an earlier run of the same code) |
| Median long article | 21.2 s | 62.3 s (a fuller rewrite when the first draft is short) |
| Output speed | ≈ 48–50 tokens/s | ≈ 45–50 tokens/s |
| Tool calling | 5/5 | 5/5 |

"Before" is the Writer on `main`; "after" is this branch. Data: `data/llm-bench-qwen3-30b-a3b-before.json`,
`data/llm-bench-qwen3-30b-a3b-after.json` — measurements only, no prompt or article text.

## The notes fake search gives ("Canned finding 1 on …"), medium length, 5 runs

| | Before | After |
|---|---|---|
| Runs that state figures the notes don't contain | **5/5** (e.g. "2060", "50", "200"; live: "58.7 gigawatts … by 2030 [2]") | **0/5** (0/10 over two runs) |
| Line breaks in the stored article | **0** — escaped twice, so the Markdown rendered as one block | 18–30 |

## Through the platform (docker compose, `FAKE_ADAPTERS=false`, `SEARCH_PROVIDER=fake`, `EMAIL_TRANSPORT=smtp`)

| Template | Result |
|---|---|
| Blog post | succeeded, 12 s |
| Research → PDF → Email | parked for approval; approved; the message reached Mailpit only; 18 s |
| Blog → Video (YouTube step removed) | succeeded, 29 s; MP4 H.264 1280×720 + AAC, 105 s |
| Blog → Video → YouTube | refused before it starts: "Publisher needs a Google connection" — as designed |

## A second model: `qwen/qwen3.8-27b` — 2026-10-17

Dense 27B, GGUF Q6_K (22.43 GB, llama.cpp engine), same machine, context and Writer (the code above).
It **thinks before it answers by default**: 1,500 tokens of reasoning for a 120-word paragraph, and no
answer at all. `LLM_REASONING_EFFORT=none` (sent as `reasoning_effort`) turns that off in LM Studio;
`chat_template_kwargs`, `/no_think` and `reasoning.effort` don't. Every result below is with it off.

| `scripts/llm_bench.py`, 5 runs per length | qwen3-30b-a3b | qwen3.8-27b |
|---|---|---|
| Valid on the first try | 14/15 | **15/15** |
| Within ±25% of the target length | 2/15 (7/15 in an earlier run) | **13/15** (short 5/5, medium 4/5, long 4/5) |
| States a figure the notes don't contain | 0/15 | 0/15 |
| Cites its sources | 15/15 | 15/15 |
| Needed the fuller rewrite | 15/15 | 0/15 |
| Median short · medium · long | 13 s · 40 s · **62 s** | 57 s · 130 s · **225 s** (p95 323 s) |
| Output speed | ≈ 45–50 tokens/s | ≈ 8–10 tokens/s |
| Tool calling | 5/5 | 5/5 |
| Live compatibility (`test_live_llm.py`) | 4/4 | 4/4 |
| Notes from fake search, medium, 5 runs: invented figures | 0/5 | 0/5 (751–964 words against 800) |

The benchmark's verdict on qwen3.8-27b is **FAIL**, narrowly: 87% within length against the 90% bar,
and a median long article of 225 s against the 3-minute bar. It writes to length, where
qwen3-30b-a3b doesn't, at about a fifth of the speed. Its slowest long article took 323 s, more than
the default `LLM_TIMEOUT_S=300`. A worker on this model needs `LLM_TIMEOUT_S=600` as well as
`LLM_REASONING_EFFORT=none`. Data: `data/llm-bench-qwen3.8-27b.json`.

qwen3-30b-a3b also reasons by default in LM Studio when asked for plain text, but not visibly under
`json_schema`, which is how the Writer asks. With `LLM_REASONING_EFFORT=none` its Writer runs took
about the same time (2 short + 2 medium runs each way: 15–21 s and 39–45 s unset, 18 s and 31–40 s
off), and one short run came back as a valid 10-word article. Leave it unset for that model.

## Open

- **Which model.** qwen3-30b-a3b is fast and writes short; qwen3.8-27b writes to length but makes a
  long article a four-minute step. Neither passes every bar. Shorter targets, richer research notes or
  a third model (Qwen3-30B-A3B-Instruct-2507, not downloaded) are the other levers. A product decision.

## Method

```bash
lms load qwen/qwen3-30b-a3b --context-length 16384 --parallel 2
lms server start --port 1234 --bind 127.0.0.1
LIVE_LLM=1 LLM_MODEL=qwen/qwen3-30b-a3b python -m pytest adapters/tests/test_live_llm.py -v
python scripts/llm_bench.py --models qwen/qwen3-30b-a3b --out docs/metrics/data/llm-bench.json

# a thinking model
lms load qwen/qwen3.8-27b --context-length 16384 --parallel 2
LIVE_LLM=1 LLM_MODEL=qwen/qwen3.8-27b LLM_REASONING_EFFORT=none LLM_TIMEOUT_S=600 \
  python -m pytest adapters/tests/test_live_llm.py -v
python scripts/llm_bench.py --models qwen/qwen3.8-27b --reasoning-effort none
```
