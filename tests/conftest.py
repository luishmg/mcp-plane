"""Shared pytest fixtures for the Plane MCP server test suite."""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Required settings must be present before importing app modules.
# Fall back to safe test values when the environment variable is missing or empty.
os.environ["PLANE_MCP_TOKEN"] = os.environ.get("PLANE_MCP_TOKEN") or "test-plane-token"
os.environ.setdefault("MCP_AUTH_TOKEN", "test-auth-token")
os.environ.setdefault("PLANE_API_BASE", "http://localhost:8000")
os.environ.setdefault("ALLOWED_ORIGINS", "http://allowed.local")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "60")

from app.server import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    """Yield a configured FastAPI TestClient with lifespan events executed."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Headers required when MCP_AUTH_TOKEN is enabled."""
    return {"Authorization": "Bearer test-auth-token"}


@pytest.fixture
def authorized_client(client: TestClient, auth_headers: dict[str, str]) -> TestClient:
    """TestClient that always sends a valid Bearer token."""
    client.headers.update(auth_headers)
    return client


class _AsyncClientMock:
    """Minimal async context manager that records the request call and returns a
    configurable response."""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def __aenter__(self) -> "_AsyncClientMock":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((method, url, {"headers": headers, "params": params, "json": json}))
        return self.response


@pytest.fixture
def mock_httpx_response(mocker: Any) -> Any:
    """Return a factory for mocking httpx.AsyncClient responses.

    Usage:
        response = make_response(status_code=200, json={"id": "1"})
        mocker.patch("app.plane_client.httpx.AsyncClient", new=_AsyncClientMock(response))
    """

    def _make(
        status_code: int = 200,
        json: Any = None,
        text: str = "",
        content: bytes | None = None,
    ) -> Any:
        resp = mocker.MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json if json is not None else {}
        resp.text = text
        if content is None:
            content = (
                b'"placeholder"'
                if json is None and text == ""
                else (text.encode() if text else b"")
            )
        resp.content = content
        return resp

    return _make


@pytest.fixture
def httpx_client_factory(mocker: Any) -> Any:
    """Patch ``httpx.AsyncClient`` and expose the call log."""

    def _patch(response: Any) -> _AsyncClientMock:
        client_mock = _AsyncClientMock(response)
        mocker.patch("app.plane_client.httpx.AsyncClient", return_value=client_mock)
        return client_mock

    return _patch
