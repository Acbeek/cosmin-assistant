"""Contract tests for profile capability metadata and limitations."""

from __future__ import annotations

from cosmin_assistant.models.enums import ProfileType
from cosmin_assistant.profiles import (
    ActivityMonitorProfile,
    BaseProfile,
    CosminBoxKey,
    MeasurementPropertyKey,
    PbomProfile,
    PromProfile,
    get_profile,
    list_profiles,
)


def test_profiles_instantiate_cleanly() -> None:
    profiles: tuple[BaseProfile, ...] = (PromProfile(), PbomProfile(), ActivityMonitorProfile())

    assert all(isinstance(profile, BaseProfile) for profile in profiles)


def test_prom_profile_is_fuller_than_non_prom_profiles() -> None:
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


def test_non_prom_profiles_have_explicit_adaptation_points_and_limits() -> None:
    pbom = PbomProfile()
    activity = ActivityMonitorProfile()

    assert pbom.adaptation_points
    assert activity.adaptation_points
    assert pbom.unsupported_auto_scoring_areas
    assert activity.unsupported_auto_scoring_areas
    assert pbom.requires_reviewer_decision("non_prom_adaptation_equivalence")
    assert activity.requires_reviewer_decision("non_prom_adaptation_equivalence")


def test_prom_assumptions_do_not_leak_into_non_prom_profiles() -> None:
    pbom = PbomProfile()
    activity = ActivityMonitorProfile()

    assert not pbom.supports_cosmin_box(CosminBoxKey.PROM_DEVELOPMENT)
    assert not activity.supports_cosmin_box(CosminBoxKey.PROM_DEVELOPMENT)
    assert not pbom.supports_measurement_property(MeasurementPropertyKey.CRITERION_VALIDITY)
    assert not activity.supports_measurement_property(MeasurementPropertyKey.CRITERION_VALIDITY)
    assert not activity.supports_measurement_property(MeasurementPropertyKey.STRUCTURAL_VALIDITY)
    assert not activity.supports_measurement_property(MeasurementPropertyKey.INTERNAL_CONSISTENCY)
    assert all("_PROM_" not in rule_id for rule_id in pbom.deterministic_rules_available)
    assert all("_PROM_" not in rule_id for rule_id in activity.deterministic_rules_available)


def test_profile_metadata_can_drive_later_stage_decisions() -> None:
    prom = get_profile(ProfileType.PROM)
    pbom = get_profile("pbom")
    activity = get_profile(ProfileType.ACTIVITY_MEASURE)

    assert prom.supports_measurement_property(MeasurementPropertyKey.CRITERION_VALIDITY)
    assert pbom.requires_field("task_protocol")
    assert not prom.requires_field("task_protocol")
    assert not pbom.supports_auto_scoring_area("criterion_validity_gold_standard_comparison")
    assert not activity.supports_auto_scoring_area("structural_validity")

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
