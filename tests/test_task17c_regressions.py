"""Task 17c regression tests for narrowly scoped scientific routing repairs."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from cosmin_assistant.cli.pipeline import run_provisional_assessment
from cosmin_assistant.extract import (
    InstrumentContextRole,
    extract_context_from_markdown_file,
)
from cosmin_assistant.models import PropertyActivationStatus
from cosmin_assistant.tables.output_builders import export_run_outputs

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "markdown"
_FRANCHIGNONI_PATH = _FIXTURE_DIR / "nonsci_franchignoni2023_rasch.md"
_FRANCHIGNONI_HEADTOHEAD_PATH = _FIXTURE_DIR / "nonsci_franchignoni2023_headtohead.md"
_GAILEY_PATH = _FIXTURE_DIR / "sci_gailey2002_amp_validation.md"
_CARSE_PATH = _FIXTURE_DIR / "sci_carse2021_mcid.md"
_CARSE_RUN8_LATEX_PATH = _FIXTURE_DIR / "sci_carse2021_mcid_run8_latex.md"
_AWAD_PATH = _FIXTURE_DIR / "awad_pbom_validation.md"
_LEGACY_ARTIFACT_FILE_NAMES = (
    "run_manifest.json",
    "evidence.json",
    "rob_assessment.json",
    "measurement_property_results.json",
    "synthesis.json",
    "grade.json",
    "summary_report.md",
    "summary_report.docx",
    "per_study_results.csv",
    "review_overrides.json",
    "adjudication_notes.json",
    "review_state.json",
)


def _instrument_name_by_id(run: object) -> dict[str, str]:
    assessment = run
    return {
        item.instrument_id: str(item.instrument_name.candidates[0].normalized_value)
        for item in assessment.context_extraction.instrument_contexts
        if item.instrument_name.candidates
    }


def _target_results_by_property(run: object) -> dict[str, object]:
    assessment = run
    target_id = assessment.context_extraction.target_instrument_id
    assert target_id is not None
    return {
        result.measurement_property: result
        for result in assessment.measurement_property_results
        if result.instrument_id == target_id
    }


def _assert_all_output_evidence_ids_resolve_within_run(run: object) -> None:
    assessment = run
    valid_span_ids = {
        span.id
        for span in (
            assessment.parsed_document.headings
            + assessment.parsed_document.paragraphs
            + assessment.parsed_document.sentences
        )
    }

    def assert_valid(evidence_span_ids: tuple[str, ...] | list[str]) -> None:
        for evidence_span_id in evidence_span_ids:
            assert evidence_span_id in valid_span_ids

    for bundle in assessment.rob_assessments:
        assert_valid(bundle.box_assessment.evidence_span_ids)
        for item in bundle.item_assessments:
            assert_valid(item.evidence_span_ids)

    for result in assessment.measurement_property_results:
        assert_valid(result.evidence_span_ids)
        for raw in result.raw_results:
            assert_valid(raw.evidence_span_ids)
        for prerequisite in result.prerequisite_decisions:
            assert_valid(prerequisite.evidence_span_ids)
        for threshold in result.threshold_comparisons:
            assert_valid(threshold.evidence_span_ids)

    for synthesis in assessment.synthesis_results:
        assert_valid(synthesis.evidence_span_ids)
        for entry in synthesis.study_entries:
            assert_valid(entry.evidence_span_ids)

    for grade in assessment.grade_results:
        assert_valid(grade.evidence_span_ids)
        for decision in grade.domain_decisions:
            assert_valid(decision.evidence_span_ids)
        for downgrade in grade.downgrade_records:
            assert_valid(downgrade.evidence_span_ids)


def _collect_evidence_span_ids(payload: object) -> set[str]:
    collected: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "evidence_span_ids" and isinstance(value, list):
                    collected.update(item for item in value if isinstance(item, str))
                else:
                    walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return collected


def test_franchignoni_activates_internal_structure_without_spurious_properties() -> None:
    run = run_provisional_assessment(article_path=_FRANCHIGNONI_PATH, profile_type="prom")
    target_results = _target_results_by_property(run)

    assert (
        target_results["structural_validity"].activation_status
        is PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )
    assert (
        target_results["internal_consistency"].activation_status
        is PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )

    for property_name in (
        "reliability",
        "responsiveness",
        "criterion_validity",
        "cross_cultural_validity_measurement_invariance",
    ):
        assert (
            target_results[property_name].activation_status
            is not PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
        )

    _assert_all_output_evidence_ids_resolve_within_run(run)


def test_franchignoni_head_to_head_rasch_and_alpha_preserve_both_proms(tmp_path: Path) -> None:
    run = run_provisional_assessment(
        article_path=_FRANCHIGNONI_HEADTOHEAD_PATH,
        profile_type="prom",
    )
    outputs = export_run_outputs(run=run, out_dir=tmp_path / "franchignoni_headtohead")

    evidence_payload = json.loads(Path(outputs["evidence_json"]).read_text(encoding="utf-8"))
    measurement_payload = json.loads(
        Path(outputs["measurement_property_results_json"]).read_text(encoding="utf-8")
    )
    synthesis_payload = json.loads(Path(outputs["synthesis_json"]).read_text(encoding="utf-8"))
    summary_text = Path(outputs["summary_report_md"]).read_text(encoding="utf-8")

    contexts = evidence_payload["context_extraction"]["instrument_contexts"]
    name_by_id = {
        context["instrument_id"]: (
            context["instrument_name"]["candidates"][0]["normalized_value"]
            if context["instrument_name"]["candidates"]
            else context["instrument_id"]
        )
        for context in contexts
    }
    role_by_name = {
        (
            context["instrument_name"]["candidates"][0]["normalized_value"]
            if context["instrument_name"]["candidates"]
            else context["instrument_id"]
        ): context["instrument_role"]
        for context in contexts
    }
    target_names = {"PEQ-MS", "PMQ 2.0"}

    assert target_names <= set(role_by_name)
    assert role_by_name["PEQ-MS"] in {
        "target_under_appraisal",
        "co_primary_outcome_instrument",
    }
    assert role_by_name["PMQ 2.0"] in {
        "target_under_appraisal",
        "co_primary_outcome_instrument",
    }

    by_name_and_property = {
        (
            str(name_by_id.get(item["instrument_id"], item["instrument_id"])),
            item["measurement_property"],
        ): item
        for item in measurement_payload
        if str(name_by_id.get(item["instrument_id"], item["instrument_id"])) in target_names
    }

    for outcome_name in target_names:
        structural = by_name_and_property[(outcome_name, "structural_validity")]
        assert structural["activation_status"] == "direct_current_study_evidence"
        assert "No structural-validity statistics" not in structural["explanation"]

        internal = by_name_and_property[(outcome_name, "internal_consistency")]
        assert internal["activation_status"] == "direct_current_study_evidence"

        reliability = by_name_and_property[(outcome_name, "reliability")]
        assert reliability["activation_status"] != "direct_current_study_evidence"

        cross_cultural = by_name_and_property[
            (outcome_name, "cross_cultural_validity_measurement_invariance")
        ]
        assert cross_cultural["activation_status"] != "direct_current_study_evidence"

    synthesis_names = {
        item["instrument_name"]
        for item in synthesis_payload
        if item["measurement_property"] in {"structural_validity", "internal_consistency"}
    }
    assert target_names <= synthesis_names

    assert "PEQ-MS" in summary_text
    assert "PMQ 2.0" in summary_text


def test_gailey_validation_preserves_amp_target_and_comparator_routing() -> None:
    context = extract_context_from_markdown_file(_GAILEY_PATH)
    by_name = {
        str(item.instrument_name.candidates[0].normalized_value): item
        for item in context.instrument_contexts
        if item.instrument_name.candidates
    }

    assert {"AMP", "AMPPRO", "AMPNOPRO"} & set(by_name)
    assert "6-MWT" in by_name
    assert "AAS" in by_name

    target_id = context.target_instrument_id
    assert target_id is not None
    target_name = next(name for name, item in by_name.items() if item.instrument_id == target_id)
    assert target_name in {"AMP", "AMPPRO", "AMPNOPRO"}

    comparator_ids = set(context.comparator_instrument_ids)
    assert by_name["6-MWT"].instrument_id in comparator_ids
    assert by_name["AAS"].instrument_id in comparator_ids
    assert by_name["6-MWT"].instrument_role is InstrumentContextRole.COMPARATOR_ONLY
    assert by_name["AAS"].instrument_role is InstrumentContextRole.COMPARATOR_ONLY

    run = run_provisional_assessment(article_path=_GAILEY_PATH, profile_type="prom")
    target_results = _target_results_by_property(run)

    assert (
        target_results["reliability"].activation_status
        is PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )
    assert (
        target_results["hypotheses_testing_for_construct_validity"].activation_status
        is PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )
    assert (
        target_results["criterion_validity"].activation_status
        is not PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )
    assert (
        target_results["criterion_validity"].activation_status
        is not PropertyActivationStatus.REVIEWER_REQUIRED
    )
    assert target_results["reliability"].inputs_used.get("sample_size_selected") == 24
    assert (
        target_results["hypotheses_testing_for_construct_validity"].inputs_used.get(
            "sample_size_selected"
        )
        == 167
    )
    assert target_results["reliability"].inputs_used.get("sample_size_selected") != 18
    assert (
        target_results["hypotheses_testing_for_construct_validity"].inputs_used.get(
            "sample_size_selected"
        )
        != 18
    )

    # PBOM/performance-test targets should not receive direct Step-6 PROM properties
    # unless internal-structure evidence was truly reported.
    assert (
        target_results["structural_validity"].activation_status
        is not PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )
    assert (
        target_results["internal_consistency"].activation_status
        is not PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
    )

    family_names = {"AMP", "AMPPRO", "AMPNOPRO"}
    synthesis_rows = [
        entry for entry in run.synthesis_results if entry.instrument_name.upper() in family_names
    ]
    assert synthesis_rows

    criterion_rows = [
        entry for entry in synthesis_rows if entry.measurement_property == "criterion_validity"
    ]
    assert not criterion_rows

    reliability_rows = [
        entry for entry in synthesis_rows if entry.measurement_property == "reliability"
    ]
    construct_rows = [
        entry
        for entry in synthesis_rows
        if entry.measurement_property == "hypotheses_testing_for_construct_validity"
    ]
    assert reliability_rows
    assert construct_rows
    assert all(entry.total_sample_size == 24 for entry in reliability_rows)
    assert all(entry.total_sample_size == 167 for entry in construct_rows)
    assert all(entry.total_sample_size != 18 for entry in reliability_rows + construct_rows)

    for property_name in ("reliability", "hypotheses_testing_for_construct_validity"):
        names_for_property = {
            entry.instrument_name.upper()
            for entry in synthesis_rows
            if entry.measurement_property == property_name
        }
        assert not (
            "AMP" in names_for_property
            and any(name.startswith("AMP") and name != "AMP" for name in names_for_property)
        )

    assert all(
        entry.instrument_name != "6-MWT"
        for entry in run.synthesis_results
        if entry.measurement_property
        in {"reliability", "hypotheses_testing_for_construct_validity"}
    )

    _assert_all_output_evidence_ids_resolve_within_run(run)


def test_gailey_export_artifacts_preserve_consistent_variant_target_set(tmp_path: Path) -> None:
    run = run_provisional_assessment(article_path=_GAILEY_PATH, profile_type="prom")
    outputs = export_run_outputs(run=run, out_dir=tmp_path / "gailey_export_coherence")

    evidence_payload = json.loads(Path(outputs["evidence_json"]).read_text(encoding="utf-8"))
    measurement_payload = json.loads(
        Path(outputs["measurement_property_results_json"]).read_text(encoding="utf-8")
    )
    synthesis_payload = json.loads(Path(outputs["synthesis_json"]).read_text(encoding="utf-8"))
    summary_text = Path(outputs["summary_report_md"]).read_text(encoding="utf-8")

    name_by_id = {
        context["instrument_id"]: (
            context["instrument_name"]["candidates"][0]["normalized_value"]
            if context["instrument_name"]["candidates"]
            else "unknown"
        )
        for context in evidence_payload["context_extraction"]["instrument_contexts"]
    }
    active_statuses = {
        "direct_current_study_evidence",
        "measurement_error_support_only",
        "interpretability_only",
        "reviewer_required",
    }

    measurement_active_keys = {
        (
            str(name_by_id.get(item["instrument_id"], "unknown")),
            item["measurement_property"],
            item["activation_status"],
        )
        for item in measurement_payload
        if item["activation_status"] in active_statuses
    }
    synthesis_keys = {
        (
            item["instrument_name"],
            item["measurement_property"],
            item["activation_status"],
        )
        for item in synthesis_payload
    }
    assert measurement_active_keys == synthesis_keys

    surviving_targets = {item["instrument_name"] for item in synthesis_payload}
    assert surviving_targets == {"AMPPRO", "AMPnoPRO"}
    assert "AMP" not in surviving_targets
    assert "6-MWT" not in surviving_targets
    assert "AAS" not in surviving_targets
    assert "`AMPPRO` / `reliability`" in summary_text
    assert "`AMPnoPRO` / `reliability`" in summary_text
    assert "`AMP` / `reliability`" not in summary_text


def test_export_writes_prefixed_and_legacy_artifacts_for_named_papers(tmp_path: Path) -> None:
    cases = (
        ("Sci_Carse2021.md", _CARSE_PATH),
        ("NonSci_Franchignoni2023.md", _FRANCHIGNONI_PATH),
    )

    for file_name, source_path in cases:
        article_path = tmp_path / file_name
        article_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

        run = run_provisional_assessment(article_path=article_path, profile_type="prom")
        out_dir = tmp_path / f"{article_path.stem}_out"
        outputs = export_run_outputs(run=run, out_dir=out_dir)

        manifest = json.loads(Path(outputs["run_manifest_json"]).read_text(encoding="utf-8"))
        assert manifest["artifact_prefix"] == article_path.stem

        for legacy_name in _LEGACY_ARTIFACT_FILE_NAMES:
            legacy_path = out_dir / legacy_name
            prefixed_path = out_dir / f"{article_path.stem}__{legacy_name}"
            assert legacy_path.exists()
            assert prefixed_path.exists()
            assert legacy_path.stat().st_size > 0
            assert prefixed_path.stat().st_size > 0


def test_export_prefix_sanitizes_spaces_and_symbols_conservatively(tmp_path: Path) -> None:
    article_path = tmp_path / "My Paper (v1)#2026.md"
    article_path.write_text(_CARSE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    run = run_provisional_assessment(article_path=article_path, profile_type="prom")
    outputs = export_run_outputs(run=run, out_dir=tmp_path / "sanitized_prefix")

    manifest = json.loads(Path(outputs["run_manifest_json"]).read_text(encoding="utf-8"))
    assert manifest["artifact_prefix"] == "My_Paper_v12026"
    assert (
        Path(outputs["run_manifest_json"]).parent / "My_Paper_v12026__run_manifest.json"
    ).exists()


def test_carse_interpretability_routing_avoids_spurious_responsiveness() -> None:
    context = extract_context_from_markdown_file(_CARSE_PATH)
    by_name = {
        str(item.instrument_name.candidates[0].normalized_value): item
        for item in context.instrument_contexts
        if item.instrument_name.candidates
    }

    studied_names = {"walking velocity", "GPS", "2-MWT"}
    present_studied_names = {
        name for name in by_name if name in studied_names or name.lower() == "walking velocity"
    }
    assert present_studied_names == studied_names
    assert not any("two minute walk test" in name.lower() for name in by_name)
    assert not any(name.lower() == "2mwt" for name in by_name)
    assert all(
        by_name[name].instrument_role
        not in (
            InstrumentContextRole.COMPARATOR_ONLY,
            InstrumentContextRole.COMPARATOR,
            InstrumentContextRole.BACKGROUND_ONLY,
        )
        for name in studied_names
    )

    run = run_provisional_assessment(article_path=_CARSE_PATH, profile_type="prom")
    names_by_id = _instrument_name_by_id(run)

    present_names = {name for name in names_by_id.values() if name in studied_names}
    assert present_names == studied_names

    for result in run.measurement_property_results:
        if names_by_id.get(result.instrument_id) not in studied_names:
            continue
        if result.measurement_property != "responsiveness":
            continue
        assert (
            result.activation_status is not PropertyActivationStatus.DIRECT_CURRENT_STUDY_EVIDENCE
        )

    interpretability_names = {
        names_by_id[result.instrument_id]
        for result in run.measurement_property_results
        if result.measurement_property == "interpretability"
        and result.activation_status is PropertyActivationStatus.INTERPRETABILITY_ONLY
        and names_by_id.get(result.instrument_id) in studied_names
    }
    assert interpretability_names == studied_names

    synthesis_interpretability_names = {
        synthesis.instrument_name
        for synthesis in run.synthesis_results
        if synthesis.measurement_property == "interpretability"
        and synthesis.activation_status is PropertyActivationStatus.INTERPRETABILITY_ONLY
    }
    assert synthesis_interpretability_names == studied_names
    assert not any(
        synthesis.instrument_name.lower() == "two minute walk test"
        for synthesis in run.synthesis_results
    )

    instrument_version_candidates = [
        candidate.normalized_value
        for instrument in run.context_extraction.instrument_contexts
        for candidate in instrument.instrument_version.candidates
    ]
    assert "22" not in {str(value) for value in instrument_version_candidates}

    _assert_all_output_evidence_ids_resolve_within_run(run)


def test_carse_export_manifest_and_artifacts_are_isolated_to_current_run(
    tmp_path: Path,
) -> None:
    run = run_provisional_assessment(article_path=_CARSE_PATH, profile_type="prom")
    outputs = export_run_outputs(run=run, out_dir=tmp_path / "carse_isolation")

    manifest_payload = json.loads(Path(outputs["run_manifest_json"]).read_text(encoding="utf-8"))
    assert manifest_payload["source_article_path"] == run.article_path
    assert manifest_payload["source_article_hash"] == run.source_article_hash
    assert manifest_payload["profile"] == "prom"

    evidence_payload = json.loads(Path(outputs["evidence_json"]).read_text(encoding="utf-8"))
    parsed_document = evidence_payload["parsed_document"]
    assert parsed_document["file_path"] == run.article_path
    assert evidence_payload["article_path"] == run.article_path
    assert (
        parsed_document["id"]
        == evidence_payload["context_extraction"]["article_id"]
        == evidence_payload["statistics_extraction"]["article_id"]
    )

    valid_span_ids = {
        item["id"]
        for key in ("headings", "paragraphs", "sentences")
        for item in parsed_document[key]
    }
    assert valid_span_ids

    artifact_paths = (
        outputs["rob_assessment_json"],
        outputs["measurement_property_results_json"],
        outputs["synthesis_json"],
        outputs["grade_json"],
    )
    for artifact_path in artifact_paths:
        artifact_payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        artifact_span_ids = _collect_evidence_span_ids(artifact_payload)
        assert artifact_span_ids <= valid_span_ids

        artifact_text = json.dumps(artifact_payload)
        assert "Q-TFA" not in artifact_text
        assert "PROMIS" not in artifact_text
        assert '"AMP"' not in artifact_text
        assert "6-MWT" not in artifact_text

    measurement_payload = json.loads(
        Path(outputs["measurement_property_results_json"]).read_text(encoding="utf-8")
    )
    synthesis_payload = json.loads(Path(outputs["synthesis_json"]).read_text(encoding="utf-8"))
    grade_payload = json.loads(Path(outputs["grade_json"]).read_text(encoding="utf-8"))
    contexts = evidence_payload["context_extraction"]["instrument_contexts"]
    name_by_id = {
        context["instrument_id"]: (
            context["instrument_name"]["candidates"][0]["normalized_value"]
            if context["instrument_name"]["candidates"]
            else context["instrument_id"]
        )
        for context in contexts
    }

    measurement_keys = {
        (
            str(name_by_id.get(item["instrument_id"], item["instrument_id"])),
            item["measurement_property"],
            item["activation_status"],
        )
        for item in measurement_payload
    }
    synthesis_keys = {
        (
            item["instrument_name"],
            item["measurement_property"],
            item["activation_status"],
        )
        for item in synthesis_payload
    }
    assert measurement_keys == synthesis_keys

    synthesis_outcomes = {
        item["instrument_name"]
        for item in synthesis_payload
        if item["measurement_property"] == "interpretability"
    }
    assert synthesis_outcomes == {"walking velocity", "GPS", "2-MWT"}
    assert "two minute walk test" not in {name.lower() for name in synthesis_outcomes}

    expected_sample_sizes = {"walking velocity": 60, "GPS": 60, "2-MWT": 119}

    observed_measurement_sizes = {
        (
            str(name_by_id.get(item["instrument_id"], item["instrument_id"])),
            item["measurement_property"],
        ): item["inputs_used"].get("sample_size_selected")
        for item in measurement_payload
        if item["measurement_property"] in {"interpretability", "measurement_error"}
        and str(name_by_id.get(item["instrument_id"], item["instrument_id"]))
        in expected_sample_sizes
    }
    for outcome_name, sample_size in expected_sample_sizes.items():
        assert observed_measurement_sizes[(outcome_name, "interpretability")] == sample_size
        assert observed_measurement_sizes[(outcome_name, "measurement_error")] == sample_size

    observed_synthesis_sizes = {
        (item["instrument_name"], item["measurement_property"]): item["total_sample_size"]
        for item in synthesis_payload
        if item["measurement_property"] in {"interpretability", "measurement_error"}
        and item["instrument_name"] in expected_sample_sizes
    }
    for outcome_name, sample_size in expected_sample_sizes.items():
        assert observed_synthesis_sizes[(outcome_name, "interpretability")] == sample_size
        assert observed_synthesis_sizes[(outcome_name, "measurement_error")] == sample_size

    synthesis_name_by_id = {item["id"]: item["instrument_name"] for item in synthesis_payload}
    observed_grade_sizes = {
        (synthesis_name_by_id[item["synthesis_id"]], item["measurement_property"]): item[
            "total_sample_size"
        ]
        for item in grade_payload
        if item["measurement_property"] in {"interpretability", "measurement_error"}
        and synthesis_name_by_id[item["synthesis_id"]] in expected_sample_sizes
    }
    for outcome_name, sample_size in expected_sample_sizes.items():
        assert observed_grade_sizes[(outcome_name, "interpretability")] == sample_size
        assert observed_grade_sizes[(outcome_name, "measurement_error")] == sample_size

    assert not any(
        item["activation_status"] == "direct_current_study_evidence"
        and item["measurement_property"]
        in (
            "internal_consistency",
            "reliability",
            "hypotheses_testing_for_construct_validity",
            "responsiveness",
        )
        for item in measurement_payload
    )

    summary_text = Path(outputs["summary_report_md"]).read_text(encoding="utf-8")
    assert "walking velocity" in summary_text
    assert "GPS" in summary_text
    assert "2-MWT" in summary_text
    assert "two minute walk test" not in summary_text.lower()
    assert "`walking velocity` / `interpretability`: `?` (total_n=60;" in summary_text
    assert "`GPS` / `interpretability`: `?` (total_n=60;" in summary_text
    assert "`2-MWT` / `interpretability`: `?` (total_n=119;" in summary_text


def test_carse_run8_latex_sample_size_fallback_is_repaired(tmp_path: Path) -> None:
    run = run_provisional_assessment(article_path=_CARSE_RUN8_LATEX_PATH, profile_type="prom")
    outputs = export_run_outputs(run=run, out_dir=tmp_path / "carse_run8_latex")

    measurement_payload = json.loads(
        Path(outputs["measurement_property_results_json"]).read_text(encoding="utf-8")
    )
    synthesis_payload = json.loads(Path(outputs["synthesis_json"]).read_text(encoding="utf-8"))
    grade_payload = json.loads(Path(outputs["grade_json"]).read_text(encoding="utf-8"))
    evidence_payload = json.loads(Path(outputs["evidence_json"]).read_text(encoding="utf-8"))

    contexts = evidence_payload["context_extraction"]["instrument_contexts"]
    name_by_id = {
        context["instrument_id"]: (
            context["instrument_name"]["candidates"][0]["normalized_value"]
            if context["instrument_name"]["candidates"]
            else context["instrument_id"]
        )
        for context in contexts
    }
    expected_sample_sizes = {"walking velocity": 60, "GPS": 60, "2-MWT": 119}

    observed_measurement_sizes = {
        (
            str(name_by_id.get(item["instrument_id"], item["instrument_id"])),
            item["measurement_property"],
        ): item["inputs_used"].get("sample_size_selected")
        for item in measurement_payload
        if item["measurement_property"] in {"interpretability", "measurement_error"}
        and str(name_by_id.get(item["instrument_id"], item["instrument_id"]))
        in expected_sample_sizes
    }
    for outcome_name, sample_size in expected_sample_sizes.items():
        assert observed_measurement_sizes[(outcome_name, "interpretability")] == sample_size
        assert observed_measurement_sizes[(outcome_name, "measurement_error")] == sample_size

    observed_synthesis_sizes = {
        (item["instrument_name"], item["measurement_property"]): (
            item["total_sample_size"],
            {entry["sample_size"] for entry in item["study_entries"]},
        )
        for item in synthesis_payload
        if item["measurement_property"] in {"interpretability", "measurement_error"}
        and item["instrument_name"] in expected_sample_sizes
    }
    for outcome_name, sample_size in expected_sample_sizes.items():
        total_size, entry_sizes = observed_synthesis_sizes[(outcome_name, "interpretability")]
        assert total_size == sample_size
        assert entry_sizes == {sample_size}
        total_size, entry_sizes = observed_synthesis_sizes[(outcome_name, "measurement_error")]
        assert total_size == sample_size
        assert entry_sizes == {sample_size}

    synthesis_name_by_id = {item["id"]: item["instrument_name"] for item in synthesis_payload}
    observed_grade_sizes = {
        (synthesis_name_by_id[item["synthesis_id"]], item["measurement_property"]): item[
            "total_sample_size"
        ]
        for item in grade_payload
        if item["measurement_property"] in {"interpretability", "measurement_error"}
        and synthesis_name_by_id[item["synthesis_id"]] in expected_sample_sizes
    }
    for outcome_name, sample_size in expected_sample_sizes.items():
        assert observed_grade_sizes[(outcome_name, "interpretability")] == sample_size
        assert observed_grade_sizes[(outcome_name, "measurement_error")] == sample_size

    summary_text = Path(outputs["summary_report_md"]).read_text(encoding="utf-8")
    assert "`walking velocity` / `interpretability`: `?` (total_n=60;" in summary_text
    assert "`GPS` / `interpretability`: `?` (total_n=60;" in summary_text
    assert "`2-MWT` / `interpretability`: `?` (total_n=119;" in summary_text
    assert "`walking velocity` / `measurement_error`: `?` (total_n=60;" in summary_text

    synthesis_props_by_outcome: dict[str, set[str]] = {}
    for item in synthesis_payload:
        if item["instrument_name"] in expected_sample_sizes:
            synthesis_props_by_outcome.setdefault(item["instrument_name"], set()).add(
                item["measurement_property"]
            )
    for outcome_name in expected_sample_sizes:
        assert synthesis_props_by_outcome[outcome_name] == {
            "interpretability",
            "measurement_error",
        }

    assert not any(
        item["activation_status"] == "direct_current_study_evidence"
        and item["measurement_property"]
        in (
            "reliability",
            "hypotheses_testing_for_construct_validity",
            "responsiveness",
        )
        for item in measurement_payload
    )


def test_export_guard_fails_on_cross_run_provenance_contamination(tmp_path: Path) -> None:
    run = run_provisional_assessment(article_path=_CARSE_PATH, profile_type="prom")

    contaminated = run.measurement_property_results[0].model_copy(
        update={"evidence_span_ids": ("sen.cross_article.fake",)}
    )
    tampered_run = replace(run, measurement_property_results=(contaminated,))

    with pytest.raises(ValueError, match="Provenance integrity check failed"):
        export_run_outputs(run=tampered_run, out_dir=tmp_path / "contaminated")


def test_export_guard_fails_on_existing_cross_article_measurement_contamination(
    tmp_path: Path,
) -> None:
    awad_run = run_provisional_assessment(article_path=_AWAD_PATH, profile_type="prom")
    awad_out = tmp_path / "awad_guard"
    outputs = export_run_outputs(run=awad_run, out_dir=awad_out)

    gailey_run = run_provisional_assessment(article_path=_GAILEY_PATH, profile_type="prom")
    gailey_measurement_payload = [
        result.model_dump(mode="json") for result in gailey_run.measurement_property_results
    ]
    Path(outputs["measurement_property_results_json"]).write_text(
        json.dumps(gailey_measurement_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Existing artifact coherence check failed"):
        export_run_outputs(run=awad_run, out_dir=awad_out)
