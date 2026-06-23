"""Plane API client implementation"""

import httpx
import os
from mcp_models import PlaneTask
from .config import PLANE_API_BASE, PLANE_MCP_TOKEN

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

# CRUD Operations

async def create_task(task: PlaneTask):
    return await plane_api_request("POST", "/api/issues", json=task.dict())

async def update_task(task_id: str, update_data: dict):
    return await plane_api_request("PUT", f"/api/issues/{task_id}", json=update_data)

async def get_task(task_id: str):
    return await plane_api_request("GET", f"/api/issues/{task_id}")

async def list_tasks(limit=50, status=None):
    params = {"limit": limit}
    if status:
        params["status"] = status
    return await plane_api_request("GET", "/api/issues", params=params)

async def delete_task(task_id: str):
    return await plane_api_request("DELETE", f"/api/issues/{task_id}")