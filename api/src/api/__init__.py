"""C2 · api — the front door.

Must not know: what an agent does, how a video is rendered, FFmpeg, any external content API.
Pushes a job carrying only `run_id`. `grep -r "from agents" api/` must return nothing.
"""

__version__ = "0.1.0"
