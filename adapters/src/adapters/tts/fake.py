from __future__ import annotations

import io
import wave


class FakeTTS:
    """Returns a valid silent WAV — about one second per 15 words — so FFmpeg can still assemble a video."""

    async def speak(self, text: str, *, voice: str) -> bytes:
        seconds = max(1, min(30, len(text.split()) // 15))
        rate = 16000
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(b"\x00\x00" * rate * seconds)
        return buffer.getvalue()
