"""Measure what the Video agent costs to run: wall time, render seconds per minute of video, CPU and memory.

Runs the real VideoAgent (and through it exporters.video.assemble_mp4 / FFmpeg) with fake adapters, for a
matrix of narration lengths and resolutions, and prints a Markdown table plus JSON.

FakeTTS caps its silent narration at 30 s, so this script swaps in a TTS that returns exactly the requested
duration (a quiet tone, so the AAC encoder has real signal to encode). Everything else is the fake adapter set.

Needs ffmpeg/ffprobe on PATH and psutil (a dev dependency). The numbers that matter are the ones taken
inside the worker image — use `make measure-video` rather than running this on a laptop without FFmpeg.

    python scripts/measure_video_worker.py                           # 30 s, 60 s, 180 s × 720p, 1080p
    python scripts/measure_video_worker.py --durations 60 --resolutions 1080p --repeat 3
    python scripts/measure_video_worker.py --parallel 2              # two renders at once (worker concurrency=2)
    python scripts/measure_video_worker.py --json out.json
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import io
import json
import math
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import wave
from array import array
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - guidance only
    sys.exit("psutil is required: pip install -c constraints.txt psutil")

from adapters.factory import AdapterSettings, build_ports
from agents.video.agent import VideoAgent

WORDS_PER_MINUTE = 150  # typical narration pace; only sizes the script text, the TTS below fixes the duration


class FixedDurationTTS:
    """A stand-in TTS that returns `seconds` of 24 kHz mono audio (gTTS-like rate) regardless of text length."""

    def __init__(self, seconds: float, audio: str = "tone") -> None:
        # Built up front so generating the audio is not counted as render cost.
        rate = 24000
        frames = int(rate * seconds)
        if audio == "silence":
            pcm = array("h", bytes(2 * frames))
        else:  # a 220 Hz tone, amplitude-modulated at 3 Hz — roughly speech-like loudness changes
            pcm = array(
                "h",
                (
                    int(6000 * (0.6 + 0.4 * math.sin(6 * math.pi * i / rate)) * math.sin(440 * math.pi * i / rate))
                    for i in range(frames)
                ),
            )
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(pcm.tobytes())
        self.data = buffer.getvalue()

    async def speak(self, text: str, *, voice: str) -> bytes:
        return self.data


class Sampler(threading.Thread):
    """Polls this process and all its descendants (FFmpeg) for summed RSS and CPU%."""

    def __init__(self, interval: float = 0.1) -> None:
        super().__init__(daemon=True)
        self.interval, self.stop_event = interval, threading.Event()
        self.root = psutil.Process(os.getpid())
        self.peak_rss = self.peak_child_rss = 0
        self.peak_cpu = 0.0
        self.cpu_samples: list[float] = []
        self._last: dict[int, tuple[float, float]] = {}

    def _tick(self) -> None:
        procs = [self.root]
        try:
            procs += self.root.children(recursive=True)
        except psutil.Error:
            pass
        now, rss, child_rss, cpu_delta, window = time.perf_counter(), 0, 0, 0.0, None
        for p in procs:
            try:
                mem = p.memory_info().rss
                t = p.cpu_times()
            except psutil.Error:
                continue
            rss += mem
            if p.pid != self.root.pid:
                child_rss += mem
            total = t.user + t.system
            if p.pid in self._last:
                last_total, last_now = self._last[p.pid]
                cpu_delta += total - last_total
                window = now - last_now
            self._last[p.pid] = (total, now)
        self.peak_rss, self.peak_child_rss = max(self.peak_rss, rss), max(self.peak_child_rss, child_rss)
        if window:
            pct = 100 * cpu_delta / window
            self.cpu_samples.append(pct)
            self.peak_cpu = max(self.peak_cpu, pct)

    def run(self) -> None:
        while not self.stop_event.is_set():
            self._tick()
            time.sleep(self.interval)

    def stop(self) -> None:
        self.stop_event.set()
        self.join()


def _cpu_seconds() -> float:
    """CPU seconds used by this process plus every reaped child (FFmpeg, ffprobe) — exact, not sampled."""
    t = os.times()
    return t.user + t.system + t.children_user + t.children_system


def _file_size(root: str, relative: str) -> int:
    return Path(root, relative).stat().st_size


def _script_for(seconds: float) -> str:
    words = max(1, int(seconds / 60 * WORDS_PER_MINUTE))
    body = " ".join(
        "Saudi Arabia receives strong sunlight all year and solar power keeps getting cheaper".split()[i % 13]
        for i in range(words)
    )
    return f"# Measurement script\n\n{body}."


async def measure_once(seconds: float, resolution: str, parallel: int, audio: str) -> dict:
    with tempfile.TemporaryDirectory() as root:
        ports = build_ports(AdapterSettings(fake=True, storage_root=root))
        ports = dataclasses.replace(ports, tts=FixedDurationTTS(seconds, audio))
        agent = VideoAgent()
        data = agent.input_model.model_validate({"script": _script_for(seconds), "resolution": resolution})
        # Timed region = agent.execute: markdown flattening, (pre-built) TTS audio, FFmpeg + ffprobe, storage write.
        cpu0, sampler = _cpu_seconds(), Sampler()
        sampler.start()
        start = time.perf_counter()
        outs = await asyncio.gather(*(agent.execute(data, ports) for _ in range(parallel)))
        wall = time.perf_counter() - start
        sampler.stop()
        cpu = _cpu_seconds() - cpu0
        sizes = [_file_size(root, o.video_path) for o in outs]
    video_seconds = outs[0].duration_seconds
    return {
        "target_seconds": seconds,
        "resolution": resolution,
        "parallel": parallel,
        "video_seconds": video_seconds,
        "wall_seconds": wall,
        "render_s_per_video_min": wall / (video_seconds / 60),
        "realtime_factor": video_seconds / wall,
        "cpu_seconds": cpu,
        "avg_cpu_pct": 100 * cpu / wall,
        "peak_cpu_pct": sampler.peak_cpu,
        "peak_rss_mib": sampler.peak_rss / 2**20,
        "peak_ffmpeg_rss_mib": sampler.peak_child_rss / 2**20,
        "output_mib": statistics.mean(sizes) / 2**20,
    }


def machine() -> dict:
    ffmpeg = shutil.which("ffmpeg")
    version = (
        subprocess.run([ffmpeg, "-version"], capture_output=True, text=True).stdout.splitlines()[0] if ffmpeg else None
    )
    cpu_model = platform.processor()
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    cgroup_cpu = cgroup_mem = None
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        cgroup_cpu = None if quota == "max" else int(quota) / int(period)
        mem = Path("/sys/fs/cgroup/memory.max").read_text().strip()
        cgroup_mem = None if mem == "max" else int(mem) / 2**30
    except (OSError, ValueError):
        pass
    return {
        "cpu_model": cpu_model,
        "logical_cpus": psutil.cpu_count(),
        "ram_gib": round(psutil.virtual_memory().total / 2**30, 1),
        "cgroup_cpu_limit": cgroup_cpu,
        "cgroup_mem_limit_gib": cgroup_mem,
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "ffmpeg": version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--durations", type=float, nargs="+", default=[30, 60, 180], help="narration seconds")
    parser.add_argument("--resolutions", nargs="+", default=["720p", "1080p"], choices=["720p", "1080p"])
    parser.add_argument("--repeat", type=int, default=3, help="runs per case; the median is reported")
    parser.add_argument("--parallel", type=int, default=1, help="renders started at once (worker concurrency)")
    parser.add_argument("--audio", choices=["tone", "silence"], default="tone")
    parser.add_argument("--json", type=Path, help="also write raw results here")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not on PATH — run inside the worker image: make measure-video")

    info = machine()
    print("machine:", json.dumps(info), file=sys.stderr)
    asyncio.run(measure_once(5, "720p", 1, args.audio))  # warm-up: imports, disk cache, FFmpeg libs

    rows = []
    for seconds in args.durations:
        for resolution in args.resolutions:
            runs = [
                asyncio.run(measure_once(seconds, resolution, args.parallel, args.audio)) for _ in range(args.repeat)
            ]
            row = {
                k: (statistics.median(r[k] for r in runs) if isinstance(runs[0][k], float) else runs[0][k])
                for k in runs[0]
            }
            row["runs"] = len(runs)
            rows.append(row)
            print(f"  {seconds:>5.0f}s {resolution:>5}  wall {row['wall_seconds']:.2f}s", file=sys.stderr)

    print(
        "| Narration | Res. | Parallel | Wall (s) | Render s / video min | × real time | Avg CPU % | Peak CPU % "
        "| Peak RSS (MiB) | of which FFmpeg | Output (MiB) |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['video_seconds']:.0f} s | {r['resolution']} | {r['parallel']} | {r['wall_seconds']:.2f} "
            f"| {r['render_s_per_video_min']:.2f} | {r['realtime_factor']:.0f}× | {r['avg_cpu_pct']:.0f} "
            f"| {r['peak_cpu_pct']:.0f} | {r['peak_rss_mib']:.0f} | {r['peak_ffmpeg_rss_mib']:.0f} | {r['output_mib']:.2f} |"
        )
    if args.json:
        args.json.write_text(
            json.dumps({"machine": info, "args": vars(args) | {"json": str(args.json)}, "results": rows}, indent=2)
        )


if __name__ == "__main__":
    main()
