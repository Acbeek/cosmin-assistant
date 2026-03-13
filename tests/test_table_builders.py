"""Tests for COSMIN-style intermediate table builders (Template 5/7/8 equivalents)."""

from __future__ import annotations

from dataclasses import dataclass

from cosmin_assistant.cosmin_rob import BoxAssessmentBundle
from cosmin_assistant.extract import (
    ContextFieldExtraction,
    ContextValueCandidate,
    FieldDetectionStatus,
    InstrumentContextExtractionResult,
    SampleSizeObservation,
    SampleSizeRole,
    StatisticType,
    StudyContextExtractionResult,
)
from cosmin_assistant.grade import (
    DomainDowngradeInput,
    DowngradeSeverity,
    ModifiedGradeDomain,
    ModifiedGradeResult,
    apply_modified_grade,
)
from cosmin_assistant.measurement_rating import (
    MeasurementPropertyRatingResult,
    RawResultRecord,
)
from cosmin_assistant.models import (
    CosminBoxAssessment,
    CosminBoxRating,
    CosminItemAssessment,
    CosminItemRating,
    MeasurementPropertyRating,
    ReviewerDecisionStatus,
    UncertaintyStatus,
)
from cosmin_assistant.synthesize import (
    StudySynthesisInput,
    SynthesisAggregateResult,
    synthesize_first_pass,
)
from cosmin_assistant.tables import (
    build_template5_characteristics_table,
    build_template7_evidence_table,
    build_template8_summary_table,
    table_to_json_ready,
    template5_to_dataframe,
    template7_to_dataframe,
    template8_to_dataframe,
)


@dataclass(frozen=True)
class _FixtureData:
    study_contexts: tuple[StudyContextExtractionResult, ...]
    instrument_contexts: tuple[InstrumentContextExtractionResult, ...]
    rob_assessments: tuple[BoxAssessmentBundle, ...]
    measurement_results: tuple[MeasurementPropertyRatingResult, ...]
    synthesis_results: tuple[SynthesisAggregateResult, ...]
    grade_results: tuple[ModifiedGradeResult, ...]


def test_template5_rows_separate_versions_and_mark_additional_studies() -> None:
    fixture = _build_fixture_data()

    table = build_template5_characteristics_table(
        study_contexts=fixture.study_contexts,
        instrument_contexts=fixture.instrument_contexts,
    )

    assert len(table.rows) == 3

    v1_rows = [row for row in table.rows if row.instrument_version == "v1"]
    assert len(v1_rows) == 2
    assert v1_rows[0].study_order_within_instrument == 1
    assert v1_rows[0].is_additional_study_row is False
    assert v1_rows[1].study_order_within_instrument == 2
    assert v1_rows[1].is_additional_study_row is True
    assert v1_rows[0].enrollment_n == 41
    assert v1_rows[0].analyzed_n == 37
    assert v1_rows[0].limb_level_n == 51

    legend_keys = {legend.key for legend in table.legends}
    assert {"additional_study_row", "blank_or_na"} <= legend_keys

    df = template5_to_dataframe(table)
    assert len(df) == len(table.rows)
    assert "instrument_version" in df.columns

    payload = table_to_json_ready(table)
    assert payload["template_code"] == "template_5"
    assert len(payload["rows"]) == 3


def test_template7_preserves_study_rows_and_suppresses_blank_summary_rows() -> None:
    fixture = _build_fixture_data()

    table = build_template7_evidence_table(
        instrument_contexts=fixture.instrument_contexts,
        rob_assessments=fixture.rob_assessments,
        measurement_results=fixture.measurement_results,
        synthesis_results=fixture.synthesis_results,
        grade_results=fixture.grade_results,
        measurement_properties_universe=("reliability", "structural_validity"),
    )

    v1_rel_rows = [
        row
        for row in table.rows
        if row.instrument_version == "v1" and row.measurement_property == "reliability"
    ]
    assert len(v1_rel_rows) == 3
    assert v1_rel_rows[0].row_kind.value == "study"
    assert v1_rel_rows[1].row_kind.value == "study"
    assert v1_rel_rows[2].row_kind.value == "summary"
    assert v1_rel_rows[1].is_additional_study_row is True
    assert v1_rel_rows[0].per_study_result is not None
    assert "icc" in v1_rel_rows[0].per_study_result

    summary_row = v1_rel_rows[2]
    assert summary_row.total_sample_size == 130
    assert summary_row.overall_rating == "±"
    assert summary_row.certainty_of_evidence == "low"
    assert summary_row.summarized_result is not None

    v1_structural = [
        row
        for row in table.rows
        if row.instrument_version == "v1" and row.measurement_property == "structural_validity"
    ]
    assert not v1_structural

    legend_keys = {legend.key for legend in table.legends}
    assert {"study", "summary", "+", "-", "?", "±", "blank_or_na"} <= legend_keys

    df = template7_to_dataframe(table)
    assert len(df) == len(table.rows)
    assert "row_kind" in df.columns

    payload = table_to_json_ready(table)
    assert payload["template_code"] == "template_7"


def test_template8_organizes_by_instrument_version_property_and_supports_na() -> None:
    fixture = _build_fixture_data()

    table = build_template8_summary_table(
        instrument_contexts=fixture.instrument_contexts,
        synthesis_results=fixture.synthesis_results,
        grade_results=fixture.grade_results,
        measurement_properties_universe=("reliability", "responsiveness"),
    )

    assert len(table.rows) == 4
    v1_rows = [row for row in table.rows if row.instrument_version == "v1"]
    v2_rows = [row for row in table.rows if row.instrument_version == "v2"]
    assert len(v1_rows) == 2
    assert len(v2_rows) == 2

    rel_v1 = next(
        row
        for row in table.rows
        if row.instrument_version == "v1" and row.measurement_property == "reliability"
    )
    assert rel_v1.overall_rating == "±"
    assert rel_v1.certainty_of_evidence == "low"

    resp_v1 = next(
        row
        for row in table.rows
        if row.instrument_version == "v1" and row.measurement_property == "responsiveness"
    )
    assert resp_v1.overall_rating is None
    assert resp_v1.certainty_of_evidence is None

    legend_keys = {legend.key for legend in table.legends}
    assert {"certainty_levels", "+", "-", "?", "±", "blank_or_na"} <= legend_keys

    df = template8_to_dataframe(table)
    assert len(df) == len(table.rows)
    assert "measurement_property" in df.columns

    payload = table_to_json_ready(table)
    assert payload["template_code"] == "template_8"


def _build_fixture_data() -> _FixtureData:
    study1 = _study_context(
        study_id="study.1",
        enrollment_n=41,
        analyzed_n=37,
        limb_n=51,
        follow_up=("baseline", "24 months"),
    )
    study2 = _study_context(
        study_id="study.2",
        enrollment_n=33,
        analyzed_n=31,
        limb_n=35,
        follow_up=("baseline", "12 months"),
    )

    inst_v1_s1 = _instrument_context(
        context_id="instctx.v1.s1",
        study_id="study.1",
        instrument_id="inst.v1.s1",
        instrument_name="PROM-X",
        instrument_version="v1",
        subscale="pain",
    )
    inst_v1_s2 = _instrument_context(
        context_id="instctx.v1.s2",
        study_id="study.2",
        instrument_id="inst.v1.s2",
        instrument_name="PROM-X",
        instrument_version="v1",
        subscale="pain",
    )
    inst_v2_s1 = _instrument_context(
        context_id="instctx.v2.s1",
        study_id="study.1",
        instrument_id="inst.v2.s1",
        instrument_name="PROM-X",
        instrument_version="v2",
        subscale="pain",
    )

    mpr1 = _measurement_result(
        result_id="mpr.1",
        study_id="study.1",
        instrument_id="inst.v1.s1",
        rating=MeasurementPropertyRating.SUFFICIENT,
        value_raw="0.81",
        evidence_span_id="sen.101",
    )
    mpr2 = _measurement_result(
        result_id="mpr.2",
        study_id="study.2",
        instrument_id="inst.v1.s2",
        rating=MeasurementPropertyRating.INSUFFICIENT,
        value_raw="0.58",
        evidence_span_id="sen.102",
    )
    mpr3 = _measurement_result(
        result_id="mpr.3",
        study_id="study.1",
        instrument_id="inst.v2.s1",
        rating=MeasurementPropertyRating.SUFFICIENT,
        value_raw="0.87",
        evidence_span_id="sen.103",
    )

    synthesis_results = synthesize_first_pass(
        (
            _study_input(
                result_id=mpr1.id,
                study_id=mpr1.study_id,
                instrument_name="PROM-X",
                instrument_version="v1",
                subscale="pain",
                rating=mpr1.computed_rating,
                sample_size=60,
                evidence_span_id="sen.101",
            ),
            _study_input(
                result_id=mpr2.id,
                study_id=mpr2.study_id,
                instrument_name="PROM-X",
                instrument_version="v1",
                subscale="pain",
                rating=mpr2.computed_rating,
                sample_size=70,
                evidence_span_id="sen.102",
            ),
            _study_input(
                result_id=mpr3.id,
                study_id=mpr3.study_id,
                instrument_name="PROM-X",
                instrument_version="v2",
                subscale="pain",
                rating=mpr3.computed_rating,
                sample_size=95,
                evidence_span_id="sen.103",
            ),
        )
    )

    grade_results = tuple(
        apply_modified_grade(
            synthesis_result=synthesis,
            risk_of_bias=(
                DomainDowngradeInput(
                    domain=ModifiedGradeDomain.RISK_OF_BIAS,
                    severity=DowngradeSeverity.SERIOUS,
                    reason="Methodological concerns in included studies.",
                    evidence_span_ids=synthesis.evidence_span_ids,
                    explanation="Downgraded one level for risk of bias.",
                )
                if synthesis.instrument_version == "v1"
                else DomainDowngradeInput(
                    domain=ModifiedGradeDomain.RISK_OF_BIAS,
                    severity=DowngradeSeverity.NONE,
                    reason=None,
                    evidence_span_ids=(),
                    explanation=None,
                )
            ),
            indirectness=DomainDowngradeInput(
                domain=ModifiedGradeDomain.INDIRECTNESS,
                severity=DowngradeSeverity.NONE,
                reason=None,
                evidence_span_ids=(),
                explanation=None,
            ),
        )
        for synthesis in synthesis_results
    )

    rob_assessments = (
        _box_assessment_bundle(
            bundle_id="boxbundle.1",
            study_id="study.1",
            instrument_id="inst.v1.s1",
            measurement_property="reliability",
            box_rating=CosminBoxRating.ADEQUATE,
            evidence_span_id="sen.101",
        ),
        _box_assessment_bundle(
            bundle_id="boxbundle.2",
            study_id="study.2",
            instrument_id="inst.v1.s2",
            measurement_property="reliability",
            box_rating=CosminBoxRating.DOUBTFUL,
            evidence_span_id="sen.102",
        ),
        _box_assessment_bundle(
            bundle_id="boxbundle.3",
            study_id="study.1",
            instrument_id="inst.v2.s1",
            measurement_property="reliability",
            box_rating=CosminBoxRating.VERY_GOOD,
            evidence_span_id="sen.103",
        ),
    )

    return _FixtureData(
        study_contexts=(study1, study2),
        instrument_contexts=(inst_v1_s1, inst_v1_s2, inst_v2_s1),
        rob_assessments=rob_assessments,
        measurement_results=(mpr1, mpr2, mpr3),
        synthesis_results=synthesis_results,
        grade_results=grade_results,
    )


def _study_context(
    *,
    study_id: str,
    enrollment_n: int,
    analyzed_n: int,
    limb_n: int,
    follow_up: tuple[str, ...],
) -> StudyContextExtractionResult:
    return StudyContextExtractionResult(
        id=f"studyctx.{study_id.split('.')[-1]}",
        article_id="article.1",
        study_id=study_id,
        study_design=_field_detected("study_design", "prospective_observational_study", "sen.1"),
        sample_sizes=_field_not_detected("sample_sizes"),
        sample_size_observations=(
            _sample_size_observation(
                obs_id=f"ssobs.{study_id}.enrollment",
                role=SampleSizeRole.ENROLLMENT,
                sample_size=enrollment_n,
                span_id=f"sen.{study_id}.enrollment",
            ),
            _sample_size_observation(
                obs_id=f"ssobs.{study_id}.analyzed",
                role=SampleSizeRole.ANALYZED,
                sample_size=analyzed_n,
                span_id=f"sen.{study_id}.analyzed",
            ),
            _sample_size_observation(
                obs_id=f"ssobs.{study_id}.limb",
                role=SampleSizeRole.LIMB_LEVEL,
                sample_size=limb_n,
                span_id=f"sen.{study_id}.limb",
            ),
        ),
        follow_up_schedule=_field_detected("follow_up_schedule", follow_up, "sen.2"),
        construct_field=_field_detected("construct", "function", "sen.3"),
        target_population=_field_detected(
            "target_population",
            "transfemoral amputation participants",
            "sen.4",
        ),
        language=_field_detected("language", "english", "sen.5"),
        country=_field_detected("country", "united states", "sen.6"),
        measurement_properties_mentioned=_field_detected(
            "measurement_properties_mentioned",
            ("reliability",),
            "sen.7",
        ),
        measurement_properties_background=_field_not_detected("measurement_properties_background"),
        measurement_properties_interpretability=_field_not_detected(
            "measurement_properties_interpretability"
        ),
        subsamples=(),
    )


def _instrument_context(
    *,
    context_id: str,
    study_id: str,
    instrument_id: str,
    instrument_name: str,
    instrument_version: str,
    subscale: str,
) -> InstrumentContextExtractionResult:
    return InstrumentContextExtractionResult(
        id=context_id,
        article_id="article.1",
        study_id=study_id,
        instrument_id=instrument_id,
        instrument_name=_field_detected("instrument_name", instrument_name, "sen.10"),
        instrument_version=_field_detected("instrument_version", instrument_version, "sen.11"),
        subscale=_field_detected("subscale", subscale, "sen.12"),
        construct_field=_field_detected("construct", "function", "sen.13"),
        target_population=_field_detected("target_population", "tfa population", "sen.14"),
    )


def _measurement_result(
    *,
    result_id: str,
    study_id: str,
    instrument_id: str,
    rating: MeasurementPropertyRating,
    value_raw: str,
    evidence_span_id: str,
) -> MeasurementPropertyRatingResult:
    raw_record = RawResultRecord(
        statistic_type=StatisticType.ICC,
        value_raw=value_raw,
        value_normalized=float(value_raw),
        subgroup_label=None,
        evidence_span_ids=(evidence_span_id,),
    )
    return MeasurementPropertyRatingResult(
        id=result_id,
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property="reliability",
        rule_name="rule.reliability.prom",
        raw_results=(raw_record,),
        computed_rating=rating,
        explanation="Deterministic reliability rating from ICC thresholds.",
        inputs_used={"statistic_count": 1},
        prerequisite_decisions=(),
        threshold_comparisons=(),
        evidence_span_ids=(evidence_span_id,),
        uncertainty_status=UncertaintyStatus.CERTAIN,
        reviewer_decision_status=ReviewerDecisionStatus.NOT_REQUIRED,
    )


def _study_input(
    *,
    result_id: str,
    study_id: str,
    instrument_name: str,
    instrument_version: str,
    subscale: str,
    rating: MeasurementPropertyRating,
    sample_size: int,
    evidence_span_id: str,
) -> StudySynthesisInput:
    return StudySynthesisInput(
        id=result_id,
        study_id=study_id,
        instrument_name=instrument_name,
        instrument_version=instrument_version,
        subscale=subscale,
        measurement_property="reliability",
        rating=rating,
        sample_size=sample_size,
        evidence_span_ids=(evidence_span_id,),
    )


def _box_assessment_bundle(
    *,
    bundle_id: str,
    study_id: str,
    instrument_id: str,
    measurement_property: str,
    box_rating: CosminBoxRating,
    evidence_span_id: str,
) -> BoxAssessmentBundle:
    item_id = f"item.{bundle_id}"
    item = CosminItemAssessment(
        id=item_id,
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=measurement_property,
        cosmin_box="box_6",
        item_code="B6.4",
        item_rating=CosminItemRating.ADEQUATE,
        evidence_span_ids=[evidence_span_id],
        uncertainty_status=UncertaintyStatus.CERTAIN,
        reviewer_decision_status=ReviewerDecisionStatus.NOT_REQUIRED,
    )
    box = CosminBoxAssessment(
        id=f"box.{bundle_id}",
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=measurement_property,
        cosmin_box="box_6",
        box_rating=box_rating,
        item_assessment_ids=[item_id],
        evidence_span_ids=[evidence_span_id],
        uncertainty_status=UncertaintyStatus.CERTAIN,
        reviewer_decision_status=ReviewerDecisionStatus.NOT_REQUIRED,
    )
    return BoxAssessmentBundle(
        id=bundle_id,
        box_assessment=box,
        item_assessments=(item,),
        aggregation_rule="WORST_SCORE_COUNTS",
        na_handling_rule="EXCLUDE_NOT_APPLICABLE",
        worst_score_counts_applied=True,
        applicable_item_assessment_ids=(item_id,),
        not_applicable_item_assessment_ids=(),
        worst_item_assessment_ids=(item_id,),
    )


def _field_detected(
    field_name: str,
    normalized_value: str | int | tuple[str, ...],
    evidence_span_id: str,
) -> ContextFieldExtraction:
    return ContextFieldExtraction(
        id=f"field.{field_name}.{evidence_span_id.replace('.', '-')}",
        field_name=field_name,
        status=FieldDetectionStatus.DETECTED,
        candidates=(
            ContextValueCandidate(
                id=f"cand.{field_name}.{evidence_span_id.replace('.', '-')}",
                raw_text=str(normalized_value),
                normalized_value=normalized_value,
                evidence_span_ids=(evidence_span_id,),
            ),
        ),
    )


def _field_not_detected(field_name: str) -> ContextFieldExtraction:
    return ContextFieldExtraction(
        id=f"field.{field_name}.none",
        field_name=field_name,
        status=FieldDetectionStatus.NOT_DETECTED,
        candidates=(),
    )


def _sample_size_observation(
    *,
    obs_id: str,
    role: SampleSizeRole,
    sample_size: int,
    span_id: str,
) -> SampleSizeObservation:
    return SampleSizeObservation(
        id=obs_id,
        role=role,
        sample_size_raw=f"n={sample_size}",
        sample_size_normalized=sample_size,
        unit="participants" if role is not SampleSizeRole.LIMB_LEVEL else "limbs",
        evidence_span_ids=(span_id,),
    )
