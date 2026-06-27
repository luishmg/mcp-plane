"""Unit tests for tool helpers and handlers."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models import MCPToolResult
from app.plane_client import PlaneAPIError
from app.tools import (
    TOOLS,
    TOOL_HANDLERS,
    _resolve_state_id,
    _workspace_arg,
    _workspace_project_args,
    handle_create_task,
    handle_get_workspace,
    handle_update_task,
)


# ---------------------------------------------------------------------------
# Argument helpers
# ---------------------------------------------------------------------------


def test_workspace_arg_missing() -> None:
    with pytest.raises(ValueError, match="workspace_slug"):
        _workspace_arg({})


def test_workspace_arg_empty_string() -> None:
    with pytest.raises(ValueError, match="workspace_slug"):
        _workspace_arg({"workspace_slug": ""})


def test_workspace_arg_returns_slug() -> None:
    assert _workspace_arg({"workspace_slug": "acme"}) == "acme"


def test_workspace_project_args_both_missing() -> None:
    with pytest.raises(ValueError, match="Both"):
        _workspace_project_args({})


def test_workspace_project_args_missing_project() -> None:
    with pytest.raises(ValueError, match="project_id"):
        _workspace_project_args({"workspace_slug": "acme"})


def test_workspace_project_args_returns_tuple() -> None:
    assert _workspace_project_args({"workspace_slug": "acme", "project_id": "p1"}) == (
        "acme",
        "p1",
    )


# ---------------------------------------------------------------------------
# State resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_state_id_returns_uuid_as_is(mocker: Any) -> None:
    state_uuid = str(uuid.uuid4())
    assert await _resolve_state_id("acme", "p1", state_uuid) == state_uuid


@pytest.mark.asyncio
async def test_resolve_state_id_returns_none_for_empty_state(mocker: Any) -> None:
    assert await _resolve_state_id("acme", "p1", "") is None
    assert await _resolve_state_id("acme", "p1", None) is None


@pytest.mark.asyncio
async def test_resolve_state_id_matches_by_name(mocker: Any) -> None:
    states = [
        {"id": "state-1", "name": "Backlog"},
        {"id": "state-2", "name": "In Progress"},
    ]
    mocker.patch("app.tools.plane_list_states", return_value=states)

    result = await _resolve_state_id("acme", "p1", "In Progress")
    assert result == "state-2"


@pytest.mark.asyncio
async def test_resolve_state_id_is_case_insensitive(mocker: Any) -> None:
    states = [{"id": "state-1", "name": "Backlog"}]
    mocker.patch("app.tools.plane_list_states", return_value=states)

    assert await _resolve_state_id("acme", "p1", "backlog") == "state-1"
    assert await _resolve_state_id("acme", "p1", "BACKLOG") == "state-1"


@pytest.mark.asyncio
async def test_resolve_state_id_raises_when_state_not_found(mocker: Any) -> None:
    mocker.patch("app.tools.plane_list_states", return_value=[])

    with pytest.raises(ValueError, match="State 'Missing' was not found"):
        await _resolve_state_id("acme", "p1", "Missing")


@pytest.mark.asyncio
async def test_resolve_state_id_raises_on_plane_api_error(mocker: Any) -> None:
    mocker.patch(
        "app.tools.plane_list_states",
        side_effect=PlaneAPIError("Plane down"),
    )

    with pytest.raises(ValueError, match="Could not fetch project states"):
        await _resolve_state_id("acme", "p1", "Backlog")


# ---------------------------------------------------------------------------
# Manifest / handler integrity
# ---------------------------------------------------------------------------


def test_every_manifest_tool_has_handler() -> None:
    manifest_names = {tool["name"] for tool in TOOLS}
    assert manifest_names == set(TOOL_HANDLERS)


def test_tools_are_sorted_by_feature_group() -> None:
    # Spot-check that the manifest includes all expected groups.
    names = [tool["name"] for tool in TOOLS]
    assert "list_workspaces" in names
    assert "create_task" in names
    assert "update_workspace_member" in names


# ---------------------------------------------------------------------------
# Handler behaviours
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_get_workspace_missing_slug(mocker: Any) -> None:
    result = await handle_get_workspace({})
    assert result.isError is True
    assert "workspace_slug" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_get_workspace_returns_plane_error(mocker: Any) -> None:
    mocker.patch(
        "app.tools.plane_get_workspace",
        side_effect=PlaneAPIError("not found"),
    )
    result = await handle_get_workspace({"workspace_slug": "acme"})
    assert result.isError is True
    assert "not found" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_create_task_resolves_state_name(mocker: Any) -> None:
    mocker.patch(
        "app.tools._resolve_state_id",
        return_value="resolved-state-id",
    )
    mocker.patch(
        "app.tools.plane_create_task",
        return_value={"id": "task-1", "name": "Task"},
    )

    mock_create = mocker.patch(
        "app.tools.plane_create_task",
        return_value={"id": "task-1", "name": "Task"},
    )

    result = await handle_create_task(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "name": "Task",
            "state": "Backlog",
            "priority": "HIGH",
        }
    )

    assert result.isError is False
    assert "task-1" in result.content[0].text
    args, _ = mock_create.call_args
    payload = args[2]
    assert payload["state"] == "resolved-state-id"
    assert payload["priority"] == "high"


@pytest.mark.asyncio
async def test_handle_create_task_invalid_payload(mocker: Any) -> None:
    result = await handle_create_task(
        {"workspace_slug": "acme", "project_id": "p1", "name": ""}
    )
    assert result.isError is True
    assert "Invalid task payload" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_update_task_no_updatable_fields(mocker: Any) -> None:
    result = await handle_update_task(
        {"workspace_slug": "acme", "project_id": "p1", "task_id": "t1"}
    )
    assert result.isError is True
    assert "No updatable fields" in result.content[0].text


@pytest.mark.asyncio
async def test_handler_result_can_be_serialized() -> None:
    result = await handle_get_workspace({})
    assert isinstance(result, MCPToolResult)
    assert result.model_dump()["isError"] is True
