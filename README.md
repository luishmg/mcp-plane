<div align="center">

# 🛩️ mcp-plane

**An MCP server that exposes Plane task-management actions to AI agents**

[![MCP Spec](https://img.shields.io/badge/MCP-2025--11--25-blue?style=flat-square)](https://modelcontextprotocol.io/specification/2025-11-25)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org/)
[![Plane](https://img.shields.io/badge/Plane-v1.3.1-1c4ebc?style=flat-square)](https://plane.so/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white&style=flat-square)](./docker-compose.yml)
[![Version](https://img.shields.io/badge/Version-1.1.0-blue?style=flat-square)]()
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)

</div>

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Layout](#project-layout)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Configuration](#configuration)
- [Testing](#testing)
- [Security](#security)
- [License](#license)

---

## 🎯 Overview

`mcp-plane` is a lightweight [MCP (Model Context Protocol)](https://modelcontextprotocol.io/specification/2025-11-25) server that bridges AI agents with [Plane](https://plane.so/) v1.3.1. It translates standard MCP tool calls into authenticated Plane REST API requests, so agents can list, read, create, update, and delete tasks in your Plane workspace without embedding Plane credentials in every prompt.

### What it does

| Component | Purpose |
|---|---|
| `app/server.py` | FastAPI + Streamable HTTP JSON-RPC `/mcp` endpoint |
| `app/tools.py` | Declarative MCP tool manifest and handlers |
| `app/plane_client.py` | Async Plane REST client with `X-API-Key` auth |
| `app/models.py` | Pydantic schemas for MCP/Plane validation |
| `app/config.py` | Environment-driven settings with fail-fast defaults |

---

## 🛠 Features

### Streamable HTTP transport

**Single-endpoint MCP over HTTP.** Implements JSON-RPC 2.0 on `/mcp`, including the full MCP lifecycle: `initialize`, `tools/list`, `tools/call`, and `ping`.

### Plane workspace & project management

**Manage workspaces and projects.** Agents can call workspace tools (`list_workspaces`, `get_workspace`, `create_workspace`, `update_workspace`), project tools (`list_projects`, `get_project`, `create_project`, `update_project`, `archive_project`, `unarchive_project`), workspace members/invites, and project members.

### Plane task management

**Task lifecycle operations exposed as MCP tools.** Agents can call `list_tasks`, `get_task`, `create_task`, and `update_task`, scoped to a Plane workspace and project. Delete operations are intentionally omitted.

### Plane cycles & modules

**Sprint and epic planning exposed as MCP tools.** Agents can manage cycles (`list_cycles`, `get_cycle`, `create_cycle`, `update_cycle`, `list_cycle_issues`, `add_cycle_issues`) and modules (`list_modules`, `get_module`, `create_module`, `update_module`, `list_module_issues`, `add_module_issues`), scoped to a Plane workspace and project. Work items are associated to a cycle or module in bulk via their UUIDs. Delete operations are intentionally omitted.

### Validated and secured inputs

**Pydantic schemas and request guards.** All tool inputs are validated, outputs are JSON-serialized, and requests are protected by origin validation and IP-based rate limiting.

### Docker-ready runtime

**Runs as a non-root user in a minimal container.** Build and run with the included `Dockerfile` and `docker-compose.yml`.

---

## 📁 Project Layout

```
mcp-plane/
├── app/
│   ├── __init__.py
│   ├── __main__.py         # python -m app
│   ├── server.py           # FastAPI + MCP JSON-RPC endpoint
│   ├── tools.py            # Tool manifest + handlers
│   ├── plane_client.py     # Async Plane REST client
│   ├── models.py           # Pydantic models
│   └── config.py           # Env-driven settings
├── tests/                  # pytest suite (asyncio_mode=auto)
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_errors.py
│   ├── test_middleware.py
│   ├── test_models.py
│   ├── test_plane_client.py
│   ├── test_server.py
│   └── test_tools.py
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

---

## 🚀 Getting Started

### Prerequisites

- Plane v1.3.1 instance and a valid API token
- Docker and Docker Compose *(recommended)*, or Python 3.x with `pip`

### Setup

Copy the example environment file and set your Plane API token (generated in Plane under **Profile Settings → API Tokens**):

```bash
cp .env.example .env
# edit .env and set PLANE_MCP_TOKEN
```

### Run with Docker Compose

```bash
# 1. Set the token in your shell (not baked into the image)
export PLANE_MCP_TOKEN="plane_api_your_token_here"

# 2. Build & run
docker compose up --build -d

# 3. Check health
curl http://127.0.0.1:8763/health
```

### Run locally

```bash
pip install -r requirements.txt
export PLANE_MCP_TOKEN="plane_api_your_token_here"
python -m app
```

---

## 💻 Usage

### Quick MCP test

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

Workspace tools require `workspace_slug`. Project and task tools also require `project_id`. Member tools require the UUID of the workspace/project membership record.

---

## 🔧 Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLANE_MCP_TOKEN` | ✅ | — | Plane API token (sent as `X-API-Key`) |
| `MCP_AUTH_TOKEN` | ❌ | _(empty)_ | When set, MCP clients must send `Authorization: Bearer <token>` on `/mcp`. Leave empty to disable client auth. |
| `PLANE_API_BASE` | ❌ | `http://umbrel:8762` | Base URL of your Plane instance |
| `HOST` | ❌ | `127.0.0.1` | Bind address (the bundled `docker-compose.yml` overrides this to `0.0.0.0` inside the container and publishes the port only on loopback) |
| `PORT` | ❌ | `8763` | Listen port |
| `ALLOWED_ORIGINS` | ❌ | _(empty)_ | Comma-separated allowed `Origin` values |
| `REQUEST_TIMEOUT_SECONDS` | ❌ | `15` | Per-request timeout to Plane |
| `RATE_LIMIT_PER_MINUTE` | ❌ | `60` | Max MCP requests/min/IP |

---

## 🧪 Testing

The test suite uses `pytest` with `asyncio_mode = auto` (see `pytest.ini`), so async tests run without explicit markers.

```bash
# install dev dependencies (pytest, pytest-asyncio, pytest-mock)
pip install -r requirements.txt -r requirements-dev.txt

# run the full suite
pytest

# run a single file or a single test
pytest tests/test_tools.py
pytest tests/test_tools.py::test_name
```

| Test file | Covers |
|---|---|
| `tests/test_config.py` | Environment-driven settings and fail-fast behavior |
| `tests/test_errors.py` | Error mapping and JSON-RPC error responses |
| `tests/test_middleware.py` | Origin validation, client auth, and rate limiting |
| `tests/test_models.py` | Pydantic schema validation |
| `tests/test_plane_client.py` | Async Plane REST client behavior |
| `tests/test_server.py` | MCP lifecycle endpoints (`initialize`, `tools/list`, `tools/call`, `ping`) |
| `tests/test_tools.py` | Tool manifest and handler dispatch |

Shared fixtures live in `tests/conftest.py`.

---

## 🔒 Security

- The Plane API token is read from the environment and **never** accepted from MCP clients (no token passthrough).
- Optional **client authentication**: set `MCP_AUTH_TOKEN` to require MCP clients to present `Authorization: Bearer <MCP_AUTH_TOKEN>` on every `/mcp` request. Unauthenticated or mismatched requests are rejected with `401`. The comparison is constant-time. Leave unset to disable (only safe on trusted networks).
- The server defaults to listening on all interfaces (`0.0.0.0`) inside the container; expose it externally only behind a TLS-terminating reverse proxy with authentication.
- All tool inputs are validated with Pydantic schemas and outputs are JSON-serialized before returning.

---

## 📄 License

MIT
