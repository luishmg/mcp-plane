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
    handle_add_cycle_issues,
    handle_add_module_issues,
    handle_create_cycle,
    handle_create_module,
    handle_create_task,
    handle_get_workspace,
    handle_update_cycle,
    handle_update_module,
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
async def test_handle_create_task_threads_parent(mocker: Any) -> None:
    mocker.patch("app.tools._resolve_state_id", return_value=None)
    mock_create = mocker.patch(
        "app.tools.plane_create_task",
        return_value={"id": "task-2", "name": "Sub"},
    )
    result = await handle_create_task(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "name": "Sub",
            "parent": "parent-uuid",
        }
    )
    assert result.isError is False
    payload = mock_create.call_args[0][2]
    assert payload["parent"] == "parent-uuid"


@pytest.mark.asyncio
async def test_handle_update_task_threads_parent(mocker: Any) -> None:
    mock_update = mocker.patch(
        "app.tools.plane_update_task",
        return_value={"id": "t1"},
    )
    result = await handle_update_task(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "task_id": "t1",
            "parent": "parent-uuid",
        }
    )
    assert result.isError is False
    payload = mock_update.call_args[0][3]
    assert payload["parent"] == "parent-uuid"


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


# ---------------------------------------------------------------------------
# Cycle handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_create_cycle_sends_validated_payload(mocker: Any) -> None:
    mock_create = mocker.patch(
        "app.tools.plane_create_cycle",
        return_value={"id": "cycle-1", "name": "Sprint 1"},
    )

    result = await handle_create_cycle(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "name": "Sprint 1",
            "start_date": "2026-01-01",
            "end_date": "2026-01-14",
            "status": "active",
        }
    )

    assert result.isError is False
    assert "cycle-1" in result.content[0].text
    ws, project, payload = mock_create.call_args[0]
    assert (ws, project) == ("acme", "p1")
    assert payload["name"] == "Sprint 1"
    # Dates are serialized to ISO strings (mode="json"), not date objects.
    assert payload["start_date"] == "2026-01-01"
    assert payload["end_date"] == "2026-01-14"
    assert payload["status"] == "active"
    # project_id must be included in the POST body (Plane requires it).
    assert payload["project_id"] == "p1"


@pytest.mark.asyncio
async def test_handle_create_cycle_rejects_empty_name(mocker: Any) -> None:
    mock_create = mocker.patch("app.tools.plane_create_cycle")
    result = await handle_create_cycle(
        {"workspace_slug": "acme", "project_id": "p1", "name": ""}
    )
    assert result.isError is True
    assert "Invalid cycle payload" in result.content[0].text
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_handle_create_cycle_requires_workspace_and_project(mocker: Any) -> None:
    result = await handle_create_cycle({"workspace_slug": "acme", "name": "Sprint"})
    assert result.isError is True
    assert "project_id" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_create_cycle_surfaces_plane_error(mocker: Any) -> None:
    mocker.patch(
        "app.tools.plane_create_cycle",
        side_effect=PlaneAPIError("boom"),
    )
    result = await handle_create_cycle(
        {"workspace_slug": "acme", "project_id": "p1", "name": "Sprint"}
    )
    assert result.isError is True
    assert "Failed to create cycle" in result.content[0].text
    assert "boom" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_update_cycle_sends_only_provided_fields(mocker: Any) -> None:
    mock_update = mocker.patch(
        "app.tools.plane_update_cycle",
        return_value={"id": "cycle-1"},
    )
    result = await handle_update_cycle(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "cycle_id": "cycle-1",
            "status": "completed",
        }
    )
    assert result.isError is False
    ws, project, cycle_id, payload = mock_update.call_args[0]
    assert (ws, project, cycle_id) == ("acme", "p1", "cycle-1")
    assert payload == {"status": "completed"}


@pytest.mark.asyncio
async def test_handle_update_cycle_requires_cycle_id(mocker: Any) -> None:
    result = await handle_update_cycle(
        {"workspace_slug": "acme", "project_id": "p1", "name": "X"}
    )
    assert result.isError is True
    assert "cycle_id" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_update_cycle_no_updatable_fields(mocker: Any) -> None:
    result = await handle_update_cycle(
        {"workspace_slug": "acme", "project_id": "p1", "cycle_id": "cycle-1"}
    )
    assert result.isError is True
    assert "No updatable fields" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_add_cycle_issues_body_shape(mocker: Any) -> None:
    mock_add = mocker.patch(
        "app.tools.plane_add_cycle_issues",
        return_value={"added": 2},
    )
    result = await handle_add_cycle_issues(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "cycle_id": "cycle-1",
            "issues": ["i1", "i2"],
        }
    )
    assert result.isError is False
    ws, project, cycle_id, body = mock_add.call_args[0]
    assert (ws, project, cycle_id) == ("acme", "p1", "cycle-1")
    assert body == {"issues": ["i1", "i2"]}


@pytest.mark.asyncio
async def test_handle_add_cycle_issues_rejects_empty_list(mocker: Any) -> None:
    mock_add = mocker.patch("app.tools.plane_add_cycle_issues")
    result = await handle_add_cycle_issues(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "cycle_id": "cycle-1",
            "issues": [],
        }
    )
    assert result.isError is True
    assert "non-empty list" in result.content[0].text
    mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_handle_add_cycle_issues_rejects_non_list(mocker: Any) -> None:
    mock_add = mocker.patch("app.tools.plane_add_cycle_issues")
    result = await handle_add_cycle_issues(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "cycle_id": "cycle-1",
            "issues": "i1",
        }
    )
    assert result.isError is True
    assert "non-empty list" in result.content[0].text
    mock_add.assert_not_called()


# ---------------------------------------------------------------------------
# Module handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_create_module_sends_validated_payload(mocker: Any) -> None:
    mock_create = mocker.patch(
        "app.tools.plane_create_module",
        return_value={"id": "mod-1", "name": "Epic 1"},
    )
    result = await handle_create_module(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "name": "Epic 1",
            "status": "planned",
            "start_date": "2026-02-01",
            "lead": "user-uuid",
        }
    )
    assert result.isError is False
    assert "mod-1" in result.content[0].text
    ws, project, payload = mock_create.call_args[0]
    assert (ws, project) == ("acme", "p1")
    assert payload["name"] == "Epic 1"
    assert payload["status"] == "planned"
    assert payload["start_date"] == "2026-02-01"
    assert payload["lead"] == "user-uuid"
    # project_id must be included in the POST body (Plane requires it).
    assert payload["project_id"] == "p1"
    # Unset optional fields must not be sent.
    assert "target_date" not in payload
    assert "description" not in payload


@pytest.mark.asyncio
async def test_handle_create_module_rejects_empty_name(mocker: Any) -> None:
    mock_create = mocker.patch("app.tools.plane_create_module")
    result = await handle_create_module(
        {"workspace_slug": "acme", "project_id": "p1", "name": ""}
    )
    assert result.isError is True
    assert "Invalid module payload" in result.content[0].text
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_handle_update_module_sends_only_provided_fields(mocker: Any) -> None:
    mock_update = mocker.patch(
        "app.tools.plane_update_module",
        return_value={"id": "mod-1"},
    )
    result = await handle_update_module(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "module_id": "mod-1",
            "name": "Renamed",
            "status": "in-progress",
        }
    )
    assert result.isError is False
    ws, project, module_id, payload = mock_update.call_args[0]
    assert (ws, project, module_id) == ("acme", "p1", "mod-1")
    assert payload == {"name": "Renamed", "status": "in-progress"}


@pytest.mark.asyncio
async def test_handle_update_module_no_updatable_fields(mocker: Any) -> None:
    result = await handle_update_module(
        {"workspace_slug": "acme", "project_id": "p1", "module_id": "mod-1"}
    )
    assert result.isError is True
    assert "No updatable fields" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_update_module_requires_module_id(mocker: Any) -> None:
    result = await handle_update_module(
        {"workspace_slug": "acme", "project_id": "p1", "status": "completed"}
    )
    assert result.isError is True
    assert "module_id" in result.content[0].text


@pytest.mark.asyncio
async def test_handle_add_module_issues_body_shape(mocker: Any) -> None:
    mock_add = mocker.patch(
        "app.tools.plane_add_module_issues",
        return_value={"added": 3},
    )
    result = await handle_add_module_issues(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "module_id": "mod-1",
            "issues": ["i1", "i2", "i3"],
        }
    )
    assert result.isError is False
    ws, project, module_id, body = mock_add.call_args[0]
    assert (ws, project, module_id) == ("acme", "p1", "mod-1")
    assert body == {"issues": ["i1", "i2", "i3"]}


@pytest.mark.asyncio
async def test_handle_add_module_issues_rejects_empty_list(mocker: Any) -> None:
    mock_add = mocker.patch("app.tools.plane_add_module_issues")
    result = await handle_add_module_issues(
        {
            "workspace_slug": "acme",
            "project_id": "p1",
            "module_id": "mod-1",
            "issues": [],
        }
    )
    assert result.isError is True
    assert "non-empty list" in result.content[0].text
    mock_add.assert_not_called()
