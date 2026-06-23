"""Pydantic models shared across the Plane MCP server."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# MCP protocol result envelopes
# ---------------------------------------------------------------------------


class MCPContent(BaseModel):
    type: str = "text"
    text: str


class MCPToolResult(BaseModel):
    content: List[MCPContent]
    isError: bool = False

    class Config:
        # Allows returning plain dicts from handlers when convenient.
        from_attributes = True


class MCPInitializeRequest(BaseModel):
    protocolVersion: str
    capabilities: Optional[dict] = None
    clientInfo: Optional[dict] = None


# ---------------------------------------------------------------------------
# Plane domain models
# ---------------------------------------------------------------------------

PRIORITY_VALUES = ["LOW", "MEDIUM", "HIGH", "URGENT"]
STATUS_VALUES = ["BACKLOG", "TODO", "IN_PROGRESS", "DONE", "CANCELLED"]


class PlaneTask(BaseModel):
    """Payload for creating a task in Plane."""

    name: str = Field(..., min_length=1, max_length=255, description="Task title")
    description_html: Optional[str] = Field(
        None, max_length=10000, description="Task description (HTML allowed by Plane)"
    )
    priority: Optional[str] = Field(
        "MEDIUM", description="Priority level", pattern="^(LOW|MEDIUM|HIGH|URGENT)$"
    )
    state: Optional[str] = Field(
        None, description="Workflow state name (e.g. Backlog, In Progress)"
    )
    target_date: Optional[datetime] = Field(
        None, description="Due date in ISO 8601 format"
    )


class PlaneTaskUpdate(BaseModel):
    """Payload for partially updating a task. All fields optional."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description_html: Optional[str] = Field(None, max_length=10000)
    priority: Optional[str] = Field(None, pattern="^(LOW|MEDIUM|HIGH|URGENT)$")
    state: Optional[str] = Field(None)
    target_date: Optional[datetime] = Field(None)


class PlaneTaskResponse(BaseModel):
    """Subset of a Plane work-item response we care about."""

    id: str
    name: str
    description_html: Optional[str] = None
    priority: Optional[str] = None
    state: Optional[str] = None
    target_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
