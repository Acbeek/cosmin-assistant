"""Typed models for first-pass study and instrument context extraction."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from cosmin_assistant.models.base import ModelBase, NonEmptyText, StableId
from cosmin_assistant.models.enums import InstrumentType


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


class SampleSizeRole(StrEnum):
    """Role label for extracted sample-size values."""

    ENROLLMENT = "enrollment"
    VALIDATION = "validation"
    PILOT = "pilot"
    RETEST = "retest"
    ANALYZED = "analyzed"
    LIMB_LEVEL = "limb_level"
    OTHER = "other"


class InstrumentContextRole(StrEnum):
    """Role of an extracted instrument in the current article context."""

    TARGET_UNDER_APPRAISAL = "target_under_appraisal"
    CO_PRIMARY_OUTCOME_INSTRUMENT = "co_primary_outcome_instrument"
    SECONDARY_OUTCOME_INSTRUMENT = "secondary_outcome_instrument"
    COMPARATOR_ONLY = "comparator_only"
    BACKGROUND_ONLY = "background_only"
    COMPARATOR = "comparator"
    ADDITIONAL = "additional"


class StudyIntent(StrEnum):
    """High-level study-intent classification used for instrument-role routing."""

    PSYCHOMETRIC_VALIDATION = "psychometric_validation_appraisal_study"
    LONGITUDINAL_OUTCOME = "longitudinal_outcome_study"
    MIXED = "mixed_study"


class SampleSizeObservation(ModelBase):
    """Role-aware sample-size extraction object with provenance links."""

    id: StableId
    role: SampleSizeRole
    sample_size_raw: NonEmptyText
    sample_size_normalized: int = Field(ge=0)
    unit: str | None = None
    evidence_span_ids: Annotated[tuple[StableId, ...], Field(min_length=1)]


class StudyContextExtractionResult(ModelBase):
    """Study-context extraction result for one study unit."""

    id: StableId
    article_id: StableId
    study_id: StableId
    study_design: ContextFieldExtraction
    sample_sizes: ContextFieldExtraction
    sample_size_observations: tuple[SampleSizeObservation, ...] = ()
    validation_sample_n: ContextFieldExtraction | None = None
    pilot_sample_n: ContextFieldExtraction | None = None
    retest_sample_n: ContextFieldExtraction | None = None
    follow_up_schedule: ContextFieldExtraction
    follow_up_interval: ContextFieldExtraction | None = None
    construct_field: ContextFieldExtraction = Field(
        validation_alias="construct",
        serialization_alias="construct",
    )
    target_population: ContextFieldExtraction
    recruitment_setting: ContextFieldExtraction | None = None
    language: ContextFieldExtraction
    country: ContextFieldExtraction
    measurement_properties_mentioned: ContextFieldExtraction
    measurement_properties_background: ContextFieldExtraction
    measurement_properties_interpretability: ContextFieldExtraction
    measurement_properties_not_assessed: ContextFieldExtraction | None = None
    study_intent: StudyIntent = StudyIntent.MIXED
    study_intent_rationale: str | None = None
    study_intent_evidence_span_ids: tuple[StableId, ...] = ()
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
    instrument_type: InstrumentType = InstrumentType.MIXED_OR_UNKNOWN
    instrument_type_rationale: str | None = None
    instrument_type_evidence_span_ids: tuple[StableId, ...] = ()
    instrument_role: InstrumentContextRole = InstrumentContextRole.ADDITIONAL
    role_rationale: str | None = None
    role_evidence_span_ids: tuple[StableId, ...] = ()


class ArticleContextExtractionResult(ModelBase):
    """Article-level extraction output containing study and instrument contexts."""

    id: StableId
    article_id: StableId
    file_path: NonEmptyText
    study_contexts: tuple[StudyContextExtractionResult, ...]
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...]
    target_instrument_id: StableId | None = None
    comparator_instrument_ids: tuple[StableId, ...] = ()
