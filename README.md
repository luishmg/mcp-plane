<div align="center">

# 🛩️ mcp-plane

**An MCP server that exposes Plane task-management actions to AI agents**

[![MCP Spec](https://img.shields.io/badge/MCP-2025--11--25-blue?style=flat-square)](https://modelcontextprotocol.io/specification/2025-11-25)
[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org/)
[![Plane](https://img.shields.io/badge/Plane-v1.3.1-1c4ebc?style=flat-square)](https://plane.so/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white&style=flat-square)](./docker-compose.yml)
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

### Plane task management

**CRUD operations exposed as MCP tools.** Agents can call `list_tasks`, `get_task`, `create_task`, `update_task`, and `delete_task`, scoped to a Plane workspace and project.

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
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
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

All task tools require `workspace_slug` and `project_id` to scope the operation to the right Plane project.

---

## 🔧 Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLANE_MCP_TOKEN` | ✅ | — | Plane API token (sent as `X-API-Key`) |
| `PLANE_API_BASE` | ❌ | `http://umbrel:8762` | Base URL of your Plane instance |
| `HOST` | ❌ | `0.0.0.0` | Bind address |
| `PORT` | ❌ | `8763` | Listen port |
| `ALLOWED_ORIGINS` | ❌ | _(empty)_ | Comma-separated allowed `Origin` values |
| `REQUEST_TIMEOUT_SECONDS` | ❌ | `15` | Per-request timeout to Plane |
| `RATE_LIMIT_PER_MINUTE` | ❌ | `60` | Max MCP requests/min/IP |

---

## 🔒 Security

- The Plane API token is read from the environment and **never** accepted from MCP clients (no token passthrough).
- The server defaults to listening on all interfaces (`0.0.0.0`) inside the container; expose it externally only behind a TLS-terminating reverse proxy with authentication.
- All tool inputs are validated with Pydantic schemas and outputs are JSON-serialized before returning.

---

## 📄 License

MIT
