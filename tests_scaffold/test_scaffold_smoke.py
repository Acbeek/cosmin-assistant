"""Scaffold smoke tests."""

import cosmin_assistant


def test_package_version_is_defined() -> None:
    assert isinstance(cosmin_assistant.__version__, str)
