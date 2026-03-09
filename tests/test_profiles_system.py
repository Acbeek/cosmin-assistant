"""Contract tests for profile capability metadata and limitations."""

from __future__ import annotations

import pytest

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles import (
    ActivityMonitorProfile,
    BaseProfile,
    CosminBoxKey,
    CosminReviewStepKey,
    MeasurementPropertyKey,
    PbomProfile,
    ProfileCapabilityStatus,
    PromProfile,
    TableTemplateKey,
    get_profile,
    list_profiles,
)


def test_profiles_instantiate_cleanly() -> None:
    profiles: tuple[BaseProfile, ...] = (PromProfile(), PbomProfile(), ActivityMonitorProfile())
    assert all(isinstance(profile, BaseProfile) for profile in profiles)


def test_prom_profile_remains_reference_with_broadest_deterministic_coverage() -> None:
    prom = PromProfile()
    pbom = PbomProfile()
    activity = ActivityMonitorProfile()

    assert len(prom.applicable_measurement_properties) > len(pbom.applicable_measurement_properties)
    assert len(prom.applicable_measurement_properties) > len(
        activity.applicable_measurement_properties
    )
    assert len(prom.applicable_cosmin_boxes) > len(pbom.applicable_cosmin_boxes)
    assert len(prom.applicable_cosmin_boxes) > len(activity.applicable_cosmin_boxes)
    assert len(prom.deterministic_rules_available) > len(pbom.deterministic_rules_available)
    assert len(prom.deterministic_rules_available) > len(activity.deterministic_rules_available)
    assert len(prom.unsupported_auto_scoring_areas) < len(pbom.unsupported_auto_scoring_areas)
    assert len(prom.unsupported_auto_scoring_areas) < len(activity.unsupported_auto_scoring_areas)


def test_non_prom_profiles_declare_adapted_steps_5_to_7() -> None:
    pbom = PbomProfile()
    activity = ActivityMonitorProfile()

    for profile in (pbom, activity):
        for step_key in (
            CosminReviewStepKey.STEP_5_MODIFIED_GRADE,
            CosminReviewStepKey.STEP_6_TABLE_BUILDING,
            CosminReviewStepKey.STEP_7_INTERPRETATION_AND_RECOMMENDATION,
        ):
            status = profile.review_step_status(step_key)
            assert status in (
                ProfileCapabilityStatus.ADAPTED,
                ProfileCapabilityStatus.REVIEWER_REQUIRED,
            )


def test_non_prom_profiles_have_explicit_adaptation_points_and_limits() -> None:
    pbom = PbomProfile()
    activity = ActivityMonitorProfile()

    assert pbom.adaptation_points
    assert activity.adaptation_points
    assert pbom.unsupported_auto_scoring_areas
    assert activity.unsupported_auto_scoring_areas
    assert pbom.profile_specific_required_extraction_fields
    assert activity.profile_specific_required_extraction_fields
    assert pbom.reviewer_questions
    assert activity.reviewer_questions
    assert pbom.requires_reviewer_decision("non_prom_adaptation_equivalence")
    assert activity.requires_reviewer_decision("non_prom_adaptation_equivalence")


def test_prom_assumptions_do_not_leak_silently_to_non_prom_profiles() -> None:
    pbom = PbomProfile()
    activity = ActivityMonitorProfile()

    assert (
        pbom.cosmin_box_status(CosminBoxKey.PROM_DEVELOPMENT) is ProfileCapabilityStatus.UNSUPPORTED
    )
    assert (
        activity.cosmin_box_status(CosminBoxKey.PROM_DEVELOPMENT)
        is ProfileCapabilityStatus.UNSUPPORTED
    )
    assert (
        pbom.measurement_property_status(MeasurementPropertyKey.CRITERION_VALIDITY)
        is ProfileCapabilityStatus.UNSUPPORTED
    )
    assert (
        activity.measurement_property_status(MeasurementPropertyKey.STRUCTURAL_VALIDITY)
        is ProfileCapabilityStatus.UNSUPPORTED
    )
    assert (
        activity.measurement_property_status(MeasurementPropertyKey.INTERNAL_CONSISTENCY)
        is ProfileCapabilityStatus.UNSUPPORTED
    )
    assert all("_PROM_" not in rule_id for rule_id in pbom.deterministic_rules_available)
    assert all("_PROM_" not in rule_id for rule_id in activity.deterministic_rules_available)


def test_profile_specific_required_fields_and_table_columns_differ() -> None:
    prom = PromProfile()
    pbom = PbomProfile()
    activity = ActivityMonitorProfile()

    assert pbom.requires_field("task_protocol")
    assert activity.requires_field("device_model")
    assert not prom.requires_field("task_protocol")
    assert not prom.requires_field("device_model")

    prom_t5 = prom.available_table_columns(TableTemplateKey.TEMPLATE_5)
    pbom_t5 = pbom.available_table_columns(TableTemplateKey.TEMPLATE_5)
    activity_t5 = activity.available_table_columns(TableTemplateKey.TEMPLATE_5)
    assert "limb_level_n" in prom_t5
    assert "limb_level_n" not in pbom_t5
    assert "limb_level_n" not in activity_t5


def test_unsupported_areas_fail_safely_and_clearly() -> None:
    pbom = PbomProfile()
    activity = ActivityMonitorProfile()

    with pytest.raises(NotImplementedError, match="unsupported for profile 'pbom'"):
        pbom.require_supported_auto_scoring_area("criterion_validity_gold_standard_comparison")

    with pytest.raises(NotImplementedError, match="unsupported for profile 'activity_measure'"):
        activity.require_supported_auto_scoring_area("structural_validity_auto_scoring")

    with pytest.raises(NotImplementedError, match="MPR_CRITERION_VALIDITY_PROM_V1"):
        pbom.require_deterministic_rule("MPR_CRITERION_VALIDITY_PROM_V1")

    with pytest.raises(NotImplementedError, match="MPR_CONSTRUCT_VALIDITY_PROM_V1"):
        activity.require_deterministic_rule("MPR_CONSTRUCT_VALIDITY_PROM_V1")


def test_profile_metadata_can_drive_later_stage_decisions() -> None:
    prom = get_profile(ProfileType.PROM)
    pbom = get_profile("pbom")
    activity = get_profile(ProfileType.ACTIVITY_MEASURE)

    assert prom.supports_measurement_property(MeasurementPropertyKey.CRITERION_VALIDITY)
    assert pbom.requires_field("task_protocol")
    assert not prom.requires_field("task_protocol")
    assert not pbom.supports_auto_scoring_area("criterion_validity_gold_standard_comparison")
    assert not activity.supports_auto_scoring_area("structural_validity_auto_scoring")
    assert pbom.rule_status("MPR_RESPONSIVENESS_PBOM_V1") is ProfileCapabilityStatus.ADAPTED
    assert activity.rule_status("MPR_RESPONSIVENESS_ACTIVITY_V1") is ProfileCapabilityStatus.ADAPTED

    profile_types = tuple(profile.profile_type for profile in list_profiles())
    assert profile_types == (
        ProfileType.PROM,
        ProfileType.PBOM,
        ProfileType.ACTIVITY_MEASURE,
    )

    metadata = activity.to_metadata()
    assert metadata["profile_type"] == "activity_measure"
    assert "unsupported_auto_scoring_areas" in metadata
    assert "adaptation_points" in metadata
    assert "review_step_capabilities" in metadata
    assert "table_column_availability" in metadata
