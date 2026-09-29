# Video worker cost — CPU, memory, render time

GP-plan W5 · C7 · feeds **PART 6 — Results & Metrics** and the §5.5 worker sizing ("2 vCPU / 4 GB is the
practical floor, and the W5 sizing test will give a real number").

Measured 2026-09-27 on the W1 video pipeline: narration over a plain ink background, H.264 + AAC, one
FFmpeg process per video (`exporters/src/exporters/video.py`). **Slides (W5) are not in this pipeline yet** —
rerun after they land, because drawing real frames will cost more than a solid colour.

## Results

"Render s / video min" = wall-clock seconds the Video agent took ÷ minutes of video produced. Lower is better;
60 would mean real time. "× real time" is the inverse. Memory is peak RSS of the Python process plus its
FFmpeg child, sampled every 100 ms. Every row is the median of 3 runs.

### A. Production limits — `--cpus 2 --memory 4g`, one render at a time

This is the number to quote: it is what one Celery slot gets inside the prod worker container.

| Video length | Res. | Wall (s) | Render s / video min | × real time | Avg CPU % | Peak RSS (MiB) | of which FFmpeg | Output (MiB) |
|---|---|---|---|---|---|---|---|---|
| 33 s | 720p | 2.26 | 4.15 | 14× | 198 | 494 | 451 | 0.29 |
| 62 s | 720p | 4.95 | 4.75 | 13× | 199 | 499 | 452 | 0.57 |
| 182 s | 720p | 13.05 | 4.31 | 14× | 199 | 519 | 453 | 1.71 |
| 33 s | 1080p | 6.28 | 11.59 | 5× | 199 | 1128 | 1085 | 0.31 |
| 63 s | 1080p | 11.23 | 10.65 | 6× | 199 | 1134 | 1086 | 0.62 |
| 183 s | 1080p | 29.05 | 9.53 | 6× | 200 | 1152 | 1087 | 1.85 |

### B. Production limits, two renders at once (`--parallel 2`, matches `celery --concurrency=2`)

Per-video numbers; the container is rendering two of these simultaneously. "Throughput" divides the wall
time by both videos.

| Video length | Res. | Wall (s) | Render s / video min (each) | Throughput s / video min | Avg CPU % | Peak RSS, both (MiB) | Output (MiB) |
|---|---|---|---|---|---|---|---|
| 32 s | 720p | 5.91 | 11.03 | 5.5 | 200 | 943 | 0.29 |
| 63 s | 720p | 12.86 | 12.37 | 6.1 | 200 | 952 | 0.57 |
| 183 s | 720p | 37.76 | 12.38 | 6.2 | 200 | 970 | 1.71 |
| 33 s | 1080p | 14.91 | 27.13 | 13.6 | 200 | 2213 | 0.31 |
| 63 s | 1080p | 27.47 | 26.44 | 13.1 | 200 | 2220 | 0.62 |
| 183 s | 1080p | 86.41 | 28.29 | 14.2 | 200 | 2239 | 1.85 |

Cross-check from the host with `docker stats` during the 1080p runs of B: **197–204 % CPU, 2.08–2.11 GiB**
container memory out of the 4 GiB limit — consistent with the in-container sampler (2.2 GiB summed RSS).

### C. No limits — all 20 host threads visible, one render at a time

Upper bound: what the same code does when FFmpeg can spread out.

| Video length | Res. | Wall (s) | Render s / video min | × real time | Avg CPU % | Peak CPU % | Peak RSS (MiB) | Output (MiB) |
|---|---|---|---|---|---|---|---|---|
| 33 s | 720p | 0.75 | 1.37 | 44× | 475 | 576 | 494 | 0.29 |
| 62 s | 720p | 1.34 | 1.29 | 46× | 509 | 567 | 499 | 0.57 |
| 182 s | 720p | 3.94 | 1.29 | 46× | 537 | 578 | 518 | 1.71 |
| 33 s | 1080p | 1.30 | 2.38 | 25× | 639 | 766 | 1128 | 0.31 |
| 63 s | 1080p | 2.60 | 2.48 | 24× | 655 | 754 | 1134 | 0.62 |
| 183 s | 1080p | 6.79 | 2.23 | 27× | 683 | 755 | 1152 | 1.85 |

### D. Side experiment — FFmpeg thread count under a 2-CPU limit

A 63 s render run directly with the exporter's FFmpeg command, `--cpus 2 --memory 4g`, one run each
(scratch script, not part of `measure_video_worker.py`):

| `-threads` | 720p wall | 720p max RSS | 1080p wall | 1080p max RSS |
|---|---|---|---|---|
| auto (today) | 5.79 s | 450 MiB | 13.20 s | 1084 MiB |
| 2 | 2.54 s | 247 MiB | 5.53 s | 454 MiB |
| 4 | 3.02 s | 267 MiB | 5.95 s | 498 MiB |

## What the numbers say

1. **Render time grows linearly with video length.** Seconds-per-minute is flat across 30 s → 3 min, so a
   10-minute 1080p video costs ≈ 10 × 10 s ≈ 100 s of one 2-CPU slot today.
2. **1080p costs ~2.3× the CPU time and ~2.2× the memory of 720p.**
3. **Memory is set by resolution and thread count, not by length** — ~450 MiB (720p) / ~1.1 GiB (1080p) per
   FFmpeg, whether the video is 30 s or 3 min. The Python side is ~45 MiB.
4. **FFmpeg over-threads inside a CPU-limited container.** A `--cpus 2` cgroup still shows all 20 host CPUs, so
   libx264 starts ~30 threads. That makes it 2.3× slower and 2.4× hungrier than `-threads 2` (table D), and it
   is why two parallel renders (table B) give *worse* throughput than one at a time (table A).
5. **Output is small**: ~0.6 MiB per minute of video with the solid background (this will rise with slides).
6. The rendered video runs **~2–3 s longer than the narration** (e.g. 30 s audio → 32.9 s MP4): `-shortest`
   with a lavfi colour source overshoots. Harmless for now; worth a look when slides are timed to narration.

## Recommendation for worker sizing

- **Keep `cpus: "2"`, `memory: 4g`** on the prod worker (`docker-compose.prod.yml`). Measured peak with two
  1080p renders at once is 2.2 GiB, so 4 GiB leaves ~45 % headroom for slides, image downloads and the other
  agents sharing the container. Going below 3 GiB is not safe at concurrency 2 with today's thread behaviour.
- **Keep `--concurrency=2`**, since most runs are not video and the other agents are I/O-bound (LLM, search,
  e-mail). Two simultaneous 1080p videos still finish at ~14 s per video-minute in total.
- **Proposed code change (not applied — exporter owner's call):** pass `-threads <cpus available>` to FFmpeg
  in `exporters/src/exporters/video.py`, e.g. from an `FFMPEG_THREADS` setting defaulting to the cgroup CPU
  quota. Table D suggests that roughly halves both render time and memory in the prod container; after it, a
  3 GiB limit would be comfortable. Re-measure before lowering the limit.
- **Proposed compose change (not applied):** once the thread cap is in, the prod worker could become
  ```yaml
  deploy:
    resources:
      limits: { cpus: "2", memory: 3g }   # measured: 2 × 1080p renders ≈ 1 GiB with -threads 2 (docs/metrics/video-worker.md)
      reservations: { memory: 1g }
  ```

## Method

`scripts/measure_video_worker.py` runs the real `VideoAgent.execute` with the fake adapter set
(`build_ports(AdapterSettings(fake=True))`), so the path is: markdown → narration text → TTS audio → FFmpeg
(`assemble_mp4`) → ffprobe → local storage write. Only the TTS is swapped:

- `FakeTTS` caps its silent WAV at 30 s, which cannot produce 1- or 3-minute videos. The script uses a
  `FixedDurationTTS` that returns exactly the target length of 24 kHz mono audio (gTTS's rate) — a 220 Hz tone
  with 3 Hz amplitude modulation, so AAC encodes real signal rather than silence (`--audio silence` to compare).
  The audio is generated before the timer starts; in production TTS is a remote call, not worker CPU.
- **Wall time**: `time.perf_counter()` around `agent.execute`.
- **CPU**: exact user+system seconds of the process and its reaped children (`os.times()`), ÷ wall time =
  average CPU %. Peak CPU % comes from a 100 ms sampler over the process tree (psutil).
- **Memory**: the same sampler sums RSS over the Python process and every descendant (FFmpeg, ffprobe).
- One 5 s warm-up render first, then 3 runs per case; the median is reported.
- The recorded runs mounted this checkout's `agents/`, `adapters/`, `exporters/`, `contracts/`, `scripts/` over
  the worker image, so the measured code is the code in this commit. `make measure-video` instead builds the
  worker image from the checkout and mounts only `scripts/` — same result, no stale code.

Raw results (every field, including machine info): `docs/metrics/data/video-worker-*.json`.

## Machine

| | |
|---|---|
| Host | Windows 11 Pro, Intel Core i5-14600KF (14 cores / 20 threads), 15.8 GiB RAM |
| Where it ran | Worker Docker image (`worker/Dockerfile`, dev target) under Docker Desktop 29.7.2 / WSL2 — Linux 6.18.33.2-microsoft-standard-WSL2, 20 CPUs and 7.6 GiB visible to containers |
| Python | 3.11.16 |
| FFmpeg | 7.1.5-0+deb13u1 (Debian package in the worker image), libx264 |

FFmpeg is not installed on the Windows host, so nothing was measured outside the container. That is the right
place anyway: the numbers describe the worker image that production runs. A desktop CPU is faster per core than
a typical cloud vCPU — expect a cloud 2-vCPU VM to be slower than table A, so re-run on the chosen host (W11).

Not measured: a full end-to-end template run through the API → Celery → Video agent with `docker stats`
(the direct agent run above exercises the same code in the same image, without queue and DB overhead);
real TTS audio (needs network/keys); slides (not built yet).

## How to rerun

```bash
make measure-video                                  # prod limits (2 CPU, 4 GiB), 30 s / 60 s / 180 s × 720p / 1080p
make measure-video args="--parallel 2"              # two renders at once, like celery --concurrency=2
make measure-video CPUS=20 MEM=8g                   # without the prod limits
make measure-video args="--durations 600 --resolutions 1080p --repeat 1"  # one 10-minute 1080p video
```

Without `make` (e.g. Windows PowerShell), from the repo root:

```powershell
docker build -q -f worker/Dockerfile --target dev -t isnad-worker-measure .
docker run --rm --cpus 2 --memory 4g -v "${PWD}\scripts:/app/scripts:ro" --entrypoint bash isnad-worker-measure `
  -c "pip install -q -c constraints.txt psutil && python scripts/measure_video_worker.py"
```

On a machine with FFmpeg and the dev tools installed (`psutil` is in `requirements-dev.txt`):
`python scripts/measure_video_worker.py --help`.
