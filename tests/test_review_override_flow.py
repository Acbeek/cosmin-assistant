"""Tests for reviewer override and adjudication flow on provisional JSON outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cosmin_assistant.cli.pipeline import run_provisional_assessment
from cosmin_assistant.cli.review_app import app as review_app
from cosmin_assistant.models import ProfileType
from cosmin_assistant.review import ReviewRequestBundle, apply_review_request_bundle
from cosmin_assistant.tables import export_run_outputs

_FIXTURE_ARTICLE = Path(__file__).resolve().parent / "fixtures" / "markdown" / "e2e_prom_article.md"


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_provisional_outputs(tmp_path: Path) -> Path:
    out_dir = tmp_path / "provisional"
    run = run_provisional_assessment(article_path=_FIXTURE_ARTICLE, profile_type=ProfileType.PROM)
    export_run_outputs(run=run, out_dir=out_dir)
    return out_dir


def test_no_op_review_preserves_artifacts_and_marks_finalized(tmp_path: Path) -> None:
    provisional_dir = _build_provisional_outputs(tmp_path)
    finalized_dir = tmp_path / "finalized"

    source_evidence = _load_json(provisional_dir / "evidence.json")
    source_measurement = _load_json(provisional_dir / "measurement_property_results.json")
    source_review_state = _load_json(provisional_dir / "review_state.json")

    outputs = apply_review_request_bundle(
        provisional_dir=provisional_dir,
        request=ReviewRequestBundle(),
        out_dir=finalized_dir,
    )

    assert Path(outputs["review_state_json"]).exists()

    reviewed_evidence = _load_json(finalized_dir / "evidence.json")
    reviewed_measurement = _load_json(finalized_dir / "measurement_property_results.json")
    reviewed_review_state = _load_json(finalized_dir / "review_state.json")

    assert source_evidence == reviewed_evidence
    assert source_measurement == reviewed_measurement
    assert source_review_state["review_status"] == "provisional"
    assert reviewed_review_state["review_status"] == "finalized"
    assert reviewed_review_state["overrides_applied_in_run"] == 0


def test_one_override_via_cli_updates_target_and_writes_audit_trail(tmp_path: Path) -> None:
    provisional_dir = _build_provisional_outputs(tmp_path)
    finalized_dir = tmp_path / "finalized_cli"
    runner = CliRunner()

    measurement = _load_json(provisional_dir / "measurement_property_results.json")
    assert isinstance(measurement, list)
    target = measurement[0]
    target_id = str(target["id"])
    old_rating = str(target["computed_rating"])
    new_rating = "-" if old_rating != "-" else "+"
    evidence_span_ids = target["evidence_span_ids"]

    review_file = tmp_path / "review_request.json"
    review_file.write_text(
        json.dumps(
            {
                "overrides": [
                    {
                        "target_object_type": "measurement_property_result",
                        "target_object_id": target_id,
                        "field_name": "computed_rating",
                        "overridden_value": new_rating,
                        "reason": "Manual adjudication corrected rating after reviewer consensus.",
                        "reviewer_id": "rev.101",
                        "evidence_span_ids": evidence_span_ids,
                    }
                ],
                "adjudication_notes": [
                    {
                        "decision_key": "adequacy_of_hypotheses",
                        "decision_value": "confirmed",
                        "reason": "Hypotheses were explicitly predefined in protocol appendix.",
                        "reviewer_id": "rev.101",
                        "evidence_span_ids": evidence_span_ids,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    invocation = runner.invoke(
        review_app,
        [
            str(provisional_dir),
            "--review-file",
            str(review_file),
            "--out",
            str(finalized_dir),
        ],
    )

    assert invocation.exit_code == 0, invocation.output

    reviewed_measurement = _load_json(finalized_dir / "measurement_property_results.json")
    assert isinstance(reviewed_measurement, list)
    updated = next(item for item in reviewed_measurement if item["id"] == target_id)
    assert updated["computed_rating"] == new_rating

    overrides = _load_json(finalized_dir / "review_overrides.json")
    assert isinstance(overrides, list)
    assert len(overrides) == 1
    override = overrides[0]
    assert override["target_object_id"] == target_id
    assert override["previous_value"] == old_rating
    assert override["overridden_value"] == new_rating
    assert override["reason"]
    assert override["reviewer_id"] == "rev.101"
    assert override["evidence_span_ids"] == evidence_span_ids
    assert override["created_at_utc"]

    source_evidence = _load_json(provisional_dir / "evidence.json")
    reviewed_evidence = _load_json(finalized_dir / "evidence.json")
    assert source_evidence == reviewed_evidence


def test_multiple_overrides_apply_deterministically(tmp_path: Path) -> None:
    provisional_dir = _build_provisional_outputs(tmp_path)
    finalized_dir = tmp_path / "finalized_multi"

    measurement = _load_json(provisional_dir / "measurement_property_results.json")
    synthesis = _load_json(provisional_dir / "synthesis.json")
    assert isinstance(measurement, list)
    assert isinstance(synthesis, list)

    measurement_target = measurement[0]
    synthesis_target = synthesis[0]

    review_payload = {
        "overrides": [
            {
                "target_object_type": "measurement_property_result",
                "target_object_id": measurement_target["id"],
                "field_name": "computed_rating",
                "overridden_value": "?",
                "reason": "Evidence uncertainty remained unresolved after team review.",
                "reviewer_id": "rev.202",
                "evidence_span_ids": measurement_target["evidence_span_ids"],
            },
            {
                "target_object_type": "synthesis_result",
                "target_object_id": synthesis_target["id"],
                "field_name": "summary_explanation",
                "overridden_value": "Reviewer provided consolidated subgroup explanation.",
                "reason": "Manual synthesis narrative required for transparent adjudication.",
                "reviewer_id": "rev.202",
                "evidence_span_ids": synthesis_target["evidence_span_ids"],
            },
        ],
    }

    outputs = apply_review_request_bundle(
        provisional_dir=provisional_dir,
        request=ReviewRequestBundle.model_validate(review_payload),
        out_dir=finalized_dir,
    )

    assert Path(outputs["measurement_property_results_json"]).exists()
    assert Path(outputs["synthesis_json"]).exists()

    reviewed_measurement = _load_json(finalized_dir / "measurement_property_results.json")
    reviewed_synthesis = _load_json(finalized_dir / "synthesis.json")

    assert isinstance(reviewed_measurement, list)
    assert isinstance(reviewed_synthesis, list)

    updated_measurement = next(
        item for item in reviewed_measurement if item["id"] == measurement_target["id"]
    )
    updated_synthesis = next(
        item for item in reviewed_synthesis if item["id"] == synthesis_target["id"]
    )

    assert updated_measurement["computed_rating"] == "?"
    assert (
        updated_synthesis["summary_explanation"]
        == "Reviewer provided consolidated subgroup explanation."
    )

    overrides = _load_json(finalized_dir / "review_overrides.json")
    assert isinstance(overrides, list)
    assert len(overrides) == 2


def test_invalid_override_target_raises_error(tmp_path: Path) -> None:
    provisional_dir = _build_provisional_outputs(tmp_path)

    invalid_request = ReviewRequestBundle.model_validate(
        {
            "overrides": [
                {
                    "target_object_type": "measurement_property_result",
                    "target_object_id": "mpr.nonexistent",
                    "field_name": "computed_rating",
                    "overridden_value": "+",
                    "reason": "Invalid target should fail fast.",
                    "reviewer_id": "rev.303",
                    "evidence_span_ids": ["sen.303"],
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="override target not found"):
        apply_review_request_bundle(
            provisional_dir=provisional_dir,
            request=invalid_request,
            out_dir=tmp_path / "invalid_out",
        )


def test_override_history_is_appended_for_auditable_trail(tmp_path: Path) -> None:
    provisional_dir = _build_provisional_outputs(tmp_path)
    first_review_dir = tmp_path / "first_review"
    second_review_dir = tmp_path / "second_review"

    measurement = _load_json(provisional_dir / "measurement_property_results.json")
    assert isinstance(measurement, list)
    target = measurement[0]

    first_request = ReviewRequestBundle.model_validate(
        {
            "overrides": [
                {
                    "target_object_type": "measurement_property_result",
                    "target_object_id": target["id"],
                    "field_name": "computed_rating",
                    "overridden_value": "?",
                    "reason": "First-pass reviewer adjudication.",
                    "reviewer_id": "rev.401",
                    "evidence_span_ids": target["evidence_span_ids"],
                }
            ]
        }
    )

    apply_review_request_bundle(
        provisional_dir=provisional_dir,
        request=first_request,
        out_dir=first_review_dir,
    )

    second_request = ReviewRequestBundle.model_validate(
        {
            "overrides": [
                {
                    "target_object_type": "measurement_property_result",
                    "target_object_id": target["id"],
                    "field_name": "reviewer_decision_status",
                    "overridden_value": "confirmed",
                    "reason": "Second reviewer confirmed adjudicated state.",
                    "reviewer_id": "rev.402",
                    "evidence_span_ids": target["evidence_span_ids"],
                }
            ]
        }
    )

    apply_review_request_bundle(
        provisional_dir=first_review_dir,
        request=second_request,
        out_dir=second_review_dir,
    )

    history = _load_json(second_review_dir / "review_overrides.json")
    assert isinstance(history, list)
    assert len(history) == 2
    assert history[0]["reviewer_id"] == "rev.401"
    assert history[1]["reviewer_id"] == "rev.402"
    assert history[0]["target_object_id"] == target["id"]
    assert history[1]["target_object_id"] == target["id"]
