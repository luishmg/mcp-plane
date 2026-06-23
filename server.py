from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import os
import httpx
import json
import re
from datetime import datetime

app = FastAPI()

# Plane API Configuration
PLANE_API_BASE = "http://umbrel:8762"
PLANE_MCP_TOKEN = os.getenv("PLANE_MCP_TOKEN")

class MCPContent(BaseModel):
    type: str = "text"
    text: str

class MCPToolResult(BaseModel):
    content: List[MCPContent]
    isError: bool = False

class PlaneTask(BaseModel):
    title: str
    description: Optional[str] = None
    status: Optional[str] = "TODO"
    priority: Optional[str] = "MEDIUM"
    due_date: Optional[datetime] = None

class MCPInitializeRequest(BaseModel):
    protocolVersion: str
    authentication: Optional[Dict] = None

# Custom Auth Middleware (IP Allowlist)
ALLOWLISTED_IPS = {"127.0.0.1", "::1"}
def verify_request(request: Request):
    client_ip = request.client.host
    if client_ip not in ALLOWLISTED_IPS:
        raise HTTPException(status_code=403, detail="Forbidden - Invalid client IP")
    
    origin = request.headers.get("Origin")
    if not origin:
        raise HTTPException(status_code=403, detail="Missing Origin header")
    return True

@app.on_event("startup")
async def startup():
    if not PLANE_MCP_TOKEN:
        raise RuntimeError("PLANE_MCP_TOKEN environment variable not set")

# MCP Core Endpoints
@app.post("/mcp", dependencies=[Depends(verify_request)])
async def mcp_endpoint(request: Request):
    body = await request.json()
    method = body.get("method")
    
    if method == "initialize":
        return handle_initialize(body)
    elif method == "tools/call":
        return await handle_tool_call(body)
    elif method == "tools/list":
        return handle_tool_list()
    else:
        return {"error": {"code": -32601, "message": "Method not found"}}

# Handlers

def handle_initialize(body: dict):
    req = MCPInitializeRequest(**body["params"])
    return {
        "jsonrpc": "2.0",
        "id": body["id"],
        "result": {
            "protocolVersion": "2025-11-25",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "plane-mcp",
                "version": "1.0"
            }
        }
    }

def handle_tool_list():
    return {
        "jsonrpc": "2.0",
        "id": "tools_list",
        "result": TOOLS
    }

async def handle_tool_call(body: dict):
    tool_name = body["params"].get("name")
    tool_args = body["params"].get("arguments", {})
    
    if tool_name not in TOOL_HANDLERS:
        return {
            "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}
        }
    
    handler = TOOL_HANDLERS[tool_name]
    return await handler(tool_args)

# Plane API Client

async def plane_api_request(method: str, endpoint: str, **kwargs):
    headers = {
        "X-API-Key": PLANE_MCP_TOKEN,
        "Content-Type": "application/json"
    }
    url = f"{PLANE_API_BASE}{endpoint}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method,
                url,
                headers=headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "content": [{"type": "text", "text": f"Plane API error: {e.response.text}"}],
                "isError": True
            }

# Plane Tool Handlers

TOOLS = [...]  # Defined in tools.py
TOOL_HANDLERS = {
    "create_task": create_task_handler,
    "update_task": update_task_handler,
    "list_tasks": list_tasks_handler,
    "get_task": get_task_handler,
    "delete_task": delete_task_handler
}

async def create_task_handler(args: dict):
    # Input validation
    if "title" not in args:
        return MCPToolResult(
            content=[MCPContent(text="Missing required field: title")],
            isError=True
        )
    
    # Create task via Plane API
    response = await plane_api_request("POST", "/api/issues", json=args)
    
    if "isError" in response and response["isError"]:
        return MCPToolResult(
            content=[MCPContent(text=response["content"][0]["text"])],
            isError=True
        )
    
    return MCPToolResult(content=[MCPContent(text=f"Task created: {response['id']}")])

# Other handlers in separate tools.py file

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8763)