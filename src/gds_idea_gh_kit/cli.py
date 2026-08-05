"""CLI entry point for idea-gh."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from gds_idea_gh_kit.github_client import GitHubClient
    from gds_idea_gh_kit.models import Config

from gds_idea_gh_kit import __version__

# Short aliases for --type values
_TYPE_ALIASES: dict[str, str] = {
    "pkg": "python-package",
}


@click.group()
@click.version_option(version=__version__, prog_name="idea-gh")
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to custom config file (default: built-in config).",
)
@click.pass_context
def cli(ctx: click.Context, config_path: Path | None):
    """Audit and enforce GitHub repo standards for GDS IDEA teams."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


@cli.command("check-config")
@click.pass_context
def check_config(ctx: click.Context):
    """Validate the configuration file."""
    from gds_idea_gh_kit.config import ConfigError, load_config

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        raise click.ClickException(str(e))

    click.echo("Configuration is valid.")
    click.echo(f"  Org: {config.org}")
    click.echo(f"  Visibility: {config.default_visibility}")
    click.echo(f"  Teams: {len(config.teams)}")
    click.echo(f"  Repo types: {', '.join(config.repo_types.keys())}")
    click.echo(f"  Required files: {len(config.required_files)}")


@cli.command("audit")
@click.option("--type", "repo_type", default=None, help="Override repo type detection.")
@click.option("--all", "audit_all", is_flag=True, help="Audit all repos in the org.")
@click.option("--fix", "apply_fix", is_flag=True, help="Auto-fix issues where possible.")
@click.option("--verbose", is_flag=True, help="Show all checks including passing.")
@click.pass_context
def audit(ctx: click.Context, repo_type: str | None, audit_all: bool, apply_fix: bool, verbose: bool):
    """Audit repo(s) against the configured standards.

    Run from inside a repo to audit that repo, or use --all to audit
    every repo in the org that matches a known prefix.

    Use --fix to automatically correct issues where possible (settings,
    teams, branch rulesets, security).
    """
    from gds_idea_gh_kit.audit import audit_repo, fix_repo, render_report
    from gds_idea_gh_kit.config import ConfigError, load_config
    from gds_idea_gh_kit.github_client import AuthError, GitHubClient, GitHubClientError
    from gds_idea_gh_kit.repo_info import RepoInfoError, get_repo_from_remote
    from gds_idea_gh_kit.version import check_tool_is_current

    # -- Check tool is current --
    check_tool_is_current()

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        raise click.ClickException(str(e))

    # Resolve type aliases (e.g. "pkg" -> "python-package")
    if repo_type:
        repo_type = _TYPE_ALIASES.get(repo_type, repo_type)

    if repo_type and repo_type not in config.repo_types:
        raise click.ClickException(f"Unknown repo type '{repo_type}'. Available: {', '.join(config.repo_types.keys())}")

    with GitHubClient(org=config.org) as client:
        try:
            client.verify_connection()
        except (GitHubClientError, AuthError) as e:
            raise click.ClickException(str(e))

        if audit_all:
            _audit_all_repos(config, client, repo_type, apply_fix=apply_fix, verbose=verbose)
        else:
            try:
                owner, repo = get_repo_from_remote()
            except RepoInfoError as e:
                raise click.ClickException(str(e))

            report = audit_repo(owner, repo, config, client, repo_type)

            if report.repo_type == "unknown":
                raise click.ClickException(
                    f"Could not detect repo type for '{repo}'. "
                    f"Use --type to specify one of: {', '.join(config.repo_types.keys())}"
                )

            click.echo(render_report(report, verbose=verbose))

            if apply_fix and report.fixable:
                click.echo()
                fix_result = fix_repo(owner, repo, config, client, report.repo_type)
                _render_fix_result(fix_result)
                _handle_stale_branches(fix_result, owner, repo, client)

                # Re-audit to show updated state
                click.echo()
                report = audit_repo(owner, repo, config, client, report.repo_type)
                click.echo(render_report(report, verbose=verbose))

            raise SystemExit(1 if report.failed > 0 else 0)


def _render_fix_result(fix_result):
    """Print the results of applying fixes."""
    if fix_result.changes:
        click.echo("Applied fixes:")
        for change in fix_result.changes:
            click.echo(f"  \u2713 {change}")

    if fix_result.errors:
        click.echo("Fix errors:")
        for error in fix_result.errors:
            click.echo(f"  \u2717 {error}")

    if not fix_result.changes and not fix_result.errors:
        click.echo("No fixes needed.")


def _handle_stale_branches(fix_result, owner, repo, client):
    """Prompt the user about stale branches left behind after a default branch change."""
    for stale in fix_result.stale_branches:
        click.echo()
        if stale.is_merged:
            click.echo(
                f"Branch '{stale.branch}' is fully merged into '{stale.default_branch}' and is no longer needed."
            )
            if click.confirm(f"Delete '{stale.branch}'?", default=False):
                client.delete_branch(owner, repo, stale.branch)
                click.echo(f"  \u2713 Deleted branch '{stale.branch}'")
            else:
                click.echo(f"  Leaving '{stale.branch}' in place.")
        else:
            click.echo(
                f"WARNING: Branch '{stale.branch}' has {stale.ahead_by} commit(s) not in '{stale.default_branch}'."
            )
            click.echo("Review these commits before deleting:")
            click.echo(
                f"  gh api repos/{owner}/{repo}/compare/"
                f"{stale.default_branch}...{stale.branch} --jq '.commits[].commit.message'"
            )
            if click.confirm(f"Delete '{stale.branch}' anyway?", default=False):
                client.delete_branch(owner, repo, stale.branch)
                click.echo(f"  \u2713 Deleted branch '{stale.branch}'")
            else:
                click.echo(f"  Leaving '{stale.branch}' in place.")


def _warn_stale_branches(fix_result, owner, repo):
    """Print warnings about stale branches (non-interactive, for --all mode)."""
    for stale in fix_result.stale_branches:
        if stale.is_merged:
            click.echo(f"  ! Branch '{stale.branch}' is fully merged into '{stale.default_branch}' and can be deleted:")
            click.echo(f"    gh api -X DELETE repos/{owner}/{repo}/git/refs/heads/{stale.branch}")
        else:
            click.echo(
                f"  ! Branch '{stale.branch}' has {stale.ahead_by} unmerged commit(s). Review and delete manually."
            )


def _audit_all_repos(
    config: Config,
    client: GitHubClient,
    repo_type_filter: str | None,
    apply_fix: bool = False,
    verbose: bool = False,
):
    """Audit all matching repos in the org."""
    from gds_idea_gh_kit.audit import audit_repo, detect_repo_type, fix_repo, render_report
    from gds_idea_gh_kit.github_client import GitHubClientError

    repos = client.list_org_repos(config.org)
    total_passed = 0
    total_failed = 0
    total_warnings = 0
    audited = 0
    skipped = 0

    for repo_data in repos:
        repo_name = repo_data["name"]

        # Only consider repos with a known prefix
        if not config.has_known_prefix(repo_name):
            continue

        # Skip archived repos
        if repo_data.get("archived", False):
            click.echo(f"Skipping {repo_name} (archived)")
            skipped += 1
            continue

        try:
            detected_type = repo_type_filter or detect_repo_type(
                config.org,
                repo_name,
                config,
                client,
            )
        except GitHubClientError as e:
            click.echo(f"Skipping {repo_name}: {e}")
            skipped += 1
            continue

        if detected_type is None:
            continue

        try:
            report = audit_repo(config.org, repo_name, config, client, detected_type)
        except GitHubClientError as e:
            click.echo(f"Skipping {repo_name}: {e}")
            skipped += 1
            continue

        click.echo(render_report(report, verbose=verbose))

        if apply_fix and report.fixable:
            click.echo()
            try:
                fix_result = fix_repo(config.org, repo_name, config, client, detected_type)
                _render_fix_result(fix_result)
                _warn_stale_branches(fix_result, config.org, repo_name)

                # Re-audit to show updated state
                click.echo()
                report = audit_repo(config.org, repo_name, config, client, detected_type)
                click.echo(render_report(report, verbose=verbose))
            except GitHubClientError as e:
                click.echo(f"  Fix failed for {repo_name}: {e}")

        click.echo()

        total_passed += report.passed
        total_failed += report.failed
        total_warnings += report.warnings
        audited += 1

    if audited == 0 and skipped == 0:
        click.echo("No matching repos found.")
        return

    click.echo("=" * 60)
    summary = f"Summary: {audited} repo(s) audited."
    if skipped:
        summary += f" {skipped} skipped."
    summary += f" {total_passed} passed, {total_failed} failed, {total_warnings} warnings."
    click.echo(summary)
    raise SystemExit(1 if total_failed > 0 else 0)


@cli.command("init")
@click.option(
    "--type",
    "repo_type",
    required=True,
    help="Repo type (e.g. cdk-app). Determines naming, branches, and rulesets.",
)
@click.pass_context
def init(ctx: click.Context, repo_type: str):
    """Create a GitHub repo and configure it to pass audit.

    Run from inside a local repo directory (after 'idea-app init').
    Creates the GitHub repo, pushes, and applies all standard settings,
    teams, branch protection, and security configuration.

    \b
    Example:
      cd gds-idea-app-my-dashboard
      idea-gh init --type cdk-app
    """
    from gds_idea_gh_kit.config import ConfigError, load_config
    from gds_idea_gh_kit.github_client import AuthError, GitHubClient, GitHubClientError
    from gds_idea_gh_kit.init import InitError, get_repo_name_from_directory, init_repo
    from gds_idea_gh_kit.version import check_tool_is_current

    # -- Check tool is current --
    check_tool_is_current()

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        raise click.ClickException(str(e))

    # Resolve type aliases (e.g. "pkg" -> "python-package")
    repo_type = _TYPE_ALIASES.get(repo_type, repo_type)

    if repo_type not in config.repo_types:
        raise click.ClickException(f"Unknown repo type '{repo_type}'. Available: {', '.join(config.repo_types.keys())}")

    repo_name = get_repo_name_from_directory()

    with GitHubClient(org=config.org) as client:
        try:
            client.verify_connection()
        except (GitHubClientError, AuthError) as e:
            raise click.ClickException(str(e))

        click.echo(f"Initialising {repo_name} as {repo_type}...\n")

        try:
            steps = init_repo(repo_name, config, repo_type, client)
        except InitError as e:
            raise click.ClickException(str(e))

        for step in steps:
            click.echo(f"  \u2713 {step}")

        click.echo("\nDone! Verify with: idea-gh audit --verbose")


@cli.command("rename")
@click.argument("new_name")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def rename(ctx: click.Context, new_name: str, yes: bool):
    """Rename the current repo. Run from inside the repo. Use with caution.

    This will break existing clones, CI/CD pipelines, and cross-repo
    references. GitHub sets up redirects for the old name, but they
    are not guaranteed to be permanent.
    """
    from gds_idea_gh_kit.config import ConfigError, load_config
    from gds_idea_gh_kit.github_client import AuthError, GitHubClient, GitHubClientError
    from gds_idea_gh_kit.repo_info import RepoInfoError, get_repo_from_remote

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        raise click.ClickException(str(e))

    try:
        owner, repo = get_repo_from_remote()
    except RepoInfoError as e:
        raise click.ClickException(str(e))

    if not yes:
        click.echo("WARNING: Renaming a repo has the following consequences:")
        click.echo("  - All existing git clones will have stale remote URLs")
        click.echo("  - CI/CD pipelines referencing the old name will break")
        click.echo("  - Cross-repo issue/PR references will not update")
        click.echo("  - GitHub redirects the old URL, but this is not permanent")
        click.echo()
        click.confirm(f"Rename '{owner}/{repo}' to '{owner}/{new_name}'?", abort=True)

    with GitHubClient(org=config.org) as client:
        try:
            client.verify_connection()
        except (GitHubClientError, AuthError) as e:
            raise click.ClickException(str(e))

        client.update_repo(owner, repo, name=new_name)
        click.echo(f"Renamed {owner}/{repo} -> {owner}/{new_name}")


@cli.command("remove-collaborators")
@click.argument("usernames", nargs=-1)
@click.option("--all", "remove_all", is_flag=True, help="Remove all direct collaborators.")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def remove_collaborators(ctx: click.Context, usernames: tuple[str, ...], remove_all: bool, yes: bool):
    """Remove direct collaborators from the current repo.

    Pass specific usernames to remove, or use --all to remove everyone.
    Run from inside the repo.

    \b
    Examples:
      idea-gh remove-collaborators jane-doe bob-smith
      idea-gh remove-collaborators --all
      idea-gh remove-collaborators --all --yes
    """
    from gds_idea_gh_kit.config import ConfigError, load_config
    from gds_idea_gh_kit.github_client import AuthError, GitHubClient, GitHubClientError
    from gds_idea_gh_kit.repo_info import RepoInfoError, get_repo_from_remote

    if not usernames and not remove_all:
        raise click.ClickException("Provide usernames to remove, or use --all to remove all direct collaborators.")

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        raise click.ClickException(str(e))

    try:
        owner, repo = get_repo_from_remote()
    except RepoInfoError as e:
        raise click.ClickException(str(e))

    with GitHubClient(org=config.org) as client:
        try:
            client.verify_connection()
        except (GitHubClientError, AuthError) as e:
            raise click.ClickException(str(e))

        collabs = client.list_direct_collaborators(owner, repo)
        collab_logins = {c["login"] for c in collabs}

        if not collabs:
            click.echo("No direct collaborators found.")
            return

        if remove_all:
            to_remove = collabs
        else:
            # Validate requested usernames exist as direct collaborators
            unknown = set(usernames) - collab_logins
            if unknown:
                raise click.ClickException(f"Not direct collaborators: {', '.join(sorted(unknown))}")
            to_remove = [c for c in collabs if c["login"] in usernames]

        click.echo(f"Will remove {len(to_remove)} direct collaborator(s) from {owner}/{repo}:")
        click.echo()
        for collab in to_remove:
            click.echo(f"  {collab['login']} ({collab.get('role_name', 'unknown')})")
        click.echo()

        if not yes:
            click.confirm(
                "Proceed? They will lose access unless they are also members of a team with repo access.",
                abort=True,
            )

        for collab in to_remove:
            username = collab["login"]
            client.remove_collaborator(owner, repo, username)
            click.echo(f"  Removed {username}")

        click.echo(f"\nRemoved {len(to_remove)} direct collaborator(s).")

@cli.command("show-id")
@click.option("--org", help="Show organisation ID.")
@click.option("--repo", help="Show repository ID.")
@click.pass_context
def show_id(ctx: click.Context, org: str, repo: str):
    """Show organisation or repo ID.

    \b
    Examples:
      idea-gh show-id
      idea-gh show-id --repo gds-idea-gh-kit
      idea-gh show-id --repo gds-idea-gh-kit --org co-cddo
    """
    from gds_idea_gh_kit.config import ConfigError, load_config
    from gds_idea_gh_kit.github_client import AuthError, GitHubClient, GitHubClientError
    from gds_idea_gh_kit.repo_info import RepoInfoError, get_repo_from_remote

    if org is None and repo is None:
        try:
            org, repo = get_repo_from_remote()
        except RepoInfoError as e:
            pass
    elif org is None:
        try:
            config = load_config(ctx.obj["config_path"])
            org = config.org
        except ConfigError as e:
            raise click.ClickException(str(e))

    with GitHubClient(org=org) as client:
        try:
            client.verify_connection()
        except (GitHubClientError, AuthError) as e:
            raise click.ClickException(str(e))

        try:
            org_id = client.get_org(org)["id"]
        except (GitHubClientError, AuthError) as e:
            raise click.ClickException(str(e))
        click.echo( f" Organisation: {org}, id: {org_id}" )

        if repo is not None:
            try:
                repo_id = client.get_repo(org, repo)["id"]
            except (GitHubClientError, AuthError) as e:
                raise click.ClickException(str(e))
            click.echo( f" Repository: {repo}, id: {repo_id}" )

        