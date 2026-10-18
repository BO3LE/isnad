"""exporters.lesson: a script's shape as a lesson — what the voice reads, in what order, and the
key points each slide gains. Pure: no FFmpeg, no Pillow."""

from __future__ import annotations

import pytest

from exporters.lesson import (
    INTRODUCTION,
    RECAP_SECONDS,
    Lesson,
    clean_inline,
    key_point,
    lesson_from_markdown,
    split_sentences,
)

SCRIPT = """# The Sun Over Riyadh

Saudi Arabia gets strong sunlight all year [1]. That makes solar power cheap there.

## How panels work

A panel turns light into electricity [2, 3]. It has no moving parts.

### Why heat matters

- Hot panels make less power.
- Dust has to be cleaned off.

## Sources

1. https://example.org/irena
2. [IEA report](https://iea.org/x)
"""


def test_the_title_parts_and_lines_come_from_the_script():
    lesson = lesson_from_markdown(SCRIPT)

    assert lesson.title == "The Sun Over Riyadh"
    assert [part.heading for part in lesson.parts] == [INTRODUCTION, "How panels work"]
    assert [line.text for line in lesson.parts[0].lines] == [
        "Saudi Arabia gets strong sunlight all year.",
        "That makes solar power cheap there.",
    ]
    assert [line.text for line in lesson.parts[1].lines] == [
        "A panel turns light into electricity.",
        "It has no moving parts.",
        "Why heat matters.",
        "Hot panels make less power.",
        "Dust has to be cleaned off.",
    ]


def test_text_before_the_first_heading_is_shown_under_introduction_but_the_heading_is_never_read():
    lesson = lesson_from_markdown(SCRIPT)

    assert lesson.parts[0].heading_spoken is False
    assert "Introduction." not in lesson.narration()
    assert "How panels work." in lesson.narration()


def test_citation_markers_urls_and_the_sources_part_reach_neither_the_voice_nor_the_screen():
    lesson = lesson_from_markdown(SCRIPT)
    everything = " ".join(lesson.narration()) + " ".join(line.point for line in lesson.lines())

    for unwanted in ("[1]", "[2, 3]", "http", "example.org", "IEA report", "Sources"):
        assert unwanted not in everything
    assert [part.heading for part in lesson.parts] == [INTRODUCTION, "How panels work"]


def test_a_sub_heading_is_read_and_is_its_own_key_point():
    line = lesson_from_markdown(SCRIPT).parts[1].lines[2]

    assert (line.text, line.point) == ("Why heat matters.", "Why heat matters")


def test_the_step_title_is_used_when_the_script_has_none():
    assert lesson_from_markdown("Plain words here.", title="Solar *basics*").title == "Solar basics"
    assert lesson_from_markdown("Plain words here.").title == "Lesson"


def test_a_script_of_only_headings_and_sources_has_no_parts():
    assert lesson_from_markdown("# Title\n\n## Sources\n\n- https://x.org").parts == ()


def test_code_tables_and_rules_are_not_read():
    lesson = lesson_from_markdown(
        "# T\n\nBefore the code.\n\n```python\nprint('hi')\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n---\n\nAfter it."
    )

    assert lesson.narration() == ["T.", "Before the code.", "After it."]


@pytest.mark.parametrize(
    ("markdown", "plain"),
    [
        ("See [IRENA](https://irena.org) now.", "See IRENA now."),
        ("A ![chart](c.png) here.", "A here."),
        ("Read <https://x.org> or www.x.org today.", "Read or today."),
        ("**Bold** and *italic* and _under_ and `code`.", "Bold and italic and under and code."),
        ("Costs fell [1][2] and rose [^3].", "Costs fell and rose."),
        ("Ranges [1-3] and lists [4; 5] go.", "Ranges and lists go."),
        ("A <b>tag</b> here.", "A tag here."),
        ("snake_case_names stay.", "snake_case_names stay."),
    ],
)
def test_inline_markup_becomes_plain_words(markdown, plain):
    assert clean_inline(markdown) == plain


def test_sentences_split_at_full_stops_but_not_after_abbreviations_or_initials():
    text = "Use panels, e.g. on roofs. Dr. Ali agrees. The U.S. does too. Costs fell 80% since 2010! Why? Because."

    assert split_sentences(text) == [
        "Use panels, e.g. on roofs.",
        "Dr. Ali agrees.",
        "The U.S. does too.",
        "Costs fell 80% since 2010! Why? Because.",
    ]


@pytest.mark.parametrize(
    ("sentence", "point"),
    [
        ("Solar power is cheap.", "Solar power is cheap"),
        ("However, dust lowers the output of panels.", "Dust lowers the output of panels"),
        ("In summary, the sun is a strong resource.", "The sun is a strong resource"),
        ("While there is interest in solar, the plans are still early.", "The plans are still early"),
        (
            "Panels lose power when hot, which is why cooling and cleaning matter in deserts.",
            "Panels lose power when hot",
        ),
        ("What does a panel need to work well in a very hot desert?", "What does a panel need to work well…"),
        ("Is solar cheap?", "Is solar cheap?"),
        ("", ""),
    ],
)
def test_the_plain_rule_makes_note_sized_points(sentence, point):
    assert key_point(sentence) == point


def test_a_plain_point_is_never_longer_than_its_limit():
    long = " ".join(f"word{i}" for i in range(40)) + "."

    assert len(key_point(long).split()) <= 9


def test_beats_follow_the_script_in_reading_order():
    lesson = lesson_from_markdown(SCRIPT, agenda_intro="In this lesson")
    beats = lesson.beats()

    assert [(b.slide, b.part, b.read) for b in beats] == [
        ("cover", -1, 0),
        ("agenda", -1, 0),
        ("part", 0, 1),
        ("part", 0, 2),
        ("part", 1, 0),  # the heading, read before any of its lines
        ("part", 1, 1),
        ("part", 1, 2),
        ("part", 1, 3),
        ("part", 1, 4),
        ("part", 1, 5),
        ("recap", -1, 0),
    ]
    assert beats[1].say == "In this lesson: Introduction and How panels work."
    assert beats[-1].say == "" and beats[-1].hold == RECAP_SECONDS
    # Each line's beat captions what it reads; the last line of a part pauses longer than the others.
    assert all(b.caption == b.say for b in beats if b.slide == "part" and b.read)
    assert beats[3].pause > beats[2].pause


def test_narration_is_every_spoken_beat_in_order():
    lesson = lesson_from_markdown(SCRIPT, agenda_intro="In this lesson")

    assert lesson.narration() == [b.say for b in lesson.beats() if b.say]
    assert lesson.narration()[0] == "The Sun Over Riyadh."


def test_the_agenda_is_left_out_without_an_intro_phrase_or_with_one_part():
    no_phrase = lesson_from_markdown(SCRIPT)
    one_part = lesson_from_markdown("# T\n\n## Only\n\nOne line here.", agenda_intro="In this lesson")

    assert "agenda" not in {b.slide for b in no_phrase.beats()}
    assert "agenda" not in {b.slide for b in one_part.beats()}


def test_three_or_more_parts_are_listed_with_and_before_the_last():
    lesson = lesson_from_markdown(
        "# T\n\n## A\n\nOne two three.\n\n## B\n\nFour five six.\n\n## C\n\nSeven eight nine."
    )

    assert Lesson(lesson.title, lesson.parts, "In this lesson").beats()[1].say == "In this lesson: A, B, and C."


def test_points_can_be_replaced_but_only_one_per_line():
    lesson = lesson_from_markdown(SCRIPT)
    points = [f"Point {i}" for i in range(len(lesson.lines()))]

    replaced = lesson.with_points(points)

    assert [line.point for line in replaced.lines()] == points
    assert [line.text for line in replaced.lines()] == [line.text for line in lesson.lines()]
    with pytest.raises(ValueError, match="key points"):
        lesson.with_points(points[:-1])


def test_the_recap_takes_each_parts_first_point_or_its_heading():
    lesson = lesson_from_markdown(SCRIPT)
    blank_first_part = lesson.with_points(["", ""] + ["Panels"] * 5)

    assert blank_first_part.takeaways() == [INTRODUCTION, "Panels"]
    assert lesson.takeaways(limit=1) == [lesson.parts[0].lines[0].point]
