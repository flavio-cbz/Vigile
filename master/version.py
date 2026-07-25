from __future__ import annotations

"""
Vigile — Version

Single source of truth for the application version.
Reads the VERSION file at the repository root.
"""

from pathlib import Path


def _read_version() -> str:
    """Read the VERSION file from the repository root."""
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


__version__ = _read_version()
