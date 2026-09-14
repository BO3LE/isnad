from __future__ import annotations

import asyncio
import io

from contracts.errors import AgentError


class GTTS:
    """TTSPort backed by gTTS (returns MP3). Install with `gp-adapters[tts]`."""

    async def speak(self, text: str, *, voice: str) -> bytes:
        return await asyncio.to_thread(self._speak, text, voice)

    @staticmethod
    def _speak(text: str, voice: str) -> bytes:
        from gtts import gTTS
        from gtts.tts import gTTSError

        lang, _, tld = voice.partition("-")
        buffer = io.BytesIO()
        try:
            gTTS(text=text, lang=lang or "en", tld={"uk": "co.uk", "us": "com"}.get(tld, "com")).write_to_fp(buffer)
        except gTTSError as exc:
            raise AgentError("Couldn't create the narration.", code="tts_error") from exc
        return buffer.getvalue()
