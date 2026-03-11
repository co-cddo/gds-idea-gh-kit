"""Tests for the branches check (rulesets-based)."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.checks import branches
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import BranchProtectionConfig, CheckStatus, RepoTypeConfig


def _make_ruleset_response(
    name="idea-gh: dev",
    ruleset_id=42,
    branch="dev",
    rules=None,
    bypass_actors=None,
):
    """Build a realistic ruleset API response."""
    return {
        "id": ruleset_id,
        "name": name,
        "target": "branch",
        "source_type": "Repository",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "include": [f"refs/heads/{branch}"],
                "exclude": [],
            }
        },
        "rules": rules or [],
        "bypass_actors": bypass_actors or [],
    }


def _full_rules(
    approvals=1,
    dismiss_stale=True,
):
    """Build a typical set of rules for a protected branch."""
    return [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "required_linear_history"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": approvals,
                "dismiss_stale_reviews_on_push": dismiss_stale,
            },
        },
    ]


# --- Default branch ---


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


# --- Classic protection warning ---


def test_classic_protection_warns(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    # Classic protection exists
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/dev/protection",
        json={"required_pull_request_reviews": {}},
    )
    # No rulesets
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets",
        json=[],
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={"dev": BranchProtectionConfig()},
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    classic_results = [r for r in results if "classic" in r.name]
    assert len(classic_results) == 1
    assert classic_results[0].status == CheckStatus.WARNING
    assert "migrated to rulesets" in classic_results[0].message


# --- Ruleset checks ---


def test_ruleset_all_pass(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    # No classic protection
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )
    # Ruleset list
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets",
        json=[{"id": 42, "name": "idea-gh: dev"}],
    )
    # Ruleset detail
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets/42",
        json=_make_ruleset_response(
            rules=_full_rules(approvals=1),
        ),
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "dev": BranchProtectionConfig(
                required_approvals=1,
                require_linear_history=True,
                prevent_deletion=True,
                prevent_force_push=True,
            )
        },
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(failed) == 0


def test_ruleset_missing(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets",
        json=[],
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={"dev": BranchProtectionConfig()},
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    ruleset_results = [r for r in results if "ruleset.dev" in r.name]
    assert len(ruleset_results) == 1
    assert ruleset_results[0].status == CheckStatus.FAILED
    assert ruleset_results[0].fix_available is True


def test_deletion_protection_missing(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets",
        json=[{"id": 42, "name": "idea-gh: dev"}],
    )
    # Ruleset exists but no deletion rule
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets/42",
        json=_make_ruleset_response(
            rules=[{"type": "non_fast_forward"}],
        ),
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "dev": BranchProtectionConfig(
                prevent_deletion=True,
                require_pr=False,
            )
        },
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    deletion_results = [r for r in results if "deletion" in r.name]
    assert len(deletion_results) == 1
    assert deletion_results[0].status == CheckStatus.FAILED


def test_bypass_teams_checked(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets",
        json=[{"id": 42, "name": "idea-gh: dev"}],
    )
    # Ruleset with no bypass actors
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets/42",
        json=_make_ruleset_response(
            rules=[{"type": "deletion"}, {"type": "non_fast_forward"}],
            bypass_actors=[],
        ),
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "dev": BranchProtectionConfig(
                require_pr=False,
                bypass_teams=["cddo-idea-superadmins"],
            )
        },
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    bypass_results = [r for r in results if "bypass" in r.name]
    assert len(bypass_results) == 1
    assert bypass_results[0].status == CheckStatus.FAILED


def test_prod_branch_stricter_rules(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Prod should have no bypass teams and require admin review."""
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo",
        json={"default_branch": "dev"},
    )
    # No classic on prod
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/branches/prod/protection",
        status_code=404,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets",
        json=[{"id": 99, "name": "idea-gh: prod"}],
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/rulesets/99",
        json=_make_ruleset_response(
            name="idea-gh: prod",
            ruleset_id=99,
            branch="prod",
            rules=_full_rules(approvals=1, dismiss_stale=True),
            bypass_actors=[],
        ),
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "prod": BranchProtectionConfig(
                required_approvals=1,
                require_linear_history=True,
                prevent_deletion=True,
                prevent_force_push=True,
                bypass_teams=[],
            )
        },
    )
    results = branches.audit("co-cddo", "my-repo", type_config, gh_client)
    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(failed) == 0


# --- Fix: stale branch detection ---

BASE = "https://api.github.com"


def _type_config_with_dev_default():
    return RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "dev": BranchProtectionConfig(
                prevent_deletion=True,
                prevent_force_push=True,
                require_pr=False,
            ),
        },
    )


def test_fix_rename_succeeds_no_stale_branch(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """When rename succeeds (main -> dev), no stale branch is reported."""
    # get_repo (called by fix)
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="GET",
        json={"default_branch": "main"},
    )
    # get_repo (called again by rename_default_branch)
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="GET",
        json={"default_branch": "main"},
    )
    # rename succeeds
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/branches/main/rename",
        method="POST",
        json={"name": "dev"},
    )
    # check if old branch exists — 404 means it was renamed away
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/git/ref/heads/main",
        method="GET",
        status_code=404,
    )
    # no classic protection
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )
    # no existing rulesets
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/rulesets",
        json=[],
    )
    # create ruleset
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/rulesets",
        method="POST",
        json={"id": 1, "name": "idea-gh: dev"},
        status_code=201,
    )

    type_config = _type_config_with_dev_default()
    changes, stale_branches = branches.fix("co-cddo", "my-repo", type_config, gh_client)

    assert any("main -> dev" in c for c in changes)
    assert len(stale_branches) == 0


def test_fix_fallback_reports_stale_merged_branch(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """When rename falls back to set-default, stale branch is reported with merge status."""
    # get_repo (called by fix)
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="GET",
        json={"default_branch": "main"},
    )
    # get_repo (called again by rename_default_branch)
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="GET",
        json={"default_branch": "main"},
    )
    # rename fails — dev already exists
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/branches/main/rename",
        method="POST",
        status_code=422,
        json={"message": "Validation Failed"},
    )
    # fallback to PATCH
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="PATCH",
        json={"default_branch": "dev"},
    )
    # old branch still exists
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/git/ref/heads/main",
        method="GET",
        json={"object": {"sha": "abc123"}},
    )
    # compare: main is fully merged into dev
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/compare/dev...main",
        json={"ahead_by": 0, "behind_by": 5},
    )
    # no classic protection
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )
    # no existing rulesets
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/rulesets",
        json=[],
    )
    # create ruleset
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/rulesets",
        method="POST",
        json={"id": 1, "name": "idea-gh: dev"},
        status_code=201,
    )

    type_config = _type_config_with_dev_default()
    changes, stale_branches = branches.fix("co-cddo", "my-repo", type_config, gh_client)

    assert any("main -> dev" in c for c in changes)
    assert len(stale_branches) == 1
    assert stale_branches[0].branch == "main"
    assert stale_branches[0].default_branch == "dev"
    assert stale_branches[0].is_merged is True


def test_fix_fallback_reports_stale_unmerged_branch(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """When main has unmerged commits, stale branch reports ahead_by count."""
    # get_repo (called by fix)
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="GET",
        json={"default_branch": "main"},
    )
    # get_repo (called again by rename_default_branch)
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="GET",
        json={"default_branch": "main"},
    )
    # rename fails
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/branches/main/rename",
        method="POST",
        status_code=422,
        json={"message": "Validation Failed"},
    )
    # fallback to PATCH
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="PATCH",
        json={"default_branch": "dev"},
    )
    # old branch still exists
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/git/ref/heads/main",
        method="GET",
        json={"object": {"sha": "abc123"}},
    )
    # compare: main has 3 unmerged commits
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/compare/dev...main",
        json={"ahead_by": 3, "behind_by": 10},
    )
    # no classic protection
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )
    # no existing rulesets
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/rulesets",
        json=[],
    )
    # create ruleset
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/rulesets",
        method="POST",
        json={"id": 1, "name": "idea-gh: dev"},
        status_code=201,
    )

    type_config = _type_config_with_dev_default()
    changes, stale_branches = branches.fix("co-cddo", "my-repo", type_config, gh_client)

    assert len(stale_branches) == 1
    assert stale_branches[0].branch == "main"
    assert stale_branches[0].ahead_by == 3
    assert stale_branches[0].is_merged is False


def test_fix_no_stale_when_default_already_correct(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """When default branch is already correct, no stale branch check needed."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo",
        method="GET",
        json={"default_branch": "dev"},
    )
    # no classic protection
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/branches/dev/protection",
        status_code=404,
    )
    # no existing rulesets
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/rulesets",
        json=[],
    )
    # create ruleset
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/rulesets",
        method="POST",
        json={"id": 1, "name": "idea-gh: dev"},
        status_code=201,
    )

    type_config = _type_config_with_dev_default()
    changes, stale_branches = branches.fix("co-cddo", "my-repo", type_config, gh_client)

    assert len(stale_branches) == 0
