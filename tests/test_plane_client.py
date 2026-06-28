"""Unit tests for the async Plane API client."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app import config, plane_client


# ---------------------------------------------------------------------------
# _request wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_returns_json(mocker: Any) -> None:
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"id": "1"}'
    mock_resp.json.return_value = {"id": "1"}

    client_mock = mocker.patch("app.plane_client.httpx.AsyncClient")
    client_mock.return_value.__aenter__.return_value.request.return_value = mock_resp

    result = await plane_client._request("GET", "/test/")
    assert result == {"id": "1"}


@pytest.mark.asyncio
async def test_request_returns_empty_dict_for_no_content(mocker: Any) -> None:
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 204
    mock_resp.content = b""

    client_mock = mocker.patch("app.plane_client.httpx.AsyncClient")
    client_mock.return_value.__aenter__.return_value.request.return_value = mock_resp

    result = await plane_client._request("DELETE", "/test/")
    assert result == {}


@pytest.mark.asyncio
async def test_request_raises_on_http_error(mocker: Any) -> None:
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 404
    mock_resp.content = b'{"detail": "not found"}'
    mock_resp.text = '{"detail": "not found"}'

    client_mock = mocker.patch("app.plane_client.httpx.AsyncClient")
    client_mock.return_value.__aenter__.return_value.request.return_value = mock_resp

    with pytest.raises(plane_client.PlaneAPIError, match="Plane API 404"):
        await plane_client._request("GET", "/missing/")


@pytest.mark.asyncio
async def test_request_raises_on_network_error(mocker: Any) -> None:
    client_mock = mocker.patch("app.plane_client.httpx.AsyncClient")
    client_mock.return_value.__aenter__.return_value.request.side_effect = (
        httpx.ConnectError("Connection refused")
    )

    with pytest.raises(plane_client.PlaneAPIError, match="Network error"):
        await plane_client._request("GET", "/test/")


@pytest.mark.asyncio
async def test_request_uses_api_base_and_headers(mocker: Any) -> None:
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{}'
    mock_resp.json.return_value = {}

    client_mock = mocker.patch("app.plane_client.httpx.AsyncClient")
    request_mock = client_mock.return_value.__aenter__.return_value.request
    request_mock.return_value = mock_resp

    await plane_client._request(
        "POST",
        "/workspaces/",
        params={"cursor": "abc"},
        json_body={"name": "ws"},
    )

    request_mock.assert_awaited_once()
    method, url = request_mock.call_args[0]
    assert method == "POST"
    assert url == f"{config.PLANE_API_BASE.rstrip('/')}/workspaces/"

    kwargs = request_mock.call_args[1]
    assert kwargs["params"] == {"cursor": "abc"}
    assert kwargs["json"] == {"name": "ws"}
    assert kwargs["headers"]["X-API-Key"] == config.PLANE_MCP_TOKEN
    assert kwargs["headers"]["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# Resource-specific helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_workspaces_uses_users_me_endpoint(mocker: Any) -> None:
    # Plane has no list-all-workspaces endpoint; we use users/me/workspaces.
    mock_request = mocker.patch("app.plane_client._request", return_value=[])
    await plane_client.list_workspaces(cursor="abc", per_page=50)
    mock_request.assert_awaited_once_with(
        "GET", "/api/v1/users/me/workspaces/", params={"per_page": 50, "cursor": "abc"}
    )


@pytest.mark.asyncio
async def test_get_workspace_filters_from_list(mocker: Any) -> None:
    mock_request = mocker.patch(
        "app.plane_client._request",
        return_value=[{"slug": "other", "name": "Other"}, {"slug": "acme", "name": "Acme"}],
    )
    result = await plane_client.get_workspace("acme")
    mock_request.assert_awaited_once_with(
        "GET", "/api/v1/users/me/workspaces/", params={"per_page": 20}
    )
    assert result == {"slug": "acme", "name": "Acme"}


@pytest.mark.asyncio
async def test_get_workspace_not_found_raises(mocker: Any) -> None:
    mocker.patch("app.plane_client._request", return_value=[{"slug": "other"}])
    with pytest.raises(plane_client.PlaneAPIError):
        await plane_client.get_workspace("acme")


@pytest.mark.asyncio
async def test_create_workspace_sends_payload(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={})
    payload = {"name": "Acme", "slug": "acme"}
    await plane_client.create_workspace(payload)
    mock_request.assert_awaited_once_with(
        "POST", "/api/v1/workspaces/", json_body=payload
    )


@pytest.mark.asyncio
async def test_update_workspace_sends_payload(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={})
    await plane_client.update_workspace("acme", {"name": "New"})
    mock_request.assert_awaited_once_with(
        "PATCH", "/api/v1/workspaces/acme/", json_body={"name": "New"}
    )


@pytest.mark.asyncio
async def test_list_projects_uses_workspace_slug(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={"results": []})
    await plane_client.list_projects("acme", cursor="abc", per_page=10)
    mock_request.assert_awaited_once_with(
        "GET",
        "/api/v1/workspaces/acme/projects/",
        params={"per_page": 10, "cursor": "abc"},
    )


@pytest.mark.asyncio
async def test_get_project_builds_endpoint(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={})
    await plane_client.get_project("acme", "p1")
    mock_request.assert_awaited_once_with(
        "GET", "/api/v1/workspaces/acme/projects/p1/"
    )


@pytest.mark.asyncio
async def test_create_project_sends_payload(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={})
    await plane_client.create_project("acme", {"name": "Proj"})
    mock_request.assert_awaited_once_with(
        "POST", "/api/v1/workspaces/acme/projects/", json_body={"name": "Proj"}
    )


@pytest.mark.asyncio
async def test_archive_and_unarchive_project(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={})
    await plane_client.archive_project("acme", "p1")
    assert mock_request.call_args_list[0].args == (
        "POST",
        "/api/v1/workspaces/acme/projects/p1/archive/",
    )

    await plane_client.unarchive_project("acme", "p1")
    assert mock_request.call_args_list[1].args == (
        "DELETE",
        "/api/v1/workspaces/acme/projects/p1/archive/",
    )


@pytest.mark.asyncio
async def test_list_workspace_members(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value=[])
    await plane_client.list_workspace_members("acme")
    mock_request.assert_awaited_once_with(
        "GET", "/api/v1/workspaces/acme/members/"
    )


@pytest.mark.asyncio
async def test_update_workspace_member(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={})
    await plane_client.update_workspace_member("acme", "m1", {"role": 20})
    mock_request.assert_awaited_once_with(
        "PATCH",
        "/api/v1/workspaces/acme/members/m1/",
        json_body={"role": 20},
    )


@pytest.mark.asyncio
async def test_workspace_invite_crud(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={})

    await plane_client.list_workspace_invites("acme")
    await plane_client.create_workspace_invite("acme", {"email": "u@e.com"})
    await plane_client.get_workspace_invite("acme", "i1")
    await plane_client.update_workspace_invite("acme", "i1", {"role": 15})

    calls = [c.args for c in mock_request.call_args_list]
    assert calls[0] == ("GET", "/api/v1/workspaces/acme/invitations/")
    assert calls[1] == (
        "POST",
        "/api/v1/workspaces/acme/invitations/",
    )
    assert calls[2] == ("GET", "/api/v1/workspaces/acme/invitations/i1/")
    assert calls[3] == ("PATCH", "/api/v1/workspaces/acme/invitations/i1/")

    kwargs = mock_request.call_args_list[1].kwargs
    assert kwargs["json_body"] == {"email": "u@e.com"}


@pytest.mark.asyncio
async def test_project_members_crud(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={})

    await plane_client.list_project_members("acme", "p1")
    await plane_client.create_project_member("acme", "p1", {"member": "u1"})
    await plane_client.get_project_member("acme", "p1", "m1")
    await plane_client.update_project_member("acme", "p1", "m1", {"role": 5})

    calls = [c.args for c in mock_request.call_args_list]
    assert calls[0] == (
        "GET",
        "/api/v1/workspaces/acme/projects/p1/members/",
    )
    assert calls[1] == (
        "POST",
        "/api/v1/workspaces/acme/projects/p1/members/",
    )
    assert calls[2] == (
        "GET",
        "/api/v1/workspaces/acme/projects/p1/members/m1/",
    )
    assert calls[3] == (
        "PATCH",
        "/api/v1/workspaces/acme/projects/p1/members/m1/",
    )


@pytest.mark.asyncio
async def test_list_states_extracts_results(mocker: Any) -> None:
    mock_request = mocker.patch(
        "app.plane_client._request",
        return_value={"results": [{"id": "s1", "name": "Backlog"}]},
    )
    states = await plane_client.list_states("acme", "p1")
    assert states == [{"id": "s1", "name": "Backlog"}]
    mock_request.assert_awaited_once_with(
        "GET",
        "/api/v1/workspaces/acme/projects/p1/states/",
        params={"per_page": 100},
    )


@pytest.mark.asyncio
async def test_task_crud(mocker: Any) -> None:
    mock_request = mocker.patch("app.plane_client._request", return_value={"id": "t1"})

    await plane_client.list_tasks("acme", "p1", cursor="c1", per_page=10)
    await plane_client.get_task("acme", "p1", "t1")
    await plane_client.create_task("acme", "p1", {"name": "Task"})
    await plane_client.update_task("acme", "p1", "t1", {"name": "Updated"})

    calls = [c.args for c in mock_request.call_args_list]
    assert calls[0] == (
        "GET",
        "/api/v1/workspaces/acme/projects/p1/work-items/",
    )
    assert calls[1] == (
        "GET",
        "/api/v1/workspaces/acme/projects/p1/work-items/t1/",
    )
    assert calls[2] == (
        "POST",
        "/api/v1/workspaces/acme/projects/p1/work-items/",
    )
    assert calls[3] == (
        "PATCH",
        "/api/v1/workspaces/acme/projects/p1/work-items/t1/",
    )

    list_kwargs = mock_request.call_args_list[0].kwargs
    assert list_kwargs["params"] == {"per_page": 10, "cursor": "c1"}
