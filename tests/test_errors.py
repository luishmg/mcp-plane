"""Integration tests for error handling paths."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import models
from app.plane_client import PlaneAPIError


async def _failing_tool_handler(args: dict) -> models.MCPToolResult:
    raise PlaneAPIError("Plane returned 500")


async def _unexpected_tool_handler(args: dict) -> models.MCPToolResult:
    raise RuntimeError("boom")


def test_mcp_tools_call_returns_plane_api_error(
    authorized_client: TestClient, mocker: Any
) -> None:
    mocker.patch.dict(
        "app.server.TOOL_HANDLERS",
        {"create_task": _failing_tool_handler},
    )
    response = authorized_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_task", "arguments": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["isError"] is True
    assert "Plane returned 500" in body["result"]["content"][0]["text"]


def test_mcp_tools_call_returns_internal_error_for_unhandled_exception(
    authorized_client: TestClient, mocker: Any
) -> None:
    mocker.patch.dict(
        "app.server.TOOL_HANDLERS",
        {"create_task": _unexpected_tool_handler},
    )
    response = authorized_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "create_task", "arguments": {}},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["isError"] is True
    assert "Internal error" in body["result"]["content"][0]["text"]


def test_mcp_tools_call_missing_arguments_still_dispatches(
    authorized_client: TestClient, mocker: Any
) -> None:
    async def handler(args: dict) -> models.MCPToolResult:
        return models.MCPToolResult(
            content=[models.MCPContent(text="ok")], isError=False
        )

    mocker.patch.dict("app.server.TOOL_HANDLERS", {"list_workspaces": handler})
    response = authorized_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_workspaces"},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["content"][0]["text"] == "ok"
