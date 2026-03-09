"""Tests for first-pass synthesis behavior."""

from __future__ import annotations

from cosmin_assistant.models import MeasurementPropertyRating
from cosmin_assistant.synthesize import StudySynthesisInput, synthesize_first_pass


def _study_result(
    *,
    result_id: str,
    study_id: str,
    instrument_name: str,
    instrument_version: str | None,
    subscale: str | None,
    measurement_property: str,
    rating: MeasurementPropertyRating,
    sample_size: int | None,
    evidence_span_id: str,
    subgroup_label: str | None = None,
) -> StudySynthesisInput:
    return StudySynthesisInput(
        id=result_id,
        study_id=study_id,
        instrument_name=instrument_name,
        instrument_version=instrument_version,
        subscale=subscale,
        measurement_property=measurement_property,
        rating=rating,
        sample_size=sample_size,
        evidence_span_ids=(evidence_span_id,),
        subgroup_label=subgroup_label,
    )


def test_synthesis_groups_by_instrument_version_subscale_and_property() -> None:
    results = (
        _study_result(
            result_id="mpr.1",
            study_id="study.1",
            instrument_name="PROM-X",
            instrument_version="v1",
            subscale="pain",
            measurement_property="reliability",
            rating=MeasurementPropertyRating.SUFFICIENT,
            sample_size=60,
            evidence_span_id="sen.1",
            subgroup_label="women",
        ),
        _study_result(
            result_id="mpr.2",
            study_id="study.2",
            instrument_name="PROM-X",
            instrument_version="v1",
            subscale="pain",
            measurement_property="reliability",
            rating=MeasurementPropertyRating.INSUFFICIENT,
            sample_size=40,
            evidence_span_id="sen.2",
            subgroup_label="men",
        ),
        _study_result(
            result_id="mpr.3",
            study_id="study.3",
            instrument_name="PROM-X",
            instrument_version="v2",
            subscale="pain",
            measurement_property="reliability",
            rating=MeasurementPropertyRating.SUFFICIENT,
            sample_size=80,
            evidence_span_id="sen.3",
        ),
    )

    synthesized = synthesize_first_pass(results)

    assert len(synthesized) == 2
    first_group = next(item for item in synthesized if item.instrument_version == "v1")
    second_group = next(item for item in synthesized if item.instrument_version == "v2")

    assert first_group.total_sample_size == 100
    assert second_group.total_sample_size == 80
    assert [entry.id for entry in first_group.study_entries] == ["mpr.1", "mpr.2"]
    assert [entry.id for entry in second_group.study_entries] == ["mpr.3"]


def test_inconsistency_is_represented_without_forced_resolution() -> None:
    synthesized = synthesize_first_pass(
        (
            _study_result(
                result_id="mpr.10",
                study_id="study.10",
                instrument_name="PROM-Y",
                instrument_version="v1",
                subscale="total",
                measurement_property="structural_validity",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=55,
                evidence_span_id="sen.10",
            ),
            _study_result(
                result_id="mpr.11",
                study_id="study.11",
                instrument_name="PROM-Y",
                instrument_version="v1",
                subscale="total",
                measurement_property="structural_validity",
                rating=MeasurementPropertyRating.INSUFFICIENT,
                sample_size=52,
                evidence_span_id="sen.11",
            ),
        )
    )

    result = synthesized[0]
    assert result.summary_rating is MeasurementPropertyRating.INCONSISTENT
    assert result.inconsistent_findings is True
    assert result.requires_subgroup_explanation is True


def test_subgroup_placeholders_are_generated_when_subgroups_exist() -> None:
    synthesized = synthesize_first_pass(
        (
            _study_result(
                result_id="mpr.20",
                study_id="study.20",
                instrument_name="PROM-Z",
                instrument_version="v1",
                subscale=None,
                measurement_property="reliability",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=70,
                evidence_span_id="sen.20",
                subgroup_label="older_adults",
            ),
            _study_result(
                result_id="mpr.21",
                study_id="study.21",
                instrument_name="PROM-Z",
                instrument_version="v1",
                subscale=None,
                measurement_property="reliability",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=75,
                evidence_span_id="sen.21",
                subgroup_label="younger_adults",
            ),
        )
    )[0]

    labels = [
        placeholder.subgroup_label for placeholder in synthesized.subgroup_explanation_placeholders
    ]
    assert labels == ["older_adults", "younger_adults"]


def test_mixed_sufficient_and_indeterminate_results_stay_indeterminate() -> None:
    synthesized = synthesize_first_pass(
        (
            _study_result(
                result_id="mpr.30",
                study_id="study.30",
                instrument_name="PROM-W",
                instrument_version="v1",
                subscale="function",
                measurement_property="reliability",
                rating=MeasurementPropertyRating.SUFFICIENT,
                sample_size=110,
                evidence_span_id="sen.30",
            ),
            _study_result(
                result_id="mpr.31",
                study_id="study.31",
                instrument_name="PROM-W",
                instrument_version="v1",
                subscale="function",
                measurement_property="reliability",
                rating=MeasurementPropertyRating.INDETERMINATE,
                sample_size=95,
                evidence_span_id="sen.31",
            ),
        )
    )[0]

    assert synthesized.summary_rating is MeasurementPropertyRating.INDETERMINATE
