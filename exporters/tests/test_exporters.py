"""Golden-file tests for C6 exporters — see docs/GP-plan.md 'C6 · exporters'.

`to_docx` is genuinely a pure function (see `_normalize_zip_timestamps` in
documents.py) so its golden fixture is compared byte-for-byte. `to_pdf` is not:
WeasyPrint's font subsetting is not byte-stable across separate process runs — this
was verified empirically (identical bytes with ASLR disabled via `setarch -R`,
different otherwise, even with `PYTHONHASHSEED` fixed) — so its golden fixture instead
pins the *extracted text*, which is what a golden PDF test can actually promise.
"""

from __future__ import annotations

import io
import shutil
import time
import wave
from pathlib import Path

import pytest
from pypdf import PdfReader

from exporters import MissingDependencyError, assemble_mp4, to_docx, to_pdf

GOLDEN_DIR = Path(__file__).parent / "golden"
SAMPLE_MARKDOWN = (GOLDEN_DIR / "sample.md").read_text()
SAMPLE_TITLE = "Quarterly Update"


def _silent_wav(seconds: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000 * seconds)
    return buffer.getvalue()


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_assemble_mp4_produces_a_playable_file():
    video = assemble_mp4(_silent_wav(2))
    assert video.data[4:8] == b"ftyp"
    assert 1.5 < video.duration_seconds < 3


class TestToPdf:
    def test_matches_golden_extracted_text(self):
        pdf_bytes = to_pdf(SAMPLE_MARKDOWN, title=SAMPLE_TITLE)
        assert pdf_bytes.startswith(b"%PDF-")
        golden_text = (GOLDEN_DIR / "sample.pdf.txt").read_text()
        assert _pdf_text(pdf_bytes) == golden_text

    def test_same_input_same_content_every_time(self):
        # Raw bytes can legitimately differ between calls (see module docstring);
        # rendered content must not.
        first = to_pdf(SAMPLE_MARKDOWN, title=SAMPLE_TITLE)
        second = to_pdf(SAMPLE_MARKDOWN, title=SAMPLE_TITLE)
        assert _pdf_text(first) == _pdf_text(second)

    def test_rejects_non_str_input(self):
        with pytest.raises(TypeError):
            to_pdf(None)  # type: ignore[arg-type]

    def test_rejects_empty_input(self):
        with pytest.raises(ValueError):
            to_pdf("   \n\t  ")

    def test_missing_weasyprint_raises_clear_error(self, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "weasyprint", None)
        with pytest.raises(MissingDependencyError):
            to_pdf("# Title")


class TestToDocx:
    def test_matches_golden_bytes_exactly(self):
        docx_bytes = to_docx(SAMPLE_MARKDOWN, title=SAMPLE_TITLE)
        golden_bytes = (GOLDEN_DIR / "sample.docx").read_bytes()
        assert docx_bytes == golden_bytes

    def test_same_input_same_bytes_across_time(self):
        # This is the case _normalize_zip_timestamps exists for: without it, the two
        # calls below produce different bytes purely because a second passed between them.
        first = to_docx(SAMPLE_MARKDOWN)
        time.sleep(1.1)
        second = to_docx(SAMPLE_MARKDOWN)
        assert first == second

    def test_rejects_non_str_input(self):
        with pytest.raises(TypeError):
            to_docx(123)  # type: ignore[arg-type]

    def test_rejects_empty_input(self):
        with pytest.raises(ValueError):
            to_docx("")

    def test_missing_python_docx_raises_clear_error(self, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "docx", None)
        with pytest.raises(MissingDependencyError):
            to_docx("# Title")
