"""GTTS hands gTTS a per-request timeout: by default gTTS waits forever for each request."""

from __future__ import annotations

from typing import ClassVar

import gtts
import pytest

from adapters.tts.gtts import GTTS
from contracts.errors import AgentError


class Recorder:
    made: ClassVar[list[dict]] = []

    def __init__(self, **kwargs):
        Recorder.made.append(kwargs)

    def write_to_fp(self, fp):
        fp.write(b"ID3-mp3")


async def test_each_request_has_a_timeout_and_the_accent_maps_to_googles_domain(monkeypatch):
    Recorder.made = []
    monkeypatch.setattr(gtts, "gTTS", Recorder)

    audio = await GTTS(timeout=(5, 20)).speak("Hello there.", voice="en-uk")

    assert audio == b"ID3-mp3"
    assert Recorder.made == [{"text": "Hello there.", "lang": "en", "tld": "co.uk", "timeout": (5, 20)}]


async def test_a_request_that_runs_out_is_a_retryable_narration_error(monkeypatch):
    from gtts.tts import gTTSError

    class TimesOut(Recorder):
        def write_to_fp(self, fp):
            raise gTTSError("Failed to connect. Probable cause: timeout")  # how gTTS reports it

    monkeypatch.setattr(gtts, "gTTS", TimesOut)

    with pytest.raises(AgentError) as caught:
        await GTTS().speak("Hello.", voice="en-us")
    assert (caught.value.code, caught.value.retryable) == ("tts_error", True)
