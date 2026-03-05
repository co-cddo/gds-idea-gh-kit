"""Tests for the teams check."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.checks import teams
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckStatus


def test_teams_all_correct(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "admin"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-devs/repos/co-cddo/my-repo",
        json={"role_name": "write"},
    )

    expected = {"cddo-admins": "admin", "cddo-devs": "write"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    assert len(results) == 2
    assert all(r.status == CheckStatus.PASSED for r in results)


def test_team_wrong_permission(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "write"},  # should be admin
    )

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    assert len(results) == 1
    assert results[0].status == CheckStatus.FAILED
    assert results[0].fix_available is True
    assert "write" in results[0].message
    assert "admin" in results[0].message


def test_team_no_access(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        status_code=404,
    )

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    assert len(results) == 1
    assert results[0].status == CheckStatus.FAILED
    assert "no access" in results[0].message
