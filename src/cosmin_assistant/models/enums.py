"""Typed enums for COSMIN assistant core model layer."""

from __future__ import annotations

from enum import StrEnum


class ProfileType(StrEnum):
    """Instrument profile type."""

    PROM = "prom"
    PBOM = "pbom"
    ACTIVITY_MEASURE = "activity_measure"


class InstrumentType(StrEnum):
    """Deterministic instrument-type classification used for COSMIN activation gates."""

    PROM = "prom"
    PBOM = "pbom"
    PERFORMANCE_TEST = "performance_test"
    MIXED_OR_UNKNOWN = "mixed_or_unknown"


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


class PropertyActivationStatus(StrEnum):
    """Scientific eligibility/activation status before COSMIN box/rating execution."""

    DIRECT_CURRENT_STUDY_EVIDENCE = "direct_current_study_evidence"
    COMPARATOR_BASED_EVIDENCE = "comparator_based_evidence"
    INDIRECT_ONLY = "indirect_only"
    INTERPRETABILITY_ONLY = "interpretability_only"
    MEASUREMENT_ERROR_SUPPORT_ONLY = "measurement_error_support_only"
    NOT_ASSESSED_IN_CURRENT_STUDY = "not_assessed_in_current_study"
    NOT_APPLICABLE_FOR_INSTRUMENT_TYPE = "not_applicable_for_instrument_type"
    REVIEWER_REQUIRED = "reviewer_required"
