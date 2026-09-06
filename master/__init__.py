from __future__ import annotations

# Vigile AI Admin — Master Node

from pathlib import Path
from typing import Any

if not hasattr(Path, "is_relative_to"):
    def _is_relative_to(self: Path, *other: Any) -> bool:
        try:
            self.relative_to(*other)
            return True
        except ValueError:
            return False

    Path.is_relative_to = _is_relative_to  # type: ignore[attr-defined]
