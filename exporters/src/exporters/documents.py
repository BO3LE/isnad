"""markdown → PDF, markdown → DOCX.

Pure functions: same input, same output, nothing read or written outside the return
value. Optional dependencies (WeasyPrint, ``markdown``, nh3, python-docx) are imported
lazily inside each function so importing this module never requires them, and a
missing one raises `MissingDependencyError` instead of a bare `ImportError` from deep
inside a third-party package.

The markdown is untrusted. An article is written by a model from web search results,
so an image, a stylesheet or a link in it may have been put there by a stranger.
WeasyPrint will happily fetch any URL it meets — over the network, or from `file://` —
and copies anything marked `rel="attachment"` into the PDF. So `to_pdf` keeps three
locks, any one of which would stop that on its own: the HTML is reduced to an allowlist
of plain document tags before rendering, nothing is resolved against a base URL, and the
renderer's fetcher refuses everything except inline raster images.
"""

from __future__ import annotations

import html as _html
import re
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docx.text.paragraph import Paragraph

# Inline markup for to_docx, tried left to right. Emphasis follows CommonMark's flanking
# rule closely enough for articles: a delimiter must touch the text it wraps, so `2 * 3`
# stays arithmetic, and an underscore inside a word (`get_user_name`) is not emphasis.
_INLINE_PATTERN = re.compile(
    r"(\\[\\`*_\[\]()#+\-.!]"  # a backslash escape: the character, literally
    r"|`[^`]+`"  # code span
    r"|\[[^\]]+\]\((?:[^()\s]|\([^()\s]*\))+\)"  # [text](url), one level of (parens) in the url
    r"|\*\*(?=\S).+?(?<=\S)\*\*"  # **bold**
    r"|(?<![\w*])\*(?=[^\s*]).*?(?<=[^\s*])\*(?![\w*])"  # *italic*
    r"|(?<!\w)_(?=[^\s_]).*?(?<=[^\s_])_(?!\w))"  # _italic_, never inside a word
)
_LINK_RE = re.compile(r"^\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*+]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\d+\.\s+(.*)$")
_FENCE_RE = re.compile(r"^```")
_MARKUP_RE = re.compile(r"[*_`]")
_SAFE_LINK_RE = re.compile(r"^(https?|mailto):", re.IGNORECASE)
_HYPERLINK_COLOR = "0563C1"

_PDF_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; color: #1a1a1a; line-height: 1.5; margin: 2.5cm; }
h1, h2, h3, h4, h5, h6 { font-family: Helvetica, Arial, sans-serif; color: #111111; }
code, pre { font-family: 'DejaVu Sans Mono', monospace; background: #f4f4f4; }
pre { padding: 0.75em; border-radius: 4px; white-space: pre-wrap; }
"""

# Not "extra": it brings attr_list, which lets plain markdown write `{: rel="attachment"}`,
# and md_in_html. Raw HTML still passes through markdown itself, which is what the
# allowlist below is for.
_PDF_MARKDOWN_EXTENSIONS = ["tables", "fenced_code", "footnotes", "def_list", "abbr", "sane_lists"]

# Plain document structure only. No <link>, <style>, <base>, <svg>, <iframe>, <object> or
# <embed>, and no `rel`, `style` or `srcset` attribute — every way of pointing WeasyPrint at
# a resource or an attachment goes with them.
_PDF_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "dd", "del", "div", "dl", "dt", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "s",
    "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
}  # fmt: skip
_PDF_DROPPED_WITH_CONTENT = {"script", "style", "svg", "math", "template", "noscript", "iframe", "object", "title"}
_PDF_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "abbr": {"title"},
    "ol": {"start"},
    "td": {"align"},
    "th": {"align"},
    # Footnote markers link to their notes and back by id.
    "sup": {"id"},
    "li": {"id"},
}
_PDF_URL_SCHEMES = {"http", "https", "mailto", "data"}
# SVG is excluded on purpose: an SVG can reference further resources of its own.
_INLINE_IMAGE_RE = re.compile(r"^data:image/(png|jpeg|gif|webp)[;,]", re.IGNORECASE)

# zip entries store a modified-time on every part. python-docx's writer stamps that with
# the wall clock (see `_normalize_zip_timestamps`), which would otherwise make `to_docx`
# return different bytes for the same input depending on when it happens to run.
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class MissingDependencyError(RuntimeError):
    """An optional rendering dependency isn't installed.

    Raised instead of letting a bare `ImportError` surface from inside WeasyPrint or
    python-docx, so callers get a message that says which extra to install.
    """


def to_pdf(markdown: str, *, title: str | None = None) -> bytes:
    """Render markdown to PDF bytes: `markdown` (the package) → sanitised HTML → WeasyPrint.

    Nothing outside the document is fetched: inline `data:` PNG, JPEG, GIF and WebP images
    render, and every other image, stylesheet, font or attachment is dropped.

    Raises:
        TypeError: `markdown` is not a `str`.
        ValueError: `markdown` is empty, or WeasyPrint failed to lay it out.
        MissingDependencyError: the `pdf` extra (`markdown`, `nh3`, `weasyprint`) or
            WeasyPrint's native libraries aren't installed.
    """
    _require_text(markdown)

    try:
        import markdown as markdown_lib
        import nh3
    except ImportError as exc:
        raise MissingDependencyError("to_pdf needs 'markdown' and 'nh3'; install gp-exporters[pdf]") from exc
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        # Without Pango, cffi's dlopen raises OSError at import time — not ImportError.
        raise MissingDependencyError(
            "to_pdf needs WeasyPrint and its native libraries (Pango); "
            "install gp-exporters[pdf] and libpango-1.0-0 libpangoft2-1.0-0"
        ) from exc

    body_html = nh3.clean(
        markdown_lib.markdown(markdown, extensions=_PDF_MARKDOWN_EXTENSIONS),
        tags=_PDF_TAGS,
        clean_content_tags=_PDF_DROPPED_WITH_CONTENT,
        attributes=_PDF_ATTRIBUTES,
        url_schemes=_PDF_URL_SCHEMES,
        link_rel=None,
    )
    title_tag = f"<title>{_html.escape(title)}</title>" if title else ""
    document_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"{title_tag}<style>{_PDF_CSS}</style></head><body>{body_html}</body></html>"
    )

    try:
        pdf_bytes = HTML(string=document_html, base_url=None, url_fetcher=_inline_images_only()).write_pdf()
    except Exception as exc:  # WeasyPrint's own errors vary by failure; wrap them uniformly
        raise ValueError(f"markdown could not be rendered to PDF: {exc}") from exc
    if not pdf_bytes:
        raise ValueError("WeasyPrint returned no PDF bytes")
    return pdf_bytes


def _inline_images_only():
    """A WeasyPrint fetcher that serves inline raster images and refuses everything else.

    A refusal is an ordinary exception, which WeasyPrint catches and logs: the resource is
    left out and the rest of the document still renders. Only `data:` is reachable at all,
    redirects are off, and the MIME type must be a raster image.
    """
    from weasyprint.urls import URLFetcher

    class InlineImagesOnly(URLFetcher):
        def __init__(self) -> None:
            super().__init__(allowed_protocols={"data"}, allow_redirects=False, timeout=5)

        def fetch(self, url, headers=None):
            if not _INLINE_IMAGE_RE.match(url):
                raise ValueError("only inline PNG, JPEG, GIF and WebP images are rendered")
            return super().fetch(url, headers)

    return InlineImagesOnly()


def to_docx(markdown: str, *, title: str | None = None) -> bytes:
    """Render markdown to DOCX bytes with python-docx.

    Handles headings (`#` … `######`), bold (`**text**`), italic (`*text*` / `_text_`),
    inline code (`` `code` ``), links (`[text](https://…)`), backslash escapes, bullet and
    numbered lists, and fenced code blocks (```` ``` ````). Anything else is emitted as a
    plain paragraph. Only http, https and mailto links become hyperlinks; any other link
    keeps its text and loses its target.

    `title` sets the document's title property and is shown as a title heading — unless the
    markdown already opens with the same `# heading`, which would print it twice.

    Raises:
        TypeError: `markdown` is not a `str`.
        ValueError: `markdown` is empty.
        MissingDependencyError: the `docx` extra (python-docx) isn't installed.
    """
    _require_text(markdown)

    try:
        import docx
        from docx.shared import Inches
    except ImportError as exc:
        raise MissingDependencyError("to_docx needs python-docx; install gp-exporters[docx]") from exc

    document = docx.Document()
    if title:
        document.core_properties.title = title
        if not _opens_with_heading(markdown, title):
            document.add_heading(title, level=0)

    code_lines: list[str] = []
    in_code_block = False

    def flush_code_block() -> None:
        if not code_lines:
            return
        code_paragraph = document.add_paragraph()
        code_paragraph.paragraph_format.left_indent = Inches(0.3)
        code_run = code_paragraph.add_run("\n".join(code_lines))
        code_run.font.name = "Consolas"
        code_lines.clear()

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if _FENCE_RE.match(line):
            if in_code_block:
                flush_code_block()
            in_code_block = not in_code_block
            continue
        if in_code_block:
            code_lines.append(raw_line)
            continue
        if not line.strip():
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            _add_inline_runs(document.add_heading(level=level), heading_match.group(2).strip())
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            _add_inline_runs(document.add_paragraph(style="List Bullet"), bullet_match.group(1))
            continue

        numbered_match = _NUMBERED_RE.match(line)
        if numbered_match:
            _add_inline_runs(document.add_paragraph(style="List Number"), numbered_match.group(1))
            continue

        _add_inline_runs(document.add_paragraph(), line)

    # An unterminated ``` fence still renders whatever it captured, rather than
    # silently dropping it — malformed input degrades gracefully.
    if in_code_block:
        flush_code_block()

    buffer = BytesIO()
    document.save(buffer)
    return _normalize_zip_timestamps(buffer.getvalue())


def _require_text(markdown: str) -> None:
    if not isinstance(markdown, str):
        raise TypeError(f"markdown must be a str, got {type(markdown).__name__}")
    if not markdown.strip():
        raise ValueError("markdown must not be empty")


def _opens_with_heading(markdown: str, title: str) -> bool:
    """Whether the first non-blank line is `# <title>` (ignoring inline markup and case)."""
    first = next((line.strip() for line in markdown.splitlines() if line.strip()), "")
    match = _HEADING_RE.match(first)
    if not match or len(match.group(1)) != 1:
        return False
    return _MARKUP_RE.sub("", match.group(2)).strip().casefold() == title.strip().casefold()


def _add_inline_runs(paragraph: Paragraph, text: str) -> None:
    """Split `text` on escapes, `code`, links, **bold** and *italic*/_italic_ spans."""
    for token in _INLINE_PATTERN.split(text):
        if not token:
            continue
        if len(token) == 2 and token.startswith("\\"):
            paragraph.add_run(token[1])
        elif token.startswith("`") and token.endswith("`") and len(token) > 2:
            paragraph.add_run(token[1:-1]).font.name = "Consolas"
        elif link := _LINK_RE.match(token):
            label, url = link.groups()
            if _SAFE_LINK_RE.match(url):
                _add_hyperlink(paragraph, label, url)
            else:
                paragraph.add_run(label)
        elif token.startswith("**") and token.endswith("**") and len(token) > 4:
            paragraph.add_run(token[2:-2]).bold = True
        elif len(token) > 2 and (
            (token.startswith("*") and token.endswith("*")) or (token.startswith("_") and token.endswith("_"))
        ):
            paragraph.add_run(token[1:-1]).italic = True
        else:
            paragraph.add_run(token)


def _add_hyperlink(paragraph: Paragraph, text: str, url: str) -> None:
    """Append a clickable external link. python-docx has no public API for one."""
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    relationship_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)

    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), _HYPERLINK_COLOR)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(color)
    properties.append(underline)
    run.append(properties)
    run_text = OxmlElement("w:t")
    run_text.set(qn("xml:space"), "preserve")
    run_text.text = text
    run.append(run_text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _normalize_zip_timestamps(data: bytes) -> bytes:
    """Rewrite every zip entry's embedded timestamp to a fixed value.

    python-docx's OPC writer stamps each part with `time.localtime()` (the default
    `zipfile.ZipInfo.date_time` when none is given to `writestr`), which would otherwise
    make `to_docx` return different bytes for the same input depending on the moment it
    runs — breaking both the "pure function" rule and byte-exact golden-file testing.
    """
    source = zipfile.ZipFile(BytesIO(data))
    out_buffer = BytesIO()
    with zipfile.ZipFile(out_buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for info in source.infolist():
            normalized = zipfile.ZipInfo(info.filename, date_time=_FIXED_ZIP_TIMESTAMP)
            normalized.compress_type = info.compress_type
            normalized.external_attr = info.external_attr
            out.writestr(normalized, source.read(info.filename))
    return out_buffer.getvalue()
