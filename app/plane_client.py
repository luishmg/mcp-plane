"""
Async client for the Plane REST API (v1.3.1).

All requests are authenticated with the X-API-Key header read from the
PLANE_MCP_TOKEN environment variable. The token never leaves this process —
it is NOT accepted from MCP clients (no token passthrough).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from .config import PLANE_API_BASE, PLANE_MCP_TOKEN, settings

logger = logging.getLogger("plane_mcp.client")

DEFAULT_HEADERS = {
    "X-API-Key": PLANE_MCP_TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json",
}


class PlaneAPIError(Exception):
    """Raised when the Plane API returns a non-2xx response."""


async def _request(
    method: str,
    endpoint: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    timeout: Optional[float] = None,
) -> Any:
    """Low-level request wrapper. Returns parsed JSON or raises PlaneAPIError."""
    url = f"{PLANE_API_BASE.rstrip('/')}{endpoint}"
    logger.debug("Plane API %s %s", method, url)

    async with httpx.AsyncClient(
        timeout=timeout or settings.REQUEST_TIMEOUT_SECONDS
    ) as client:
        try:
            resp = await client.request(
                method,
                url,
                headers=DEFAULT_HEADERS,
                params=params,
                json=json_body,
            )
        except httpx.RequestError as exc:
            # Network / connection failure — surface as a recoverable error.
            raise PlaneAPIError(f"Network error contacting Plane: {exc}") from exc

        if resp.status_code >= 400:
            # Include a trimmed body so callers can self-correct, but never log
            # the full raw response (could contain sensitive data).
            body = (resp.text or "")[:500]
            raise PlaneAPIError(
                f"Plane API {resp.status_code} for {method} {endpoint}: {body}"
            )

        # Some endpoints (DELETE/unarchive, DELETE workspace) may return empty body.
        if not resp.content:
            return {}
        return resp.json()


# ---------------------------------------------------------------------------
# Generic pagination helpers
# ---------------------------------------------------------------------------


def _paginated_params(cursor: Optional[str] = None, per_page: int = 20) -> dict[str, Any]:
    params: dict[str, Any] = {"per_page": per_page}
    if cursor:
        params["cursor"] = cursor
    return params


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


async def list_workspaces(
    *,
    cursor: Optional[str] = None,
    per_page: int = 20,
) -> Any:
    """List workspaces the API token owner belongs to.

    Plane's public API has NO list-all-workspaces endpoint (GET /api/v1/workspaces/
    returns 404 — every other resource is scoped under a known {workspace_slug}).
    We use the `users/me/workspaces` endpoint, which returns the caller's
    workspaces as a plain array and ignores pagination params. Do not "fix" this
    back to /api/v1/workspaces/ — that path 404s.
    """
    return await _request(
        "GET", "/api/v1/users/me/workspaces/", params=_paginated_params(cursor, per_page)
    )


async def get_workspace(workspace_slug: str) -> dict:
    """Retrieve a single workspace by slug.

    There is no per-workspace GET on the API-key surface, so we list the
    caller's workspaces (see ``list_workspaces``) and return the slug match.
    """
    data = await list_workspaces()
    items = data if isinstance(data, list) else (data.get("results") or data.get("workspaces") or [])
    for workspace in items:
        if isinstance(workspace, dict) and workspace.get("slug") == workspace_slug:
            return workspace
    raise PlaneAPIError(
        f"Workspace '{workspace_slug}' not found among accessible workspaces"
    )


async def create_workspace(payload: dict) -> dict:
    """Create a new workspace."""
    return await _request("POST", "/api/v1/workspaces/", json_body=payload)


async def update_workspace(workspace_slug: str, payload: dict) -> dict:
    """Partially update a workspace."""
    return await _request(
        "PATCH", f"/api/v1/workspaces/{workspace_slug}/", json_body=payload
    )


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


async def list_projects(
    workspace_slug: str,
    *,
    cursor: Optional[str] = None,
    per_page: int = 20,
) -> dict:
    """List projects in a workspace."""
    endpoint = f"/api/v1/workspaces/{workspace_slug}/projects/"
    return await _request("GET", endpoint, params=_paginated_params(cursor, per_page))


async def get_project(workspace_slug: str, project_id: str) -> dict:
    """Retrieve a project by ID."""
    endpoint = f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/"
    return await _request("GET", endpoint)


async def create_project(workspace_slug: str, payload: dict) -> dict:
    """Create a new project."""
    endpoint = f"/api/v1/workspaces/{workspace_slug}/projects/"
    return await _request("POST", endpoint, json_body=payload)


async def update_project(
    workspace_slug: str, project_id: str, payload: dict
) -> dict:
    """Partially update a project."""
    endpoint = f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/"
    return await _request("PATCH", endpoint, json_body=payload)


async def archive_project(workspace_slug: str, project_id: str) -> dict:
    """Archive a project."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/archive/"
    )
    return await _request("POST", endpoint)


async def unarchive_project(workspace_slug: str, project_id: str) -> dict:
    """Unarchive a project."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/archive/"
    )
    return await _request("DELETE", endpoint)


# ---------------------------------------------------------------------------
# Workspace members & invites
# ---------------------------------------------------------------------------


async def list_workspace_members(workspace_slug: str) -> list:
    """List members of a workspace."""
    return await _request("GET", f"/api/v1/workspaces/{workspace_slug}/members/")


async def update_workspace_member(
    workspace_slug: str, member_id: str, payload: dict
) -> dict:
    """Update a workspace member's role."""
    endpoint = f"/api/v1/workspaces/{workspace_slug}/members/{member_id}/"
    return await _request("PATCH", endpoint, json_body=payload)


async def list_workspace_invites(workspace_slug: str) -> list:
    """List pending workspace invitations."""
    return await _request(
        "GET", f"/api/v1/workspaces/{workspace_slug}/invitations/"
    )


async def create_workspace_invite(workspace_slug: str, payload: dict) -> dict:
    """Invite an email address to a workspace."""
    return await _request(
        "POST", f"/api/v1/workspaces/{workspace_slug}/invitations/", json_body=payload
    )


async def get_workspace_invite(workspace_slug: str, invite_id: str) -> dict:
    """Retrieve a workspace invitation."""
    return await _request(
        "GET", f"/api/v1/workspaces/{workspace_slug}/invitations/{invite_id}/"
    )


async def update_workspace_invite(
    workspace_slug: str, invite_id: str, payload: dict
) -> dict:
    """Update a pending workspace invitation (e.g. change role)."""
    endpoint = f"/api/v1/workspaces/{workspace_slug}/invitations/{invite_id}/"
    return await _request("PATCH", endpoint, json_body=payload)


# ---------------------------------------------------------------------------
# Project members
# ---------------------------------------------------------------------------


def _project_members_endpoint(
    workspace_slug: str, project_id: str, member_id: Optional[str] = None
) -> str:
    endpoint = f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/members/"
    if member_id:
        endpoint += f"{member_id}/"
    return endpoint


async def list_project_members(workspace_slug: str, project_id: str) -> list:
    """List members of a project."""
    return await _request(
        "GET", _project_members_endpoint(workspace_slug, project_id)
    )


async def create_project_member(
    workspace_slug: str, project_id: str, payload: dict
) -> dict:
    """Add a workspace member to a project."""
    return await _request(
        "POST",
        _project_members_endpoint(workspace_slug, project_id),
        json_body=payload,
    )


async def get_project_member(
    workspace_slug: str, project_id: str, member_id: str
) -> dict:
    """Retrieve a project member record."""
    return await _request(
        "GET", _project_members_endpoint(workspace_slug, project_id, member_id)
    )


async def update_project_member(
    workspace_slug: str, project_id: str, member_id: str, payload: dict
) -> dict:
    """Update a project member's role."""
    return await _request(
        "PATCH",
        _project_members_endpoint(workspace_slug, project_id, member_id),
        json_body=payload,
    )


# ---------------------------------------------------------------------------
# Work-items (tasks)
# ---------------------------------------------------------------------------


async def list_states(
    workspace_slug: str,
    project_id: str,
    *,
    per_page: int = 100,
) -> list:
    """List workflow states for a project so state names can be mapped to UUIDs."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/states/"
    )
    params: dict[str, Any] = {"per_page": per_page}
    data = await _request("GET", endpoint, params=params)
    return data.get("results", [])


async def list_tasks(
    workspace_slug: str,
    project_id: str,
    *,
    cursor: Optional[str] = None,
    per_page: int = 20,
) -> dict:
    """List work items in a project (paginated, cursor-based)."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/"
    )
    params: dict[str, Any] = {"per_page": per_page}
    if cursor:
        params["cursor"] = cursor
    return await _request("GET", endpoint, params=params)


async def get_task(
    workspace_slug: str,
    project_id: str,
    task_id: str,
) -> dict:
    """Retrieve a single work item by ID."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{task_id}/"
    )
    return await _request("GET", endpoint)


async def create_task(
    workspace_slug: str,
    project_id: str,
    payload: dict,
) -> dict:
    """Create a new work item."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/"
    )
    return await _request("POST", endpoint, json_body=payload)


async def update_task(
    workspace_slug: str,
    project_id: str,
    task_id: str,
    payload: dict,
) -> dict:
    """Update (partial) an existing work item."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{task_id}/"
    )
    return await _request("PATCH", endpoint, json_body=payload)


# ---------------------------------------------------------------------------
# Cycles (sprints)
# ---------------------------------------------------------------------------


async def list_cycles(
    workspace_slug: str,
    project_id: str,
    *,
    cursor: Optional[str] = None,
    per_page: int = 20,
) -> dict:
    """List cycles in a project (paginated, cursor-based)."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/cycles/"
    )
    return await _request("GET", endpoint, params=_paginated_params(cursor, per_page))


async def get_cycle(
    workspace_slug: str,
    project_id: str,
    cycle_id: str,
) -> dict:
    """Retrieve a single cycle by ID."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/cycles/{cycle_id}/"
    )
    return await _request("GET", endpoint)


async def create_cycle(
    workspace_slug: str,
    project_id: str,
    payload: dict,
) -> dict:
    """Create a new cycle."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/cycles/"
    )
    return await _request("POST", endpoint, json_body=payload)


async def update_cycle(
    workspace_slug: str,
    project_id: str,
    cycle_id: str,
    payload: dict,
) -> dict:
    """Update (partial) an existing cycle."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/cycles/{cycle_id}/"
    )
    return await _request("PATCH", endpoint, json_body=payload)


async def list_cycle_issues(
    workspace_slug: str,
    project_id: str,
    cycle_id: str,
    *,
    cursor: Optional[str] = None,
    per_page: int = 20,
) -> dict:
    """List work items assigned to a cycle (paginated, cursor-based)."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/cycles/{cycle_id}/cycle-issues/"
    )
    return await _request("GET", endpoint, params=_paginated_params(cursor, per_page))


async def add_cycle_issues(
    workspace_slug: str,
    project_id: str,
    cycle_id: str,
    payload: dict,
) -> dict:
    """Add existing work items to a cycle (bulk association)."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/cycles/{cycle_id}/cycle-issues/"
    )
    return await _request("POST", endpoint, json_body=payload)


# ---------------------------------------------------------------------------
# Modules (epics)
# ---------------------------------------------------------------------------


async def list_modules(
    workspace_slug: str,
    project_id: str,
    *,
    cursor: Optional[str] = None,
    per_page: int = 20,
) -> dict:
    """List modules in a project (paginated, cursor-based)."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/modules/"
    )
    return await _request("GET", endpoint, params=_paginated_params(cursor, per_page))


async def get_module(
    workspace_slug: str,
    project_id: str,
    module_id: str,
) -> dict:
    """Retrieve a single module by ID."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/modules/{module_id}/"
    )
    return await _request("GET", endpoint)


async def create_module(
    workspace_slug: str,
    project_id: str,
    payload: dict,
) -> dict:
    """Create a new module."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/modules/"
    )
    return await _request("POST", endpoint, json_body=payload)


async def update_module(
    workspace_slug: str,
    project_id: str,
    module_id: str,
    payload: dict,
) -> dict:
    """Update (partial) an existing module."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/modules/{module_id}/"
    )
    return await _request("PATCH", endpoint, json_body=payload)


async def list_module_issues(
    workspace_slug: str,
    project_id: str,
    module_id: str,
    *,
    cursor: Optional[str] = None,
    per_page: int = 20,
) -> dict:
    """List work items associated with a module (paginated, cursor-based)."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/modules/{module_id}/module-issues/"
    )
    return await _request("GET", endpoint, params=_paginated_params(cursor, per_page))


async def add_module_issues(
    workspace_slug: str,
    project_id: str,
    module_id: str,
    payload: dict,
) -> dict:
    """Associate existing work items with a module (bulk association)."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/modules/{module_id}/module-issues/"
    )
    return await _request("POST", endpoint, json_body=payload)
