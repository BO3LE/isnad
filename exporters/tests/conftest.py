"""Whether to_pdf can run here.

WeasyPrint needs Pango, a native library pip can't install. A laptop without it skips the
PDF tests and says why, the way the MP4 test skips without FFmpeg. CI sets REQUIRE_PDF=1:
there, a missing library is an error, so the PDF security tests can never be skipped
silently on the one machine that gates the merge.
"""

from __future__ import annotations

import os

import pytest


def _weasyprint_loads() -> str | None:
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return "WeasyPrint isn't installed"
    except OSError:  # cffi couldn't dlopen a native library
        return "the Pango library isn't installed"
    return None


PDF_UNAVAILABLE = _weasyprint_loads()

if PDF_UNAVAILABLE and os.environ.get("REQUIRE_PDF"):
    raise RuntimeError(f"REQUIRE_PDF is set but WeasyPrint can't load: {PDF_UNAVAILABLE}")

requires_pdf = pytest.mark.skipif(
    PDF_UNAVAILABLE is not None,
    reason=f"to_pdf can't run here: {PDF_UNAVAILABLE} (brew install pango, or apt-get install libpango-1.0-0)",
)
