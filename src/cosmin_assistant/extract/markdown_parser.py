"""Markdown parsing foundation with stable spans and provenance tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cosmin_assistant.extract.provenance import (
    build_provenance,
    canonical_file_path,
    compute_line_start_offsets,
    stable_document_id,
    stable_span_id,
)
from cosmin_assistant.extract.spans import (
    HeadingRecord,
    ParagraphRecord,
    ParsedMarkdownDocument,
    SentenceRecord,
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SENTENCE_RE = re.compile(r".+?(?:(?<!\d)[.!?](?!\d)|$)", re.DOTALL)


@dataclass(frozen=True)
class _LineRecord:
    line_no: int
    start_char: int
    end_char: int
    text: str


def read_markdown_file(file_path: str | Path) -> str:
    """Read markdown file contents as UTF-8 text."""

    return Path(file_path).read_text(encoding="utf-8")


def parse_markdown_file(file_path: str | Path) -> ParsedMarkdownDocument:
    """Parse a markdown file into heading, paragraph, and sentence spans."""

    canonical_path = canonical_file_path(file_path)
    raw_text = read_markdown_file(file_path)
    return parse_markdown_text(raw_text, canonical_path)


def parse_markdown_text(raw_text: str, file_path: str | Path) -> ParsedMarkdownDocument:
    """Parse markdown text with a known source path into structured spans."""

    canonical_path = canonical_file_path(file_path)
    line_starts = compute_line_start_offsets(raw_text)
    lines = _line_records(raw_text)

    headings: list[HeadingRecord] = []
    paragraphs: list[ParagraphRecord] = []
    sentences: list[SentenceRecord] = []

    heading_stack: list[HeadingRecord] = []
    paragraph_start: int | None = None
    paragraph_end: int | None = None
    paragraph_heading_path: tuple[str, ...] = ()
    paragraph_heading_path_ids: tuple[str, ...] = ()
    inside_code_fence = False

    def flush_paragraph() -> None:
        nonlocal paragraph_start, paragraph_end

        if paragraph_start is None or paragraph_end is None:
            paragraph_start = None
            paragraph_end = None
            return

        paragraph_text = raw_text[paragraph_start:paragraph_end]
        if not paragraph_text.strip():
            paragraph_start = None
            paragraph_end = None
            return

        paragraph_id = stable_span_id(
            "par",
            canonical_path,
            paragraph_start,
            paragraph_end,
            paragraph_text,
        )
        paragraph_record = ParagraphRecord(
            id=paragraph_id,
            heading_id=paragraph_heading_path_ids[-1] if paragraph_heading_path_ids else None,
            heading_path=paragraph_heading_path,
            heading_path_ids=paragraph_heading_path_ids,
            paragraph_index=len(paragraphs),
            provenance=build_provenance(
                file_path=canonical_path,
                heading_path=paragraph_heading_path,
                start_char=paragraph_start,
                end_char=paragraph_end,
                raw_text=paragraph_text,
                line_start_offsets=line_starts,
            ),
        )
        paragraphs.append(paragraph_record)
        sentences.extend(
            _sentence_records(
                paragraph_record,
                canonical_path,
                raw_text,
                line_starts,
            )
        )

        paragraph_start = None
        paragraph_end = None

    for line in lines:
        stripped = line.text.strip()

        if _is_code_fence_line(stripped):
            flush_paragraph()
            inside_code_fence = not inside_code_fence
            continue

        if inside_code_fence:
            continue

        heading_match = _HEADING_RE.match(line.text)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            while len(heading_stack) >= level:
                heading_stack.pop()

            heading_id = stable_span_id(
                "hdg",
                canonical_path,
                line.start_char,
                line.end_char,
                line.text,
            )
            heading_path = tuple([item.title for item in heading_stack] + [title])
            heading_path_ids = tuple([item.id for item in heading_stack] + [heading_id])
            heading_record = HeadingRecord(
                id=heading_id,
                level=level,
                title=title,
                parent_heading_id=heading_stack[-1].id if heading_stack else None,
                heading_path=heading_path,
                heading_path_ids=heading_path_ids,
                heading_index=len(headings),
                provenance=build_provenance(
                    file_path=canonical_path,
                    heading_path=heading_path,
                    start_char=line.start_char,
                    end_char=line.end_char,
                    raw_text=line.text,
                    line_start_offsets=line_starts,
                ),
            )
            headings.append(heading_record)
            heading_stack.append(heading_record)
            continue

        if not stripped:
            flush_paragraph()
            continue

        if paragraph_start is None:
            paragraph_start = line.start_char
            paragraph_heading_path = tuple(item.title for item in heading_stack)
            paragraph_heading_path_ids = tuple(item.id for item in heading_stack)
        paragraph_end = line.end_char

    flush_paragraph()

    return ParsedMarkdownDocument(
        id=stable_document_id(canonical_path, raw_text),
        file_path=canonical_path,
        raw_text=raw_text,
        headings=tuple(headings),
        paragraphs=tuple(paragraphs),
        sentences=tuple(sentences),
    )


def _line_records(raw_text: str) -> tuple[_LineRecord, ...]:
    """Split raw text into deterministic line records with character offsets."""

    records: list[_LineRecord] = []
    offset = 0
    for line_no, raw_line in enumerate(raw_text.splitlines(keepends=True), start=1):
        text = raw_line[:-1] if raw_line.endswith("\n") else raw_line
        start_char = offset
        end_char = start_char + len(text)
        records.append(
            _LineRecord(
                line_no=line_no,
                start_char=start_char,
                end_char=end_char,
                text=text,
            )
        )
        offset += len(raw_line)

    if not records and raw_text == "":
        return tuple()

    return tuple(records)


def _is_code_fence_line(stripped_line: str) -> bool:
    return stripped_line.startswith("```") or stripped_line.startswith("~~~")


def _sentence_records(
    paragraph: ParagraphRecord,
    canonical_path: str,
    raw_text: str,
    line_starts: tuple[int, ...],
) -> list[SentenceRecord]:
    """Split paragraph text into sentence records with exact provenance spans."""

    sentences: list[SentenceRecord] = []
    paragraph_text = paragraph.provenance.raw_text
    paragraph_start = paragraph.provenance.start_char

    for match in _SENTENCE_RE.finditer(paragraph_text):
        candidate = match.group(0)
        leading_ws = len(candidate) - len(candidate.lstrip())
        trailing_ws = len(candidate) - len(candidate.rstrip())
        start_rel = match.start() + leading_ws
        end_rel = match.end() - trailing_ws

        if end_rel <= start_rel:
            continue

        sentence_start = paragraph_start + start_rel
        sentence_end = paragraph_start + end_rel
        sentence_text = raw_text[sentence_start:sentence_end]

        if not sentence_text.strip():
            continue

        sentence_id = stable_span_id(
            "sen",
            canonical_path,
            sentence_start,
            sentence_end,
            sentence_text,
        )
        sentences.append(
            SentenceRecord(
                id=sentence_id,
                parent_paragraph_id=paragraph.id,
                heading_id=paragraph.heading_id,
                heading_path=paragraph.heading_path,
                heading_path_ids=paragraph.heading_path_ids,
                sentence_index=len(sentences),
                provenance=build_provenance(
                    file_path=canonical_path,
                    heading_path=paragraph.heading_path,
                    start_char=sentence_start,
                    end_char=sentence_end,
                    raw_text=sentence_text,
                    line_start_offsets=line_starts,
                ),
            )
        )

    return sentences
