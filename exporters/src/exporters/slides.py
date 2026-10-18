"""Lesson slides as images (Pillow), in Isnad's visual language (DESIGN-SYSTEM §03, §04, §09, deck grid).

Laid out on the 1920 × 1080 deck grid (96 px margins) and scaled to the video's size:

- **cover** — the lesson title on the Handoff gradient (G-1);
- **agenda** — "What you'll learn": the parts as a chain of nodes, the Isnad mark's own language;
- **part** — the part's heading, its key points appearing one by one as the voice reaches them
  (the current one solid, the ones before it outlined), the spoken sentence as a caption, a
  gradient card with the part's number and the chain of parts, and a progress bar;
- **recap** — one takeaway per part on the Signal gradient (G-2).

Text on a gradient is Paper and at least 44 px (on the 1920 grid); a slide never carries two gradients.
Fonts are the product's own (OFL, bundled under `fonts/`); a line with a character they lack — Arabic,
say — falls back to DejaVu Sans when the system has it.
"""

from __future__ import annotations

import math
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from exporters.lesson import Beat, Lesson

FONTS = Path(__file__).with_name("fonts")
FONT_FILES = {
    "sans": "Geist-Regular.ttf",
    "sans-medium": "Geist-Medium.ttf",
    "sans-semibold": "Geist-SemiBold.ttf",
    "serif": "InstrumentSerif-Regular.ttf",
    "mono": "GeistMono-Medium.ttf",
}
FALLBACK_FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/Library/Fonts/Arial Unicode.ttf")

INK = (11, 11, 10)
PAPER = (250, 250, 248)
MUTED = (112, 112, 107)
HAIRLINE = (226, 226, 220)
CAPTION = (239, 239, 233)

# §09: the stops of each gradient's CSS recipe, as (color, centre x, centre y, radius x, radius y, fade-out stop).
GRADIENTS: dict[
    str, tuple[tuple[int, int, int], list[tuple[tuple[int, int, int], float, float, float, float, float]]]
] = {
    "handoff": (
        INK,
        [
            ((0x1E, 0x3A, 0x5F), 0.40, 0.40, 0.90, 0.90, 0.70),
            ((0x24, 0x56, 0xF5), 0.85, 0.70, 1.00, 0.80, 0.55),
            ((0x9F, 0xB6, 0xFF), 1.00, 1.00, 1.20, 0.90, 0.45),
        ],
    ),
    "signal": (
        INK,
        [
            ((0x13, 0x46, 0x3A), 0.40, 0.40, 0.90, 0.90, 0.70),
            ((0x1F, 0x8A, 0x66), 0.85, 0.70, 1.00, 0.80, 0.55),
            ((0xD7, 0xFF, 0x3A), 1.00, 1.00, 1.20, 0.90, 0.45),
        ],
    ),
    "review": (
        INK,
        [
            ((0x3B, 0x1F, 0x5C), 0.40, 0.40, 0.90, 0.90, 0.70),
            ((0x6D, 0x3F, 0xD9), 0.85, 0.70, 1.00, 0.80, 0.55),
            ((0xE8, 0x6A, 0xD8), 1.00, 1.00, 1.20, 0.90, 0.45),
        ],
    ),
}
PART_GRADIENTS = ("handoff", "signal", "review")

MAX_POINTS_SHOWN = 4


class Canvas:
    """A slide being drawn: coordinates and sizes in 1920-grid units, scaled to the real size."""

    def __init__(self, size: tuple[int, int], background: tuple[int, int, int] | Image.Image):
        self.size = size
        self.k = size[0] / 1920
        if isinstance(background, Image.Image):
            self.image = background.copy()
        else:
            self.image = Image.new("RGB", size, background)
        self.draw = ImageDraw.Draw(self.image)

    def px(self, value: float) -> int:
        return round(value * self.k)

    def font(self, kind: str, size: float, text: str = "") -> ImageFont.FreeTypeFont:
        return _font(kind, max(8, self.px(size)), _needs_fallback(kind, text))

    def text(self, xy: tuple[float, float], text: str, kind: str, size: float, fill, *, anchor: str = "la") -> None:
        self.draw.text(
            (self.px(xy[0]), self.px(xy[1])), text, font=self.font(kind, size, text), fill=fill, anchor=anchor
        )

    def width(self, text: str, kind: str, size: float) -> float:
        """Advance width in 1920-grid units."""
        return self.draw.textlength(text, font=self.font(kind, size, text)) / self.k

    def fit(
        self, text: str, kind: str, size: float, max_width: float, max_lines: int, min_size: float
    ) -> tuple[float, list[str]]:
        """The largest size from `size` down to `min_size` at which `text` wraps into `max_lines`;
        at `min_size` the last line is cut short with an ellipsis."""
        current = size
        while True:
            lines = self.wrap(text, kind, current, max_width)
            if len(lines) <= max_lines:
                return current, lines
            if current <= min_size:
                kept = lines[:max_lines]
                last = kept[-1]
                while last and self.width(last + "…", kind, current) > max_width:
                    last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
                kept[-1] = last.rstrip(" ,;:") + "…"
                return current, kept
            current = max(min_size, current * 0.9)

    def wrap(self, text: str, kind: str, size: float, max_width: float) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in text.split():
            trial = f"{current} {word}".strip()
            if self.width(trial, kind, size) <= max_width:
                current = trial
                continue
            if current:
                lines.append(current)
            # A single word wider than the line is broken by characters.
            while self.width(word, kind, size) > max_width and len(word) > 1:
                cut = len(word)
                while cut > 1 and self.width(word[:cut], kind, size) > max_width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        if current:
            lines.append(current)
        return lines

    def paragraph(
        self, xy: tuple[float, float], lines: list[str], kind: str, size: float, fill, leading: float = 1.25
    ) -> float:
        """Draw wrapped lines from the top; returns the y below the last line (1920 units)."""
        x, y = xy
        for line in lines:
            self.text((x, y), line, kind, size, fill)
            y += size * leading
        return y

    def node(self, centre: tuple[float, float], radius: float, color, *, solid: bool, stroke: float = 3) -> None:
        cx, cy, r = self.px(centre[0]), self.px(centre[1]), self.px(radius)
        width = max(1, self.px(stroke))
        if solid:
            self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        else:
            self.draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width)

    def line(self, start: tuple[float, float], end: tuple[float, float], color, width: float = 2) -> None:
        self.draw.line(
            (self.px(start[0]), self.px(start[1]), self.px(end[0]), self.px(end[1])),
            fill=color,
            width=max(1, self.px(width)),
        )

    def mark(self, x: float, y: float, height: float, color) -> float:
        """The Isnad mark (§03: 64 × 24 units — two outlined nodes and a solid one on a line), top-left at
        (x, y); returns its width."""
        unit = height / 24
        for x1, x2 in ((11, 27), (37, 53)):
            self.line((x + x1 * unit, y + 12 * unit), (x + x2 * unit, y + 12 * unit), color, 2 * unit)
        for cx, solid in ((6, False), (32, False), (58, True)):
            self.node((x + cx * unit, y + 12 * unit), 5 * unit, color, solid=solid, stroke=2 * unit)
        return 64 * unit

    def wordmark(self, x: float, y: float, color, height: float = 22) -> None:
        width = self.mark(x, y, height, color)
        self.text(
            (x + width + height * 0.6, y + height / 2), "isnad", "sans-semibold", height * 1.35, color, anchor="lm"
        )

    def wordmark_right(self, right: float, y: float, color, height: float = 22) -> None:
        width = 64 * height / 24 + height * 0.6 + self.width("isnad", "sans-semibold", height * 1.35)
        self.wordmark(right - width, y, color, height)

    def card(self, box: tuple[float, float, float, float], gradient: str, radius: float = 24) -> None:
        x0, y0, x1, y1 = (self.px(v) for v in box)
        fill = gradient_image(gradient, (x1 - x0, y1 - y0))
        mask = Image.new("L", fill.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, fill.size[0] - 1, fill.size[1] - 1), self.px(radius), fill=255)
        self.image.paste(fill, (x0, y0), mask)

    def spark(self, x: float, y: float, size: float, color) -> None:
        """✦ — the "generated by an agent" symbol (§10), drawn: the fonts don't carry the glyph."""
        cx, cy, r, waist = self.px(x), self.px(y), self.px(size / 2), self.px(size / 2) * 0.28
        points = []
        for i in range(8):
            angle = math.pi / 4 * i - math.pi / 2
            radius = r if i % 2 == 0 else waist
            points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        self.draw.polygon(points, fill=color)


@lru_cache(maxsize=64)
def _font(kind: str, size: int, fallback: bool) -> ImageFont.FreeTypeFont:
    if fallback:
        for path in FALLBACK_FONTS:
            if Path(path).is_file():
                return ImageFont.truetype(path, size)
    path = FONTS / FONT_FILES[kind]
    if path.is_file():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


@lru_cache(maxsize=8)
def _cmap(kind: str) -> frozenset[int]:
    path = FONTS / FONT_FILES[kind]
    if not path.is_file():
        return frozenset()
    from fontTools.ttLib import TTFont  # a WeasyPrint dependency; only needed to read the font's character map

    return frozenset(TTFont(str(path), lazy=True).getBestCmap())


def _needs_fallback(kind: str, text: str) -> bool:
    if not text or text.isascii():
        return False
    try:
        cmap = _cmap(kind)
    except ImportError:
        return False
    return bool(cmap) and any(ord(c) not in cmap for c in text if not c.isspace())


@lru_cache(maxsize=16)
def gradient_image(name: str, size: tuple[int, int]) -> Image.Image:
    """A §09 grain gradient: radial color fields over Ink, Ink in the top-left corner, ~8 % grain."""
    base, layers = GRADIENTS[name]
    w, h = 160, 90  # computed small, then smoothly scaled up
    small = Image.new("RGB", (w, h))
    pixels = small.load()
    for j in range(h):
        v = (j + 0.5) / h
        for i in range(w):
            u = (i + 0.5) / w
            r, g, b = base
            for color, cx, cy, rx, ry, stop in layers:
                distance = math.hypot((u - cx) / rx, (v - cy) / ry)
                alpha = max(0.0, 1.0 - distance / stop)
                r += (color[0] - r) * alpha
                g += (color[1] - g) * alpha
                b += (color[2] - b) * alpha
            pixels[i, j] = (round(r), round(g), round(b))
    smooth = small.resize(size, Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(max(1, size[0] // 200)))
    grain = Image.effect_noise(size, 48).convert("RGB")
    return Image.blend(smooth, ImageChops.overlay(smooth, grain), 0.08)


# ---------------------------------------------------------------- the slides
def render(
    lesson: Lesson, beat: Beat, size: tuple[int, int], *, progress: float = 0.0, minutes: int = 0
) -> Image.Image:
    if beat.slide == "cover":
        return cover(lesson, size, minutes=minutes)
    if beat.slide == "agenda":
        return agenda(lesson, size, minutes=minutes)
    if beat.slide == "recap":
        return recap(lesson, size)
    return part(lesson, beat.part, beat.read, beat.caption, size, progress=progress)


def _about(parts: int, minutes: int) -> str:
    bits = [f"{parts} part{'s' if parts != 1 else ''}"]
    if minutes:
        bits.append(f"about {minutes} min")
    return " · ".join(bits)


def cover(lesson: Lesson, size: tuple[int, int], *, minutes: int = 0) -> Image.Image:
    c = Canvas(size, gradient_image("handoff", size))
    title_size, lines = c.fit(lesson.title, "serif", 136, 1500, 3, 88)
    y = c.paragraph((96, 250), lines, "serif", title_size, PAPER, leading=1.08)
    c.text((96, y + 36), _about(len(lesson.parts), minutes), "sans", 44, PAPER)
    c.wordmark(96, 960, PAPER, height=30)
    return c.image


def _header(c: Canvas, label: str) -> None:
    c.text((96, 88), label.upper(), "mono", 24, MUTED)
    c.wordmark_right(1824, 82, INK, height=22)
    generated_x = 1824 - 64 * 22 / 24 - 22 * 0.6 - c.width("isnad", "sans-semibold", 22 * 1.35) - 48
    c.text((generated_x, 93), "Generated", "sans-medium", 24, MUTED, anchor="rm")
    c.spark(generated_x - c.width("Generated", "sans-medium", 24) - 20, 93, 22, MUTED)


def agenda(lesson: Lesson, size: tuple[int, int], *, minutes: int = 0) -> Image.Image:
    c = Canvas(size, PAPER)
    _header(c, "In this lesson")
    c.text((96, 140), "What you’ll learn", "serif", 104, INK)
    count = len(lesson.parts)
    top, bottom = 330, 930
    step = min(132.0, (bottom - top) / max(1, count))
    centres = [top + step * i + 28 for i in range(count)]
    for a, b in pairwise(centres):
        c.line((110, a + 16), (110, b - 16), INK, 2)
    for i, (part, y) in enumerate(zip(lesson.parts, centres, strict=True)):
        c.node((110, y), 14, INK, solid=False, stroke=3)
        c.text((160, y), f"{i + 1:02d}", "mono", 26, MUTED, anchor="lm")
        heading_size, lines = c.fit(part.heading, "sans-medium", 48, 940, 1, 34)
        c.text((230, y), lines[0], "sans-medium", heading_size, INK, anchor="lm")
    c.card((1240, 160, 1824, 930), "handoff")
    c.text((1288, 190), str(count), "serif", 360, PAPER)
    c.text((1288, 800), _about(count, minutes), "sans", 44, PAPER)
    return c.image


def part(
    lesson: Lesson, index: int, read: int, caption: str, size: tuple[int, int], *, progress: float = 0.0
) -> Image.Image:
    c = Canvas(size, PAPER)
    current = lesson.parts[index]
    _header(c, f"Part {index + 1} of {len(lesson.parts)}")

    heading_size, heading_lines = c.fit(current.heading, "serif", 92, 1060, 2, 64)
    y = c.paragraph((96, 140), heading_lines, "serif", heading_size, INK, leading=1.05) + 44

    # Key points so far, newest last; the newest is the one being read.
    points = [line.point for line in current.lines[:read] if line.point]
    newest_is_current = bool(read) and bool(current.lines[read - 1].point)
    bottom = 830 if caption else 960
    shown = points[-MAX_POINTS_SHOWN:]
    while shown:
        laid = [c.fit(p, "sans", 42, 1000, 2, 34) for p in shown]
        height = sum(len(lines) * s * 1.25 for s, lines in laid) + 30 * (len(laid) - 1)
        if y + height <= bottom:
            break
        shown = shown[1:]
    if shown:
        laid = [c.fit(p, "sans", 42, 1000, 2, 34) for p in shown]
        centres = []
        for i, ((point_size, lines), _text) in enumerate(zip(laid, shown, strict=True)):
            is_current = newest_is_current and i == len(shown) - 1
            centre = y + point_size * 0.62
            centres.append(centre)
            color = INK if is_current else MUTED
            c.paragraph((156, y), lines, "sans-medium" if is_current else "sans", point_size, color)
            y += len(lines) * point_size * 1.25 + 30
        for a, b in pairwise(centres):
            c.line((112, a + 12), (112, b - 12), HAIRLINE, 2)
        for i, centre in enumerate(centres):
            is_current = newest_is_current and i == len(centres) - 1
            c.node((112, centre), 11, INK if is_current else MUTED, solid=is_current, stroke=3)

    # The part's card: its number and the chain of parts, done parts solid.
    gradient = PART_GRADIENTS[index % len(PART_GRADIENTS)]
    c.card((1240, 160, 1824, 800), gradient)
    c.text((1284, 170), f"{index + 1:02d}", "serif", 300, PAPER)
    c.text((1290, 480), f"of {len(lesson.parts):02d}", "sans", 44, PAPER)
    count = len(lesson.parts)
    left, right, chain_y = 1290, 1774, 720
    xs = [left + (right - left) * i / (count - 1) for i in range(count)] if count > 1 else [(left + right) / 2]
    for a, b in pairwise(xs):
        c.line((a + 13, chain_y), (b - 13, chain_y), PAPER, 2)
    for i, x in enumerate(xs):
        c.node((x, chain_y), 10, PAPER, solid=i <= index, stroke=3)

    if caption:
        c.draw.rounded_rectangle((c.px(96), c.px(856), c.px(1824), c.px(1004)), c.px(20), fill=CAPTION)
        caption_size, caption_lines = c.fit(caption, "sans", 38, 1664, 2, 28)
        if len(caption_lines) == 2 and caption_lines[-1].endswith("…"):
            caption_size, caption_lines = c.fit(caption, "sans", 30, 1664, 3, 26)
        block = len(caption_lines) * caption_size * 1.22
        c.paragraph((128, 930 - block / 2), caption_lines, "sans", caption_size, INK, leading=1.22)

    c.draw.rectangle((0, c.px(1048), size[0], c.px(1054)), fill=HAIRLINE)
    c.draw.rectangle((0, c.px(1048), round(size[0] * max(0.0, min(1.0, progress))), c.px(1054)), fill=INK)
    return c.image


def recap(lesson: Lesson, size: tuple[int, int]) -> Image.Image:
    c = Canvas(size, gradient_image("signal", size))
    c.text((96, 110), "What we covered", "serif", 112, PAPER)
    y = 300.0
    takeaways = lesson.takeaways()
    room = min(130.0, (900 - y) / max(1, len(takeaways)))
    for takeaway in takeaways:
        point_size, lines = c.fit(takeaway, "sans", 48, 1500, 1 if room < 110 else 2, 44)
        c.node((112, y + point_size * 0.62), 11, PAPER, solid=True)
        c.paragraph((156, y), lines, "sans", point_size, PAPER)
        y += max(room, len(lines) * point_size * 1.25 + 24)
    c.wordmark(96, 960, PAPER, height=30)
    return c.image
