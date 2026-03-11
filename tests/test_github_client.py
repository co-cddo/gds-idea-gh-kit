"""Tests for GitHubClient.verify_connection()."""


import httpx
import pytest
from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.github_client import AuthError, GitHubClient, GitHubClientError


def test_verify_connection_success(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/user",
        json={"login": "test-user"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo",
        json={"login": "co-cddo"},
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    client.verify_connection()  # should not raise


def test_verify_connection_expired_token(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/user",
        status_code=401,
        json={"message": "Bad credentials"},
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    with pytest.raises(AuthError, match="invalid or expired"):
        client.verify_connection()


def test_verify_connection_network_error(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ConnectError("Connection refused"),
        url="https://api.github.com/user",
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    with pytest.raises(GitHubClientError, match="Cannot reach api.github.com"):
        client.verify_connection()


def test_verify_connection_timeout(httpx_mock: HTTPXMock):
    httpx_mock.add_exception(
        httpx.ReadTimeout("Read timed out"),
        url="https://api.github.com/user",
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    with pytest.raises(GitHubClientError, match="Cannot reach api.github.com"):
        client.verify_connection()


def test_verify_connection_org_not_accessible(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/user",
        json={"login": "test-user"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo",
        status_code=404,
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    with pytest.raises(GitHubClientError, match="Cannot access org"):
        client.verify_connection()


def test_verify_connection_org_forbidden(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://api.github.com/user",
        json={"login": "test-user"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo",
        status_code=403,
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    with pytest.raises(GitHubClientError, match="Cannot access org"):
        client.verify_connection()


def test_verify_connection_no_org(httpx_mock: HTTPXMock):
    """When no org is configured, skip the org check."""
    httpx_mock.add_response(
        url="https://api.github.com/user",
        json={"login": "test-user"},
    )

    client = GitHubClient(token="fake-token", org=None)
    client.verify_connection()  # should not raise
    # Only one request should have been made (no /orgs/ call)


def test_verify_connection_ttl_cache(httpx_mock: HTTPXMock):
    """Second call within TTL should not make API requests."""
    httpx_mock.add_response(
        url="https://api.github.com/user",
        json={"login": "test-user"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo",
        json={"login": "co-cddo"},
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    client.verify_connection()
    client.verify_connection()  # should use cache, no extra requests

    # pytest-httpx would raise if more requests were made than registered


# --- rename_default_branch ---


BASE = "https://api.github.com"


def test_rename_default_branch_renames(httpx_mock: HTTPXMock):
    """When target branch doesn't exist, rename succeeds normally."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        json={"default_branch": "main"},
    )
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/branches/main/rename",
        method="POST",
        json={"name": "dev"},
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    result = client.rename_default_branch("co-cddo", "my-repo", "dev")
    assert result["name"] == "dev"


# --- compare_branches ---


def test_compare_branches(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/compare/dev...main",
        json={"ahead_by": 3, "behind_by": 0, "status": "ahead"},
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    result = client.compare_branches("co-cddo", "my-repo", "dev", "main")
    assert result["ahead_by"] == 3


# --- delete_branch ---


def test_delete_branch(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/git/refs/heads/main",
        method="DELETE",
        status_code=204,
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    client.delete_branch("co-cddo", "my-repo", "main")  # should not raise


def test_rename_default_branch_noop_when_already_correct(httpx_mock: HTTPXMock):
    """When default branch is already correct, no rename needed."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="GET",
        json={"default_branch": "dev"},
    )

    client = GitHubClient(token="fake-token", org="co-cddo")
    result = client.rename_default_branch("co-cddo", "my-repo", "dev")
    assert result["default_branch"] == "dev"
