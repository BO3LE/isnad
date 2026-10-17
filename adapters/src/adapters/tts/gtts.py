from __future__ import annotations

import asyncio
import io

from contracts.errors import AgentError


class GTTS:
    """TTSPort backed by gTTS (returns MP3). Install with `gp-adapters[tts]`.

    gTTS sends one request per ~100 characters and, by default, waits forever for each. `timeout`
    is (connect, read) seconds per request; gTTS reports one that runs out as a gTTSError, so the
    step is retried — narration has no side effect.
    """

    def __init__(self, timeout: tuple[float, float] = (10.0, 30.0)):
        self._timeout = timeout

    async def speak(self, text: str, *, voice: str) -> bytes:
        return await asyncio.to_thread(self._speak, text, voice)

    def _speak(self, text: str, voice: str) -> bytes:
        from gtts import gTTS
        from gtts.tts import gTTSError

        lang, _, tld = voice.partition("-")
        tld = {"uk": "co.uk", "us": "com"}.get(tld, "com")
        buffer = io.BytesIO()
        try:
            gTTS(text=text, lang=lang or "en", tld=tld, timeout=self._timeout).write_to_fp(buffer)
        except gTTSError as exc:
            raise AgentError("Couldn't create the narration.", code="tts_error") from exc
        return buffer.getvalue()
