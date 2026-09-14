from __future__ import annotations


def to_pdf(markdown: str, *, title: str | None = None) -> bytes:
    """Render markdown to PDF bytes.

    TODO(W4, Zain): markdown → HTML (markdown lib) → PDF (WeasyPrint). Keep it pure and add golden-file tests.
    """
    raise NotImplementedError("PDF export lands in W4")


def to_docx(markdown: str, *, title: str | None = None) -> bytes:
    """Render markdown to DOCX bytes.

    TODO(W4, Zain): python-docx; headings, paragraphs, lists, links. Golden-file tests.
    """
    raise NotImplementedError("DOCX export lands in W4")
