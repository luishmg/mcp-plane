# mcp-plane

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/specification/2025-11-25) server that exposes **Plane** (v1.3.1) task-management actions as tools an AI agent can call.

## Features

- Streamable HTTP transport (JSON-RPC 2.0 over a single `/mcp` endpoint)
- Full MCP lifecycle (`initialize`, `tools/list`, `tools/call`, `ping`)
- Tools: `list_tasks`, `get_task`, `create_task`, `update_task`, `delete_task`
- Authenticated Plane API client (`X-API-Key` from `$PLANE_MCP_TOKEN`)
- Input validation (Pydantic), rate limiting, Origin validation
- Runs as a non-root user inside Docker

## Project layout

```
mcp-plane/
├── app/
│   ├── __init__.py
│   ├── __main__.py        # `python -m app`
│   ├── server.py           # FastAPI + MCP JSON-RPC endpoint
│   ├── tools.py            # Declarative tool manifest + handlers
│   ├── plane_client.py     # Async Plane REST API client
│   ├── models.py           # Pydantic models (MCP + Plane)
│   └── config.py           # Settings (env-driven, fail-fast)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Configuration

Copy the example env file and set your Plane API token (generated in Plane under **Profile Settings → API Tokens**):

```bash
cp .env.example .env
# edit .env and set PLANE_MCP_TOKEN
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLANE_MCP_TOKEN` | ✅ | — | Plane API token (sent as `X-API-Key`) |
| `PLANE_API_BASE` | ❌ | `http://umbrel:8762` | Base URL of your Plane instance |
| `HOST` | ❌ | `127.0.0.1` | Bind address |
| `PORT` | ❌ | `8763` | Listen port |
| `ALLOWED_ORIGINS` | ❌ | _(empty)_ | Comma-separated allowed `Origin` values |
| `REQUEST_TIMEOUT_SECONDS` | ❌ | `15` | Per-request timeout to Plane |
| `RATE_LIMIT_PER_MINUTE` | ❌ | `60` | Max MCP requests/min/IP |

## Run with Docker Compose

```bash
# 1. Set the token in your shell (not baked into the image)
export PLANE_MCP_TOKEN="plane_api_your_token_here"

# 2. Build & run
docker compose up --build -d

# 3. Check health
curl http://127.0.0.1:8763/health
```

## Run locally (without Docker)

```bash
pip install -r requirements.txt
export PLANE_MCP_TOKEN="plane_api_your_token_here"
python -m app      # serves on 127.0.0.1:8763
```

## MCP quick test

```bash
# initialize
curl -s http://127.0.0.1:8763/mcp -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"initialize",
  "params":{"protocolVersion":"2025-11-25"}
}'

# list tools
curl -s http://127.0.0.1:8763/mcp -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":2,"method":"tools/list"
}'
```

All task tools require `workspace_slug` and `project_id` to scope the operation to the right Plane project.

## Security notes

- The token is read from the environment and **never** accepted from MCP clients (no token passthrough).
- Defaults to loopback binding (`127.0.0.1`). For remote access, run behind a TLS-terminating reverse proxy with authentication.
- All tool inputs are validated with Pydantic schemas; outputs are JSON-serialized before returning.
