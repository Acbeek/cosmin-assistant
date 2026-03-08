"""Provenance primitives for exact markdown evidence traceability."""

from __future__ import annotations

import hashlib
from bisect import bisect_right
from pathlib import Path

from pydantic import Field, model_validator

from cosmin_assistant.models.base import ModelBase, NonEmptyText, StableId


class SpanProvenance(ModelBase):
    """Exact provenance payload for a text span in a markdown source file."""

    file_path: NonEmptyText
    heading_path: tuple[str, ...]
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    raw_text: NonEmptyText

    @model_validator(mode="after")
    def _validate_bounds(self) -> SpanProvenance:
        if self.end_char <= self.start_char:
            msg = "end_char must be greater than start_char"
            raise ValueError(msg)
        if self.end_line < self.start_line:
            msg = "end_line must be greater than or equal to start_line"
            raise ValueError(msg)
        return self


def canonical_file_path(file_path: str | Path) -> str:
    """Return a canonical absolute path string for deterministic provenance."""

    return str(Path(file_path).expanduser().resolve())


def compute_line_start_offsets(text: str) -> tuple[int, ...]:
    """Compute 0-based character offsets for each line start in document text."""

    starts: list[int] = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return tuple(starts)


def line_number_for_char(line_start_offsets: tuple[int, ...], char_index: int) -> int:
    """Resolve a 1-based line number for a 0-based character index."""

    return bisect_right(line_start_offsets, char_index)


def stable_document_id(file_path: str, raw_text: str) -> StableId:
    """Generate deterministic document IDs from canonical path and raw text."""

    digest = hashlib.sha1(f"doc|{file_path}|{raw_text}".encode()).hexdigest()[:16]
    return f"doc.{digest}"


def stable_span_id(
    span_kind: str,
    file_path: str,
    start_char: int,
    end_char: int,
    raw_text: str,
) -> StableId:
    """Generate deterministic span IDs based on location and text payload."""

    canonical = f"{span_kind}|{file_path}|{start_char}|{end_char}|{raw_text}"
    digest = hashlib.sha1(canonical.encode()).hexdigest()[:16]
    return f"{span_kind}.{digest}"


def build_provenance(
    *,
    file_path: str,
    heading_path: tuple[str, ...],
    start_char: int,
    end_char: int,
    raw_text: str,
    line_start_offsets: tuple[int, ...],
) -> SpanProvenance:
    """Build provenance payload with line and character span tracking."""

    start_line = line_number_for_char(line_start_offsets, start_char)
    end_line = line_number_for_char(line_start_offsets, end_char - 1)
    return SpanProvenance(
        file_path=file_path,
        heading_path=heading_path,
        start_char=start_char,
        end_char=end_char,
        start_line=start_line,
        end_line=end_line,
        raw_text=raw_text,
    )
