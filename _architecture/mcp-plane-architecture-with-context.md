# MCP Plane Server Architecture

## Task
Build an MCP server to manage all task-related actions of the Plane tool version 1.3.1

## Context
- Plane API base URL: http://umbrel:8762
- Token: $PLANE_MCP_TOKEN environment variable
- MCP Spec Version: 2025-11-25

## Domain Spec Compliance
- **Capabilities**: Declared (tools only)
- **Lifecycle**: Implemented (initialize, shutdown)
- **Transport**: HTTP with Origin validation
- **Security**: Input validation, rate limiting, output sanitization

## Components
1. **JSON-RPC Endpoint**: Single /mcp endpoint
2. **Tool Registry**: Declarative manifest
3. **Plane Client**: Authenticated API client
4. **Auth Middleware**: Validates requests

## Tools Implemented
- `create_task`: Create tasks
- `list_tasks`: List tasks
- `update_task`: Update tasks
- `get_task`: Get task details
- `delete_task`: Delete tasks

## Security Measures
1. Input validation with Pydantic
2. Rate limiting (10 req/IP/min)
3. Token rotation
4. Output sanitization
5. IP allowlisting

## Implementation Status
| File | Status | Notes |
|------|--------|-------|
| server.py | Pending | Main entrypoint |
| tools.py | Pending | Tool manifest |
| plane_client.py | Pending | API client |
| mcp_models.py | Pending | Pydantic models |
| .env.example | Pending | Environment template |
| requirements.txt | Pending | Dependencies |