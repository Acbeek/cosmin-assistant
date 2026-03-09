"""Tests for markdown parsing, stable IDs, and provenance traceability."""

from __future__ import annotations

from pathlib import Path

from cosmin_assistant.extract import parse_markdown_file

_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "markdown" / "nested_repeated_headings.md"
)


def test_parser_preserves_heading_hierarchy_with_repeated_titles() -> None:
    parsed = parse_markdown_file(_FIXTURE_PATH)

    heading_titles = [heading.title for heading in parsed.headings]
    assert heading_titles == [
        "Study Overview",
        "Methods",
        "Participants",
        "Participants",
        "Methods",
        "Results",
        "Subgroup Analysis",
    ]

    first_participants = parsed.headings[2]
    second_participants = parsed.headings[3]
    repeated_methods = parsed.headings[4]

    assert first_participants.heading_path == (
        "Study Overview",
        "Methods",
        "Participants",
    )
    assert second_participants.heading_path == (
        "Study Overview",
        "Methods",
        "Participants",
    )
    assert repeated_methods.heading_path == (
        "Study Overview",
        "Methods",
    )

    assert first_participants.id != second_participants.id


def test_paragraph_and_sentence_spans_trace_to_exact_text_locations() -> None:
    parsed = parse_markdown_file(_FIXTURE_PATH)

    for paragraph in parsed.paragraphs:
        start = paragraph.provenance.start_char
        end = paragraph.provenance.end_char
        assert parsed.raw_text[start:end] == paragraph.provenance.raw_text
        assert paragraph.provenance.file_path == str(_FIXTURE_PATH.resolve())
        assert paragraph.provenance.start_line <= paragraph.provenance.end_line

    for sentence in parsed.sentences:
        start = sentence.provenance.start_char
        end = sentence.provenance.end_char
        assert parsed.raw_text[start:end] == sentence.provenance.raw_text
        assert sentence.provenance.file_path == str(_FIXTURE_PATH.resolve())
        assert sentence.provenance.start_line <= sentence.provenance.end_line


def test_span_ids_are_stable_across_repeated_parses() -> None:
    parsed_a = parse_markdown_file(_FIXTURE_PATH)
    parsed_b = parse_markdown_file(_FIXTURE_PATH)

    assert parsed_a.id == parsed_b.id
    assert [heading.id for heading in parsed_a.headings] == [
        heading.id for heading in parsed_b.headings
    ]
    assert [paragraph.id for paragraph in parsed_a.paragraphs] == [
        paragraph.id for paragraph in parsed_b.paragraphs
    ]
    assert [sentence.id for sentence in parsed_a.sentences] == [
        sentence.id for sentence in parsed_b.sentences
    ]


def test_provenance_contains_heading_path_and_line_character_spans() -> None:
    parsed = parse_markdown_file(_FIXTURE_PATH)

    assert parsed.headings[0].provenance.start_line == 1
    assert parsed.headings[0].provenance.heading_path == ("Study Overview",)

    repeated_methods = parsed.headings[4]
    assert repeated_methods.provenance.heading_path == (
        "Study Overview",
        "Methods",
    )

    methods_paragraph = parsed.paragraphs[4]
    assert methods_paragraph.heading_path == (
        "Study Overview",
        "Methods",
    )
    assert methods_paragraph.provenance.start_char < methods_paragraph.provenance.end_char
