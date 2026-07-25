from __future__ import annotations

import os
import tempfile

import pytest

from master.core.secret_loader import load_secret


class TestSecretLoader:
    """4 cases: env set, file set, both set, neither."""

    def test_env_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Priority 1: returns the env var value."""
        monkeypatch.setenv("MY_SECRET", "direct-value")
        monkeypatch.delenv("MY_SECRET_FILE", raising=False)
        assert load_secret("MY_SECRET") == "direct-value"

    def test_file_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Priority 2: reads secret from file when env var is not set."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("file-value\n")
            f.flush()
            file_path = f.name
        try:
            monkeypatch.delenv("MY_SECRET", raising=False)
            monkeypatch.setenv("MY_SECRET_FILE", file_path)
            assert load_secret("MY_SECRET") == "file-value"
        finally:
            os.unlink(file_path)

    def test_both_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Priority 1 wins when both env var and file are configured."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("file-value\n")
            f.flush()
            file_path = f.name
        try:
            monkeypatch.setenv("MY_SECRET", "direct-value")
            monkeypatch.setenv("MY_SECRET_FILE", file_path)
            assert load_secret("MY_SECRET") == "direct-value"
        finally:
            os.unlink(file_path)

    def test_neither_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns empty string when neither env var nor file is configured."""
        monkeypatch.delenv("MY_SECRET", raising=False)
        monkeypatch.delenv("MY_SECRET_FILE", raising=False)
        assert load_secret("MY_SECRET") == ""

    def test_custom_file_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom file_var parameter overrides the default _FILE suffix."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("custom-path-value\n")
            f.flush()
            file_path = f.name
        try:
            monkeypatch.delenv("MY_SECRET", raising=False)
            monkeypatch.setenv("CUSTOM_PATH", file_path)
            assert load_secret("MY_SECRET", file_var="CUSTOM_PATH") == "custom-path-value"
        finally:
            os.unlink(file_path)
