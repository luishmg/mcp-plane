"""Integration tests for the FastAPI MCP and health endpoints."""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import config, models, server


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# MCP protocol methods
# ---------------------------------------------------------------------------


def test_mcp_initialize(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    result = body["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "plane-mcp"


def test_mcp_initialize_rejects_invalid_params(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": 123},  # wrong type
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32602


def test_mcp_tools_list(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "tools" in body["result"]
    assert any(tool["name"] == "create_task" for tool in body["result"]["tools"])


def test_mcp_ping(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 4, "method": "ping"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == {}


def test_mcp_notifications_initialized(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert response.status_code == 204
    assert response.content == b""


def test_mcp_unknown_method(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 5, "method": "foo/bar"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32601
    assert "foo/bar" in body["error"]["message"]


# ---------------------------------------------------------------------------
# tools/call dispatch
# ---------------------------------------------------------------------------


async def _fake_tool_handler(args: dict) -> models.MCPToolResult:
    return models.MCPToolResult(
        content=[models.MCPContent(text=f"handled {args}")],
        isError=False,
    )


@pytest.mark.parametrize("tool_name", [tool["name"] for tool in server.TOOLS])
def test_mcp_tools_call_dispatches_every_tool(
    authorized_client: TestClient, mocker: Any, tool_name: str
) -> None:
    mocker.patch.dict(
        "app.server.TOOL_HANDLERS",
        {tool_name: _fake_tool_handler},
    )
    response = authorized_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "result" in body
    assert body["result"]["isError"] is False


def test_mcp_tools_call_missing_name(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"arguments": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32602


def test_mcp_tools_call_unknown_tool(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "not_a_real_tool", "arguments": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# Input validation errors
# ---------------------------------------------------------------------------


def test_mcp_invalid_json(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == -32700


def test_mcp_body_must_be_object(authorized_client: TestClient) -> None:
    response = authorized_client.post(
        "/mcp",
        json="string-body",
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == -32600


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def test_mcp_rate_limit_blocks_excess_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings, "RATE_LIMIT_PER_MINUTE", 1)
    importlib.reload(server)

    limited_app = server.app
    with TestClient(limited_app) as limited_client:
        headers = {
            "Authorization": f"Bearer {config.settings.MCP_AUTH_TOKEN}",
            "Origin": "http://allowed.local",
        }
        first = limited_client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert first.status_code == 200

        second = limited_client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert second.status_code == 429

    # Reload back to the default limit for the remaining suite.
    monkeypatch.undo()
    importlib.reload(server)
