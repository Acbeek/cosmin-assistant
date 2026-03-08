"""Markdown extraction and provenance foundation."""

from cosmin_assistant.extract.context_extractor import (
    extract_context_from_markdown_file,
    extract_context_from_parsed_document,
)
from cosmin_assistant.extract.context_models import (
    ArticleContextExtractionResult,
    ContextFieldExtraction,
    ContextValueCandidate,
    FieldDetectionStatus,
    InstrumentContextExtractionResult,
    StudyContextExtractionResult,
    SubsampleExtraction,
)
from cosmin_assistant.extract.markdown_parser import (
    parse_markdown_file,
    parse_markdown_text,
    read_markdown_file,
)
from cosmin_assistant.extract.provenance import SpanProvenance
from cosmin_assistant.extract.spans import (
    HeadingRecord,
    ParagraphRecord,
    ParsedMarkdownDocument,
    SentenceRecord,
)

__all__ = [
    "ArticleContextExtractionResult",
    "ContextFieldExtraction",
    "ContextValueCandidate",
    "FieldDetectionStatus",
    "HeadingRecord",
    "InstrumentContextExtractionResult",
    "ParagraphRecord",
    "ParsedMarkdownDocument",
    "SentenceRecord",
    "SpanProvenance",
    "StudyContextExtractionResult",
    "SubsampleExtraction",
    "extract_context_from_markdown_file",
    "extract_context_from_parsed_document",
    "parse_markdown_file",
    "parse_markdown_text",
    "read_markdown_file",
]
