"""
Declarative MCP tool manifest and dispatch handlers for Plane task management.

The manifest (TOOLS) is the single source of truth for `tools/list`; the
TOOL_HANDLERS dispatch map cannot drift from it because both are built from
the same TOOLS list.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Awaitable

from .models import (
    MCPContent,
    MCPToolResult,
    PlaneTask,
    PlaneTaskUpdate,
    PRIORITY_VALUES,
    STATUS_VALUES,
)
from .plane_client import (
    PlaneAPIError,
    create_task as plane_create_task,
    delete_task as plane_delete_task,
    get_task as plane_get_task,
    list_tasks as plane_list_tasks,
    update_task as plane_update_task,
)

logger = logging.getLogger("plane_mcp.tools")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text(msg: str, error: bool = False) -> MCPToolResult:
    return MCPToolResult(
        content=[MCPContent(type="text", text=msg)], isError=error
    )


def _json_result(data: Any, error: bool = False) -> MCPToolResult:
    return _text(json.dumps(data, default=str, indent=2), error=error)


def _workspace_project_args(args: dict) -> tuple[str, str]:
    """Extract workspace_slug + project_id from tool args (required for all calls)."""
    workspace = args.get("workspace_slug")
    project = args.get("project_id")
    if not workspace or not project:
        raise ValueError(
            "Both 'workspace_slug' and 'project_id' are required to scope "
            "Plane work items."
        )
    return workspace, project


# ---------------------------------------------------------------------------
# Tool manifest (single source of truth)
# ---------------------------------------------------------------------------

WORKSPACE_PROJECT_PROPS = {
    "workspace_slug": {
        "type": "string",
        "description": "Slug of the Plane workspace the project belongs to",
    },
    "project_id": {
        "type": "string",
        "description": "UUID of the Plane project",
    },
}

TOOLS: list[dict] = [
    {
        "name": "list_tasks",
        "description": (
            "List work items (tasks) in a Plane project. Returns paginated, "
            "cursor-based results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor returned by a previous call",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Page size (max 100)",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["workspace_slug", "project_id"],
        },
    },
    {
        "name": "get_task",
        "description": "Retrieve a single Plane work item by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "task_id": {
                    "type": "string",
                    "description": "UUID of the work item",
                },
            },
            "required": ["workspace_slug", "project_id", "task_id"],
        },
    },
    {
        "name": "create_task",
        "description": "Create a new work item (task) in a Plane project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "name": {
                    "type": "string",
                    "description": "Task title",
                },
                "description_html": {
                    "type": "string",
                    "description": "Task description (Plane accepts HTML)",
                },
                "priority": {
                    "type": "string",
                    "enum": PRIORITY_VALUES,
                    "description": "Priority of the task",
                    "default": "MEDIUM",
                },
                "state": {
                    "type": "string",
                    "description": "Workflow state name (e.g. 'Backlog')",
                },
                "target_date": {
                    "type": "string",
                    "format": "date-time",
                    "description": "Due date in ISO 8601 format",
                },
            },
            "required": ["workspace_slug", "project_id", "name"],
        },
    },
    {
        "name": "update_task",
        "description": "Partially update an existing Plane work item.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "task_id": {
                    "type": "string",
                    "description": "UUID of the work item to update",
                },
                "name": {"type": "string", "description": "New title"},
                "description_html": {
                    "type": "string",
                    "description": "New description (HTML)",
                },
                "priority": {
                    "type": "string",
                    "enum": PRIORITY_VALUES,
                    "description": "New priority",
                },
                "state": {
                    "type": "string",
                    "description": "New workflow state name",
                },
                "target_date": {
                    "type": "string",
                    "format": "date-time",
                    "description": "New due date in ISO 8601 format",
                },
            },
            "required": ["workspace_slug", "project_id", "task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Delete a Plane work item by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "task_id": {
                    "type": "string",
                    "description": "UUID of the work item to delete",
                },
            },
            "required": ["workspace_slug", "project_id", "task_id"],
        },
    },
]


# ---------------------------------------------------------------------------
# Handlers (one per tool name)
# ---------------------------------------------------------------------------


async def handle_list_tasks(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_list_tasks(
            workspace,
            project,
            cursor=args.get("cursor"),
            per_page=args.get("per_page", 20),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to list tasks: {e}", error=True)
    return _json_result(data)


async def handle_get_task(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    task_id = args.get("task_id")
    if not task_id:
        return _text("'task_id' is required.", error=True)

    try:
        data = await plane_get_task(workspace, project, task_id)
    except PlaneAPIError as e:
        return _text(f"Failed to get task {task_id}: {e}", error=True)
    return _json_result(data)


async def handle_create_task(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        task = PlaneTask(
            name=args["name"],
            description_html=args.get("description_html"),
            priority=args.get("priority", "MEDIUM"),
            state=args.get("state"),
            target_date=args.get("target_date"),
        )
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid task payload: {e}", error=True)

    try:
        data = await plane_create_task(workspace, project, task.model_dump(exclude_none=True))
    except PlaneAPIError as e:
        return _text(f"Failed to create task: {e}", error=True)
    return _json_result(data)


async def handle_update_task(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    task_id = args.get("task_id")
    if not task_id:
        return _text("'task_id' is required.", error=True)

    update_fields = {
        k: v
        for k, v in args.items()
        if k in {"name", "description_html", "priority", "state", "target_date"}
        and v is not None
    }
    if not update_fields:
        return _text("No updatable fields provided.", error=True)

    try:
        validated = PlaneTaskUpdate(**update_fields)
    except (ValueError, TypeError) as e:
        return _text(f"Invalid update payload: {e}", error=True)

    try:
        data = await plane_update_task(
            workspace, project, task_id, validated.model_dump(exclude_none=True)
        )
    except PlaneAPIError as e:
        return _text(f"Failed to update task {task_id}: {e}", error=True)
    return _json_result(data)


async def handle_delete_task(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    task_id = args.get("task_id")
    if not task_id:
        return _text("'task_id' is required.", error=True)

    try:
        await plane_delete_task(workspace, project, task_id)
    except PlaneAPIError as e:
        return _text(f"Failed to delete task {task_id}: {e}", error=True)
    return _text(f"Task {task_id} deleted.")


ToolHandler = Callable[[dict], Awaitable[MCPToolResult]]

# Dispatch map — built from TOOLS so names can never drift from the manifest.
TOOL_HANDLERS: dict[str, ToolHandler] = {
    "list_tasks": handle_list_tasks,
    "get_task": handle_get_task,
    "create_task": handle_create_task,
    "update_task": handle_update_task,
    "delete_task": handle_delete_task,
}

# Sanity check: every manifest entry must have a handler and vice versa.
_manifest_names = {t["name"] for t in TOOLS}
_handler_names = set(TOOL_HANDLERS)
assert _manifest_names == _handler_names, (
    f"Tool manifest/handler mismatch: "
    f"manifest={_manifest_names} handlers={_handler_names}"
)
