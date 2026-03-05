"""Check that the correct teams have the correct permissions on a repo."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckResult, CheckStatus


def audit(
    owner: str, repo: str, expected_teams: dict[str, str], client: GitHubClient
) -> list[CheckResult]:
    """Check each expected team has the right permission on the repo."""
    results = []

    for team_slug, expected_perm in expected_teams.items():
        actual_perm = client.get_team_repo_permission(client.org or owner, team_slug, owner, repo)

        if actual_perm is None:
            results.append(
                CheckResult(
                    name=f"teams.{team_slug}",
                    status=CheckStatus.FAILED,
                    message=f"Team '{team_slug}' has no access (expected {expected_perm})",
                    fix_available=True,
                )
            )
        elif actual_perm == expected_perm:
            results.append(
                CheckResult(
                    name=f"teams.{team_slug}",
                    status=CheckStatus.PASSED,
                    message=f"Team '{team_slug}': {actual_perm}",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"teams.{team_slug}",
                    status=CheckStatus.FAILED,
                    message=(
                        f"Team '{team_slug}': {actual_perm} (expected {expected_perm})"
                    ),
                    fix_available=True,
                )
            )

    return results


def fix(
    owner: str, repo: str, expected_teams: dict[str, str], client: GitHubClient
) -> list[str]:
    """Grant/update team permissions to match config. Returns list of changes made."""
    org = client.org or owner
    changes = []

    for team_slug, expected_perm in expected_teams.items():
        actual_perm = client.get_team_repo_permission(org, team_slug, owner, repo)
        if actual_perm != expected_perm:
            client.set_team_repo_permission(org, team_slug, owner, repo, expected_perm)
            changes.append(f"{team_slug}: {actual_perm} -> {expected_perm}")

    return changes
