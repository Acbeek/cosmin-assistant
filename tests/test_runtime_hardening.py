"""Runtime and manifest hardening tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cosmin_assistant.utils import ensure_supported_python


def test_python_version_guard_rejects_older_versions() -> None:
    with pytest.raises(RuntimeError, match="requires Python >= 3.11"):
        ensure_supported_python((3, 10, 19))


def test_python_version_guard_allows_supported_versions() -> None:
    ensure_supported_python((3, 11, 0))
    ensure_supported_python((3, 13, 3))


def test_manifest_schema_has_required_run_fields(tmp_path: Path) -> None:
    payload = {
        "python_version": "3.13.3",
        "package_version": "0.1.0",
        "git_commit_if_available": "abc123",
        "profile": "prom",
        "source_article_path": "/tmp/article.md",
        "source_article_hash": "hash",
        "generated_at_utc": "2026-03-10T00:00:00+00:00",
    }
    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(payload) <= set(loaded)
