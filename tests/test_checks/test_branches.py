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
    contexts=None,
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
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [
                    {"context": c} for c in (contexts or [])
                ],
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
            rules=_full_rules(approvals=1, contexts=["lint", "test"]),
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
            rules=_full_rules(approvals=1, dismiss_stale=True, contexts=["lint", "test"]),
            bypass_actors=[],
        ),
    )

    type_config = RepoTypeConfig(
        naming_pattern="gds-idea-app-{name}",
        default_branch="dev",
        branch_protection={
            "prod": BranchProtectionConfig(
                required_approvals=1,
                require_status_checks=["lint", "test"],
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
