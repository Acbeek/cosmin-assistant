"""PROM reference profile with the broadest deterministic coverage."""

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


class PromProfile(BaseProfile):
    """Reference profile for patient-reported outcome measures (PROMs)."""

    @property
    def profile_type(self) -> ProfileType:
        return ProfileType.PROM

    @property
    def measurement_property_capabilities(
        self,
    ) -> Mapping[MeasurementPropertyKey, ProfileCapabilityStatus]:
        return {
            MeasurementPropertyKey.CONTENT_VALIDITY: ProfileCapabilityStatus.REUSED,
            MeasurementPropertyKey.STRUCTURAL_VALIDITY: ProfileCapabilityStatus.REUSED,
            MeasurementPropertyKey.INTERNAL_CONSISTENCY: ProfileCapabilityStatus.REUSED,
            MeasurementPropertyKey.CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE: (
                ProfileCapabilityStatus.REUSED
            ),
            MeasurementPropertyKey.RELIABILITY: ProfileCapabilityStatus.REUSED,
            MeasurementPropertyKey.MEASUREMENT_ERROR: ProfileCapabilityStatus.REUSED,
            MeasurementPropertyKey.CRITERION_VALIDITY: ProfileCapabilityStatus.REUSED,
            MeasurementPropertyKey.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY: (
                ProfileCapabilityStatus.REUSED
            ),
            MeasurementPropertyKey.RESPONSIVENESS: ProfileCapabilityStatus.REUSED,
        }

    @property
    def cosmin_box_capabilities(self) -> Mapping[CosminBoxKey, ProfileCapabilityStatus]:
        return {
            CosminBoxKey.PROM_DEVELOPMENT: ProfileCapabilityStatus.REUSED,
            CosminBoxKey.CONTENT_VALIDITY: ProfileCapabilityStatus.REUSED,
            CosminBoxKey.STRUCTURAL_VALIDITY: ProfileCapabilityStatus.REUSED,
            CosminBoxKey.INTERNAL_CONSISTENCY: ProfileCapabilityStatus.REUSED,
            CosminBoxKey.CROSS_CULTURAL_VALIDITY_MEASUREMENT_INVARIANCE: (
                ProfileCapabilityStatus.REUSED
            ),
            CosminBoxKey.RELIABILITY: ProfileCapabilityStatus.REUSED,
            CosminBoxKey.MEASUREMENT_ERROR: ProfileCapabilityStatus.REUSED,
            CosminBoxKey.CRITERION_VALIDITY: ProfileCapabilityStatus.REUSED,
            CosminBoxKey.HYPOTHESES_TESTING_FOR_CONSTRUCT_VALIDITY: (
                ProfileCapabilityStatus.REUSED
            ),
            CosminBoxKey.RESPONSIVENESS: ProfileCapabilityStatus.REUSED,
        }

    @property
    def review_step_capabilities(self) -> Mapping[CosminReviewStepKey, ProfileCapabilityStatus]:
        return {
            CosminReviewStepKey.STEP_1_EXTRACTION_AND_NORMALIZATION: (
                ProfileCapabilityStatus.REUSED
            ),
            CosminReviewStepKey.STEP_2_RISK_OF_BIAS: ProfileCapabilityStatus.REUSED,
            CosminReviewStepKey.STEP_3_STUDY_LEVEL_RATING: ProfileCapabilityStatus.REUSED,
            CosminReviewStepKey.STEP_4_SYNTHESIS: ProfileCapabilityStatus.REUSED,
            CosminReviewStepKey.STEP_5_MODIFIED_GRADE: ProfileCapabilityStatus.REUSED,
            CosminReviewStepKey.STEP_6_TABLE_BUILDING: ProfileCapabilityStatus.REUSED,
            CosminReviewStepKey.STEP_7_INTERPRETATION_AND_RECOMMENDATION: (
                ProfileCapabilityStatus.REVIEWER_REQUIRED
            ),
        }

    @property
    def rule_capabilities(self) -> Mapping[str, ProfileCapabilityStatus]:
        return {
            "ROB_WORST_SCORE_COUNTS_V1": ProfileCapabilityStatus.REUSED,
            "ROB_NA_EXCLUSION_V1": ProfileCapabilityStatus.REUSED,
            "MPR_STRUCTURAL_VALIDITY_PROM_V1": ProfileCapabilityStatus.REUSED,
            "MPR_INTERNAL_CONSISTENCY_PROM_V1": ProfileCapabilityStatus.REUSED,
            "MPR_RELIABILITY_PROM_V1": ProfileCapabilityStatus.REUSED,
            "MPR_MEASUREMENT_ERROR_PROM_V1": ProfileCapabilityStatus.REUSED,
            "MPR_CROSS_CULTURAL_PROM_V1": ProfileCapabilityStatus.REUSED,
            "MPR_CRITERION_VALIDITY_PROM_V1": ProfileCapabilityStatus.REUSED,
            "MPR_CONSTRUCT_VALIDITY_PROM_V1": ProfileCapabilityStatus.REUSED,
            "MPR_RESPONSIVENESS_PROM_V1": ProfileCapabilityStatus.REUSED,
            "MPR_MEASUREMENT_ERROR_PBOM_V1": ProfileCapabilityStatus.UNSUPPORTED,
            "MPR_CONSTRUCT_VALIDITY_PBOM_V1": ProfileCapabilityStatus.UNSUPPORTED,
            "MPR_RESPONSIVENESS_PBOM_V1": ProfileCapabilityStatus.UNSUPPORTED,
            "MPR_MEASUREMENT_ERROR_ACTIVITY_V1": ProfileCapabilityStatus.UNSUPPORTED,
            "MPR_RESPONSIVENESS_ACTIVITY_V1": ProfileCapabilityStatus.UNSUPPORTED,
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
            "construct_definition",
            "statistical_method",
            "time_interval",
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
    def reviewer_questions(self) -> tuple[str, ...]:
        return (
            "Does the study population match the review target population?",
            "Were hypotheses predefined and clinically meaningful?",
            "Is the comparator acceptable as a gold standard?",
            "Is the inconsistency explanation adequate for synthesis?",
            "Is indirectness serious enough to downgrade certainty?",
            "Does content validity need manual expert adjudication?",
        )

    @property
    def unsupported_auto_scoring_areas(self) -> tuple[str, ...]:
        return ()

    @property
    def adaptation_points(self) -> tuple[str, ...]:
        return ()

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
                "limb_level_n",
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
