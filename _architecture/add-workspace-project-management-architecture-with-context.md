# Workspace & Project Management in mcp-plane

## Task
Add workspace, project, workspace-member/invite, and project-member management tools to the existing `mcp-plane` MCP server for Plane v1.3.1. Remove all delete actions, including the existing `delete_task` tool.

## Context
- Plane API base URL: `http://umbrel:8762` (configurable via `PLANE_API_BASE`).
- Authentication: `X-API-Key` header from `PLANE_MCP_TOKEN` env var; no MCP client passthrough.
- MCP transport: Streamable HTTP JSON-RPC at `/mcp`; tools-only capability.
- Version of MCP spec: 2025-11-25.

## Domain Spec Compliance
- **Capability**: tools only.
- **Lifecycle**: already implemented; no changes.
- **Transport / auth**: already implemented; no changes.
- **Tool schemas**: new tools return valid inputSchema with required fields, enums, and descriptions.
- **Tool results**: continue using `content[]` + `isError` envelope.
- **No token passthrough**: token remains env-only.
- **Security**: origin validation, optional Bearer auth, rate limiting remain unchanged.

## Tools to Add

### Workspaces
- `list_workspaces` — paginated list of accessible workspaces.
- `get_workspace` — get a workspace by slug.
- `create_workspace` — requires `name` and `slug`.
- `update_workspace` — partial update by slug.

### Projects
- `list_projects` — paginated list of projects in a workspace.
- `get_project` — get a project by ID.
- `create_project` — requires `name` and `identifier`; optional `description`, `project_lead`, `default_assignee`.
- `update_project` — partial update by project ID.
- `archive_project` — archive a project.
- `unarchive_project` — unarchive a project.

### Workspace members & invites
- `list_workspace_members` — list members.
- `update_workspace_member` — update member role.
- `list_workspace_invites` — list pending invites.
- `create_workspace_invite` — invite by email and role.
- `get_workspace_invite` — get invite details.
- `update_workspace_invite` — update invite role.

### Project members
- `list_project_members` — list members.
- `create_project_member` — add workspace user to project with role.
- `get_project_member` — get member.
- `update_project_member` — update role.

### Task changes
- Remove `delete_task` from the tool manifest and handlers.

## Plane API Endpoints Used
All endpoints are prefixed with `PLANE_API_BASE` + `/api/v1`.

| Entity | Endpoints |
|---|---|
| Workspace | `GET /workspaces/`, `POST /workspaces/`, `GET /workspaces/{slug}/`, `PATCH /workspaces/{slug}/` |
| Project | `GET /workspaces/{slug}/projects/`, `POST /workspaces/{slug}/projects/`, `GET /workspaces/{slug}/projects/{id}/`, `PATCH /workspaces/{slug}/projects/{id}/`, `POST /workspaces/{slug}/projects/{id}/archive/`, `DELETE /workspaces/{slug}/projects/{id}/archive/` |
| Workspace members | `GET /workspaces/{slug}/members/`, `PATCH /workspaces/{slug}/members/{member_id}/` |
| Workspace invites | `GET /workspaces/{slug}/invitations/`, `POST /workspaces/{slug}/invitations/`, `GET /workspaces/{slug}/invitations/{id}/`, `PATCH /workspaces/{slug}/invitations/{id}/` |
| Project members | `GET /workspaces/{slug}/projects/{id}/members/`, `POST /workspaces/{slug}/projects/{id}/members/`, `GET /workspaces/{slug}/projects/{id}/members/{member_id}/`, `PATCH /workspaces/{slug}/projects/{id}/members/{member_id}/` |

## Role Values
Follow Plane's role enum:
- `GUEST = 5`
- `MEMBER = 15`
- `ADMIN = 20`

Expose as JSON Schema `enum: [5, 15, 20]` with descriptive parameter text.

## Data Validation
- Workspace `slug` must match `^[a-zA-Z0-9_-]{1,48}$`.
- Workspace `name` max length 80, must not be empty.
- Project `identifier` must match `^[A-Za-z0-9_-]{1,20}$`; Plane will uppercase it server-side.
- Project `name` required for create.
- Invite `email` must be a valid email format.
- All role fields must be one of `5`, `15`, `20`.

## Implementation Sequence
1. Extend `app/models.py` with Pydantic schemas for new domains and role enum.
2. Extend `app/plane_client.py` with async REST helpers for new endpoints and remove `delete_task`.
3. Extend `app/tools.py` manifest, helpers, and handlers; remove `delete_task` handler.
4. Update `app/server.py` instructions string.
5. Update `README.md` feature list.
6. Bump server version to `1.1.0`.
7. Smoke-test discovery and read-only calls.

## Security Measures
- All inputs validated with Pydantic before touching Plane.
- No MCP client token is accepted or forwarded.
- Plane API RBAC enforces permissions; failures returned with `isError: true`.
- Rate limiting remains per-IP.

## Risks
- **Medium**: increased tool count (25+) may require very precise tool descriptions. Mitigated by naming convention and detailed parameter docs.
- **Low**: user IDs for member operations may be unknown; callers can discover them via `list_workspace_members` first. Plane returns clear errors if they are invalid.

## Domain Spec Compliance
No deviations from `mcp-server-guidelines` (spec v2025-11-25) are expected.

## Implementation Status
| File | Status | Notes |
|------|--------|-------|
| `app/models.py` | To update | New schemas |
| `app/plane_client.py` | To update | New API functions, remove delete_task |
| `app/tools.py` | To update | New tools/handlers, remove delete_task |
| `app/server.py` | To update | New instructions |
| `README.md` | To update | New feature list |
| `app/__init__.py` | To update | Version bump |
