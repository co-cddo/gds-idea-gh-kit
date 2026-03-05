"""Tests for GitHubClient.verify_connection()."""

import time

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
