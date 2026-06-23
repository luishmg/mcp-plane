"""Declarative MCP tool definitions for Plane API integration"""

from mcp_models import PlaneTask

def _text_result(msg: str, error: bool = False) -> dict:
    return {
        "content": [{"type": "text", "text": msg}],
        "isError": error
    }

TOOLS = [
    {
        "name": "create_task",
        "description": "Create a new task in Plane",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "description": {"type": "string", "description": "Task description"},
                "status": {"type": "string", "description": "Task status", "default": "TODO"},
                "priority": {"type": "string", "description": "Priority level", "enum": ["LOW", "MEDIUM", "HIGH"]},
                "due_date": {"type": "string", "format": "date-time", "description": "Due date in ISO format"},
            },
            "required": ["title"]
        }
    },
    {
        "name": "list_tasks",
        "description": "List all tasks in Plane",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max tasks to return", "default": 50},
                "status": {"type": "string", "description": "Filter by status"}
            }
        }
    },
    {
        "name": "get_task",
        "description": "Get task details by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Task ID"}
            },
            "required": ["id"]
        }
    },
    {
        "name": "update_task",
        "description": "Update a task",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Task ID"},
                "title": {"type": "string", "description": "New title"},
                "description": {"type": "string", "description": "New description"},
                "status": {"type": "string", "description": "New status"},
                "priority": {"type": "string", "description": "New priority"},
                "due_date": {"type": "string", "format": "date-time", "description": "New due date"},
            },
            "required": ["id"]
        }
    },
    {
        "name": "delete_task",
        "description": "Delete a task by ID",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Task ID"}
            },
            "required": ["id"]
        }
    }
]

# Connect to handlers
from server import MCPToolResult
from plane_client import *

async def create_task_handler(args: dict):
    try:
        task = PlaneTask(**args)
    except ValueError as e:
        return MCPToolResult(
            content=[MCPContent(text=f"Validation error: {str(e)}")],
            isError=True
        )
        
    response = await create_task(task)
    if "isError" in response:
        return response
    return MCPToolResult(content=[MCPContent(text=f"Created task {response['id']}")])

# Implement other handlers using similar pattern