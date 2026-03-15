"""Tests for COSMIN-style intermediate table builders (Template 5/6/7/8 equivalents)."""

from __future__ import annotations

from dataclasses import dataclass

from cosmin_assistant.cosmin_rob import BoxAssessmentBundle
from cosmin_assistant.extract import (
    ContextFieldExtraction,
    ContextValueCandidate,
    FieldDetectionStatus,
    InstrumentContextExtractionResult,
    InstrumentContextRole,
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
    build_template6_content_validity_table,
    build_template7_evidence_table,
    build_template8_summary_table,
    table_to_json_ready,
    template5_to_dataframe,
    template6_to_dataframe,
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


def test_study_display_labels_are_deterministic_and_preserve_study_ids_across_templates() -> None:
    article_file_path = "/tmp/reviewer/Garcia2024_custom_validation.md"
    article_markdown_text = "# Example study\nPublished online: 14 May 2024\n"
    study = _study_context(
        study_id="study.1",
        enrollment_n=41,
        analyzed_n=37,
        limb_n=51,
        follow_up=("baseline", "24 months"),
    )
    context = _instrument_context(
        context_id="instctx.target",
        study_id="study.1",
        instrument_id="inst.target",
        instrument_name="PROM-X",
        instrument_version="v1",
        subscale="overall",
        instrument_role=InstrumentContextRole.TARGET_UNDER_APPRAISAL,
    )
    reliability_bundle = _box_assessment_bundle(
        bundle_id="bundle.box6.target",
        study_id="study.1",
        instrument_id="inst.target",
        measurement_property="reliability",
        box_rating=CosminBoxRating.ADEQUATE,
        evidence_span_id="sen.999",
    )
    content_bundle = _manual_box_assessment_bundle(
        bundle_id="bundle.box1.target",
        study_id="study.1",
        instrument_id="inst.target",
        measurement_property="prom_development",
        cosmin_box="box_1_prom_development",
        item_code="B1.1_target_population_definition",
    )
    measurement_result = _measurement_result(
        result_id="mpr.1",
        study_id="study.1",
        instrument_id="inst.target",
        rating=MeasurementPropertyRating.SUFFICIENT,
        value_raw="0.81",
        evidence_span_id="sen.101",
    )

    template5 = build_template5_characteristics_table(
        study_contexts=(study,),
        instrument_contexts=(context,),
        article_file_path=article_file_path,
        article_markdown_text=article_markdown_text,
    )
    template6 = build_template6_content_validity_table(
        study_contexts=(study,),
        instrument_contexts=(context,),
        rob_assessments=(content_bundle,),
        article_file_path=article_file_path,
        article_markdown_text=article_markdown_text,
    )
    template7 = build_template7_evidence_table(
        instrument_contexts=(context,),
        rob_assessments=(reliability_bundle,),
        measurement_results=(measurement_result,),
        synthesis_results=(),
        grade_results=(),
        article_file_path=article_file_path,
        article_markdown_text=article_markdown_text,
    )
    template8 = build_template8_summary_table(
        instrument_contexts=(context,),
        synthesis_results=(),
        grade_results=(),
    )

    expected_label = "Garcia et al., 2024"
    template5_row = template5.rows[0]
    template6_row = template6.rows[0]
    template7_study_row = next(row for row in template7.rows if row.row_kind.value == "study")
    assert template5_row.study_id == "study.1"
    assert template6_row.study_id == "study.1"
    assert template7_study_row.study_id == "study.1"
    assert template5_row.study_display_label == expected_label
    assert template6_row.study_display_label == expected_label
    assert template7_study_row.study_display_label == expected_label

    template5_df = template5_to_dataframe(template5)
    template6_df = template6_to_dataframe(template6)
    template7_df = template7_to_dataframe(template7)
    template8_df = template8_to_dataframe(template8)
    assert template5_df.loc[0, "study"] == expected_label
    assert template5_df.loc[0, "study_id"] == "study.1"
    assert template6_df.loc[0, "study"] == expected_label
    assert template6_df.loc[0, "study_id"] == "study.1"
    assert template7_df.loc[0, "study"] == expected_label
    assert template7_df.loc[0, "study_id"] == "study.1"
    assert "study" not in template8_df.columns

    template5_payload = table_to_json_ready(template5)
    template7_payload = table_to_json_ready(template7)
    assert template5_payload["rows"][0]["study_id"] == "study.1"
    assert template5_payload["rows"][0]["study_display_label"] == expected_label
    assert template7_payload["rows"][0]["study_id"] == "study.1"
    assert template7_payload["rows"][0]["study_display_label"] == expected_label


def test_template5_filters_method_and_generic_category_tokens_from_rows() -> None:
    study = _study_context(
        study_id="study.1",
        enrollment_n=41,
        analyzed_n=37,
        limb_n=51,
        follow_up=("baseline", "24 months"),
    )
    contexts = (
        _instrument_context(
            context_id="instctx.plusm",
            study_id="study.1",
            instrument_id="inst.plusm",
            instrument_name="PLUS-M",
            instrument_version="v1",
            subscale="overall",
        ),
        _instrument_context(
            context_id="instctx.anova",
            study_id="study.1",
            instrument_id="inst.anova",
            instrument_name="ANOVA",
            instrument_version="v1",
            subscale="overall",
        ),
        _instrument_context(
            context_id="instctx.cfa",
            study_id="study.1",
            instrument_id="inst.cfa",
            instrument_name="CFA",
            instrument_version="v1",
            subscale="overall",
        ),
        _instrument_context(
            context_id="instctx.prom",
            study_id="study.1",
            instrument_id="inst.prom",
            instrument_name="PROM",
            instrument_version="v1",
            subscale="overall",
        ),
        _instrument_context(
            context_id="instctx.proms",
            study_id="study.1",
            instrument_id="inst.proms",
            instrument_name="PROMs",
            instrument_version="v1",
            subscale="overall",
        ),
        _instrument_context(
            context_id="instctx.wlsmv",
            study_id="study.1",
            instrument_id="inst.wlsmv",
            instrument_name="WLSMV",
            instrument_version="v1",
            subscale="overall",
        ),
    )

    table = build_template5_characteristics_table(
        study_contexts=(study,),
        instrument_contexts=contexts,
    )

    assert {row.instrument_name for row in table.rows} == {"PLUS-M"}


def test_template5_prefers_target_context_and_excludes_comparator_rows() -> None:
    study = _study_context(
        study_id="study.1",
        enrollment_n=41,
        analyzed_n=37,
        limb_n=51,
        follow_up=("baseline", "24 months"),
    )
    contexts = (
        _instrument_context(
            context_id="instctx.target",
            study_id="study.1",
            instrument_id="inst.target",
            instrument_name="PLUS-M",
            instrument_version="v1",
            subscale="overall",
            instrument_role=InstrumentContextRole.TARGET_UNDER_APPRAISAL,
        ),
        _instrument_context(
            context_id="instctx.abc",
            study_id="study.1",
            instrument_id="inst.abc",
            instrument_name="ABC",
            instrument_version="v1",
            subscale="overall",
            instrument_role=InstrumentContextRole.COMPARATOR_ONLY,
        ),
        _instrument_context(
            context_id="instctx.peqms",
            study_id="study.1",
            instrument_id="inst.peqms",
            instrument_name="PEQ-MS",
            instrument_version="v1",
            subscale="overall",
            instrument_role=InstrumentContextRole.COMPARATOR,
        ),
    )

    table = build_template5_characteristics_table(
        study_contexts=(study,),
        instrument_contexts=contexts,
    )

    assert {row.instrument_name for row in table.rows} == {"PLUS-M"}


def test_template5_populates_enrollment_and_analyzed_from_structured_roles() -> None:
    study = _study_context(
        study_id="study.1",
        enrollment_n=1180,
        analyzed_n=1091,
        limb_n=51,
        follow_up=("baseline", "24 months"),
    ).model_copy(
        update={
            "sample_size_observations": (
                _sample_size_observation(
                    obs_id="ssobs.study.1.enrollment",
                    role=SampleSizeRole.ENROLLMENT,
                    sample_size=1180,
                    span_id="sen.study.1.enrollment",
                ),
                _sample_size_observation(
                    obs_id="ssobs.study.1.analyzed",
                    role=SampleSizeRole.ANALYZED,
                    sample_size=1091,
                    span_id="sen.study.1.analyzed",
                ),
            )
        }
    )
    context = _instrument_context(
        context_id="instctx.target",
        study_id="study.1",
        instrument_id="inst.target",
        instrument_name="PLUS-M",
        instrument_version="v1",
        subscale="overall",
        instrument_role=InstrumentContextRole.TARGET_UNDER_APPRAISAL,
    )

    table = build_template5_characteristics_table(
        study_contexts=(study,),
        instrument_contexts=(context,),
    )

    assert len(table.rows) == 1
    assert table.rows[0].enrollment_n == 1180
    assert table.rows[0].analyzed_n == 1091
    assert table.rows[0].limb_level_n is None


def test_template5_populates_analyzed_from_measurement_results_when_structured_role_is_absent() -> None:
    study = _study_context(
        study_id="study.1",
        enrollment_n=1180,
        analyzed_n=1091,
        limb_n=51,
        follow_up=("baseline", "24 months"),
    ).model_copy(
        update={
            "sample_size_observations": (
                _sample_size_observation(
                    obs_id="ssobs.study.1.enrollment",
                    role=SampleSizeRole.ENROLLMENT,
                    sample_size=1180,
                    span_id="sen.study.1.enrollment",
                ),
            )
        }
    )
    context = _instrument_context(
        context_id="instctx.target",
        study_id="study.1",
        instrument_id="inst.target",
        instrument_name="PLUS-M",
        instrument_version="v1",
        subscale="overall",
        instrument_role=InstrumentContextRole.TARGET_UNDER_APPRAISAL,
    )
    measurement_result = _measurement_result(
        result_id="mpr.1",
        study_id="study.1",
        instrument_id="inst.target",
        rating=MeasurementPropertyRating.SUFFICIENT,
        value_raw="0.81",
        evidence_span_id="sen.101",
    ).model_copy(update={"inputs_used": {"sample_size_selected": 1091}})

    table = build_template5_characteristics_table(
        study_contexts=(study,),
        instrument_contexts=(context,),
        measurement_results=(measurement_result,),
    )

    assert len(table.rows) == 1
    assert table.rows[0].enrollment_n == 1180
    assert table.rows[0].analyzed_n == 1091
    assert table.rows[0].limb_level_n is None


def test_template5_leaves_sample_sizes_blank_when_no_structured_role_is_available() -> None:
    study = _study_context(
        study_id="study.1",
        enrollment_n=1180,
        analyzed_n=1091,
        limb_n=51,
        follow_up=("baseline", "24 months"),
    ).model_copy(
        update={
            "sample_size_observations": (
                _sample_size_observation(
                    obs_id="ssobs.study.1.other",
                    role=SampleSizeRole.OTHER,
                    sample_size=1091,
                    span_id="sen.study.1.other",
                ),
            )
        }
    )
    context = _instrument_context(
        context_id="instctx.target",
        study_id="study.1",
        instrument_id="inst.target",
        instrument_name="PLUS-M",
        instrument_version="v1",
        subscale="overall",
        instrument_role=InstrumentContextRole.TARGET_UNDER_APPRAISAL,
    )

    table = build_template5_characteristics_table(
        study_contexts=(study,),
        instrument_contexts=(context,),
    )

    assert len(table.rows) == 1
    assert table.rows[0].enrollment_n is None
    assert table.rows[0].analyzed_n is None
    assert table.rows[0].limb_level_n is None


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


def test_template6_includes_box1_and_linked_box2_rows_for_target_prom_only() -> None:
    study = _study_context(
        study_id="study.1",
        enrollment_n=42,
        analyzed_n=39,
        limb_n=46,
        follow_up=("baseline", "6 months"),
    )
    target_context = _instrument_context(
        context_id="instctx.target",
        study_id="study.1",
        instrument_id="inst.target",
        instrument_name="PROM-X",
        instrument_version="v1",
        subscale="overall",
        instrument_role=InstrumentContextRole.TARGET_UNDER_APPRAISAL,
    )
    comparator_context = _instrument_context(
        context_id="instctx.comparator",
        study_id="study.1",
        instrument_id="inst.comparator",
        instrument_name="Comparator-Y",
        instrument_version="v1",
        subscale="overall",
        instrument_role=InstrumentContextRole.ADDITIONAL,
    )

    rob_assessments = (
        _manual_box_assessment_bundle(
            bundle_id="bundle.box1.target",
            study_id="study.1",
            instrument_id="inst.target",
            measurement_property="prom_development",
            cosmin_box="box_1_prom_development",
            item_code="B1.1_target_population_definition",
        ),
        _manual_box_assessment_bundle(
            bundle_id="bundle.box2.target",
            study_id="study.1",
            instrument_id="inst.target",
            measurement_property="content_validity",
            cosmin_box="box_2_content_validity",
            item_code="B2.1_relevance_to_construct",
        ),
        _manual_box_assessment_bundle(
            bundle_id="bundle.box2.comparator",
            study_id="study.1",
            instrument_id="inst.comparator",
            measurement_property="content_validity",
            cosmin_box="box_2_content_validity",
            item_code="B2.1_relevance_to_construct",
        ),
        _box_assessment_bundle(
            bundle_id="bundle.box6.target",
            study_id="study.1",
            instrument_id="inst.target",
            measurement_property="reliability",
            box_rating=CosminBoxRating.ADEQUATE,
            evidence_span_id="sen.999",
        ),
    )

    table = build_template6_content_validity_table(
        study_contexts=(study,),
        instrument_contexts=(target_context, comparator_context),
        rob_assessments=rob_assessments,
    )

    assert table.template_code == "template_6"
    assert len(table.rows) == 4
    assert all(row.instrument_name == "PROM-X" for row in table.rows)
    assert {row.cosmin_box for row in table.rows} == {
        "box_1_prom_development",
        "box_2_content_validity",
    }
    assert {row.measurement_property for row in table.rows} == {
        "prom_development",
        "content_validity",
    }
    assert {row.row_kind.value for row in table.rows} == {"box_summary", "item"}
    assert all(row.uncertainty_status == "reviewer_required" for row in table.rows)
    assert all(row.reviewer_decision_status == "pending" for row in table.rows)
    box_rows = [row for row in table.rows if row.row_kind.value == "box_summary"]
    item_rows = [row for row in table.rows if row.row_kind.value == "item"]
    assert len(box_rows) == 2
    assert len(item_rows) == 2
    assert all(row.box_rating == "doubtful" for row in box_rows)
    assert all(row.item_rating is None for row in item_rows)

    df = template6_to_dataframe(table)
    assert len(df) == len(table.rows)
    assert "cosmin_box" in df.columns

    payload = table_to_json_ready(table)
    assert payload["template_code"] == "template_6"
    assert len(payload["rows"]) == len(table.rows)
    payload_item_rows = [row for row in payload["rows"] if row["row_kind"] == "item"]
    assert payload_item_rows
    assert all(row["item_rating"] is None for row in payload_item_rows)


def test_template6_future_paper_style_pending_item_rows_stay_neutral_until_reviewed() -> None:
    study = _study_context(
        study_id="study.future.1",
        enrollment_n=88,
        analyzed_n=80,
        limb_n=96,
        follow_up=("baseline", "3 months"),
    )
    target_context = _instrument_context(
        context_id="instctx.future.target",
        study_id="study.future.1",
        instrument_id="inst.future.target",
        instrument_name="PROM-Future",
        instrument_version="vNext",
        subscale="mobility",
        instrument_role=InstrumentContextRole.TARGET_UNDER_APPRAISAL,
    )
    table = build_template6_content_validity_table(
        study_contexts=(study,),
        instrument_contexts=(target_context,),
        rob_assessments=(
            _manual_box_assessment_bundle(
                bundle_id="bundle.future.box1.target",
                study_id="study.future.1",
                instrument_id="inst.future.target",
                measurement_property="prom_development",
                cosmin_box="box_1_prom_development",
                item_code="B1.1_target_population_definition",
            ),
        ),
    )

    assert len(table.rows) == 2
    box_row = next(row for row in table.rows if row.row_kind.value == "box_summary")
    item_row = next(row for row in table.rows if row.row_kind.value == "item")
    assert box_row.box_rating == "doubtful"
    assert item_row.item_rating is None
    assert item_row.uncertainty_status == "reviewer_required"
    assert item_row.reviewer_decision_status == "pending"


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
    instrument_role: InstrumentContextRole = InstrumentContextRole.ADDITIONAL,
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
        instrument_role=instrument_role,
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


def _manual_box_assessment_bundle(
    *,
    bundle_id: str,
    study_id: str,
    instrument_id: str,
    measurement_property: str,
    cosmin_box: str,
    item_code: str,
) -> BoxAssessmentBundle:
    item_id = f"item.{bundle_id}"
    item = CosminItemAssessment(
        id=item_id,
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=measurement_property,
        cosmin_box=cosmin_box,
        item_code=item_code,
        item_rating=CosminItemRating.DOUBTFUL,
        evidence_span_ids=["sen.manual"],
        uncertainty_status=UncertaintyStatus.REVIEWER_REQUIRED,
        reviewer_decision_status=ReviewerDecisionStatus.PENDING,
    )
    box = CosminBoxAssessment(
        id=f"box.{bundle_id}",
        study_id=study_id,
        instrument_id=instrument_id,
        measurement_property=measurement_property,
        cosmin_box=cosmin_box,
        box_rating=CosminBoxRating.DOUBTFUL,
        item_assessment_ids=[item_id],
        evidence_span_ids=["sen.manual"],
        uncertainty_status=UncertaintyStatus.REVIEWER_REQUIRED,
        reviewer_decision_status=ReviewerDecisionStatus.PENDING,
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
