"""Typed models for first-pass study and instrument context extraction."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from cosmin_assistant.models.base import ModelBase, NonEmptyText, StableId


class FieldDetectionStatus(StrEnum):
    """Detection status for a context field extraction."""

    DETECTED = "detected"
    AMBIGUOUS = "ambiguous"
    NOT_REPORTED = "not_reported"
    NOT_DETECTED = "not_detected"


class ContextValueCandidate(ModelBase):
    """One candidate value with raw evidence and normalized representation."""

    id: StableId
    raw_text: NonEmptyText
    normalized_value: str | int | tuple[str, ...] | None
    evidence_span_ids: Annotated[tuple[StableId, ...], Field(min_length=1)]


class ContextFieldExtraction(ModelBase):
    """Extraction payload for one semantic field."""

    id: StableId
    field_name: NonEmptyText
    status: FieldDetectionStatus
    candidates: tuple[ContextValueCandidate, ...] = ()

    @model_validator(mode="after")
    def _validate_status_candidate_shape(self) -> ContextFieldExtraction:
        candidate_count = len(self.candidates)
        if self.status is FieldDetectionStatus.DETECTED and candidate_count != 1:
            msg = "detected status requires exactly one candidate"
            raise ValueError(msg)
        if self.status is FieldDetectionStatus.AMBIGUOUS and candidate_count < 2:
            msg = "ambiguous status requires at least two candidates"
            raise ValueError(msg)
        if self.status is FieldDetectionStatus.NOT_REPORTED and candidate_count < 1:
            msg = "not_reported status requires at least one supporting candidate"
            raise ValueError(msg)
        if self.status is FieldDetectionStatus.NOT_DETECTED and candidate_count != 0:
            msg = "not_detected status requires zero candidates"
            raise ValueError(msg)
        return self


class SubsampleExtraction(ModelBase):
    """Subsample context supporting multiple subgroup sample sizes per article."""

    id: StableId
    label_raw: NonEmptyText
    label_normalized: NonEmptyText
    sample_size_raw: NonEmptyText
    sample_size_normalized: int = Field(ge=0)
    evidence_span_ids: Annotated[tuple[StableId, ...], Field(min_length=1)]


class StudyContextExtractionResult(ModelBase):
    """Study-context extraction result for one study unit."""

    id: StableId
    article_id: StableId
    study_id: StableId
    study_design: ContextFieldExtraction
    sample_sizes: ContextFieldExtraction
    construct_field: ContextFieldExtraction = Field(
        validation_alias="construct",
        serialization_alias="construct",
    )
    target_population: ContextFieldExtraction
    language: ContextFieldExtraction
    country: ContextFieldExtraction
    measurement_properties_mentioned: ContextFieldExtraction
    subsamples: tuple[SubsampleExtraction, ...] = ()


class InstrumentContextExtractionResult(ModelBase):
    """Instrument-context extraction result for one instrument unit."""

    id: StableId
    article_id: StableId
    study_id: StableId
    instrument_id: StableId
    instrument_name: ContextFieldExtraction
    instrument_version: ContextFieldExtraction
    subscale: ContextFieldExtraction
    construct_field: ContextFieldExtraction = Field(
        validation_alias="construct",
        serialization_alias="construct",
    )
    target_population: ContextFieldExtraction


class ArticleContextExtractionResult(ModelBase):
    """Article-level extraction output containing study and instrument contexts."""

    id: StableId
    article_id: StableId
    file_path: NonEmptyText
    study_contexts: tuple[StudyContextExtractionResult, ...]
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...]
