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

## Open

- **Length.** On notes this thin (8 one-line notes), the model writes shorter than asked rather than
  pad or invent, and varies widely run to run. Choosing between shorter targets, richer research
  notes (more sources, longer extracts) or another model is a product decision.
- `qwen/qwen3.8-27b` (downloaded) and Qwen3-30B-A3B-Instruct-2507 (not downloaded) are not
  benchmarked yet.

## Method

```bash
lms load qwen/qwen3-30b-a3b --context-length 16384 --parallel 2
lms server start --port 1234 --bind 127.0.0.1
LIVE_LLM=1 LLM_MODEL=qwen/qwen3-30b-a3b python -m pytest adapters/tests/test_live_llm.py -v
python scripts/llm_bench.py --models qwen/qwen3-30b-a3b --out docs/metrics/data/llm-bench.json
```
