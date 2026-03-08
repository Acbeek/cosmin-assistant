"""PROM reference profile with the broadest deterministic coverage."""

from __future__ import annotations

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles.base import BaseProfile
from cosmin_assistant.profiles.constants import CosminBoxKey, MeasurementPropertyKey


class PromProfile(BaseProfile):
    """Reference profile for patient-reported outcome measures (PROMs)."""

    @property
    def profile_type(self) -> ProfileType:
        return ProfileType.PROM

    @property
    def applicable_measurement_properties(self) -> tuple[MeasurementPropertyKey, ...]:
        return (
            MeasurementPropertyKey.CONTENT_VALIDITY,
            MeasurementPropertyKey.STRUCTURAL_VALIDITY,
            MeasurementPropertyKey.INTERNAL_CONSISTENCY,
            MeasurementPropertyKey.CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE,
            MeasurementPropertyKey.RELIABILITY,
            MeasurementPropertyKey.MEASUREMENT_ERROR,
            MeasurementPropertyKey.CRITERION_VALIDITY,
            MeasurementPropertyKey.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY,
            MeasurementPropertyKey.RESPONSIVENESS,
        )

    @property
    def applicable_cosmin_boxes(self) -> tuple[CosminBoxKey, ...]:
        return (
            CosminBoxKey.PROM_DEVELOPMENT,
            CosminBoxKey.CONTENT_VALIDITY,
            CosminBoxKey.STRUCTURAL_VALIDITY,
            CosminBoxKey.INTERNAL_CONSISTENCY,
            CosminBoxKey.CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE,
            CosminBoxKey.RELIABILITY,
            CosminBoxKey.MEASUREMENT_ERROR,
            CosminBoxKey.CRITERION_VALIDITY,
            CosminBoxKey.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY,
            CosminBoxKey.RESPONSIVENESS,
        )

    @property
    def required_extraction_fields(self) -> tuple[str, ...]:
        return (
            "study_design",
            "population_description",
            "sample_size",
            "instrument_name",
            "instrument_version",
            "subscale",
            "statistical_method",
            "time_interval",
            "language",
            "country",
            "construct_definition",
            "target_population",
        )

    @property
    def deterministic_rules_available(self) -> tuple[str, ...]:
        return (
            "ROB_WORST_SCORE_COUNTS_V1",
            "ROB_NA_EXCLUSION_V1",
            "MPR_STRUCTURAL_VALIDITY_PROM_V1",
            "MPR_INTERNAL_CONSISTENCY_PROM_V1",
            "MPR_RELIABILITY_PROM_V1",
            "MPR_MEASUREMENT_ERROR_PROM_V1",
            "MPR_CROSS_CULTURAL_PROM_V1",
            "MPR_CRITERION_VALIDITY_PROM_V1",
            "MPR_CONSTRUCT_VALIDITY_PROM_V1",
            "MPR_RESPONSIVENESS_PROM_V1",
            "SYN_ALL_SUFFICIENT_TO_PLUS_V1",
            "SYN_ALL_INSUFFICIENT_TO_MINUS_V1",
            "SYN_UNEXPLAINED_MIXED_TO_PLUSMINUS_V1",
            "SYN_INSUFFICIENT_INFORMATION_TO_QUESTION_V1",
            "GR_START_HIGH_V1",
            "GR_DOWNGRADE_ROB_V1",
            "GR_DOWNGRADE_INCONSISTENCY_V1",
            "GR_DOWNGRADE_IMPRECISION_V1",
            "GR_FLOOR_VERY_LOW_V1",
        )

    @property
    def reviewer_required_decisions(self) -> tuple[str, ...]:
        return (
            "target_population_fit",
            "predefined_hypothesis_adequacy",
            "comparator_gold_standard_suitability",
            "inconsistency_explanation_acceptance",
            "grade_indirectness_judgment",
            "content_validity_expert_appraisal",
            "conflicting_explicit_values_resolution",
        )

    @property
    def unsupported_auto_scoring_areas(self) -> tuple[str, ...]:
        return ()

    @property
    def adaptation_points(self) -> tuple[str, ...]:
        return ()
