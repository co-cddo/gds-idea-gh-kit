"""Tests for the teams check."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.checks import teams
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckStatus

COLLABS_URL = "https://api.github.com/repos/co-cddo/my-repo/collaborators?affiliation=direct"
TEAMS_URL = "https://api.github.com/repos/co-cddo/my-repo/teams"


def _mock_no_direct_collabs(httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=COLLABS_URL, json=[])


def test_teams_all_correct(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "admin"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-devs/repos/co-cddo/my-repo",
        json={"role_name": "write"},
    )
    httpx_mock.add_response(
        url=TEAMS_URL,
        json=[
            {"slug": "cddo-admins", "permission": "admin"},
            {"slug": "cddo-devs", "permission": "push"},
        ],
    )
    _mock_no_direct_collabs(httpx_mock)

    expected = {"cddo-admins": "admin", "cddo-devs": "write"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    passed = [r for r in results if r.status == CheckStatus.PASSED]
    assert len(passed) == 2


def test_team_wrong_permission(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "write"},
    )
    httpx_mock.add_response(url=TEAMS_URL, json=[{"slug": "cddo-admins", "permission": "push"}])
    _mock_no_direct_collabs(httpx_mock)

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(failed) == 1
    assert failed[0].fix_available is True
    assert "write" in failed[0].message
    assert "admin" in failed[0].message


def test_team_no_access(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        status_code=404,
    )
    httpx_mock.add_response(url=TEAMS_URL, json=[])
    _mock_no_direct_collabs(httpx_mock)

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(failed) == 1
    assert "no access" in failed[0].message


def test_unexpected_team_warned(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "admin"},
    )
    httpx_mock.add_response(
        url=TEAMS_URL,
        json=[
            {"slug": "cddo-admins", "permission": "admin"},
            {"slug": "some-random-team", "permission": "push"},
        ],
    )
    _mock_no_direct_collabs(httpx_mock)

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    warnings = [r for r in results if r.status == CheckStatus.WARNING]
    assert len(warnings) == 1
    assert "some-random-team" in warnings[0].message
    assert "not in config" in warnings[0].message


def test_no_unexpected_teams(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "admin"},
    )
    httpx_mock.add_response(
        url=TEAMS_URL,
        json=[{"slug": "cddo-admins", "permission": "admin"}],
    )
    _mock_no_direct_collabs(httpx_mock)

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    warnings = [r for r in results if r.status == CheckStatus.WARNING]
    assert len(warnings) == 0


def test_direct_collaborator_warned(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "admin"},
    )
    httpx_mock.add_response(
        url=TEAMS_URL,
        json=[{"slug": "cddo-admins", "permission": "admin"}],
    )
    httpx_mock.add_response(
        url=COLLABS_URL,
        json=[
            {"login": "jane-doe", "role_name": "write"},
            {"login": "bob-smith", "role_name": "admin"},
        ],
    )

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    warnings = [r for r in results if "direct_collaborator" in r.name]
    assert len(warnings) == 2
    logins = {w.message.split("'")[1] for w in warnings}
    assert logins == {"jane-doe", "bob-smith"}
    assert all("through teams instead" in w.message for w in warnings)
    assert all("idea-gh remove-collaborators" in w.message for w in warnings)
