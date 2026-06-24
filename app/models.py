"""Pydantic models shared across the Plane MCP server."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


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
# Shared enums and constants
# ---------------------------------------------------------------------------

PRIORITY_VALUES = ["LOW", "MEDIUM", "HIGH", "URGENT"]
STATUS_VALUES = ["BACKLOG", "TODO", "IN_PROGRESS", "DONE", "CANCELLED"]

ROLE_VALUES = [5, 15, 20]
ROLE_GUEST = 5
ROLE_MEMBER = 15
ROLE_ADMIN = 20

_WORKSPACE_SLUG_PATTERN = r"^[a-zA-Z0-9_-]+$"
_PROJECT_IDENTIFIER_PATTERN = r"^[A-Za-z0-9_-]+$"


# ---------------------------------------------------------------------------
# Plane task models (existing)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Workspace models
# ---------------------------------------------------------------------------


class PlaneWorkspaceCreate(BaseModel):
    """Payload for creating a Plane workspace."""

    name: str = Field(
        ..., min_length=1, max_length=80, description="Display name of the workspace"
    )
    slug: str = Field(
        ...,
        min_length=1,
        max_length=48,
        description="URL-safe identifier (letters, numbers, hyphens, underscores)",
    )
    organization_size: Optional[str] = Field(
        None, description="Organization size label, e.g. '1-10'"
    )
    timezone: Optional[str] = Field("UTC", description="Timezone for the workspace")

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, value: str) -> str:
        import re

        if not re.match(_WORKSPACE_SLUG_PATTERN, value):
            raise ValueError(
                "slug may only contain letters, numbers, hyphens, and underscores"
            )
        return value


class PlaneWorkspaceUpdate(BaseModel):
    """Payload for partially updating a Plane workspace."""

    name: Optional[str] = Field(None, min_length=1, max_length=80)
    slug: Optional[str] = Field(None, min_length=1, max_length=48)
    organization_size: Optional[str] = None
    timezone: Optional[str] = None


# ---------------------------------------------------------------------------
# Project models
# ---------------------------------------------------------------------------


class PlaneProjectCreate(BaseModel):
    """Payload for creating a Plane project."""

    name: str = Field(..., min_length=1, description="Project name")
    identifier: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Short uppercase identifier, e.g. 'PROJ'. Plane upper-cases it server-side.",
    )
    description: Optional[str] = Field(None, description="Project description text")
    project_lead: Optional[str] = Field(
        None, description="User ID of the project lead (must be a workspace member)"
    )
    default_assignee: Optional[str] = Field(
        None, description="User ID of the default assignee"
    )

    @field_validator("identifier")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        import re

        if not re.match(_PROJECT_IDENTIFIER_PATTERN, value):
            raise ValueError(
                "identifier may only contain letters, numbers, hyphens, and underscores"
            )
        return value


class PlaneProjectUpdate(BaseModel):
    """Payload for partially updating a Plane project."""

    name: Optional[str] = Field(None, min_length=1)
    identifier: Optional[str] = Field(None, min_length=1, max_length=20)
    description: Optional[str] = None
    project_lead: Optional[str] = None
    default_assignee: Optional[str] = None


# ---------------------------------------------------------------------------
# Workspace member & invite models
# ---------------------------------------------------------------------------


class PlaneWorkspaceMemberUpdate(BaseModel):
    """Payload for updating a workspace member's role."""

    role: int = Field(
        ..., ge=5, le=20, description="Role: 5=Guest, 15=Member, 20=Admin"
    )


class PlaneWorkspaceInviteCreate(BaseModel):
    """Payload for inviting a user to a workspace."""

    email: str = Field(..., description="Email address to invite")
    role: int = Field(
        ROLE_MEMBER,
        ge=5,
        le=20,
        description="Role: 5=Guest, 15=Member, 20=Admin",
    )

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        import re

        if not re.match(_EMAIL_PATTERN, value):
            raise ValueError("invalid email address")
        return value


class PlaneWorkspaceInviteUpdate(BaseModel):
    """Payload for updating a pending workspace invite."""

    role: int = Field(
        ..., ge=5, le=20, description="Role: 5=Guest, 15=Member, 20=Admin"
    )


# ---------------------------------------------------------------------------
# Project member models
# ---------------------------------------------------------------------------


class PlaneProjectMemberCreate(BaseModel):
    """Payload for adding a member to a project."""

    member: str = Field(
        ..., description="User ID of the workspace member to add to the project"
    )
    role: int = Field(
        ROLE_MEMBER,
        ge=5,
        le=20,
        description="Role: 5=Guest, 15=Member, 20=Admin",
    )


class PlaneProjectMemberUpdate(BaseModel):
    """Payload for updating a project member's role."""

    role: int = Field(
        ..., ge=5, le=20, description="Role: 5=Guest, 15=Member, 20=Admin"
    )
