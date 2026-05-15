"""
Vigile — Configuration
Loads all settings from environment variables with sensible defaults.
"""

import os
import secrets
from pathlib import Path
from pydantic import BaseModel, field_validator


class Settings(BaseModel):
    """Application settings loaded from environment variables."""

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
    cors_origins: list[str] = []

    # --- Security: Trusted proxies for X-Forwarded-For ---
    trusted_proxies: list[str] = []

    # --- Security: HTTPS enforcement ---
    enforce_https: bool = os.getenv("ENFORCE_HTTPS", "false").lower() == "true"

    # --- Plugins ---
    plugins_dir: str = os.getenv("PLUGINS_DIR", "./master/plugins")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, list):
            return v
        return [o.strip() for o in v.split(",") if o.strip()]

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def _parse_trusted_proxies(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, list):
            return v
        return [o.strip() for o in v.split(",") if o.strip()]

    def model_post_init(self, __context) -> None:
        """Generate secrets if not provided (dev convenience, NOT for production)."""
        if not self.server_secret_key:
            self.server_secret_key = secrets.token_hex(32)
        if not self.jwt_secret_key:
            self.jwt_secret_key = secrets.token_hex(32)


# Singleton
settings = Settings()
