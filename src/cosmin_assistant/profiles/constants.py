"""Profile-domain constants for measurement properties and COSMIN boxes."""

from __future__ import annotations

from enum import StrEnum


class MeasurementPropertyKey(StrEnum):
    """Measurement-property keys used by profile capability metadata."""

    CONTENT_VALIDITY = "content_validity"
    STRUCTURAL_VALIDITY = "structural_validity"
    INTERNAL_CONSISTENCY = "internal_consistency"
    CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE = (
        "cross_cultural_validity_measurement_invariance"
    )
    RELIABILITY = "reliability"
    MEASUREMENT_ERROR = "measurement_error"
    CRITERION_VALIDITY = "criterion_validity"
    HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY = "hypotheses_testing_for_construct_validity"
    RESPONSIVENESS = "responsiveness"


class CosminBoxKey(StrEnum):
    """COSMIN RoB box keys used by profile capability metadata."""

    PROM_DEVELOPMENT = "prom_development"
    CONTENT_VALIDITY = "content_validity"
    STRUCTURAL_VALIDITY = "structural_validity"
    INTERNAL_CONSISTENCY = "internal_consistency"
    CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE = (
        "cross_cultural_validity_measurement_invariance"
    )
    RELIABILITY = "reliability"
    MEASUREMENT_ERROR = "measurement_error"
    CRITERION_VALIDITY = "criterion_validity"
    HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY = "hypotheses_testing_for_construct_validity"
    RESPONSIVENESS = "responsiveness"
