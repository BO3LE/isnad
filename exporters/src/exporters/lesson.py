"""A narrated script → a lesson: what the voice reads and what each slide shows. Pure: no audio, no pixels.

The Video agent turns a Writer script into a short lesson video (`exporters.video.assemble_lesson`).
This module decides the lesson's shape:

- the script's `# Title` — or the step's title — opens the lesson on a cover slide;
- each `## Heading` starts a part; text before the first heading is an "Introduction" part whose
  heading is shown but not read (the script never says it);
- every sentence, list item and `###` sub-heading is one line: read aloud, shown as the caption,
  and — when it adds something — summed up as a key point that appears on the part's slide as
  the voice reaches it.

Citation markers ([1], [2, 3]), links, URLs, code and tables reach neither the voice nor the
screen, and a "Sources"/"References" part is dropped: a URL read aloud teaches nothing.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from typing import Literal

INTRODUCTION = "Introduction"

# Pauses after a line, in seconds: a beat to read the slide before the voice moves on.
PAUSE_AFTER_TITLE = 0.8
PAUSE_AFTER_AGENDA = 0.8
PAUSE_AFTER_HEADING = 0.5
PAUSE_AFTER_LINE = 0.35
PAUSE_AFTER_PART = 0.9
RECAP_SECONDS = 5.0

MAX_POINT_WORDS = 9


@dataclass(frozen=True)
class Line:
    text: str  # what the voice reads and the caption shows
    point: str = ""  # the key point it adds to the slide; "" adds none


@dataclass(frozen=True)
class Part:
    heading: str
    lines: tuple[Line, ...]
    heading_spoken: bool = True


@dataclass(frozen=True)
class Beat:
    """One moment of the video: a slide on screen while the voice reads `say` (or, silent, for `hold` s)."""

    slide: Literal["cover", "agenda", "part", "recap"]
    say: str = ""
    pause: float = 0.0
    hold: float = 0.0
    part: int = -1  # for "part": which part
    read: int = 0  # for "part": lines of that part read once this beat starts; 0 while the heading is read
    caption: str = ""


@dataclass(frozen=True)
class Lesson:
    title: str
    parts: tuple[Part, ...]
    # Read before the agenda slide ("In this lesson"); None leaves the agenda slide out — the phrase
    # is the only text the video adds to the script, so it is given only in the voice's language.
    agenda_intro: str | None = None

    def beats(self) -> list[Beat]:
        beats = [Beat("cover", say=_sentence(self.title), pause=PAUSE_AFTER_TITLE)]
        if self.agenda_intro and len(self.parts) > 1:
            headings = [p.heading for p in self.parts]
            listed = ", ".join(headings[:-1]) + f", and {headings[-1]}" if len(headings) > 2 else " and ".join(headings)
            beats.append(Beat("agenda", say=f"{self.agenda_intro}: {listed}.", pause=PAUSE_AFTER_AGENDA))
        for index, part in enumerate(self.parts):
            if part.heading_spoken:
                beats.append(Beat("part", say=_sentence(part.heading), pause=PAUSE_AFTER_HEADING, part=index))
            for read, line in enumerate(part.lines, start=1):
                last = read == len(part.lines)
                beats.append(
                    Beat(
                        "part",
                        say=line.text,
                        pause=PAUSE_AFTER_PART if last else PAUSE_AFTER_LINE,
                        part=index,
                        read=read,
                        caption=line.text,
                    )
                )
        beats.append(Beat("recap", hold=RECAP_SECONDS))
        return beats

    def narration(self) -> list[str]:
        """What the voice reads, in order — one clip per entry, as `assemble_lesson` expects them."""
        return [beat.say for beat in self.beats() if beat.say]

    def lines(self) -> list[Line]:
        return [line for part in self.parts for line in part.lines]

    def with_points(self, points: Sequence[str]) -> Lesson:
        """The same lesson with every line's key point replaced, in reading order."""
        if len(points) != len(self.lines()):
            raise ValueError(f"expected {len(self.lines())} key points, got {len(points)}")
        given = iter(points)
        parts = tuple(
            replace(part, lines=tuple(replace(line, point=next(given)) for line in part.lines)) for part in self.parts
        )
        return replace(self, parts=parts)

    def takeaways(self, limit: int = 6) -> list[str]:
        """For the recap: each part's first key point (its heading when it has none)."""
        found = [next((line.point for line in part.lines if line.point), part.heading) for part in self.parts]
        return found[:limit]


# ---------------------------------------------------------------- markdown → lesson
_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_RULE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
_TABLE = re.compile(r"^\s*\|")
_SOURCES = re.compile(r"^(?:sources?|references?|bibliography|citations?|further reading|works cited)\b", re.I)

_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_AUTOLINK = re.compile(r"<(?:https?|mailto):[^>]*>")
_URL = re.compile(r"\b(?:https?://|www\.)\S+")
_HTML = re.compile(r"</?[a-zA-Z][^>]*>")
_CITATION = re.compile(r"\s*\[(?:\^?\d+(?:\s*[,;–-]\s*\^?\d+)*)\]")
_CODE = re.compile(r"`([^`]*)`")
_STRONG = re.compile(r"\*\*|__")
_EMPHASIS = re.compile(r"(?<![\w*])[*_](?=\S)|(?<=\S)[*_](?![\w*])")
_SPACE_BEFORE_MARK = re.compile(r"\s+([.,;:!?)])")


def lesson_from_markdown(markdown: str, *, title: str = "", agenda_intro: str | None = None) -> Lesson:
    """The lesson in a Writer script. `title` is used when the script has no `# Title`."""
    found_title = ""
    parts: list[Part] = []
    heading, spoken, lines = INTRODUCTION, False, []
    skipping = False

    def close() -> None:
        if lines and not skipping:
            parts.append(Part(heading, tuple(lines), heading_spoken=spoken))

    for kind, text in _blocks(markdown):
        if kind == "h1" and not found_title:
            found_title = text
            continue
        if kind in ("h1", "h2"):
            close()
            heading, spoken, lines = text, True, []
            skipping = bool(_SOURCES.match(text))
            continue
        if kind == "h3":
            lines.append(Line(_sentence(text), point=text))
            continue
        lines.extend(Line(s, point=key_point(s)) for s in split_sentences(text))
    close()
    return Lesson(title=found_title or clean_inline(title) or "Lesson", parts=tuple(parts), agenda_intro=agenda_intro)


def _blocks(markdown: str) -> Iterator[tuple[str, str]]:
    """("h1" | "h2" | "h3" | "text", cleaned text) for each heading, paragraph and list item."""
    paragraph: list[str] = []

    def flush() -> Iterator[tuple[str, str]]:
        text = clean_inline(" ".join(paragraph))
        paragraph.clear()
        if text:
            yield "text", text

    for raw in _FENCE.sub("\n", markdown).splitlines():
        line = raw.strip()
        if not line or _RULE.match(line) or _TABLE.match(line):
            yield from flush()
            continue
        if heading := _HEADING.match(line):
            yield from flush()
            level, text = len(heading.group(1)), clean_inline(heading.group(2))
            if text:
                yield ("h1" if level == 1 else "h2" if level == 2 else "h3"), text
            continue
        if item := _LIST_ITEM.match(line):
            yield from flush()
            paragraph.append(item.group(1))
            yield from flush()
            continue
        paragraph.append(line.lstrip("> "))
    yield from flush()


def clean_inline(text: str) -> str:
    """Markdown and HTML inline markup → the plain words a person would read out."""
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _AUTOLINK.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _HTML.sub(" ", text)
    text = _CITATION.sub("", text)
    text = _CODE.sub(r"\1", text)
    text = _STRONG.sub("", text)
    text = _EMPHASIS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _SPACE_BEFORE_MARK.sub(r"\1", text)


# ---------------------------------------------------------------- sentences
_BOUNDARY = re.compile(r"[.!?…]+[\"”’)\]]*\s+(?=[\"“‘(\[]?[A-Z0-9])")
_ABBREVIATION = re.compile(
    r"(?:\b(?:e\.g|i\.e|etc|vs|approx|dr|mr|mrs|ms|prof|st|no|fig|vol|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"|\b[A-Z](?:\.[A-Z])*)\.$",
    re.I,
)
_TOO_SHORT = 3  # words: a shorter "sentence" is a split in the wrong place and joins its neighbour


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for boundary in _BOUNDARY.finditer(text):
        candidate = text[start : boundary.end()].strip()
        if _ABBREVIATION.search(candidate.rstrip('"”’)] ')):
            continue
        sentences.append(candidate)
        start = boundary.end()
    if rest := text[start:].strip():
        sentences.append(rest)
    merged: list[str] = []
    for sentence in sentences:
        if merged and len(sentence.split()) < _TOO_SHORT:
            merged[-1] = f"{merged[-1]} {sentence}"
        else:
            merged.append(sentence)
    return merged


def _sentence(text: str) -> str:
    """A heading or title, read as a sentence: the voice pauses after it."""
    text = text.strip()
    return text if not text or text[-1] in ".!?…" else f"{text}."


# ---------------------------------------------------------------- key points
_LEAD_IN = re.compile(
    r"^(?:however|in summary|in conclusion|in short|to sum up|overall|finally|first(?:ly)?|second(?:ly)?|"
    r"third(?:ly)?|next|also|moreover|furthermore|additionally|in addition|for example|for instance|"
    r"as a result|therefore|thus|meanwhile|today|currently|importantly|notably|"
    r"despite (?:this|that|the [\w-]+)|this (?:suggests|means|shows|indicates) that|"
    r"(?:findings|research|studies|evidence) (?:indicates?|suggests?|shows?) that)\b[,:]?\s*",
    re.I,
)
_SUBORDINATE = re.compile(r"^(?:while|although|though|whereas|even though|if|when|as|since|because)\b", re.I)
_CLAUSE = re.compile(r"[,;:—–]| but | while | which | because | although | though | whereas ")
# A note cut short doesn't end on one of these ("…work well in…").
_DANGLING = frozenset("a an the of to in on at by for from with and or but as that than is are was were".split())


def key_point(sentence: str, max_words: int = MAX_POINT_WORDS) -> str:
    """A note-sized version of a sentence, for when no model writes the key points: the sentence
    without its lead-in, cut at a clause boundary, at most `max_words` words."""
    text = sentence.strip()
    question = text.endswith("?")
    text = text.rstrip(".!?… ")
    for _ in range(2):
        text = _LEAD_IN.sub("", text)
    # "While X, Y" / "Although X, Y": the point is Y.
    if _SUBORDINATE.match(text) and "," in text:
        text = text.split(",", 1)[1]
    words = text.split()
    if len(words) > max_words:
        for clause in _CLAUSE.finditer(text):
            if len(text[: clause.start()].split()) >= 3:
                text = text[: clause.start()]
                break
        words = text.split()
        if len(words) > max_words:
            kept = words[:max_words]
            while len(kept) > 3 and kept[-1].lower().strip(",;:") in _DANGLING:
                kept.pop()
            text = " ".join(kept).rstrip(",;:") + "…"
    text = text.strip(" ,;:")
    if not text:
        return ""
    return text[0].upper() + text[1:] + ("?" if question and not text.endswith("…") else "")
