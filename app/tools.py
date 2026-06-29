"""
Declarative MCP tool manifest and dispatch handlers for Plane management.

The manifest (TOOLS) is the single source of truth for `tools/list`; the
TOOL_HANDLERS dispatch map cannot drift from it because both are built from
the same TOOLS list.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable, Optional

from .models import (
    MCPContent,
    MCPToolResult,
    PlaneCycleCreate,
    PlaneCycleUpdate,
    PlaneModuleCreate,
    PlaneModuleUpdate,
    PlaneProjectCreate,
    PlaneProjectMemberCreate,
    PlaneProjectMemberUpdate,
    PlaneProjectUpdate,
    PlaneTask,
    PlaneTaskUpdate,
    PlaneWorkspaceCreate,
    PlaneWorkspaceInviteCreate,
    PlaneWorkspaceInviteUpdate,
    PlaneWorkspaceMemberUpdate,
    PlaneWorkspaceUpdate,
    CYCLE_STATUS_VALUES,
    MODULE_STATUS_VALUES,
    PRIORITY_VALUES,
    ROLE_VALUES,
)
from .plane_client import (
    PlaneAPIError,
    add_cycle_issues as plane_add_cycle_issues,
    add_module_issues as plane_add_module_issues,
    archive_project as plane_archive_project,
    create_cycle as plane_create_cycle,
    create_module as plane_create_module,
    create_project as plane_create_project,
    create_project_member as plane_create_project_member,
    create_task as plane_create_task,
    create_workspace as plane_create_workspace,
    create_workspace_invite as plane_create_workspace_invite,
    get_cycle as plane_get_cycle,
    get_module as plane_get_module,
    get_project as plane_get_project,
    get_project_member as plane_get_project_member,
    get_task as plane_get_task,
    get_workspace as plane_get_workspace,
    get_workspace_invite as plane_get_workspace_invite,
    list_cycle_issues as plane_list_cycle_issues,
    list_cycles as plane_list_cycles,
    list_module_issues as plane_list_module_issues,
    list_modules as plane_list_modules,
    list_projects as plane_list_projects,
    list_project_members as plane_list_project_members,
    list_states as plane_list_states,
    list_tasks as plane_list_tasks,
    list_workspace_invites as plane_list_workspace_invites,
    list_workspace_members as plane_list_workspace_members,
    list_workspaces as plane_list_workspaces,
    unarchive_project as plane_unarchive_project,
    update_cycle as plane_update_cycle,
    update_module as plane_update_module,
    update_project as plane_update_project,
    update_project_member as plane_update_project_member,
    update_task as plane_update_task,
    update_workspace as plane_update_workspace,
    update_workspace_invite as plane_update_workspace_invite,
    update_workspace_member as plane_update_workspace_member,
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
    """Extract workspace_slug + project_id from tool args (required for task/project calls)."""
    workspace = args.get("workspace_slug")
    project = args.get("project_id")
    if not workspace or not project:
        raise ValueError(
            "Both 'workspace_slug' and 'project_id' are required to scope "
            "Plane projects/work items."
        )
    return workspace, project


def _workspace_arg(args: dict) -> str:
    """Extract workspace_slug from tool args."""
    workspace = args.get("workspace_slug")
    if not workspace:
        raise ValueError("'workspace_slug' is required to scope Plane operations.")
    return workspace


_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


async def _resolve_state_id(
    workspace_slug: str, project_id: str, state: Optional[str]
) -> Optional[str]:
    """Translate a state name to a Plane state UUID.

    Accepts UUIDs as-is. Raises ValueError if the name cannot be matched.
    """
    if not state:
        return None
    if _UUID_RE.match(state):
        return state

    try:
        states = await plane_list_states(workspace_slug, project_id, per_page=100)
    except PlaneAPIError as e:
        raise ValueError(f"Could not fetch project states: {e}") from e

    needle = state.strip().lower()
    for entry in states:
        name = entry.get("name", "")
        if name == state or name.strip().lower() == needle:
            return entry.get("id")

    raise ValueError(f"State '{state}' was not found in project {project_id}.")


# ---------------------------------------------------------------------------
# Reusable JSON Schema fragments
# ---------------------------------------------------------------------------

WORKSPACE_SLUG_PROP = {
    "type": "string",
    "description": "Slug of the Plane workspace",
}

PROJECT_ID_PROP = {
    "type": "string",
    "description": "UUID of the Plane project",
}

PAGINATION_PROPS = {
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
}

ROLE_PROP = {
    "type": "integer",
    "enum": ROLE_VALUES,
    "description": "Role: 5=Guest, 15=Member, 20=Admin",
}


# ---------------------------------------------------------------------------
# Tool manifest (single source of truth)
# ---------------------------------------------------------------------------

WORKSPACE_PROJECT_PROPS = {
    "workspace_slug": WORKSPACE_SLUG_PROP,
    "project_id": PROJECT_ID_PROP,
}

TOOLS: list[dict] = [
    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------
    {
        "name": "list_workspaces",
        "description": "List Plane workspaces accessible to the API token.",
        "inputSchema": {
            "type": "object",
            "properties": PAGINATION_PROPS,
            "additionalProperties": False,
        },
    },
    {
        "name": "get_workspace",
        "description": "Retrieve a Plane workspace by its slug.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
            },
            "required": ["workspace_slug"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_workspace",
        "description": "Create a new Plane workspace. Both name and slug are required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Workspace display name (1-80 characters)",
                },
                "slug": {
                    "type": "string",
                    "description": "URL-safe slug: letters, numbers, hyphens, underscores (1-48 characters)",
                },
                "organization_size": {
                    "type": "string",
                    "description": "Organization size label, e.g. '1-10'",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for the workspace, e.g. 'UTC'",
                },
            },
            "required": ["name", "slug"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_workspace",
        "description": "Partially update a Plane workspace by slug.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
                "name": {
                    "type": "string",
                    "description": "New workspace name (1-80 characters)",
                },
                "slug": {
                    "type": "string",
                    "description": "New workspace slug (1-48 characters)",
                },
                "organization_size": {
                    "type": "string",
                    "description": "Organization size label",
                },
                "timezone": {
                    "type": "string",
                    "description": "Timezone for the workspace",
                },
            },
            "required": ["workspace_slug"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    {
        "name": "list_projects",
        "description": "List projects in a Plane workspace. Returns paginated, cursor-based results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
                **PAGINATION_PROPS,
            },
            "required": ["workspace_slug"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_project",
        "description": "Retrieve a single Plane project by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": WORKSPACE_PROJECT_PROPS,
            "required": ["workspace_slug", "project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_project",
        "description": "Create a new Plane project in a workspace. Both name and identifier are required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
                "name": {
                    "type": "string",
                    "description": "Project name",
                },
                "identifier": {
                    "type": "string",
                    "description": "Short uppercase identifier, e.g. 'PROJ' (Plane upper-cases it server-side)",
                },
                "description": {
                    "type": "string",
                    "description": "Project description text",
                },
                "project_lead": {
                    "type": "string",
                    "description": "User ID of the project lead (must be a workspace member)",
                },
                "default_assignee": {
                    "type": "string",
                    "description": "User ID of the default assignee",
                },
            },
            "required": ["workspace_slug", "name", "identifier"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_project",
        "description": "Partially update an existing Plane project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "name": {"type": "string", "description": "New project name"},
                "identifier": {"type": "string", "description": "New project identifier"},
                "description": {"type": "string", "description": "New description"},
                "project_lead": {"type": "string", "description": "New project lead user ID"},
                "default_assignee": {"type": "string", "description": "New default assignee user ID"},
            },
            "required": ["workspace_slug", "project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "archive_project",
        "description": "Archive a Plane project. Requires sufficient permissions.",
        "inputSchema": {
            "type": "object",
            "properties": WORKSPACE_PROJECT_PROPS,
            "required": ["workspace_slug", "project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unarchive_project",
        "description": "Unarchive a Plane project. Requires sufficient permissions.",
        "inputSchema": {
            "type": "object",
            "properties": WORKSPACE_PROJECT_PROPS,
            "required": ["workspace_slug", "project_id"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------
    # Workspace members & invites
    # ------------------------------------------------------------------
    {
        "name": "list_workspace_members",
        "description": "List members of a Plane workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
            },
            "required": ["workspace_slug"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_workspace_member",
        "description": "Update a workspace member's role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
                "member_id": {
                    "type": "string",
                    "description": "UUID of the workspace membership record",
                },
                "role": ROLE_PROP,
            },
            "required": ["workspace_slug", "member_id", "role"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_workspace_invites",
        "description": "List pending invitations for a Plane workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
            },
            "required": ["workspace_slug"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_workspace_invite",
        "description": "Invite an email address to a Plane workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
                "email": {
                    "type": "string",
                    "format": "email",
                    "description": "Email address to invite",
                },
                "role": ROLE_PROP,
            },
            "required": ["workspace_slug", "email", "role"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_workspace_invite",
        "description": "Retrieve a pending workspace invitation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
                "invite_id": {
                    "type": "string",
                    "description": "UUID of the workspace invitation",
                },
            },
            "required": ["workspace_slug", "invite_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_workspace_invite",
        "description": "Update a pending workspace invitation, e.g. change its role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_slug": WORKSPACE_SLUG_PROP,
                "invite_id": {
                    "type": "string",
                    "description": "UUID of the workspace invitation",
                },
                "role": ROLE_PROP,
            },
            "required": ["workspace_slug", "invite_id", "role"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------
    # Project members
    # ------------------------------------------------------------------
    {
        "name": "list_project_members",
        "description": "List members of a Plane project.",
        "inputSchema": {
            "type": "object",
            "properties": WORKSPACE_PROJECT_PROPS,
            "required": ["workspace_slug", "project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_project_member",
        "description": "Add a workspace member to a Plane project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "member": {
                    "type": "string",
                    "description": "User ID of the workspace member to add",
                },
                "role": ROLE_PROP,
            },
            "required": ["workspace_slug", "project_id", "member", "role"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_project_member",
        "description": "Retrieve a project member record.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "member_id": {
                    "type": "string",
                    "description": "UUID of the project membership record",
                },
            },
            "required": ["workspace_slug", "project_id", "member_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_project_member",
        "description": "Update a project member's role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "member_id": {
                    "type": "string",
                    "description": "UUID of the project membership record",
                },
                "role": ROLE_PROP,
            },
            "required": ["workspace_slug", "project_id", "member_id", "role"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------
    # Tasks (work-items)
    # ------------------------------------------------------------------
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
                **PAGINATION_PROPS,
            },
            "required": ["workspace_slug", "project_id"],
            "additionalProperties": False,
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
            "additionalProperties": False,
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
                    "description": "Workflow state name (e.g. 'Backlog') or state UUID",
                },
                "target_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Due date in YYYY-MM-DD format",
                },
                "parent": {
                    "type": "string",
                    "description": "UUID of the parent work item to nest this task under (sub-issue). Must be a work-item UUID.",
                },
            },
            "required": ["workspace_slug", "project_id", "name"],
            "additionalProperties": False,
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
                    "description": "New workflow state name or state UUID",
                },
                "target_date": {
                    "type": "string",
                    "format": "date",
                    "description": "New due date in YYYY-MM-DD format",
                },
                "parent": {
                    "type": "string",
                    "description": "UUID of the parent work item to nest this task under (sub-issue). Must be a work-item UUID.",
                },
            },
            "required": ["workspace_slug", "project_id", "task_id"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------
    # Cycles (sprints)
    # ------------------------------------------------------------------
    {
        "name": "list_cycles",
        "description": (
            "List cycles (sprints) in a Plane project. Returns paginated, "
            "cursor-based results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                **PAGINATION_PROPS,
            },
            "required": ["workspace_slug", "project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_cycle",
        "description": "Retrieve a single Plane cycle by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "cycle_id": {
                    "type": "string",
                    "description": "UUID of the cycle",
                },
            },
            "required": ["workspace_slug", "project_id", "cycle_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_cycle",
        "description": "Create a new cycle (sprint) in a Plane project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "name": {
                    "type": "string",
                    "description": "Cycle name",
                },
                "description": {
                    "type": "string",
                    "description": "Cycle description text",
                },
                "start_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "format": "date",
                    "description": "End date in YYYY-MM-DD format",
                },
                "status": {
                    "type": "string",
                    "enum": CYCLE_STATUS_VALUES,
                    "description": "Cycle status",
                },
            },
            "required": ["workspace_slug", "project_id", "name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_cycle",
        "description": "Partially update an existing Plane cycle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "cycle_id": {
                    "type": "string",
                    "description": "UUID of the cycle to update",
                },
                "name": {"type": "string", "description": "New cycle name"},
                "description": {"type": "string", "description": "New description"},
                "start_date": {
                    "type": "string",
                    "format": "date",
                    "description": "New start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "format": "date",
                    "description": "New end date in YYYY-MM-DD format",
                },
                "status": {
                    "type": "string",
                    "enum": CYCLE_STATUS_VALUES,
                    "description": "New cycle status",
                },
            },
            "required": ["workspace_slug", "project_id", "cycle_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_cycle_issues",
        "description": (
            "List work items (issues) assigned to a Plane cycle. Returns "
            "paginated, cursor-based results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "cycle_id": {
                    "type": "string",
                    "description": "UUID of the cycle",
                },
                **PAGINATION_PROPS,
            },
            "required": ["workspace_slug", "project_id", "cycle_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_cycle_issues",
        "description": "Add existing work items to a Plane cycle (bulk association).",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "cycle_id": {
                    "type": "string",
                    "description": "UUID of the cycle",
                },
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "List of work-item UUIDs to add to the cycle",
                },
            },
            "required": ["workspace_slug", "project_id", "cycle_id", "issues"],
            "additionalProperties": False,
        },
    },
    # ------------------------------------------------------------------
    # Modules (epics)
    # ------------------------------------------------------------------
    {
        "name": "list_modules",
        "description": (
            "List modules (epics) in a Plane project. Returns paginated, "
            "cursor-based results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                **PAGINATION_PROPS,
            },
            "required": ["workspace_slug", "project_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_module",
        "description": "Retrieve a single Plane module by its ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "module_id": {
                    "type": "string",
                    "description": "UUID of the module",
                },
            },
            "required": ["workspace_slug", "project_id", "module_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_module",
        "description": "Create a new module (epic) in a Plane project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "name": {
                    "type": "string",
                    "description": "Module name",
                },
                "description": {
                    "type": "string",
                    "description": "Module description text",
                },
                "status": {
                    "type": "string",
                    "enum": MODULE_STATUS_VALUES,
                    "description": "Module status",
                },
                "start_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "target_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Module target/due date in YYYY-MM-DD format",
                },
                "lead": {
                    "type": "string",
                    "description": "User UUID of the module lead",
                },
            },
            "required": ["workspace_slug", "project_id", "name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_module",
        "description": "Partially update an existing Plane module.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "module_id": {
                    "type": "string",
                    "description": "UUID of the module to update",
                },
                "name": {"type": "string", "description": "New module name"},
                "description": {"type": "string", "description": "New description"},
                "status": {
                    "type": "string",
                    "enum": MODULE_STATUS_VALUES,
                    "description": "New module status",
                },
                "start_date": {
                    "type": "string",
                    "format": "date",
                    "description": "New start date in YYYY-MM-DD format",
                },
                "target_date": {
                    "type": "string",
                    "format": "date",
                    "description": "Module target/due date in YYYY-MM-DD format",
                },
                "lead": {
                    "type": "string",
                    "description": "New module lead user UUID",
                },
            },
            "required": ["workspace_slug", "project_id", "module_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_module_issues",
        "description": (
            "List work items (issues) associated with a Plane module. Returns "
            "paginated, cursor-based results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "module_id": {
                    "type": "string",
                    "description": "UUID of the module",
                },
                **PAGINATION_PROPS,
            },
            "required": ["workspace_slug", "project_id", "module_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_module_issues",
        "description": "Associate existing work items with a Plane module (bulk association).",
        "inputSchema": {
            "type": "object",
            "properties": {
                **WORKSPACE_PROJECT_PROPS,
                "module_id": {
                    "type": "string",
                    "description": "UUID of the module",
                },
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": "List of work-item UUIDs to add to the module",
                },
            },
            "required": ["workspace_slug", "project_id", "module_id", "issues"],
            "additionalProperties": False,
        },
    },
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


# --- Workspaces -----------------------------------------------------------


async def handle_list_workspaces(args: dict) -> MCPToolResult:
    try:
        data = await plane_list_workspaces(
            cursor=args.get("cursor"),
            per_page=args.get("per_page", 20),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to list workspaces: {e}", error=True)
    return _json_result(data)


async def handle_get_workspace(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)
    try:
        data = await plane_get_workspace(workspace)
    except PlaneAPIError as e:
        return _text(f"Failed to get workspace {workspace}: {e}", error=True)
    return _json_result(data)


async def handle_create_workspace(args: dict) -> MCPToolResult:
    try:
        payload = PlaneWorkspaceCreate(
            name=args["name"],
            slug=args["slug"],
            organization_size=args.get("organization_size"),
            timezone=args.get("timezone"),
        ).model_dump(exclude_none=True)
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid workspace payload: {e}", error=True)

    try:
        data = await plane_create_workspace(payload)
    except PlaneAPIError as e:
        return _text(f"Failed to create workspace: {e}", error=True)
    return _json_result(data)


async def handle_update_workspace(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)

    update_fields = {
        k: v
        for k, v in args.items()
        if k in {"name", "slug", "organization_size", "timezone"} and v is not None
    }
    if not update_fields:
        return _text("No updatable fields provided.", error=True)

    try:
        validated = PlaneWorkspaceUpdate(**update_fields)
    except (ValueError, TypeError) as e:
        return _text(f"Invalid update payload: {e}", error=True)

    try:
        data = await plane_update_workspace(
            workspace, validated.model_dump(exclude_none=True)
        )
    except PlaneAPIError as e:
        return _text(f"Failed to update workspace {workspace}: {e}", error=True)
    return _json_result(data)


# --- Projects --------------------------------------------------------------


async def handle_list_projects(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_list_projects(
            workspace,
            cursor=args.get("cursor"),
            per_page=args.get("per_page", 20),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to list projects: {e}", error=True)
    return _json_result(data)


async def handle_get_project(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_get_project(workspace, project)
    except PlaneAPIError as e:
        return _text(f"Failed to get project {project}: {e}", error=True)
    return _json_result(data)


async def handle_create_project(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        payload = PlaneProjectCreate(
            name=args["name"],
            identifier=args["identifier"],
            description=args.get("description"),
            project_lead=args.get("project_lead"),
            default_assignee=args.get("default_assignee"),
        ).model_dump(exclude_none=True)
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid project payload: {e}", error=True)

    try:
        data = await plane_create_project(workspace, payload)
    except PlaneAPIError as e:
        return _text(f"Failed to create project: {e}", error=True)
    return _json_result(data)


async def handle_update_project(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    update_fields = {
        k: v
        for k, v in args.items()
        if k in {"name", "identifier", "description", "project_lead", "default_assignee"}
        and v is not None
    }
    if not update_fields:
        return _text("No updatable fields provided.", error=True)

    try:
        validated = PlaneProjectUpdate(**update_fields)
    except (ValueError, TypeError) as e:
        return _text(f"Invalid update payload: {e}", error=True)

    try:
        data = await plane_update_project(
            workspace, project, validated.model_dump(exclude_none=True)
        )
    except PlaneAPIError as e:
        return _text(f"Failed to update project {project}: {e}", error=True)
    return _json_result(data)


async def handle_archive_project(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_archive_project(workspace, project)
    except PlaneAPIError as e:
        return _text(f"Failed to archive project {project}: {e}", error=True)
    return _json_result(data)


async def handle_unarchive_project(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_unarchive_project(workspace, project)
    except PlaneAPIError as e:
        return _text(f"Failed to unarchive project {project}: {e}", error=True)
    return _json_result(data)


# --- Workspace members & invites -----------------------------------------


async def handle_list_workspace_members(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_list_workspace_members(workspace)
    except PlaneAPIError as e:
        return _text(f"Failed to list workspace members: {e}", error=True)
    return _json_result(data)


async def handle_update_workspace_member(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)

    member_id = args.get("member_id")
    if not member_id:
        return _text("'member_id' is required.", error=True)

    try:
        validated = PlaneWorkspaceMemberUpdate(role=args["role"])
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid member payload: {e}", error=True)

    try:
        data = await plane_update_workspace_member(
            workspace, member_id, validated.model_dump(exclude_none=True)
        )
    except PlaneAPIError as e:
        return _text(f"Failed to update workspace member {member_id}: {e}", error=True)
    return _json_result(data)


async def handle_list_workspace_invites(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_list_workspace_invites(workspace)
    except PlaneAPIError as e:
        return _text(f"Failed to list workspace invites: {e}", error=True)
    return _json_result(data)


async def handle_create_workspace_invite(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        payload = PlaneWorkspaceInviteCreate(
            email=args["email"],
            role=args.get("role", 15),
        ).model_dump(exclude_none=True)
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid invite payload: {e}", error=True)

    try:
        data = await plane_create_workspace_invite(workspace, payload)
    except PlaneAPIError as e:
        return _text(f"Failed to create workspace invite: {e}", error=True)
    return _json_result(data)


async def handle_get_workspace_invite(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)

    invite_id = args.get("invite_id")
    if not invite_id:
        return _text("'invite_id' is required.", error=True)

    try:
        data = await plane_get_workspace_invite(workspace, invite_id)
    except PlaneAPIError as e:
        return _text(f"Failed to get workspace invite {invite_id}: {e}", error=True)
    return _json_result(data)


async def handle_update_workspace_invite(args: dict) -> MCPToolResult:
    try:
        workspace = _workspace_arg(args)
    except ValueError as e:
        return _text(str(e), error=True)

    invite_id = args.get("invite_id")
    if not invite_id:
        return _text("'invite_id' is required.", error=True)

    try:
        validated = PlaneWorkspaceInviteUpdate(role=args["role"])
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid invite payload: {e}", error=True)

    try:
        data = await plane_update_workspace_invite(
            workspace, invite_id, validated.model_dump(exclude_none=True)
        )
    except PlaneAPIError as e:
        return _text(f"Failed to update workspace invite {invite_id}: {e}", error=True)
    return _json_result(data)


# --- Project members -------------------------------------------------------


async def handle_list_project_members(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_list_project_members(workspace, project)
    except PlaneAPIError as e:
        return _text(f"Failed to list project members: {e}", error=True)
    return _json_result(data)


async def handle_create_project_member(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        payload = PlaneProjectMemberCreate(
            member=args["member"],
            role=args.get("role", 15),
        ).model_dump(exclude_none=True)
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid project member payload: {e}", error=True)

    try:
        data = await plane_create_project_member(workspace, project, payload)
    except PlaneAPIError as e:
        return _text(f"Failed to create project member: {e}", error=True)
    return _json_result(data)


async def handle_get_project_member(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    member_id = args.get("member_id")
    if not member_id:
        return _text("'member_id' is required.", error=True)

    try:
        data = await plane_get_project_member(workspace, project, member_id)
    except PlaneAPIError as e:
        return _text(f"Failed to get project member {member_id}: {e}", error=True)
    return _json_result(data)


async def handle_update_project_member(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    member_id = args.get("member_id")
    if not member_id:
        return _text("'member_id' is required.", error=True)

    try:
        validated = PlaneProjectMemberUpdate(role=args["role"])
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid member payload: {e}", error=True)

    try:
        data = await plane_update_project_member(
            workspace, project, member_id, validated.model_dump(exclude_none=True)
        )
    except PlaneAPIError as e:
        return _text(f"Failed to update project member {member_id}: {e}", error=True)
    return _json_result(data)


# --- Tasks (work-items) ----------------------------------------------------


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
            target_date=args.get("target_date"),
            parent=args.get("parent"),
        )
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid task payload: {e}", error=True)

    try:
        payload = task.model_dump(mode="json", exclude_none=True)
        # Translate a state name to the UUID the Plane API expects.
        state_id = await _resolve_state_id(workspace, project, args.get("state"))
        if state_id:
            payload["state"] = state_id
        elif "state" in payload:
            del payload["state"]
        data = await plane_create_task(workspace, project, payload)
    except (KeyError, ValueError, TypeError, PlaneAPIError) as e:
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
        if k in {"name", "description_html", "priority", "state", "target_date", "parent"}
        and v is not None
    }
    if not update_fields:
        return _text("No updatable fields provided.", error=True)

    try:
        validated = PlaneTaskUpdate(**update_fields)
    except (ValueError, TypeError) as e:
        return _text(f"Invalid update payload: {e}", error=True)

    try:
        payload = validated.model_dump(mode="json", exclude_none=True)
        if "state" in update_fields:
            state_id = await _resolve_state_id(workspace, project, update_fields["state"])
            if state_id:
                payload["state"] = state_id
            else:
                payload.pop("state", None)
        data = await plane_update_task(workspace, project, task_id, payload)
    except (ValueError, TypeError, PlaneAPIError) as e:
        return _text(f"Failed to update task {task_id}: {e}", error=True)
    return _json_result(data)


# --- Cycles (sprints) ------------------------------------------------------


async def handle_list_cycles(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_list_cycles(
            workspace,
            project,
            cursor=args.get("cursor"),
            per_page=args.get("per_page", 20),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to list cycles: {e}", error=True)
    return _json_result(data)


async def handle_get_cycle(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    cycle_id = args.get("cycle_id")
    if not cycle_id:
        return _text("'cycle_id' is required.", error=True)

    try:
        data = await plane_get_cycle(workspace, project, cycle_id)
    except PlaneAPIError as e:
        return _text(f"Failed to get cycle {cycle_id}: {e}", error=True)
    return _json_result(data)


async def handle_create_cycle(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        payload = PlaneCycleCreate(
            name=args["name"],
            description=args.get("description"),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            status=args.get("status"),
        ).model_dump(mode="json", exclude_none=True)
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid cycle payload: {e}", error=True)

    payload["project_id"] = project

    try:
        data = await plane_create_cycle(workspace, project, payload)
    except PlaneAPIError as e:
        return _text(f"Failed to create cycle: {e}", error=True)
    return _json_result(data)


async def handle_update_cycle(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    cycle_id = args.get("cycle_id")
    if not cycle_id:
        return _text("'cycle_id' is required.", error=True)

    update_fields = {
        k: v
        for k, v in args.items()
        if k in {"name", "description", "start_date", "end_date", "status"}
        and v is not None
    }
    if not update_fields:
        return _text("No updatable fields provided.", error=True)

    try:
        validated = PlaneCycleUpdate(**update_fields)
    except (ValueError, TypeError) as e:
        return _text(f"Invalid update payload: {e}", error=True)

    try:
        data = await plane_update_cycle(
            workspace,
            project,
            cycle_id,
            validated.model_dump(mode="json", exclude_none=True),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to update cycle {cycle_id}: {e}", error=True)
    return _json_result(data)


async def handle_list_cycle_issues(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    cycle_id = args.get("cycle_id")
    if not cycle_id:
        return _text("'cycle_id' is required.", error=True)

    try:
        data = await plane_list_cycle_issues(
            workspace,
            project,
            cycle_id,
            cursor=args.get("cursor"),
            per_page=args.get("per_page", 20),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to list cycle issues: {e}", error=True)
    return _json_result(data)


async def handle_add_cycle_issues(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    cycle_id = args.get("cycle_id")
    if not cycle_id:
        return _text("'cycle_id' is required.", error=True)

    issues = args.get("issues")
    if not isinstance(issues, list) or not issues:
        return _text(
            "'issues' is required and must be a non-empty list of work-item UUIDs.",
            error=True,
        )

    try:
        data = await plane_add_cycle_issues(
            workspace, project, cycle_id, {"issues": issues}
        )
    except PlaneAPIError as e:
        return _text(f"Failed to add issues to cycle {cycle_id}: {e}", error=True)
    return _json_result(data)


# --- Modules (epics) -------------------------------------------------------


async def handle_list_modules(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        data = await plane_list_modules(
            workspace,
            project,
            cursor=args.get("cursor"),
            per_page=args.get("per_page", 20),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to list modules: {e}", error=True)
    return _json_result(data)


async def handle_get_module(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    module_id = args.get("module_id")
    if not module_id:
        return _text("'module_id' is required.", error=True)

    try:
        data = await plane_get_module(workspace, project, module_id)
    except PlaneAPIError as e:
        return _text(f"Failed to get module {module_id}: {e}", error=True)
    return _json_result(data)


async def handle_create_module(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    try:
        payload = PlaneModuleCreate(
            name=args["name"],
            description=args.get("description"),
            status=args.get("status"),
            start_date=args.get("start_date"),
            target_date=args.get("target_date"),
            lead=args.get("lead"),
        ).model_dump(mode="json", exclude_none=True)
    except (KeyError, ValueError, TypeError) as e:
        return _text(f"Invalid module payload: {e}", error=True)

    payload["project_id"] = project

    try:
        data = await plane_create_module(workspace, project, payload)
    except PlaneAPIError as e:
        return _text(f"Failed to create module: {e}", error=True)
    return _json_result(data)


async def handle_update_module(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    module_id = args.get("module_id")
    if not module_id:
        return _text("'module_id' is required.", error=True)

    update_fields = {
        k: v
        for k, v in args.items()
        if k in {"name", "description", "status", "start_date", "target_date", "lead"}
        and v is not None
    }
    if not update_fields:
        return _text("No updatable fields provided.", error=True)

    try:
        validated = PlaneModuleUpdate(**update_fields)
    except (ValueError, TypeError) as e:
        return _text(f"Invalid update payload: {e}", error=True)

    try:
        data = await plane_update_module(
            workspace,
            project,
            module_id,
            validated.model_dump(mode="json", exclude_none=True),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to update module {module_id}: {e}", error=True)
    return _json_result(data)


async def handle_list_module_issues(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    module_id = args.get("module_id")
    if not module_id:
        return _text("'module_id' is required.", error=True)

    try:
        data = await plane_list_module_issues(
            workspace,
            project,
            module_id,
            cursor=args.get("cursor"),
            per_page=args.get("per_page", 20),
        )
    except PlaneAPIError as e:
        return _text(f"Failed to list module issues: {e}", error=True)
    return _json_result(data)


async def handle_add_module_issues(args: dict) -> MCPToolResult:
    try:
        workspace, project = _workspace_project_args(args)
    except ValueError as e:
        return _text(str(e), error=True)

    module_id = args.get("module_id")
    if not module_id:
        return _text("'module_id' is required.", error=True)

    issues = args.get("issues")
    if not isinstance(issues, list) or not issues:
        return _text(
            "'issues' is required and must be a non-empty list of work-item UUIDs.",
            error=True,
        )

    try:
        data = await plane_add_module_issues(
            workspace, project, module_id, {"issues": issues}
        )
    except PlaneAPIError as e:
        return _text(f"Failed to add issues to module {module_id}: {e}", error=True)
    return _json_result(data)


ToolHandler = Callable[[dict], Awaitable[MCPToolResult]]

# Dispatch map — built from TOOLS so names can never drift from the manifest.
TOOL_HANDLERS: dict[str, ToolHandler] = {
    # Workspaces
    "list_workspaces": handle_list_workspaces,
    "get_workspace": handle_get_workspace,
    "create_workspace": handle_create_workspace,
    "update_workspace": handle_update_workspace,
    # Projects
    "list_projects": handle_list_projects,
    "get_project": handle_get_project,
    "create_project": handle_create_project,
    "update_project": handle_update_project,
    "archive_project": handle_archive_project,
    "unarchive_project": handle_unarchive_project,
    # Workspace members / invites
    "list_workspace_members": handle_list_workspace_members,
    "update_workspace_member": handle_update_workspace_member,
    "list_workspace_invites": handle_list_workspace_invites,
    "create_workspace_invite": handle_create_workspace_invite,
    "get_workspace_invite": handle_get_workspace_invite,
    "update_workspace_invite": handle_update_workspace_invite,
    # Project members
    "list_project_members": handle_list_project_members,
    "create_project_member": handle_create_project_member,
    "get_project_member": handle_get_project_member,
    "update_project_member": handle_update_project_member,
    # Tasks
    "list_tasks": handle_list_tasks,
    "get_task": handle_get_task,
    "create_task": handle_create_task,
    "update_task": handle_update_task,
    # Cycles
    "list_cycles": handle_list_cycles,
    "get_cycle": handle_get_cycle,
    "create_cycle": handle_create_cycle,
    "update_cycle": handle_update_cycle,
    "list_cycle_issues": handle_list_cycle_issues,
    "add_cycle_issues": handle_add_cycle_issues,
    # Modules
    "list_modules": handle_list_modules,
    "get_module": handle_get_module,
    "create_module": handle_create_module,
    "update_module": handle_update_module,
    "list_module_issues": handle_list_module_issues,
    "add_module_issues": handle_add_module_issues,
}

# Sanity check: every manifest entry must have a handler and vice versa.
_manifest_names = {t["name"] for t in TOOLS}
_handler_names = set(TOOL_HANDLERS)
assert _manifest_names == _handler_names, (
    f"Tool manifest/handler mismatch: "
    f"manifest={_manifest_names} handlers={_handler_names}"
)
