"""Check default branch name and branch protection via rulesets."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient, GitHubClientError
from gds_idea_gh_kit.models import (
    BranchProtectionConfig,
    CheckResult,
    CheckStatus,
    RepoTypeConfig,
    StaleBranch,
)

RULESET_PREFIX = "idea-gh"


def ruleset_name(branch: str) -> str:
    """Name for a managed ruleset."""
    return f"{RULESET_PREFIX}: {branch}"


def audit(owner: str, repo: str, type_config: RepoTypeConfig, client: GitHubClient) -> list[CheckResult]:
    """Check default branch and all configured branch protection rulesets."""
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
                message=(f"Default branch: {actual_default} (expected {type_config.default_branch})"),
                fix_available=True,
            )
        )

    # --- Classic branch protection warning ---
    for branch_name in type_config.branch_protection:
        classic = client.get_branch_protection(owner, repo, branch_name)
        if classic is not None:
            results.append(
                CheckResult(
                    name=f"branches.classic_protection.{branch_name}",
                    status=CheckStatus.WARNING,
                    message=(
                        f"Branch '{branch_name}' has classic branch protection rules. "
                        f"These should be migrated to rulesets. "
                        f"Run with --fix to remove and replace with rulesets."
                    ),
                    fix_available=True,
                )
            )

    # --- Rulesets ---
    for branch_name, expected_bp in type_config.branch_protection.items():
        results.extend(_audit_ruleset(owner, repo, branch_name, expected_bp, client))

    return results


def _audit_ruleset(
    owner: str,
    repo: str,
    branch: str,
    expected: BranchProtectionConfig,
    client: GitHubClient,
) -> list[CheckResult]:
    """Audit the ruleset for a single branch."""
    name = ruleset_name(branch)
    ruleset = client.find_ruleset_by_name(owner, repo, name)

    if ruleset is None:
        return [
            CheckResult(
                name=f"branches.ruleset.{branch}",
                status=CheckStatus.FAILED,
                message=f"Ruleset '{name}' not found",
                fix_available=True,
            )
        ]

    results = []
    actual_rules = {r["type"]: r for r in ruleset.get("rules", [])}

    # --- Deletion protection ---
    has_deletion = "deletion" in actual_rules
    if has_deletion == expected.prevent_deletion:
        results.append(
            CheckResult(
                name=f"branches.ruleset.{branch}.deletion",
                status=CheckStatus.PASSED,
                message=f"Branch '{branch}': prevent deletion: {has_deletion}",
            )
        )
    else:
        results.append(
            CheckResult(
                name=f"branches.ruleset.{branch}.deletion",
                status=CheckStatus.FAILED,
                message=(f"Branch '{branch}': prevent deletion: {has_deletion} (expected {expected.prevent_deletion})"),
                fix_available=True,
            )
        )

    # --- Force push protection ---
    has_nff = "non_fast_forward" in actual_rules
    if has_nff == expected.prevent_force_push:
        results.append(
            CheckResult(
                name=f"branches.ruleset.{branch}.force_push",
                status=CheckStatus.PASSED,
                message=f"Branch '{branch}': prevent force push: {has_nff}",
            )
        )
    else:
        results.append(
            CheckResult(
                name=f"branches.ruleset.{branch}.force_push",
                status=CheckStatus.FAILED,
                message=(f"Branch '{branch}': prevent force push: {has_nff} (expected {expected.prevent_force_push})"),
                fix_available=True,
            )
        )

    # --- Linear history ---
    has_linear = "required_linear_history" in actual_rules
    if has_linear == expected.require_linear_history:
        results.append(
            CheckResult(
                name=f"branches.ruleset.{branch}.linear_history",
                status=CheckStatus.PASSED,
                message=f"Branch '{branch}': linear history: {has_linear}",
            )
        )
    else:
        results.append(
            CheckResult(
                name=f"branches.ruleset.{branch}.linear_history",
                status=CheckStatus.FAILED,
                message=(
                    f"Branch '{branch}': linear history: {has_linear} (expected {expected.require_linear_history})"
                ),
                fix_available=True,
            )
        )

    # --- Pull request rules ---
    pr_rule = actual_rules.get("pull_request")
    if expected.require_pr:
        if pr_rule is None:
            results.append(
                CheckResult(
                    name=f"branches.ruleset.{branch}.require_pr",
                    status=CheckStatus.FAILED,
                    message=f"Branch '{branch}': pull request rule missing",
                    fix_available=True,
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"branches.ruleset.{branch}.require_pr",
                    status=CheckStatus.PASSED,
                    message=f"Branch '{branch}': pull request required",
                )
            )
            params = pr_rule.get("parameters", {})

            # Approvals
            actual_approvals = params.get("required_approving_review_count", 0)
            if actual_approvals == expected.required_approvals:
                results.append(
                    CheckResult(
                        name=f"branches.ruleset.{branch}.approvals",
                        status=CheckStatus.PASSED,
                        message=f"Branch '{branch}': {actual_approvals} approval(s) required",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"branches.ruleset.{branch}.approvals",
                        status=CheckStatus.FAILED,
                        message=(
                            f"Branch '{branch}': {actual_approvals} approval(s) required "
                            f"(expected {expected.required_approvals})"
                        ),
                        fix_available=True,
                    )
                )

            # Dismiss stale reviews
            actual_dismiss = params.get("dismiss_stale_reviews_on_push", False)
            if actual_dismiss == expected.dismiss_stale_reviews:
                results.append(
                    CheckResult(
                        name=f"branches.ruleset.{branch}.dismiss_stale",
                        status=CheckStatus.PASSED,
                        message=f"Branch '{branch}': dismiss stale reviews: {actual_dismiss}",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"branches.ruleset.{branch}.dismiss_stale",
                        status=CheckStatus.FAILED,
                        message=(
                            f"Branch '{branch}': dismiss stale reviews: {actual_dismiss} "
                            f"(expected {expected.dismiss_stale_reviews})"
                        ),
                        fix_available=True,
                    )
                )

            # Allowed merge methods
            if expected.allowed_merge_methods:
                actual_methods = sorted(params.get("allowed_merge_methods", []))
                expected_methods = sorted(expected.allowed_merge_methods)
                if actual_methods == expected_methods:
                    results.append(
                        CheckResult(
                            name=f"branches.ruleset.{branch}.merge_methods",
                            status=CheckStatus.PASSED,
                            message=f"Branch '{branch}': allowed merge methods: {actual_methods}",
                        )
                    )
                else:
                    results.append(
                        CheckResult(
                            name=f"branches.ruleset.{branch}.merge_methods",
                            status=CheckStatus.FAILED,
                            message=(
                                f"Branch '{branch}': allowed merge methods: {actual_methods} "
                                f"(expected {expected_methods})"
                            ),
                            fix_available=True,
                        )
                    )

    # --- Bypass actors ---
    actual_bypass = ruleset.get("bypass_actors", [])
    actual_bypass_team_ids = {a["actor_id"] for a in actual_bypass if a.get("actor_type") == "Team"}
    if expected.bypass_teams:
        # We can't resolve slugs to IDs during audit without extra API calls,
        # so we check count and report slugs for readability
        if len(actual_bypass_team_ids) >= len(expected.bypass_teams):
            results.append(
                CheckResult(
                    name=f"branches.ruleset.{branch}.bypass_teams",
                    status=CheckStatus.PASSED,
                    message=(f"Branch '{branch}': bypass teams configured ({len(actual_bypass_team_ids)} team(s))"),
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"branches.ruleset.{branch}.bypass_teams",
                    status=CheckStatus.FAILED,
                    message=(
                        f"Branch '{branch}': expected {len(expected.bypass_teams)} "
                        f"bypass team(s), found {len(actual_bypass_team_ids)}"
                    ),
                    fix_available=True,
                )
            )
    elif actual_bypass_team_ids:
        results.append(
            CheckResult(
                name=f"branches.ruleset.{branch}.bypass_teams",
                status=CheckStatus.WARNING,
                message=(
                    f"Branch '{branch}': {len(actual_bypass_team_ids)} bypass team(s) configured but none expected"
                ),
            )
        )

    return results


# --- Fix ---


def fix(
    owner: str, repo: str, type_config: RepoTypeConfig, client: GitHubClient
) -> tuple[list[str], list[StaleBranch]]:
    """Apply default branch and ruleset fixes.

    Returns a tuple of (changes, stale_branches).  *stale_branches*
    lists any branches that were superseded by the new default but
    could not be renamed away (because the target already existed).
    The caller is responsible for prompting the user about deletion.
    """
    changes: list[str] = []
    stale_branches: list[StaleBranch] = []
    repo_data = client.get_repo(owner, repo)
    org = client.org or owner
    old_default = repo_data["default_branch"]
    new_default = type_config.default_branch

    # Fix default branch
    if old_default != new_default:
        client.rename_default_branch(owner, repo, new_default)
        changes.append(f"Default branch: {old_default} -> {new_default}")

        # Check if the old branch still exists (rename vs set-default).
        # If rename succeeded, the old branch is gone.  If we fell back
        # to set-default, it's still there and is now stale.
        try:
            client._request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{old_default}")
            # Old branch still exists — compare with new default
            comparison = client.compare_branches(owner, repo, new_default, old_default)
            stale_branches.append(
                StaleBranch(
                    branch=old_default,
                    default_branch=new_default,
                    ahead_by=comparison.get("ahead_by", 0),
                )
            )
        except GitHubClientError:
            # Old branch was renamed away — nothing stale
            pass

    # Remove classic branch protection if present
    for branch_name in type_config.branch_protection:
        classic = client.get_branch_protection(owner, repo, branch_name)
        if classic is not None:
            client.delete_branch_protection(owner, repo, branch_name)
            changes.append(f"Removed classic branch protection from '{branch_name}'")

    # Create or update rulesets
    for branch_name, expected_bp in type_config.branch_protection.items():
        name = ruleset_name(branch_name)
        payload = build_ruleset_payload(name, branch_name, expected_bp, org, client)

        existing = client.find_ruleset_by_name(owner, repo, name)
        if existing:
            client.update_ruleset(owner, repo, existing["id"], payload)
            changes.append(f"Updated ruleset '{name}'")
        else:
            client.create_ruleset(owner, repo, payload)
            changes.append(f"Created ruleset '{name}'")

    return changes, stale_branches


def build_ruleset_payload(
    name: str,
    branch: str,
    bp: BranchProtectionConfig,
    org: str,
    client: GitHubClient,
) -> dict:
    """Build the GitHub API payload for a ruleset."""
    rules: list[dict] = []

    if bp.prevent_deletion:
        rules.append({"type": "deletion"})

    if bp.prevent_force_push:
        rules.append({"type": "non_fast_forward"})

    if bp.require_linear_history:
        rules.append({"type": "required_linear_history"})

    if bp.require_pr:
        pr_params: dict = {
            "required_approving_review_count": bp.required_approvals,
            "dismiss_stale_reviews_on_push": bp.dismiss_stale_reviews,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_review_thread_resolution": False,
        }
        if bp.allowed_merge_methods:
            pr_params["allowed_merge_methods"] = bp.allowed_merge_methods
        rules.append({"type": "pull_request", "parameters": pr_params})

    # Bypass actors
    bypass_actors = []
    for team_slug in bp.bypass_teams:
        team_id = client.get_team_id(org, team_slug)
        bypass_actors.append(
            {
                "actor_id": team_id,
                "actor_type": "Team",
                "bypass_mode": bp.bypass_mode,
            }
        )

    return {
        "name": name,
        "target": "branch",
        "enforcement": "active",
        "conditions": {
            "ref_name": {
                "include": [f"refs/heads/{branch}"],
                "exclude": [],
            }
        },
        "rules": rules,
        "bypass_actors": bypass_actors,
    }
