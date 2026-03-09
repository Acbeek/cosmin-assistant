"""Profile-domain constants for measurement properties and COSMIN boxes."""

from __future__ import annotations

from enum import StrEnum


class ProfileCapabilityStatus(StrEnum):
    """Capability status for profile-specific method support declarations."""

    REUSED = "reused"
    ADAPTED = "adapted"
    REVIEWER_REQUIRED = "reviewer_required"
    UNSUPPORTED = "unsupported"


class CosminReviewStepKey(StrEnum):
    """Ordered COSMIN review steps represented in profile capability matrices."""

    STEP_1_EXTRACTION_AND_NORMALIZATION = "step_1_extraction_and_normalization"
    STEP_2_RISK_OF_BIAS = "step_2_risk_of_bias_assessment"
    STEP_3_STUDY_LEVEL_RATING = "step_3_study_level_measurement_property_rating"
    STEP_4_SYNTHESIS = "step_4_synthesis_across_studies"
    STEP_5_MODIFIED_GRADE = "step_5_modified_grade_certainty"
    STEP_6_TABLE_BUILDING = "step_6_table_building_and_exports"
    STEP_7_INTERPRETATION_AND_RECOMMENDATION = "step_7_interpretation_and_recommendation"


class TableTemplateKey(StrEnum):
    """Template keys for profile-specific table column availability metadata."""

    TEMPLATE_5 = "template_5"
    TEMPLATE_7 = "template_7"
    TEMPLATE_8 = "template_8"


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
