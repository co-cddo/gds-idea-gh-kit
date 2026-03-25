"""Initialise a new GitHub repo with the correct settings, teams, and branch protection."""

from __future__ import annotations

import subprocess
from pathlib import Path

from gds_idea_gh_kit.checks.branches import build_ruleset_payload, ruleset_name
from gds_idea_gh_kit.github_client import GitHubClient, GitHubClientError
from gds_idea_gh_kit.models import Config

# GitHub API uses different permission names for writing vs config:
#   Config uses: read, write, admin, maintain, triage
#   PUT expects: pull, push, admin, maintain, triage
_PERM_TO_API = {
    "read": "pull",
    "write": "push",
    "admin": "admin",
    "maintain": "maintain",
    "triage": "triage",
}


class InitError(Exception):
    """Raised when repo initialisation fails."""


def get_repo_name_from_directory() -> str:
    """Get the repo name from the current directory name."""
    return Path.cwd().name


def _run_git(*args: str) -> str:
    """Run a git command and return stdout. Raises InitError on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return result.stdout.strip()
    except FileNotFoundError:
        raise InitError("git is not installed or not on PATH.")
    except subprocess.CalledProcessError as e:
        raise InitError(f"git {' '.join(args)} failed: {e.stderr.strip()}")


def _check_preconditions(repo_name: str, config: Config, repo_type: str) -> None:
    """Validate preconditions before init. Raises InitError on failure."""
    # Must be inside a git repo
    try:
        _run_git("rev-parse", "--is-inside-work-tree")
    except InitError:
        raise InitError("Not inside a git repo. Run 'idea-app init' first to scaffold the project.")

    # Must have at least one commit
    try:
        _run_git("rev-parse", "HEAD")
    except InitError:
        raise InitError("Git repo has no commits. Run 'idea-app init' first to scaffold the project.")

    # Must not already have a remote
    try:
        _run_git("remote", "get-url", "origin")
        raise InitError(
            "This repo already has a remote 'origin'. Use 'idea-gh audit --fix' to configure an existing repo."
        )
    except InitError as e:
        if "already has a remote" in str(e):
            raise
        # No remote is what we want — continue

    # Repo name must match the type's naming pattern
    type_config = config.repo_types[repo_type]
    if not type_config.matches_name(repo_name):
        raise InitError(
            f"Directory name '{repo_name}' does not match the expected naming "
            f"pattern for {repo_type}: {type_config.naming_pattern}"
        )


def init_repo(
    repo_name: str,
    config: Config,
    repo_type: str,
    client: GitHubClient,
) -> list[str]:
    """Create and configure a new GitHub repo.

    Assumes the user has already run `idea-app init` and is inside the
    local repo directory. Returns a list of steps completed.

    Raises InitError if preconditions are not met or a step fails.
    """
    steps: list[str] = []
    org = config.org
    type_config = config.repo_types[repo_type]
    default_branch = type_config.default_branch

    _check_preconditions(repo_name, config, repo_type)

    # 1. Create the GitHub repo
    try:
        client.create_repo(
            org,
            repo_name,
            visibility=config.default_visibility,
            auto_init=False,
        )
    except GitHubClientError as e:
        raise InitError(f"Failed to create repo: {e}")
    steps.append(f"Created repo {org}/{repo_name} ({config.default_visibility})")

    # 2. Add remote and push
    _run_git("remote", "add", "origin", f"git@github.com:{org}/{repo_name}.git")
    steps.append("Added remote origin")

    _run_git("push", "-u", "origin", "HEAD:main")
    steps.append("Pushed to origin/main")

    # 3. Apply repo settings
    settings = config.repo_settings.model_dump()
    client.update_repo(org, repo_name, **settings)
    steps.append("Applied repo settings")

    # 4. Rename default branch (main -> dev for cdk-app)
    if default_branch != "main":
        client.rename_default_branch(org, repo_name, default_branch)
        # Update local branch to track the renamed remote branch
        _run_git("branch", "-m", "main", default_branch)
        _run_git("fetch", "origin")
        _run_git("branch", "--set-upstream-to", f"origin/{default_branch}")
        steps.append(f"Renamed default branch main -> {default_branch}")

    # 5. Create additional branches (e.g. prod from dev)
    for branch_name in type_config.branch_protection:
        if branch_name != default_branch:
            client.create_branch(org, repo_name, branch_name, default_branch)
            steps.append(f"Created {branch_name} branch from {default_branch}")

    # 6. Attach teams (global + type-specific)
    all_teams = {**config.teams, **type_config.extra_teams}
    for team_slug, perm in all_teams.items():
        api_perm = _PERM_TO_API.get(perm, perm)
        client.set_team_repo_permission(org, team_slug, org, repo_name, api_perm)
        steps.append(f"Attached team {team_slug} ({perm})")

    # 7. Create rulesets
    for branch_name, bp_config in type_config.branch_protection.items():
        name = ruleset_name(branch_name)
        payload = build_ruleset_payload(name, branch_name, bp_config, org, client)
        client.create_ruleset(org, repo_name, payload)
        steps.append(f"Created ruleset '{name}'")

    # 8. Enable security
    if config.security.vulnerability_alerts:
        client.enable_vulnerability_alerts(org, repo_name)
        steps.append("Enabled vulnerability alerts")

    if config.security.automated_security_fixes:
        client.enable_automated_security_fixes(org, repo_name)
        steps.append("Enabled automated security fixes")

    return steps
