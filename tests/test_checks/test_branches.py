"""Tests for the branches check."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.checks import branches
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import BranchProtectionConfig, CheckStatus, RepoTypeConfig


def _make_protection_response(
    approvals=1,
    dismiss_stale=True,
    enforce_admins=False,
    contexts=None,
    linear_history=True,
    review_teams=None,
):
    """Build a realistic branch protection API response."""
    resp = {
        "required_pull_request_reviews": {
            "required_approving_review_count": approvals,
            "dismiss_stale_reviews": dismiss_stale,
            "dismissal_restrictions": {
                "teams": [{"slug": t} for t in (review_teams or [])],
                "users": [],
            },
        },
        "enforce_admins": {"enabled": enforce_admins},
        "required_status_checks": {"contexts": contexts or []},
        "required_linear_history": {"enabled": linear_history},
    }
    return resp


def test_default_branch_correct(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}", default_branch="dev"
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)

    default_result = [r for r in results if r.name == "branches.default"][0]
    assert default_result.status == CheckStatus.PASSED


def test_default_branch_wrong(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "main"},
    )
    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}", default_branch="dev"
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)

    default_result = [r for r in results if r.name == "branches.default"][0]
    assert default_result.status == CheckStatus.FAILED
    assert default_result.fix_available is True


def test_branch_protection_all_pass(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/dev/protection",
        json=_make_protection_response(
            approvals=1,
            contexts=["lint", "test"],
            review_teams=["cddo-idea-developers"],
        ),
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "dev": BranchProtectionConfig(
                required_approvals=1,
                require_status_checks=["lint", "test"],
                require_linear_history=True,
                required_review_teams=["cddo-idea-developers"],
            )
        },
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(failed) == 0


def test_branch_protection_missing(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "dev": BranchProtectionConfig()
        },
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    bp_results = [r for r in results if "protection" in r.name]
    assert len(bp_results) == 1
    assert bp_results[0].status == CheckStatus.FAILED
    assert bp_results[0].fix_available is True


def test_review_teams_missing(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/dev/protection",
        json=_make_protection_response(
            approvals=1,
            review_teams=[],  # no teams set
        ),
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "dev": BranchProtectionConfig(
                required_review_teams=["cddo-idea-developers"],
            )
        },
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    team_results = [r for r in results if "review_teams" in r.name]
    assert len(team_results) == 1
    assert team_results[0].status == CheckStatus.FAILED
    assert "cddo-idea-developers" in team_results[0].message


def test_prod_branch_enforce_admins(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/prod/protection",
        json=_make_protection_response(
            approvals=1,
            enforce_admins=False,  # should be True for prod
            review_teams=["cddo-idea-admins"],
        ),
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "prod": BranchProtectionConfig(
                required_approvals=1,
                enforce_admins=True,
                required_review_teams=["cddo-idea-admins"],
            )
        },
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    admin_results = [r for r in results if "enforce_admins" in r.name]
    assert len(admin_results) == 1
    assert admin_results[0].status == CheckStatus.FAILED
