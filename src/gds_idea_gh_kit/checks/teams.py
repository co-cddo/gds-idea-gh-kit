"""Check that the correct teams have the correct permissions on a repo."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient, GitHubClientError
from gds_idea_gh_kit.models import CheckResult, CheckStatus

# The GitHub API uses different permission names for reading vs writing:
#   GET returns role_name: read, write, admin, maintain, triage
#   PUT expects:           pull, push,  admin, maintain, triage
_PERM_TO_API = {
    "read": "pull",
    "write": "push",
    "admin": "admin",
    "maintain": "maintain",
    "triage": "triage",
}


def audit(owner: str, repo: str, expected_teams: dict[str, str], client: GitHubClient) -> list[CheckResult]:
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
                    message=(f"Team '{team_slug}': {actual_perm} (expected {expected_perm})"),
                    fix_available=True,
                )
            )

    # Flag unexpected teams
    try:
        actual_teams = client.list_repo_teams(owner, repo)
    except GitHubClientError:
        actual_teams = None
        results.append(
            CheckResult(
                name="teams.unexpected",
                status=CheckStatus.SKIPPED,
                message="Unexpected-team check skipped.",
            )
        )

    if actual_teams is not None:
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
    try:
        direct_collabs = client.list_direct_collaborators(owner, repo)
    except GitHubClientError:
        direct_collabs = None
        results.append(
            CheckResult(
                name="teams.direct_collaborators",
                status=CheckStatus.SKIPPED,
                message="Direct-collaborator check skipped.",
            )
        )

    if direct_collabs:
        # Look up which configured teams each collaborator belongs to
        team_members: dict[str, set[str]] = {}
        for team_slug in expected_teams:
            try:
                members = client.list_team_members(org, team_slug)
                team_members[team_slug] = {m["login"] for m in members}
            except Exception:
                team_members[team_slug] = set()

        user_lines = []
        for c in direct_collabs:
            login = c["login"]
            role = c.get("role_name", "unknown")
            member_of = [t for t in expected_teams if login in team_members.get(t, set())]
            if member_of:
                teams_str = ", ".join(member_of)
                user_lines.append(f"    - {login} ({role}) — member of: {teams_str}")
            else:
                user_lines.append(f"    - {login} ({role}) — not in any configured team")

        results.append(
            CheckResult(
                name="teams.direct_collaborators",
                status=CheckStatus.WARNING,
                message=(
                    f"{len(direct_collabs)} direct collaborator(s) found "
                    f"(not via a team):\n"
                    f"{chr(10).join(user_lines)}\n"
                    f"  Consider managing access through teams instead.\n"
                    f"  To remove specific users:\n"
                    f"    idea-gh remove-collaborators <username> [<username> ...]\n"
                    f"  To remove all:\n"
                    f"    idea-gh remove-collaborators --all"
                ),
            )
        )

    return results


def fix(owner: str, repo: str, expected_teams: dict[str, str], client: GitHubClient) -> list[str]:
    """Grant/update team permissions to match config. Returns list of changes made."""
    org = client.org or owner
    changes = []

    for team_slug, expected_perm in expected_teams.items():
        actual_perm = client.get_team_repo_permission(org, team_slug, owner, repo)
        if actual_perm != expected_perm:
            api_perm = _PERM_TO_API.get(expected_perm, expected_perm)
            client.set_team_repo_permission(org, team_slug, owner, repo, api_perm)
            changes.append(f"{team_slug}: {actual_perm} -> {expected_perm}")

    return changes
