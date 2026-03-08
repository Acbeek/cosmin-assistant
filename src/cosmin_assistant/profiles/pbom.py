"""PBOM adapter profile with explicit non-PROM limitations."""

from __future__ import annotations

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles.base import BaseProfile
from cosmin_assistant.profiles.constants import CosminBoxKey, MeasurementPropertyKey


class PbomProfile(BaseProfile):
    """Adapter profile for performance-based outcome measures (PBOMs)."""

    @property
    def profile_type(self) -> ProfileType:
        return ProfileType.PBOM

    @property
    def applicable_measurement_properties(self) -> tuple[MeasurementPropertyKey, ...]:
        return (
            MeasurementPropertyKey.CONTENT_VALIDITY,
            MeasurementPropertyKey.STRUCTURAL_VALIDITY,
            MeasurementPropertyKey.INTERNAL_CONSISTENCY,
            MeasurementPropertyKey.RELIABILITY,
            MeasurementPropertyKey.MEASUREMENT_ERROR,
            MeasurementPropertyKey.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY,
            MeasurementPropertyKey.RESPONSIVENESS,
        )

    @property
    def applicable_cosmin_boxes(self) -> tuple[CosminBoxKey, ...]:
        return (
            CosminBoxKey.CONTENT_VALIDITY,
            CosminBoxKey.STRUCTURAL_VALIDITY,
            CosminBoxKey.INTERNAL_CONSISTENCY,
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
            "task_protocol",
            "assessor_training",
            "scoring_algorithm",
            "time_interval",
            "setting",
        )

    @property
    def deterministic_rules_available(self) -> tuple[str, ...]:
        return (
            "ROB_WORST_SCORE_COUNTS_V1",
            "ROB_NA_EXCLUSION_V1",
            "MPR_RELIABILITY_PBOM_V1",
            "MPR_MEASUREMENT_ERROR_PBOM_V1",
            "MPR_RESPONSIVENESS_PBOM_V1",
            "MPR_CONSTRUCT_VALIDITY_PBOM_V1",
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
            "target_population_fit",
            "predefined_hypothesis_adequacy",
            "inconsistency_explanation_acceptance",
            "grade_indirectness_judgment",
            "content_validity_expert_appraisal",
            "conflicting_explicit_values_resolution",
        )

    @property
    def unsupported_auto_scoring_areas(self) -> tuple[str, ...]:
        return (
            "prom_development_box_assessment",
            "criterion_validity_gold_standard_comparison",
            "cross_cultural_validity_measurement_invariance",
        )

    @property
    def adaptation_points(self) -> tuple[str, ...]:
        return (
            (
                "PBOM protocols may involve observer scoring not equivalent "
                "to PROM self-report semantics."
            ),
            "Criterion-validity assumptions from PROM workflows are not transferred by default.",
            "Cross-cultural invariance workflows require PBOM-specific reviewer confirmation.",
        )
