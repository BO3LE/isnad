"""exporters.slides: every slide draws at the video's size, long text stays inside its box, and a
part's slide changes as its points are read. Needs Pillow (gp-exporters[video]); no FFmpeg."""

from __future__ import annotations

import pytest
from PIL import ImageChops

from exporters import slides
from exporters.lesson import Beat, lesson_from_markdown

SIZE = (1280, 720)

SCRIPT = """# The Sun Over Riyadh

## How panels work

A panel turns light into electricity. It has no moving parts. Heat lowers its output. Dust does too.
Cleaning helps a lot.

## What it costs

Prices fell by most of their value in ten years.

## What comes next

Storage is the next big step.
"""


@pytest.fixture(scope="module")
def lesson():
    return lesson_from_markdown(SCRIPT, agenda_intro="In this lesson")


def test_the_fonts_ship_with_their_licences():
    for name in slides.FONT_FILES.values():
        assert (slides.FONTS / name).is_file(), name
    assert sorted(p.name for p in slides.FONTS.glob("OFL-*.txt")) == [
        "OFL-Geist.txt",
        "OFL-GeistMono.txt",
        "OFL-InstrumentSerif.txt",
    ]


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080)])
def test_every_kind_of_slide_draws_at_the_videos_size(lesson, size):
    for beat in lesson.beats():
        image = slides.render(lesson, beat, size, progress=0.5, minutes=2)
        assert (image.size, image.mode) == (size, "RGB")


def test_the_cover_and_recap_sit_on_a_gradient_and_the_part_slides_on_paper(lesson):
    cover = slides.render(lesson, Beat("cover"), SIZE)
    part = slides.render(lesson, Beat("part", part=0, read=1, caption="A panel turns light into electricity."), SIZE)

    assert max(cover.getpixel((4, 4))) < 40  # the gradient's Ink corner
    assert part.getpixel((4, 4)) == slides.PAPER


def test_a_part_slide_gains_its_points_as_they_are_read(lesson):
    first = slides.part(lesson, 0, 1, "A panel turns light into electricity.", SIZE)
    second = slides.part(lesson, 0, 2, "It has no moving parts.", SIZE)
    same = slides.part(lesson, 0, 2, "It has no moving parts.", SIZE)

    # Points sit left of the card (x < 1240 on the 1920 grid), above the caption band.
    points_area = (0, round(150 * SIZE[0] / 1920), round(1200 * SIZE[0] / 1920), round(830 * SIZE[0] / 1920))
    assert ImageChops.difference(first.crop(points_area), second.crop(points_area)).getbbox() is not None
    assert ImageChops.difference(second.crop(points_area), same.crop(points_area)).getbbox() is None


def test_the_progress_bar_fills_as_far_as_the_video_has_played(lesson):
    image = slides.part(lesson, 1, 1, "", SIZE, progress=0.25)
    y = round(1051 * SIZE[0] / 1920)

    assert image.getpixel((round(SIZE[0] * 0.20), y)) == slides.INK
    assert image.getpixel((round(SIZE[0] * 0.30), y)) == slides.HAIRLINE


def test_each_part_has_its_own_gradient_card(lesson):
    inside_card = (round(1700 * SIZE[0] / 1920), round(600 * SIZE[0] / 1920))
    colors = [slides.part(lesson, i, 1, "", SIZE).getpixel(inside_card) for i in range(3)]

    assert len(set(colors)) == 3


def test_long_text_is_shrunk_then_cut_to_fit_its_box():
    canvas = slides.Canvas(SIZE, slides.PAPER)
    text = "A very long heading that goes on and on about solar power in the desert " * 6

    size, lines = canvas.fit(text, "serif", 92, 1060, 2, 64)

    assert size == 64
    assert len(lines) == 2
    assert lines[-1].endswith("…")
    assert all(canvas.width(line, "serif", size) <= 1060 for line in lines)


def test_a_word_wider_than_its_line_is_broken_rather_than_overflowing():
    canvas = slides.Canvas(SIZE, slides.PAPER)

    lines = canvas.wrap("Pneumonoultramicroscopicsilicovolcanoconiosis" * 3, "sans", 42, 400)

    assert len(lines) > 1
    assert all(canvas.width(line, "sans", 42) <= 400 for line in lines)


def test_long_and_many_lines_still_draw(lesson):
    many = lesson_from_markdown(
        "# "
        + "Long title " * 30
        + "\n\n"
        + "\n\n".join(f"## Part {i} " + "word " * 40 + "\n\nA line here." for i in range(9)),
        agenda_intro="In this lesson",
    )
    for beat in many.beats():
        assert slides.render(many, beat, SIZE).size == SIZE


def test_text_the_fonts_lack_falls_back_rather_than_failing():
    arabic = lesson_from_markdown("# الطاقة الشمسية\n\n## الألواح\n\nتحول الألواح الضوء إلى كهرباء.")

    for beat in arabic.beats():
        assert slides.render(arabic, beat, SIZE).size == SIZE
    assert slides._needs_fallback("sans", "الطاقة") is True
    assert slides._needs_fallback("sans", "Solar") is False
