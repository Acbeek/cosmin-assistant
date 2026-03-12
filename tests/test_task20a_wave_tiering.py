"""Task 20a wave-tier governance checks (metadata-only, no logic assertions)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_CORPUS_ROOT = Path(__file__).resolve().parent / "fixtures" / "corpus"
_MANIFEST_PATH = _CORPUS_ROOT / "manifest.yaml"


def _load_manifest_index() -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    papers = payload.get("papers")
    assert isinstance(papers, list)
    index: dict[str, dict[str, Any]] = {}
    for entry in papers:
        assert isinstance(entry, dict)
        paper_id = str(entry["paper_id"])
        index[paper_id] = entry
    return index


def _load_expected_payload(entry: dict[str, Any]) -> dict[str, Any]:
    rel = Path(str(entry["expected_metadata_path"]))
    path = (_CORPUS_ROOT / rel).resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_task20a_wave_tier_reclassification_is_locked() -> None:
    manifest = _load_manifest_index()

    protected_papers = (
        "azadinia_2025",
        "potter_2025",
        "awad_2025",
        "nonsci_franchignoni2023",
        "sci_gailey2002",
        "sci_carse2021",
        "sci_hafner2017",
        "sci_cox2017",
        "sci_cotemartin2020",
    )
    for paper_id in protected_papers:
        assert manifest[paper_id]["protected_or_exploratory"] == "protected"
        assert manifest[paper_id]["manual_validation_status"] == "reviewed_for_light_assertions"

    assert manifest["nonsci_hafner2022"]["protected_or_exploratory"] == "exploratory"
    assert manifest["nonsci_hafner2022"]["manual_validation_status"] == "pending_review"


def test_task20a_protected_scientific_assertions_for_sci_hafner2017() -> None:
    manifest = _load_manifest_index()
    payload = _load_expected_payload(manifest["sci_hafner2017"])

    assert payload["paper_id"] == "sci_hafner2017"
    assert payload["protected_or_exploratory"] == "protected"
    assert payload["manual_validation_status"] == "reviewed_for_light_assertions"

    # Protected scientific assertions (lightweight): target + intent + key activation.
    assert payload["expected_target_instruments"] == ["PLUS-M"]
    assert payload["expected_study_intent"] == "construct_validity_study"
    assert "hypotheses_testing_for_construct_validity" in payload["expected_key_properties"]

    # One key suppressed property.
    suppressed = payload["expected_key_suppressed_or_inapplicable_properties"]
    assert isinstance(suppressed, list)
    assert "reliability" in suppressed

    # One must-not-happen assertion.
    must_not_happen = payload["must_not_happen"]
    assert isinstance(must_not_happen, list)
    assert "AMP_or_TUG_or_PEQ_MS_or_ABC_or_PROMIS_PF_selected_as_target" in must_not_happen


def test_task20a_exploratory_fixtures_have_lightweight_identity_checks_only() -> None:
    manifest = _load_manifest_index()
    exploratory_papers = ("nonsci_hafner2022",)

    for paper_id in exploratory_papers:
        payload = _load_expected_payload(manifest[paper_id])

        assert payload["paper_id"] == paper_id
        assert payload["protected_or_exploratory"] == "exploratory"
        assert payload["manual_validation_status"] == "pending_review"

        # Identity/integrity checks only (no strict scientific expectations asserted here).
        assert isinstance(payload.get("expected_target_instruments"), list)
        assert payload.get("expected_target_instruments")
        must_not_happen = payload.get("must_not_happen")
        assert isinstance(must_not_happen, list)
        assert must_not_happen
