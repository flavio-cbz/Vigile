"""
Vigile — Secret Loader

Utility for loading secrets from environment variables or Docker secrets files.
Supports the Docker secrets pattern where sensitive values are mounted as files.

Priority:
  1. Direct environment variable (e.g., ``LLM_API_KEY``)
  2. File path from ``{ENV_VAR}_FILE`` env var (Docker secrets pattern)

Usage::

    api_key = load_secret("LLM_API_KEY")
    # Returns env var LLM_API_KEY, or reads file from LLM_API_KEY_FILE path
"""

import os
from pathlib import Path


def load_secret(
    env_var: str,
    file_var: str | None = None,
) -> str:
    """
    Load a secret from an environment variable or from a Docker secrets file.

    Parameters
    ----------
    env_var : str
        Primary environment variable name (e.g. ``"LLM_API_KEY"``).
    file_var : str | None
        Environment variable holding the file path. If ``None``,
        defaults to ``f"{env_var}_FILE"`` (Docker secrets convention).

    Returns
    -------
    str
        The secret value, or empty string if neither source is configured.

    Raises
    ------
    RuntimeError
        If a file path is configured but cannot be read.
    """
    if file_var is None:
        file_var = f"{env_var}_FILE"

    value = os.environ.get(env_var)
    if value:
        return value

    file_path_str = os.environ.get(file_var)
    if file_path_str:
        try:
            return Path(file_path_str).read_text().strip()
        except (OSError, IOError) as exc:
            raise RuntimeError(
                f"Cannot read secret file '{file_path_str}' (from {file_var}): {exc}"
            ) from exc

    return ""
