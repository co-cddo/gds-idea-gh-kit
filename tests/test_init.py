"""Tests for the init command."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.init import InitError, init_repo, _check_preconditions, get_repo_name_from_directory
from gds_idea_gh_kit.models import (
    BranchProtectionConfig,
    Config,
    RepoSettings,
    RepoTypeConfig,
    SecurityConfig,
)

BASE = "https://api.github.com"


def _test_config() -> Config:
    return Config(
        org="co-cddo",
        repo_prefixes=["gds-idea-"],
        teams={
            "gds-idea-all": "read",
            "gds-idea-ds": "maintain",
            "gds-idea-senior-ds": "admin",
            "gds-idea-super-admin": "admin",
        },
        repo_settings=RepoSettings(),
        required_files=[".gitignore"],
        security=SecurityConfig(),
        repo_types={
            "cdk-app": RepoTypeConfig(
                naming_pattern="gds-idea-app-{name}",
                detection_files=["cdk.json"],
                default_branch="dev",
                required_workflows=["lint.yml"],
                branch_protection={
                    "dev": BranchProtectionConfig(
                        prevent_deletion=True,
                        prevent_force_push=True,
                        require_linear_history=True,
                        bypass_teams=["gds-idea-super-admin"],
                        bypass_mode="pull_request",
                    ),
                    "prod": BranchProtectionConfig(
                        prevent_deletion=True,
                        prevent_force_push=True,
                        bypass_teams=[],
                        bypass_mode="pull_request",
                    ),
                },
            ),
        },
    )


def _mock_git_success(cmd_results: dict[tuple[str, ...], str] | None = None):
    """Return a mock for _run_git that returns preset values."""
    defaults: dict[tuple[str, ...], str] = {
        ("rev-parse", "--is-inside-work-tree"): "true",
        ("rev-parse", "HEAD"): "abc123",
        ("remote", "get-url", "origin"): "",  # Will raise CalledProcessError
        ("remote", "add", "origin"): "",
        ("push", "-u", "origin", "HEAD:main"): "",
        ("branch", "-m", "main", "dev"): "",
        ("fetch", "origin"): "",
        ("branch", "--set-upstream-to", "origin/dev"): "",
    }
    if cmd_results:
        defaults.update(cmd_results)

    def fake_run_git(*args: str) -> str:
        key = tuple(args)
        # Simulate "no remote" by raising for remote get-url
        if key == ("remote", "get-url", "origin"):
            raise InitError("git remote get-url origin failed: ")
        if key in defaults:
            return defaults[key]
        # Allow any git command not in defaults to succeed
        return ""

    return fake_run_git


def _mock_all_api_calls(httpx_mock: HTTPXMock):
    """Mock all GitHub API calls for a successful init."""
    # 1. Create repo
    httpx_mock.add_response(
        url=f"{BASE}/orgs/co-cddo/repos",
        method="POST",
        json={"name": "gds-idea-app-dashboard", "full_name": "co-cddo/gds-idea-app-dashboard"},
        status_code=201,
    )

    # 2. Update repo settings
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard",
        method="PATCH",
        json={"name": "gds-idea-app-dashboard"},
    )

    # 3. Rename default branch (get_repo + rename)
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard",
        method="GET",
        json={"name": "gds-idea-app-dashboard", "default_branch": "main"},
    )
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard/branches/main/rename",
        method="POST",
        json={"name": "dev"},
    )

    # 4. Create prod branch (get ref + create ref)
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard/git/ref/heads/dev",
        method="GET",
        json={"object": {"sha": "abc123def456"}},
    )
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard/git/refs",
        method="POST",
        json={"ref": "refs/heads/prod"},
        status_code=201,
    )

    # 5. Attach teams (4 teams)
    for team in ["gds-idea-all", "gds-idea-ds", "gds-idea-senior-ds", "gds-idea-super-admin"]:
        httpx_mock.add_response(
            url=f"{BASE}/orgs/co-cddo/teams/{team}/repos/co-cddo/gds-idea-app-dashboard",
            method="PUT",
            status_code=204,
        )

    # 6. Create rulesets (dev + prod) — need team ID lookups for bypass
    httpx_mock.add_response(
        url=f"{BASE}/orgs/co-cddo/teams/gds-idea-super-admin",
        method="GET",
        json={"id": 999, "slug": "gds-idea-super-admin"},
    )
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard/rulesets",
        method="POST",
        json={"id": 1, "name": "idea-gh: dev"},
        status_code=201,
    )
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard/rulesets",
        method="POST",
        json={"id": 2, "name": "idea-gh: prod"},
        status_code=201,
    )

    # 7. Security
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard/vulnerability-alerts",
        method="PUT",
        status_code=204,
    )
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/gds-idea-app-dashboard/automated-security-fixes",
        method="PUT",
        status_code=204,
    )


@patch("gds_idea_gh_kit.init._run_git")
def test_init_repo_full_flow(mock_git, httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Full successful init creates repo and configures everything."""
    mock_git.side_effect = _mock_git_success()
    _mock_all_api_calls(httpx_mock)

    config = _test_config()
    steps = init_repo("gds-idea-app-dashboard", config, "cdk-app", gh_client)

    assert any("Created repo" in s for s in steps)
    assert any("Added remote" in s for s in steps)
    assert any("Pushed" in s for s in steps)
    assert any("repo settings" in s for s in steps)
    assert any("main -> dev" in s for s in steps)
    assert any("prod" in s and "branch" in s for s in steps)
    assert any("gds-idea-all" in s for s in steps)
    assert any("gds-idea-ds" in s for s in steps)
    assert any("gds-idea-senior-ds" in s for s in steps)
    assert any("gds-idea-super-admin" in s for s in steps)
    assert any("ruleset" in s and "dev" in s for s in steps)
    assert any("ruleset" in s and "prod" in s for s in steps)
    assert any("vulnerability" in s for s in steps)
    assert any("automated security" in s for s in steps)


@patch("gds_idea_gh_kit.init._run_git")
def test_init_repo_rejects_bad_name(mock_git, httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Init errors if directory name doesn't match naming pattern."""
    mock_git.side_effect = _mock_git_success()

    config = _test_config()
    with pytest.raises(InitError, match="does not match"):
        init_repo("bad-repo-name", config, "cdk-app", gh_client)


@patch("gds_idea_gh_kit.init._run_git")
def test_init_repo_rejects_existing_remote(mock_git, httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Init errors if the repo already has a remote."""
    def fake_git(*args):
        key = tuple(args)
        if key == ("rev-parse", "--is-inside-work-tree"):
            return "true"
        if key == ("rev-parse", "HEAD"):
            return "abc123"
        if key == ("remote", "get-url", "origin"):
            return "git@github.com:co-cddo/gds-idea-app-dashboard.git"
        return ""

    mock_git.side_effect = fake_git

    config = _test_config()
    with pytest.raises(InitError, match="already has a remote"):
        init_repo("gds-idea-app-dashboard", config, "cdk-app", gh_client)


@patch("gds_idea_gh_kit.init._run_git")
def test_init_repo_rejects_no_git_repo(mock_git, httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Init errors if not inside a git repo."""
    def fake_git(*args):
        raise InitError("git rev-parse failed: not a git repository")

    mock_git.side_effect = fake_git

    config = _test_config()
    with pytest.raises(InitError, match="Not inside a git repo"):
        init_repo("gds-idea-app-dashboard", config, "cdk-app", gh_client)


@patch("gds_idea_gh_kit.init._run_git")
def test_init_repo_rejects_no_commits(mock_git, httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Init errors if the repo has no commits."""
    def fake_git(*args):
        key = tuple(args)
        if key == ("rev-parse", "--is-inside-work-tree"):
            return "true"
        raise InitError("git rev-parse HEAD failed: ")

    mock_git.side_effect = fake_git

    config = _test_config()
    with pytest.raises(InitError, match="no commits"):
        init_repo("gds-idea-app-dashboard", config, "cdk-app", gh_client)


@patch("gds_idea_gh_kit.init._run_git")
def test_init_repo_handles_create_failure(mock_git, httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Init wraps GitHub API errors in InitError."""
    mock_git.side_effect = _mock_git_success()

    # Repo already exists on GitHub
    httpx_mock.add_response(
        url=f"{BASE}/orgs/co-cddo/repos",
        method="POST",
        status_code=422,
        json={"message": "Validation Failed", "errors": [{"message": "name already exists"}]},
    )

    config = _test_config()
    with pytest.raises(InitError, match="Failed to create repo"):
        init_repo("gds-idea-app-dashboard", config, "cdk-app", gh_client)


def test_get_repo_name_from_directory(tmp_path):
    """get_repo_name_from_directory returns the directory name."""
    with patch("gds_idea_gh_kit.init.Path") as mock_path:
        mock_path.cwd.return_value = tmp_path / "gds-idea-app-my-thing"
        name = get_repo_name_from_directory()
        assert name == "gds-idea-app-my-thing"
