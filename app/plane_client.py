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

        # Some endpoints (DELETE) may return empty body.
        if not resp.content:
            return {}
        return resp.json()


# ---------------------------------------------------------------------------
# Work-item (task) CRUD
# ---------------------------------------------------------------------------


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


async def delete_task(
    workspace_slug: str,
    project_id: str,
    task_id: str,
) -> dict:
    """Delete a work item."""
    endpoint = (
        f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{task_id}/"
    )
    return await _request("DELETE", endpoint)
