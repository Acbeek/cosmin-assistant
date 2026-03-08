"""Structured markdown span records for extraction and audit stages."""

from __future__ import annotations

from pydantic import Field

from cosmin_assistant.extract.provenance import SpanProvenance
from cosmin_assistant.models.base import ModelBase, NonEmptyText, StableId


class HeadingRecord(ModelBase):
    """Detected markdown heading with hierarchy metadata and provenance."""

    id: StableId
    level: int = Field(ge=1, le=6)
    title: NonEmptyText
    parent_heading_id: StableId | None = None
    heading_path: tuple[str, ...]
    heading_path_ids: tuple[StableId, ...]
    heading_index: int = Field(ge=0)
    provenance: SpanProvenance


class ParagraphRecord(ModelBase):
    """Detected paragraph block mapped to heading context and provenance."""

    id: StableId
    heading_id: StableId | None = None
    heading_path: tuple[str, ...]
    heading_path_ids: tuple[StableId, ...]
    paragraph_index: int = Field(ge=0)
    provenance: SpanProvenance


class SentenceRecord(ModelBase):
    """Detected sentence span nested within a paragraph and heading context."""

    id: StableId
    parent_paragraph_id: StableId
    heading_id: StableId | None = None
    heading_path: tuple[str, ...]
    heading_path_ids: tuple[StableId, ...]
    sentence_index: int = Field(ge=0)
    provenance: SpanProvenance


class ParsedMarkdownDocument(ModelBase):
    """Parsed markdown file with heading, paragraph, and sentence spans."""

    id: StableId
    file_path: NonEmptyText
    raw_text: str
    headings: tuple[HeadingRecord, ...]
    paragraphs: tuple[ParagraphRecord, ...]
    sentences: tuple[SentenceRecord, ...]
