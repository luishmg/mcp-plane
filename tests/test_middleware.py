"""Integration tests for security middleware (origin + Bearer auth)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config


# ---------------------------------------------------------------------------
# Origin validation
# ---------------------------------------------------------------------------


def test_allowed_origin_permitted(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/mcp",
        headers={**auth_headers, "Origin": "http://allowed.local"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 200


def test_missing_origin_allowed(client: TestClient, auth_headers: dict[str, str]) -> None:
    # The server only rejects non-empty origins that are not in the allowlist.
    response = client.post(
        "/mcp",
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 200


def test_wrong_origin_blocked(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/mcp",
        headers={**auth_headers, "Origin": "http://evil.local"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden origin"


# ---------------------------------------------------------------------------
# Bearer token auth
# ---------------------------------------------------------------------------


def test_valid_bearer_token_succeeds(client: TestClient) -> None:
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-auth-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 200


def test_missing_bearer_token_blocked(client: TestClient) -> None:
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_wrong_bearer_token_blocked(client: TestClient) -> None:
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer wrong-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 401


def test_auth_not_required_for_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Combined auth + origin
# ---------------------------------------------------------------------------


def test_origin_check_applies_to_health(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://evil.local"})
    assert response.status_code == 403


def test_origin_disabled_when_allowlist_empty(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, auth_headers: dict[str, str]
) -> None:
    monkeypatch.setattr(config.settings, "ALLOWED_ORIGINS", "")
    response = client.post(
        "/mcp",
        headers={**auth_headers, "Origin": "http://any.local"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 200
