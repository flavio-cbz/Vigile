"""
Vigile — Configuration
Loads all settings from environment variables with sensible defaults.
"""

import os
import secrets
from pathlib import Path
from pydantic import BaseModel, field_validator, ConfigDict


class Settings(BaseModel):
    """Application settings loaded from environment variables."""

    model_config = ConfigDict(frozen=False)

    # --- Server ---
    master_url: str = os.getenv("MASTER_URL", "http://localhost:8000")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # --- Database ---
    database_path: str = os.getenv("DATABASE_PATH", "./data/vigile.db")

    # --- Security: Server Secret (HMAC signing for JOIN_TOKENs) ---
    server_secret_key: str = os.getenv("SERVER_SECRET_KEY", "")

    # --- Security: JWT ---
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl: int = int(os.getenv("JWT_ACCESS_TOKEN_TTL", "3600"))
    jwt_refresh_token_ttl: int = int(os.getenv("JWT_REFRESH_TOKEN_TTL", "86400"))

    # --- Enrollment ---
    join_token_ttl: int = int(os.getenv("JOIN_TOKEN_TTL", "1800"))
    worker_token_ttl: int = int(os.getenv("WORKER_TOKEN_TTL", "2592000"))
    worker_token_rotation: int = int(os.getenv("WORKER_TOKEN_ROTATION", "604800"))

    # --- Node Monitoring ---
    heartbeat_interval: int = int(os.getenv("HEARTBEAT_INTERVAL", "30"))
    heartbeat_lost_threshold: int = int(os.getenv("HEARTBEAT_LOST_THRESHOLD", "300"))
    heartbeat_stale_threshold: int = int(os.getenv("HEARTBEAT_STALE_THRESHOLD", "86400"))

    # --- Master Ed25519 Keypair ---
    master_key_path: str = os.getenv("MASTER_KEY_PATH", "./data/master_ed25519.key")

    # --- CORS ---
    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

    # --- Security: Trusted proxies for X-Forwarded-For ---
    trusted_proxies: list[str] = os.getenv("TRUSTED_PROXIES", "").split(",") if os.getenv("TRUSTED_PROXIES") else []

    # --- Security: HTTPS enforcement ---
    enforce_https: bool = os.getenv("ENFORCE_HTTPS", "false").lower() == "true"

    # --- LLM Provider ---
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # --- Plugins ---
    plugins_dir: str = os.getenv("PLUGINS_DIR", "./master/plugins")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, list):
            return v
        return [o.strip() for o in v.split(",") if o.strip()]

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_with_credentials(cls, v: list[str]) -> list[str]:
        if "*" in v:
            import logging
            _log = logging.getLogger(__name__)
            _log.warning(
                "CORS_ORIGINS contains '*' — this is incompatible with "
                "allow_credentials=True (hardcoded in main.py). "
                "Browsers will reject credentialed requests. "
                "Set specific origins instead."
            )
        return v

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _parse_trusted_proxies(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, list):
            return v
        return [o.strip() for o in v.split(",") if o.strip()]

    def model_post_init(self, __context) -> None:
        """Generate secrets if not provided (dev convenience, NOT for production)."""
        import logging
        _log = logging.getLogger(__name__)
        if not self.server_secret_key:
            self.server_secret_key = secrets.token_hex(32)
            _log.warning("SERVER_SECRET_KEY auto-generated (dev mode). Set it in production.")
        if not self.jwt_secret_key:
            self.jwt_secret_key = secrets.token_hex(32)
            _log.warning("JWT_SECRET_KEY auto-generated (dev mode). Set it in production.")

    def apply_overrides(self, base_url: str, api_key: str, model: str) -> None:
        """Mutate LLM configuration in memory (Zero filesystem I/O per DI rule)."""
        self.llm_base_url = base_url
        if api_key != "••••••••":
            self.llm_api_key = api_key
        self.llm_model = model


# Singleton
settings = Settings()
