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


def test_direct_collaborators_grouped(httpx_mock: HTTPXMock, gh_client: GitHubClient):
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
    # list_team_members for each configured team
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/members",
        json=[{"login": "bob-smith"}],
    )

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    warnings = [r for r in results if "direct_collaborator" in r.name]
    assert len(warnings) == 1  # grouped into one result
    msg = warnings[0].message
    assert "2 direct collaborator(s)" in msg
    assert "jane-doe" in msg
    assert "bob-smith" in msg
    assert "through teams instead" in msg
    assert "idea-gh remove-collaborators --all" in msg
    assert "idea-gh remove-collaborators <username>" in msg
    # bob-smith is in cddo-admins
    assert "bob-smith (admin) — member of: cddo-admins" in msg
    # jane-doe is not in any configured team
    assert "jane-doe (write) — not in any configured team" in msg


def test_direct_collaborators_shows_multiple_teams(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """A collaborator in multiple configured teams shows all of them."""
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
    httpx_mock.add_response(
        url=COLLABS_URL,
        json=[{"login": "alice", "role_name": "admin"}],
    )
    # alice is in both teams
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/members",
        json=[{"login": "alice"}],
    )
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-devs/members",
        json=[{"login": "alice"}],
    )

    expected = {"cddo-admins": "admin", "cddo-devs": "write"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    warnings = [r for r in results if "direct_collaborator" in r.name]
    assert len(warnings) == 1
    msg = warnings[0].message
    assert "alice (admin) — member of: cddo-admins, cddo-devs" in msg


def test_list_repo_teams_permission_denied(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Non-admin users get a SKIPPED result instead of a crash when listing teams fails."""
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "admin"},
    )
    # Repo teams endpoint returns 404 for non-admins
    httpx_mock.add_response(url=TEAMS_URL, status_code=404)
    _mock_no_direct_collabs(httpx_mock)

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    skipped = [r for r in results if r.status == CheckStatus.SKIPPED]
    assert len(skipped) == 1
    assert skipped[0].name == "teams.unexpected"
    assert "skipped" in skipped[0].message.lower()

    # Expected team check should still pass
    passed = [r for r in results if r.status == CheckStatus.PASSED]
    assert len(passed) == 1


def test_list_direct_collaborators_permission_denied(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Non-admin users get a SKIPPED result instead of a crash when listing collaborators fails."""
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "admin"},
    )
    httpx_mock.add_response(
        url=TEAMS_URL,
        json=[{"slug": "cddo-admins", "permission": "admin"}],
    )
    # Collaborators endpoint returns 404 for non-admins
    httpx_mock.add_response(url=COLLABS_URL, status_code=404)

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    skipped = [r for r in results if r.status == CheckStatus.SKIPPED]
    assert len(skipped) == 1
    assert skipped[0].name == "teams.direct_collaborators"
    assert "skipped" in skipped[0].message.lower()


def test_both_admin_checks_skipped_for_non_admin(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Both unexpected-teams and direct-collaborators skip gracefully for non-admins."""
    httpx_mock.add_response(
        url="https://api.github.com/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/my-repo",
        json={"role_name": "admin"},
    )
    # Both admin-only endpoints return 404
    httpx_mock.add_response(url=TEAMS_URL, status_code=404)
    httpx_mock.add_response(url=COLLABS_URL, status_code=404)

    expected = {"cddo-admins": "admin"}
    results = teams.audit("co-cddo", "my-repo", expected, gh_client)

    skipped = [r for r in results if r.status == CheckStatus.SKIPPED]
    assert len(skipped) == 2
    skipped_names = {r.name for r in skipped}
    assert skipped_names == {"teams.unexpected", "teams.direct_collaborators"}

    # Expected team check should still pass
    passed = [r for r in results if r.status == CheckStatus.PASSED]
    assert len(passed) == 1


# --- fix ---


def test_fix_maps_read_to_pull(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Fix should send 'pull' to the API when config says 'read'."""
    base = "https://api.github.com"

    # Team has no access
    httpx_mock.add_response(
        url=f"{base}/orgs/co-cddo/teams/cddo-readers/repos/co-cddo/my-repo",
        status_code=404,
    )
    # Expect PUT with 'pull' (not 'read')
    httpx_mock.add_response(
        url=f"{base}/orgs/co-cddo/teams/cddo-readers/repos/co-cddo/my-repo",
        method="PUT",
        status_code=204,
    )

    changes = teams.fix("co-cddo", "my-repo", {"cddo-readers": "read"}, gh_client)
    assert len(changes) == 1
    assert "cddo-readers" in changes[0]


def test_fix_maps_write_to_push(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Fix should send 'push' to the API when config says 'write'."""
    base = "https://api.github.com"

    # Team has no access
    httpx_mock.add_response(
        url=f"{base}/orgs/co-cddo/teams/cddo-devs/repos/co-cddo/my-repo",
        status_code=404,
    )
    # Expect PUT with 'push' (not 'write')
    httpx_mock.add_response(
        url=f"{base}/orgs/co-cddo/teams/cddo-devs/repos/co-cddo/my-repo",
        method="PUT",
        status_code=204,
    )

    changes = teams.fix("co-cddo", "my-repo", {"cddo-devs": "write"}, gh_client)
    assert len(changes) == 1
    assert "cddo-devs" in changes[0]


def test_fix_passes_maintain_unchanged(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Fix should send 'maintain' as-is (no mapping needed)."""
    base = "https://api.github.com"

    httpx_mock.add_response(
        url=f"{base}/orgs/co-cddo/teams/cddo-devs/repos/co-cddo/my-repo",
        status_code=404,
    )
    httpx_mock.add_response(
        url=f"{base}/orgs/co-cddo/teams/cddo-devs/repos/co-cddo/my-repo",
        method="PUT",
        status_code=204,
    )

    changes = teams.fix("co-cddo", "my-repo", {"cddo-devs": "maintain"}, gh_client)
    assert len(changes) == 1
