"""Typed enums for COSMIN assistant core model layer."""

from __future__ import annotations

from enum import StrEnum


class ProfileType(StrEnum):
    """Instrument profile type."""

    PROM = "prom"
    PBOM = "pbom"
    ACTIVITY_MEASURE = "activity_measure"


class CosminItemRating(StrEnum):
    """COSMIN item-level methodological quality rating."""

    VERY_GOOD = "very_good"
    ADEQUATE = "adequate"
    DOUBTFUL = "doubtful"
    INADEQUATE = "inadequate"
    NOT_APPLICABLE = "not_applicable"


class CosminBoxRating(StrEnum):
    """COSMIN box-level methodological quality rating."""

    VERY_GOOD = "very_good"
    ADEQUATE = "adequate"
    DOUBTFUL = "doubtful"
    INADEQUATE = "inadequate"
    INDETERMINATE = "indeterminate"


class MeasurementPropertyRating(StrEnum):
    """Study-level and synthesis-level measurement property ratings."""

    SUFFICIENT = "+"
    INSUFFICIENT = "-"
    INDETERMINATE = "?"
    INCONSISTENT = "±"


class EvidenceCertaintyLevel(StrEnum):
    """Modified GRADE evidence certainty levels."""

    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"


class UncertaintyStatus(StrEnum):
    """Explicit uncertainty state for extracted or derived objects."""

    CERTAIN = "certain"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    MISSING_EVIDENCE = "missing_evidence"
    REVIEWER_REQUIRED = "reviewer_required"


class ReviewerDecisionStatus(StrEnum):
    """Explicit status of reviewer-facing decisions."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    OVERRIDDEN = "overridden"
