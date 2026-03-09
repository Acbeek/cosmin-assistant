"""Typed models for modified GRADE certainty assessment."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from cosmin_assistant.models import (
    EvidenceCertaintyLevel,
    ModelBase,
    NonEmptyText,
    StableId,
)


class ModifiedGradeDomain(StrEnum):
    """Supported modified-GRADE downgrade domains."""

    RISK_OF_BIAS = "risk_of_bias"
    INCONSISTENCY = "inconsistency"
    IMPRECISION = "imprecision"
    INDIRECTNESS = "indirectness"


class DowngradeSeverity(StrEnum):
    """Downgrade severity labels aligned to modified GRADE."""

    NONE = "none"
    SERIOUS = "serious"
    VERY_SERIOUS = "very_serious"
    EXTREMELY_SERIOUS = "extremely_serious"


class DomainDowngradeInput(ModelBase):
    """Input assessment for one modified-GRADE domain."""

    domain: ModifiedGradeDomain
    severity: DowngradeSeverity
    reason: str | None = None
    evidence_span_ids: tuple[StableId, ...] = ()
    explanation: str | None = None

    @model_validator(mode="after")
    def _validate_reason_and_explanation(self) -> DomainDowngradeInput:
        if self.severity is DowngradeSeverity.NONE:
            return self

        if not self.reason or not self.reason.strip():
            msg = "reason is required when downgrade severity is not 'none'"
            raise ValueError(msg)
        if not self.explanation or not self.explanation.strip():
            msg = "explanation is required when downgrade severity is not 'none'"
            raise ValueError(msg)
        if not self.evidence_span_ids:
            msg = "evidence_span_ids are required when downgrade severity is not 'none'"
            raise ValueError(msg)
        return self


class DomainDowngradeRecord(ModelBase):
    """Applied domain downgrade with certainty transition metadata."""

    id: StableId
    domain: ModifiedGradeDomain
    severity: DowngradeSeverity
    downgrade_steps: int = Field(ge=1, le=3)
    reason: NonEmptyText
    evidence_span_ids: tuple[StableId, ...] = Field(min_length=1)
    explanation: NonEmptyText
    certainty_before: EvidenceCertaintyLevel
    certainty_after: EvidenceCertaintyLevel


class ModifiedGradeResult(ModelBase):
    """Final modified-GRADE certainty result for one synthesis aggregate."""

    id: StableId
    synthesis_id: StableId
    measurement_property: NonEmptyText
    starting_certainty: EvidenceCertaintyLevel
    final_certainty: EvidenceCertaintyLevel
    total_downgrade_steps: int = Field(ge=0)
    total_sample_size: int | None = Field(default=None, ge=0)
    domain_decisions: tuple[DomainDowngradeInput, ...] = Field(min_length=4, max_length=4)
    downgrade_records: tuple[DomainDowngradeRecord, ...] = ()
    evidence_span_ids: tuple[StableId, ...] = ()
    explanation: NonEmptyText
