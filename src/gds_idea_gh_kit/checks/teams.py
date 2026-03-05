"""Check that the correct teams have the correct permissions on a repo."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckResult, CheckStatus


def audit(
    owner: str, repo: str, expected_teams: dict[str, str], client: GitHubClient
) -> list[CheckResult]:
    """Check each expected team has the right permission, and flag unexpected teams."""
    results = []
    org = client.org or owner

    # Check expected teams
    for team_slug, expected_perm in expected_teams.items():
        actual_perm = client.get_team_repo_permission(org, team_slug, owner, repo)

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

    # Flag unexpected teams
    actual_teams = client.list_repo_teams(owner, repo)
    for team in actual_teams:
        slug = team["slug"]
        if slug not in expected_teams:
            permission = team.get("permission", "unknown")
            results.append(
                CheckResult(
                    name=f"teams.unexpected.{slug}",
                    status=CheckStatus.WARNING,
                    message=(
                        f"Team '{slug}' has '{permission}' access "
                        f"but is not in config. Review and remove if unneeded."
                    ),
                )
            )

    # Flag direct collaborators (people added outside of teams)
    direct_collabs = client.list_direct_collaborators(owner, repo)
    for collab in direct_collabs:
        username = collab["login"]
        permission = collab.get("role_name", "unknown")
        results.append(
            CheckResult(
                name=f"teams.direct_collaborator.{username}",
                status=CheckStatus.WARNING,
                message=(
                    f"User '{username}' has direct '{permission}' access "
                    f"(not via a team). Consider managing access through "
                    f"teams instead.\n"
                    f"  To remove all direct collaborators, run from inside the repo:\n"
                    f"    idea-gh remove-collaborators"
                ),
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
