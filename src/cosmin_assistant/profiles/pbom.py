"""PBOM adapter profile with explicit non-PROM limitations."""

from __future__ import annotations

from collections.abc import Mapping

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles.base import BaseProfile
from cosmin_assistant.profiles.constants import (
    CosminBoxKey,
    CosminReviewStepKey,
    MeasurementPropertyKey,
    ProfileCapabilityStatus,
    TableTemplateKey,
)


class PbomProfile(BaseProfile):
    """Adapter profile for performance-based outcome measures (PBOMs)."""

    @property
    def profile_type(self) -> ProfileType:
        return ProfileType.PBOM

    @property
    def measurement_property_capabilities(
        self,
    ) -> Mapping[MeasurementPropertyKey, ProfileCapabilityStatus]:
        return {
            MeasurementPropertyKey.CONTENT_VALIDITY: ProfileCapabilityStatus.REVIEWER_REQUIRED,
            MeasurementPropertyKey.STRUCTURAL_VALIDITY: ProfileCapabilityStatus.REVIEWER_REQUIRED,
            MeasurementPropertyKey.INTERNAL_CONSISTENCY: (
                ProfileCapabilityStatus.REVIEWER_REQUIRED
            ),
            MeasurementPropertyKey.CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE: (
                ProfileCapabilityStatus.UNSUPPORTED
            ),
            MeasurementPropertyKey.RELIABILITY: ProfileCapabilityStatus.REVIEWER_REQUIRED,
            MeasurementPropertyKey.MEASUREMENT_ERROR: ProfileCapabilityStatus.ADAPTED,
            MeasurementPropertyKey.CRITERION_VALIDITY: ProfileCapabilityStatus.UNSUPPORTED,
            MeasurementPropertyKey.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY: (
                ProfileCapabilityStatus.ADAPTED
            ),
            MeasurementPropertyKey.RESPONSIVENESS: ProfileCapabilityStatus.ADAPTED,
        }

    @property
    def cosmin_box_capabilities(self) -> Mapping[CosminBoxKey, ProfileCapabilityStatus]:
        return {
            CosminBoxKey.PROM_DEVELOPMENT: ProfileCapabilityStatus.UNSUPPORTED,
            CosminBoxKey.CONTENT_VALIDITY: ProfileCapabilityStatus.REVIEWER_REQUIRED,
            CosminBoxKey.STRUCTURAL_VALIDITY: ProfileCapabilityStatus.REVIEWER_REQUIRED,
            CosminBoxKey.INTERNAL_CONSISTENCY: ProfileCapabilityStatus.REVIEWER_REQUIRED,
            CosminBoxKey.CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE: (
                ProfileCapabilityStatus.UNSUPPORTED
            ),
            CosminBoxKey.RELIABILITY: ProfileCapabilityStatus.REVIEWER_REQUIRED,
            CosminBoxKey.MEASUREMENT_ERROR: ProfileCapabilityStatus.ADAPTED,
            CosminBoxKey.CRITERION_VALIDITY: ProfileCapabilityStatus.UNSUPPORTED,
            CosminBoxKey.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY: (
                ProfileCapabilityStatus.ADAPTED
            ),
            CosminBoxKey.RESPONSIVENESS: ProfileCapabilityStatus.ADAPTED,
        }

    @property
    def review_step_capabilities(self) -> Mapping[CosminReviewStepKey, ProfileCapabilityStatus]:
        return {
            CosminReviewStepKey.STEP_1_EXTRACTION_AND_NORMALIZATION: (
                ProfileCapabilityStatus.ADAPTED
            ),
            CosminReviewStepKey.STEP_2_RISK_OF_BIAS: ProfileCapabilityStatus.ADAPTED,
            CosminReviewStepKey.STEP_3_STUDY_LEVEL_RATING: ProfileCapabilityStatus.ADAPTED,
            CosminReviewStepKey.STEP_4_SYNTHESIS: ProfileCapabilityStatus.ADAPTED,
            CosminReviewStepKey.STEP_5_MODIFIED_GRADE: ProfileCapabilityStatus.ADAPTED,
            CosminReviewStepKey.STEP_6_TABLE_BUILDING: ProfileCapabilityStatus.ADAPTED,
            CosminReviewStepKey.STEP_7_INTERPRETATION_AND_RECOMMENDATION: (
                ProfileCapabilityStatus.REVIEWER_REQUIRED
            ),
        }

    @property
    def rule_capabilities(self) -> Mapping[str, ProfileCapabilityStatus]:
        return {
            "ROB_WORST_SCORE_COUNTS_V1": ProfileCapabilityStatus.REUSED,
            "ROB_NA_EXCLUSION_V1": ProfileCapabilityStatus.REUSED,
            "MPR_MEASUREMENT_ERROR_PBOM_V1": ProfileCapabilityStatus.ADAPTED,
            "MPR_CONSTRUCT_VALIDITY_PBOM_V1": ProfileCapabilityStatus.ADAPTED,
            "MPR_RESPONSIVENESS_PBOM_V1": ProfileCapabilityStatus.ADAPTED,
            "MPR_RELIABILITY_PBOM_REVIEWER_V1": ProfileCapabilityStatus.REVIEWER_REQUIRED,
            "MPR_STRUCTURAL_VALIDITY_PBOM_REVIEWER_V1": (ProfileCapabilityStatus.REVIEWER_REQUIRED),
            "MPR_INTERNAL_CONSISTENCY_PBOM_REVIEWER_V1": (
                ProfileCapabilityStatus.REVIEWER_REQUIRED
            ),
            "MPR_CROSS_CULTURAL_PBOM_V1": ProfileCapabilityStatus.UNSUPPORTED,
            "MPR_CRITERION_VALIDITY_PBOM_V1": ProfileCapabilityStatus.UNSUPPORTED,
            "SYN_ALL_SUFFICIENT_TO_PLUS_V1": ProfileCapabilityStatus.REUSED,
            "SYN_ALL_INSUFFICIENT_TO_MINUS_V1": ProfileCapabilityStatus.REUSED,
            "SYN_UNEXPLAINED_MIXED_TO_PLUSMINUS_V1": ProfileCapabilityStatus.REUSED,
            "SYN_INSUFFICIENT_INFORMATION_TO_QUESTION_V1": ProfileCapabilityStatus.REUSED,
            "GR_START_HIGH_V1": ProfileCapabilityStatus.REUSED,
            "GR_DOWNGRADE_ROB_V1": ProfileCapabilityStatus.REUSED,
            "GR_DOWNGRADE_INCONSISTENCY_V1": ProfileCapabilityStatus.REUSED,
            "GR_DOWNGRADE_IMPRECISION_V1": ProfileCapabilityStatus.REUSED,
            "GR_FLOOR_VERY_LOW_V1": ProfileCapabilityStatus.REUSED,
        }

    @property
    def profile_specific_required_extraction_fields(self) -> tuple[str, ...]:
        return (
            "population_description",
            "task_protocol",
            "assessor_training",
            "scoring_algorithm",
            "time_interval",
            "setting",
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
            "pbom_protocol_equivalence",
            "conflicting_explicit_values_resolution",
        )

    @property
    def reviewer_questions(self) -> tuple[str, ...]:
        return (
            "Is PBOM protocol comparability acceptable across included studies?",
            "Is assessor training and scoring protocol sufficient for synthesis?",
            "Can non-PROM adaptation equivalence be accepted for this property?",
            "Does indirectness require additional downgrading for PBOM context?",
            "Should reliability be rated manually due to PBOM-specific scoring assumptions?",
        )

    @property
    def unsupported_auto_scoring_areas(self) -> tuple[str, ...]:
        return (
            "prom_development_box_assessment",
            "structural_validity_auto_scoring",
            "internal_consistency_auto_scoring",
            "reliability_auto_scoring",
            "criterion_validity_gold_standard_comparison",
            "cross_cultural_validity_measurement_invariance",
        )

    @property
    def adaptation_points(self) -> tuple[str, ...]:
        return (
            (
                "PBOM workflows require explicit protocol/scoring adaptation checks; "
                "PROM self-report assumptions are not transferred automatically."
            ),
            (
                "COSMIN steps 5-7 (modified GRADE, table synthesis, recommendation) are "
                "declared as adapted for PBOM interpretation."
            ),
            "Content validity and reliability remain reviewer-in-the-loop for PBOM contexts.",
        )

    @property
    def table_column_availability(self) -> Mapping[TableTemplateKey, tuple[str, ...]]:
        return {
            TableTemplateKey.TEMPLATE_5: (
                "instrument_name",
                "instrument_version",
                "subscale",
                "study_id",
                "study_design",
                "target_population",
                "language",
                "country",
                "enrollment_n",
                "analyzed_n",
                "follow_up_schedule",
                "measurement_properties_mentioned",
            ),
            TableTemplateKey.TEMPLATE_7: (
                "instrument_name",
                "instrument_version",
                "subscale",
                "measurement_property",
                "study_id",
                "per_study_rob",
                "per_study_result",
                "study_rating",
                "summarized_result",
                "overall_rating",
                "certainty_of_evidence",
                "total_sample_size",
            ),
            TableTemplateKey.TEMPLATE_8: (
                "instrument_name",
                "instrument_version",
                "subscale",
                "measurement_property",
                "summarized_result",
                "overall_rating",
                "certainty_of_evidence",
                "total_sample_size",
                "inconsistent_findings",
            ),
        }
