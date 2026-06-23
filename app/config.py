"""
Centralized configuration for the Plane MCP server.
All settings are loaded from environment variables (fail-fast on missing secrets).
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Required secrets have no default so the server
    fails fast at startup if unset."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Required secrets ---
    PLANE_MCP_TOKEN: str

    # --- Plane API ---
    PLANE_API_BASE: str = "http://umbrel:8762"

    # --- Server ---
    HOST: str = "127.0.0.1"
    PORT: int = 8763
    ALLOWED_ORIGINS: str = ""  # comma-separated, empty = allow all validated origins

    # --- Request limits ---
    REQUEST_TIMEOUT_SECONDS: float = 15.0
    RATE_LIMIT_PER_MINUTE: int = 60

    @property
    def allowed_origin_set(self) -> set[str]:
        if not self.ALLOWED_ORIGINS:
            return set()
        return {o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Convenience module-level singletons for code that doesn't need FastAPI's DI.
settings = get_settings()
PLANE_API_BASE = settings.PLANE_API_BASE
PLANE_MCP_TOKEN = settings.PLANE_MCP_TOKEN
