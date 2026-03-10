"""Runtime/environment helpers for deterministic CLI execution."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

MIN_SUPPORTED_PYTHON: tuple[int, int] = (3, 11)


def ensure_supported_python(
    version_info: tuple[int, int, int] | None = None,
) -> None:
    """Raise RuntimeError when runtime Python is below project minimum."""

    major, minor, micro = version_info or (
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    )
    if (major, minor) < MIN_SUPPORTED_PYTHON:
        required = ".".join(str(part) for part in MIN_SUPPORTED_PYTHON)
        current = f"{major}.{minor}.{micro}"
        msg = (
            "COSMIN Assistant requires Python >= "
            f"{required}. Current runtime is {current}. "
            "Create a Python 3.11+ environment and reinstall the package."
        )
        raise RuntimeError(msg)


def sha256_file(path: str | Path) -> str:
    """Return deterministic SHA-256 hash of a source file."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit_if_available(cwd: str | Path | None = None) -> str | None:
    """Return current git commit hash when available, otherwise None."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd) if cwd is not None else None,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    value = completed.stdout.strip()
    return value or None


def python_version_string() -> str:
    """Return normalized current runtime Python version."""

    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def repo_root_from_file(path: str | Path) -> Path:
    """Resolve best-effort repository root from a file path."""

    current = Path(path).resolve()
    if current.is_file():
        current = current.parent

    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return Path(os.getcwd()).resolve()
