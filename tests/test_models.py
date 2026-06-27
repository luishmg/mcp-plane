"""Unit tests for Pydantic models used by the Plane MCP server."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.models import (
    PlaneProjectCreate,
    PlaneProjectMemberCreate,
    PlaneProjectMemberUpdate,
    PlaneProjectUpdate,
    PlaneTask,
    PlaneTaskUpdate,
    PlaneWorkspaceCreate,
    PlaneWorkspaceInviteCreate,
    PlaneWorkspaceInviteUpdate,
    PlaneWorkspaceMemberUpdate,
    PlaneWorkspaceUpdate,
)


# ---------------------------------------------------------------------------
# PlaneTask
# ---------------------------------------------------------------------------


def test_task_defaults_priority_to_lowercase_medium() -> None:
    task = PlaneTask(name="Fix bug")
    assert task.priority == "medium"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("MEDIUM", "medium"),
        ("medium", "medium"),
        ("Medium", "medium"),
        ("HIGH", "high"),
        ("low", "low"),
        ("urgent", "urgent"),
        ("none", "none"),
    ],
)
def test_task_normalizes_priority(raw: str, expected: str) -> None:
    task = PlaneTask(name="Task", priority=raw)
    assert task.priority == expected


def test_task_rejects_invalid_priority() -> None:
    with pytest.raises(ValidationError):
        PlaneTask(name="Task", priority="CRITICAL")


def test_task_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        PlaneTask(name="")


def test_task_accepts_target_date() -> None:
    task = PlaneTask(name="Task", target_date="2025-12-31")
    assert task.target_date == date(2025, 12, 31)


def test_task_rejects_invalid_date() -> None:
    with pytest.raises(ValidationError):
        PlaneTask(name="Task", target_date="not-a-date")


def test_task_update_normalizes_priority() -> None:
    update = PlaneTaskUpdate(priority="LOW")
    assert update.priority == "low"


# ---------------------------------------------------------------------------
# PlaneWorkspace
# ---------------------------------------------------------------------------


def test_workspace_create_validates_slug() -> None:
    ws = PlaneWorkspaceCreate(name="My Workspace", slug="my_workspace-1")
    assert ws.slug == "my_workspace-1"


@pytest.mark.parametrize("bad_slug", ["", "my workspace", "foo@bar", "foo.bar"])
def test_workspace_create_rejects_invalid_slug(bad_slug: str) -> None:
    with pytest.raises(ValidationError):
        PlaneWorkspaceCreate(name="Name", slug=bad_slug)


def test_workspace_create_accepts_optional_fields() -> None:
    ws = PlaneWorkspaceCreate(
        name="Name",
        slug="slug",
        organization_size="1-10",
        timezone="America/Sao_Paulo",
    )
    assert ws.timezone == "America/Sao_Paulo"


def test_workspace_update_requires_no_fields() -> None:
    update = PlaneWorkspaceUpdate()
    assert update.name is None
    assert update.slug is None


def test_workspace_update_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        PlaneWorkspaceUpdate(name="")


# ---------------------------------------------------------------------------
# PlaneProject
# ---------------------------------------------------------------------------


def test_project_create_validates_identifier() -> None:
    project = PlaneProjectCreate(name="Project", identifier="PROJ_1")
    assert project.identifier == "PROJ_1"


@pytest.mark.parametrize("bad_identifier", ["", "PROJ 1", "PROJ.1"])
def test_project_create_rejects_invalid_identifier(bad_identifier: str) -> None:
    with pytest.raises(ValidationError):
        PlaneProjectCreate(name="Project", identifier=bad_identifier)


def test_project_update_accepts_partial_fields() -> None:
    update = PlaneProjectUpdate(description="New description")
    assert update.description == "New description"


# ---------------------------------------------------------------------------
# Members / invites
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", [5, 15, 20])
def test_workspace_member_update_accepts_valid_roles(role: int) -> None:
    update = PlaneWorkspaceMemberUpdate(role=role)
    assert update.role == role


@pytest.mark.parametrize("bad_role", [4, 21])
def test_workspace_member_update_rejects_out_of_range_roles(bad_role: int) -> None:
    with pytest.raises(ValidationError):
        PlaneWorkspaceMemberUpdate(role=bad_role)


def test_workspace_member_update_accepts_values_between_bounds() -> None:
    # Models validate the role range (5-20); the manifest narrows it to 5/15/20.
    update = PlaneWorkspaceMemberUpdate(role=10)
    assert update.role == 10


def test_workspace_invite_create_validates_email() -> None:
    invite = PlaneWorkspaceInviteCreate(email="user@example.com", role=15)
    assert invite.email == "user@example.com"
    assert invite.role == 15


@pytest.mark.parametrize(
    "bad_email",
    [
        "not-an-email",
        "missing@domain",
        "@example.com",
        "user@.com",
    ],
)
def test_workspace_invite_create_rejects_invalid_email(bad_email: str) -> None:
    with pytest.raises(ValidationError):
        PlaneWorkspaceInviteCreate(email=bad_email, role=15)


def test_workspace_invite_create_defaults_role_to_member() -> None:
    invite = PlaneWorkspaceInviteCreate(email="user@example.com")
    assert invite.role == 15


def test_workspace_invite_update_requires_role() -> None:
    update = PlaneWorkspaceInviteUpdate(role=20)
    assert update.role == 20


def test_project_member_create_requires_member() -> None:
    member = PlaneProjectMemberCreate(member="user-id-123")
    assert member.member == "user-id-123"
    assert member.role == 15


def test_project_member_update_role() -> None:
    update = PlaneProjectMemberUpdate(role=5)
    assert update.role == 5


@pytest.mark.parametrize("bad_role", [0, 25, 100])
def test_invite_and_member_roles_reject_invalid_values(bad_role: int) -> None:
    with pytest.raises(ValidationError):
        PlaneWorkspaceInviteCreate(email="user@example.com", role=bad_role)
    with pytest.raises(ValidationError):
        PlaneProjectMemberCreate(member="user", role=bad_role)
