"""Check default branch name and branch protection rules."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import (
    BranchProtectionConfig,
    CheckResult,
    CheckStatus,
    RepoTypeConfig,
)


def audit(
    owner: str, repo: str, type_config: RepoTypeConfig, client: GitHubClient
) -> list[CheckResult]:
    """Check default branch and all configured branch protection rules."""
    results = []
    repo_data = client.get_repo(owner, repo)

    # --- Default branch ---
    actual_default = repo_data["default_branch"]
    if actual_default == type_config.default_branch:
        results.append(
            CheckResult(
                name="branches.default",
                status=CheckStatus.PASSED,
                message=f"Default branch: {actual_default}",
            )
        )
    else:
        results.append(
            CheckResult(
                name="branches.default",
                status=CheckStatus.FAILED,
                message=(
                    f"Default branch: {actual_default} "
                    f"(expected {type_config.default_branch})"
                ),
                fix_available=True,
            )
        )

    # --- Branch protection ---
    for branch_name, expected_bp in type_config.branch_protection.items():
        results.extend(_audit_branch_protection(owner, repo, branch_name, expected_bp, client))

    return results


def _audit_branch_protection(
    owner: str,
    repo: str,
    branch: str,
    expected: BranchProtectionConfig,
    client: GitHubClient,
) -> list[CheckResult]:
    """Audit protection rules for a single branch."""
    actual = client.get_branch_protection(owner, repo, branch)

    if actual is None:
        return [
            CheckResult(
                name=f"branches.protection.{branch}",
                status=CheckStatus.FAILED,
                message=f"Branch '{branch}' has no protection rules",
                fix_available=True,
            )
        ]

    results = []

    # PR required
    pr_reviews = actual.get("required_pull_request_reviews")
    if expected.require_pr and pr_reviews is None:
        results.append(
            CheckResult(
                name=f"branches.protection.{branch}.require_pr",
                status=CheckStatus.FAILED,
                message=f"Branch '{branch}': PR reviews not required (expected required)",
                fix_available=True,
            )
        )
    elif expected.require_pr and pr_reviews is not None:
        results.append(
            CheckResult(
                name=f"branches.protection.{branch}.require_pr",
                status=CheckStatus.PASSED,
                message=f"Branch '{branch}': PR reviews required",
            )
        )

        # Approvals count
        actual_approvals = pr_reviews.get("required_approving_review_count", 0)
        if actual_approvals == expected.required_approvals:
            results.append(
                CheckResult(
                    name=f"branches.protection.{branch}.required_approvals",
                    status=CheckStatus.PASSED,
                    message=f"Branch '{branch}': {actual_approvals} approval(s) required",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"branches.protection.{branch}.required_approvals",
                    status=CheckStatus.FAILED,
                    message=(
                        f"Branch '{branch}': {actual_approvals} approval(s) required "
                        f"(expected {expected.required_approvals})"
                    ),
                    fix_available=True,
                )
            )

        # Dismiss stale reviews
        actual_dismiss = pr_reviews.get("dismiss_stale_reviews", False)
        if actual_dismiss == expected.dismiss_stale_reviews:
            results.append(
                CheckResult(
                    name=f"branches.protection.{branch}.dismiss_stale",
                    status=CheckStatus.PASSED,
                    message=f"Branch '{branch}': dismiss stale reviews: {actual_dismiss}",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"branches.protection.{branch}.dismiss_stale",
                    status=CheckStatus.FAILED,
                    message=(
                        f"Branch '{branch}': dismiss stale reviews: {actual_dismiss} "
                        f"(expected {expected.dismiss_stale_reviews})"
                    ),
                    fix_available=True,
                )
            )

        # Required review teams (dismissal_restrictions.teams)
        if expected.required_review_teams:
            restrictions = pr_reviews.get("dismissal_restrictions", {})
            actual_teams = {
                t["slug"] for t in restrictions.get("teams", [])
            }
            expected_set = set(expected.required_review_teams)

            if expected_set <= actual_teams:
                results.append(
                    CheckResult(
                        name=f"branches.protection.{branch}.review_teams",
                        status=CheckStatus.PASSED,
                        message=(
                            f"Branch '{branch}': required review teams: "
                            f"{', '.join(sorted(expected_set))}"
                        ),
                    )
                )
            else:
                missing = expected_set - actual_teams
                results.append(
                    CheckResult(
                        name=f"branches.protection.{branch}.review_teams",
                        status=CheckStatus.FAILED,
                        message=(
                            f"Branch '{branch}': missing review teams: "
                            f"{', '.join(sorted(missing))}"
                        ),
                        fix_available=True,
                    )
                )

    # Enforce admins
    enforce = actual.get("enforce_admins", {})
    actual_enforce = enforce.get("enabled", False) if isinstance(enforce, dict) else False
    if actual_enforce == expected.enforce_admins:
        results.append(
            CheckResult(
                name=f"branches.protection.{branch}.enforce_admins",
                status=CheckStatus.PASSED,
                message=f"Branch '{branch}': enforce admins: {actual_enforce}",
            )
        )
    else:
        results.append(
            CheckResult(
                name=f"branches.protection.{branch}.enforce_admins",
                status=CheckStatus.FAILED,
                message=(
                    f"Branch '{branch}': enforce admins: {actual_enforce} "
                    f"(expected {expected.enforce_admins})"
                ),
                fix_available=True,
            )
        )

    # Required status checks
    status_checks = actual.get("required_status_checks")
    if expected.require_status_checks:
        if status_checks is None:
            results.append(
                CheckResult(
                    name=f"branches.protection.{branch}.status_checks",
                    status=CheckStatus.FAILED,
                    message=f"Branch '{branch}': no status checks configured",
                    fix_available=True,
                )
            )
        else:
            actual_contexts = set(status_checks.get("contexts", []))
            expected_contexts = set(expected.require_status_checks)
            missing = expected_contexts - actual_contexts
            if not missing:
                results.append(
                    CheckResult(
                        name=f"branches.protection.{branch}.status_checks",
                        status=CheckStatus.PASSED,
                        message=(
                            f"Branch '{branch}': status checks: "
                            f"{', '.join(sorted(expected_contexts))}"
                        ),
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"branches.protection.{branch}.status_checks",
                        status=CheckStatus.FAILED,
                        message=(
                            f"Branch '{branch}': missing status checks: "
                            f"{', '.join(sorted(missing))}"
                        ),
                        fix_available=True,
                    )
                )

    # Linear history
    actual_linear = actual.get("required_linear_history", {})
    actual_linear_enabled = (
        actual_linear.get("enabled", False) if isinstance(actual_linear, dict) else False
    )
    if actual_linear_enabled == expected.require_linear_history:
        results.append(
            CheckResult(
                name=f"branches.protection.{branch}.linear_history",
                status=CheckStatus.PASSED,
                message=f"Branch '{branch}': linear history: {actual_linear_enabled}",
            )
        )
    else:
        results.append(
            CheckResult(
                name=f"branches.protection.{branch}.linear_history",
                status=CheckStatus.FAILED,
                message=(
                    f"Branch '{branch}': linear history: {actual_linear_enabled} "
                    f"(expected {expected.require_linear_history})"
                ),
                fix_available=True,
            )
        )

    return results


def fix(
    owner: str, repo: str, type_config: RepoTypeConfig, client: GitHubClient
) -> list[str]:
    """Apply default branch and branch protection fixes. Returns list of changes."""
    changes = []
    repo_data = client.get_repo(owner, repo)
    org = client.org or owner

    # Fix default branch
    if repo_data["default_branch"] != type_config.default_branch:
        client.rename_default_branch(owner, repo, type_config.default_branch)
        changes.append(
            f"Default branch: {repo_data['default_branch']} -> {type_config.default_branch}"
        )

    # Fix branch protection
    for branch_name, expected_bp in type_config.branch_protection.items():
        payload = _build_protection_payload(expected_bp, org)
        client.set_branch_protection(owner, repo, branch_name, **payload)
        changes.append(f"Branch protection applied to '{branch_name}'")

    return changes


def _build_protection_payload(bp: BranchProtectionConfig, org: str) -> dict:
    """Build the GitHub API payload for branch protection."""
    payload: dict = {
        "enforce_admins": bp.enforce_admins,
        "required_linear_history": bp.require_linear_history,
        "restrictions": None,
    }

    if bp.require_pr:
        pr_reviews: dict = {
            "required_approving_review_count": bp.required_approvals,
            "dismiss_stale_reviews": bp.dismiss_stale_reviews,
        }
        if bp.required_review_teams:
            pr_reviews["dismissal_restrictions"] = {
                "users": [],
                "teams": bp.required_review_teams,
            }
        payload["required_pull_request_reviews"] = pr_reviews
    else:
        payload["required_pull_request_reviews"] = None

    if bp.require_status_checks:
        payload["required_status_checks"] = {
            "strict": True,
            "contexts": bp.require_status_checks,
        }
    else:
        payload["required_status_checks"] = None

    return payload
