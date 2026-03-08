"""Activity-monitor adapter profile with explicit sensor-domain limitations."""

from __future__ import annotations

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles.base import BaseProfile
from cosmin_assistant.profiles.constants import CosminBoxKey, MeasurementPropertyKey


class ActivityMonitorProfile(BaseProfile):
    """Adapter profile for activity monitor and sensor-based outcome instruments."""

    @property
    def profile_type(self) -> ProfileType:
        return ProfileType.ACTIVITY_MEASURE

    @property
    def applicable_measurement_properties(self) -> tuple[MeasurementPropertyKey, ...]:
        return (
            MeasurementPropertyKey.CONTENT_VALIDITY,
            MeasurementPropertyKey.RELIABILITY,
            MeasurementPropertyKey.MEASUREMENT_ERROR,
            MeasurementPropertyKey.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY,
            MeasurementPropertyKey.RESPONSIVENESS,
        )

    @property
    def applicable_cosmin_boxes(self) -> tuple[CosminBoxKey, ...]:
        return (
            CosminBoxKey.CONTENT_VALIDITY,
            CosminBoxKey.RELIABILITY,
            CosminBoxKey.MEASUREMENT_ERROR,
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
            "device_model",
            "firmware_version",
            "wear_location",
            "sampling_frequency_hz",
            "epoch_length_seconds",
            "nonwear_algorithm",
            "calibration_method",
            "cut_points_reference",
        )

    @property
    def deterministic_rules_available(self) -> tuple[str, ...]:
        return (
            "ROB_WORST_SCORE_COUNTS_V1",
            "ROB_NA_EXCLUSION_V1",
            "MPR_RELIABILITY_ACTIVITY_V1",
            "MPR_MEASUREMENT_ERROR_ACTIVITY_V1",
            "MPR_RESPONSIVENESS_ACTIVITY_V1",
            "MPR_INDETERMINATE_ON_MISSING_EVIDENCE_V1",
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
            "non_prom_adaptation_equivalence",
            "sensor_signal_processing_appropriateness",
            "device_generation_compatibility",
            "target_population_fit",
            "predefined_hypothesis_adequacy",
            "grade_indirectness_judgment",
            "content_validity_expert_appraisal",
            "conflicting_explicit_values_resolution",
        )

    @property
    def unsupported_auto_scoring_areas(self) -> tuple[str, ...]:
        return (
            "prom_development_box_assessment",
            "structural_validity",
            "internal_consistency",
            "criterion_validity_gold_standard_comparison",
            "cross_cultural_validity_measurement_invariance",
        )

    @property
    def adaptation_points(self) -> tuple[str, ...]:
        return (
            "Sensor firmware and signal-processing changes can alter comparability across studies.",
            (
                "PROM-based structural validity and internal consistency workflows "
                "do not transfer directly."
            ),
            (
                "Gold-standard assumptions for criterion validity require "
                "activity-domain reviewer judgment."
            ),
        )
