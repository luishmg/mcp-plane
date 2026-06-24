"""
Plane MCP server — FastAPI application exposing the MCP JSON-RPC 2.0 endpoint
over Streamable HTTP transport (single /mcp POST endpoint).

Compliance notes (MCP spec v2025-11-25):
  * initialize returns protocolVersion + capabilities + serverInfo
  * capabilities declares ONLY tools (no resources/prompts)
  * tools/list returns the declarative manifest
  * tools/call dispatches via the name -> handler map
  * Two error channels: JSON-RPC error for protocol issues, isError=True
    in the result for business/downstream failures
  * Origin header validated; binds to 127.0.0.1 by default
  * Token is read from env, never accepted from clients (no passthrough)
"""

from __future__ import annotations

import json
import logging
import secrets
import hmac
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from . import __version__
from .config import settings
from .models import MCPInitializeRequest
from .tools import TOOLS, TOOL_HANDLERS, MCPToolResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("plane_mcp.server")

# --- Rate limiting -----------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Plane MCP Server",
    description="Manage Plane work items (tasks) via the Model Context Protocol.",
    version="1.2.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- Lifespan / startup ------------------------------------------------------


@app.on_event("startup")
async def startup() -> None:
    if not settings.PLANE_MCP_TOKEN:
        raise RuntimeError(
            "PLANE_MCP_TOKEN environment variable is required but not set."
        )
    logger.info(
        "Plane MCP server starting (Plane API: %s, client auth: %s)",
        settings.PLANE_API_BASE,
        "enabled" if settings.MCP_AUTH_TOKEN else "disabled",
    )


# --- Security middleware -----------------------------------------------------


@app.middleware("http")
async def validate_origin_and_auth(request: Request, call_next):
    """Reject requests with a missing/unexpected Origin header (DNS rebinding
    mitigation). Allowed origins come from ALLOWED_ORIGINS (comma-separated).

    When MCP_AUTH_TOKEN is set, also require a matching Bearer token on the
    Authorization header for the /mcp endpoint. The comparison uses
    ``hmac.compare_digest`` to be constant-time."""
    allowed = settings.allowed_origin_set
    # Only enforce origin checks when an allowlist is configured. For local
    # stdio-style usage the client may not send one; binding to 127.0.0.1 is
    # the primary control in that case.
    if allowed:
        origin = request.headers.get("Origin", "")
        if origin and origin not in allowed:
            return JSONResponse(
                status_code=403, content={"detail": "Forbidden origin"}
            )
    # Client-facing auth for the MCP endpoint.
    expected_token = settings.MCP_AUTH_TOKEN
    if expected_token and request.url.path == "/mcp":
        header = request.headers.get("Authorization", "")
        scheme, _, provided = header.partition(" ")
        if (
            scheme.lower() != "bearer"
            or not provided
            or not hmac.compare_digest(provided, expected_token)
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
                headers={"WWW-Authenticate": "Bearer"},
            )

    return await call_next(request)


# --- JSON-RPC helpers --------------------------------------------------------


def _rpc_response(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# --- MCP endpoint ------------------------------------------------------------


@app.post("/mcp")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def mcp_endpoint(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(_rpc_error(None, -32700, "Parse error"), status_code=400)

    if not isinstance(body, dict):
        return JSONResponse(
            _rpc_error(None, -32600, "Invalid Request"), status_code=400
        )

    req_id = body.get("id")
    method = body.get("method")

    # --- initialize ----------------------------------------------------------
    if method == "initialize":
        try:
            params = body.get("params") or {}
            MCPInitializeRequest(**params)
        except Exception as e:  # validation error
            return _rpc_error(req_id, -32602, f"Invalid params: {e}")
        return _rpc_response(
            req_id,
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "plane-mcp",
                    "version": __version__,
                },
                "instructions": (
                    "This server exposes Plane workspace, project, member, invite, "
                    "and task management tools. Workspaces are scoped by "
                    "workspace_slug; projects and tasks additionally require "
                    "project_id. Members require the workspace/project membership "
                    "record UUID. Available tools: list_workspaces, get_workspace, "
                    "create_workspace, update_workspace, list_projects, get_project, "
                    "create_project, update_project, archive_project, unarchive_project, "
                    "list_workspace_members, update_workspace_member, list_workspace_invites, "
                    "create_workspace_invite, get_workspace_invite, update_workspace_invite, "
                    "list_project_members, create_project_member, get_project_member, "
                    "update_project_member, list_tasks, get_task, create_task, update_task."
                ),
            },
        )

    # --- notifications/initialized (no response required) --------------------
    if method == "notifications/initialized":
        return JSONResponse(status_code=204, content=None)

    # --- tools/list ----------------------------------------------------------
    if method == "tools/list":
        return _rpc_response(req_id, {"tools": TOOLS})

    # --- tools/call ----------------------------------------------------------
    if method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}

        if not name:
            return _rpc_error(req_id, -32602, "Missing tool name")
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return _rpc_error(req_id, -32601, f"Unknown tool: {name}")

        try:
            result: MCPToolResult = await handler(args)
        except Exception as e:  # never leak raw tracebacks to the agent
            logger.exception("Unhandled error in tool '%s'", name)
            result = MCPToolResult(
                content=[{"type": "text", "text": f"Internal error: {e}"}],
                isError=True,
            )
        return _rpc_response(req_id, result.model_dump())

    # --- ping ----------------------------------------------------------------
    if method == "ping":
        return _rpc_response(req_id, {})

    return _rpc_error(req_id, -32601, f"Method not found: {method}")


# --- Health endpoint (not part of MCP, useful for Docker) -------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.server:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
    )
