"""Check that repo settings (merge strategy, wiki, etc.) match config."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckResult, CheckStatus, RepoSettings

# Map our config field names to GitHub API field names
_SETTINGS_MAP = {
    "delete_branch_on_merge": "delete_branch_on_merge",
    "allow_squash_merge": "allow_squash_merge",
    "allow_merge_commit": "allow_merge_commit",
    "allow_rebase_merge": "allow_rebase_merge",
    "has_issues": "has_issues",
    "has_wiki": "has_wiki",
    "has_projects": "has_projects",
}


def audit(
    owner: str, repo: str, expected: RepoSettings, client: GitHubClient
) -> list[CheckResult]:
    """Compare actual repo settings against expected."""
    repo_data = client.get_repo(owner, repo)
    results = []

    for config_key, api_key in _SETTINGS_MAP.items():
        expected_val = getattr(expected, config_key)
        actual_val = repo_data.get(api_key)

        if actual_val == expected_val:
            results.append(
                CheckResult(
                    name=f"settings.{config_key}",
                    status=CheckStatus.PASSED,
                    message=f"{config_key}: {actual_val}",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"settings.{config_key}",
                    status=CheckStatus.FAILED,
                    message=f"{config_key}: {actual_val} (expected {expected_val})",
                    fix_available=True,
                )
            )

    return results


def fix(
    owner: str, repo: str, expected: RepoSettings, client: GitHubClient
) -> list[str]:
    """Apply repo settings to match expected config. Returns list of changes made."""
    repo_data = client.get_repo(owner, repo)
    updates = {}

    for config_key, api_key in _SETTINGS_MAP.items():
        expected_val = getattr(expected, config_key)
        actual_val = repo_data.get(api_key)
        if actual_val != expected_val:
            updates[api_key] = expected_val

    if updates:
        client.update_repo(owner, repo, **updates)

    return [f"{k}: {v}" for k, v in updates.items()]
