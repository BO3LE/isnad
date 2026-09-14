import io
import shutil
import wave

import pytest

from exporters import assemble_mp4, to_docx, to_pdf


def _silent_wav(seconds: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000 * seconds)
    return buffer.getvalue()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_assemble_mp4_produces_a_playable_file():
    video = assemble_mp4(_silent_wav(2))
    assert video.data[4:8] == b"ftyp"
    assert 1.5 < video.duration_seconds < 3


@pytest.mark.parametrize("export", [to_pdf, to_docx])
def test_document_exporters_are_declared(export):
    with pytest.raises(NotImplementedError):
        export("# Title")
