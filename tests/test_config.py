"""Unit tests for configuration loading."""

from __future__ import annotations

import os

import pytest

from app import config


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure each config test starts from a known default state."""
    monkeypatch.setenv("PLANE_MCP_TOKEN", "test-token")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("PLANE_API_BASE", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)


def test_settings_require_plane_mcp_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLANE_MCP_TOKEN", raising=False)
    with pytest.raises(Exception):  # pydantic ValidationError
        config.Settings()


def test_settings_parse_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLANE_MCP_TOKEN", "plane-token")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "auth-token")
    monkeypatch.setenv("PLANE_API_BASE", "https://plane.example.com")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app1.local, https://app2.local")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "120")

    settings = config.Settings()
    assert settings.PLANE_MCP_TOKEN == "plane-token"
    assert settings.MCP_AUTH_TOKEN == "auth-token"
    assert settings.PLANE_API_BASE == "https://plane.example.com"
    assert settings.allowed_origin_set == {"https://app1.local", "https://app2.local"}
    assert settings.RATE_LIMIT_PER_MINUTE == 120


def test_allowed_origin_set_is_empty_when_not_configured() -> None:
    settings = config.Settings()
    assert settings.allowed_origin_set == set()


def test_default_settings_values() -> None:
    settings = config.Settings()
    assert settings.PLANE_API_BASE == "http://umbrel:8762"
    assert settings.HOST == "127.0.0.1"
    assert settings.PORT == 8763
    assert settings.REQUEST_TIMEOUT_SECONDS == 15.0
    assert settings.RATE_LIMIT_PER_MINUTE == 60


def test_module_singletons_match_settings() -> None:
    """The module-level re-exports used by the client match the settings object."""
    assert config.PLANE_API_BASE == config.settings.PLANE_API_BASE
    assert config.PLANE_MCP_TOKEN == config.settings.PLANE_MCP_TOKEN
