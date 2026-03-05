"""CLI entry point for idea-gh."""

from __future__ import annotations

from pathlib import Path

import click

from gds_idea_gh_kit import __version__


@click.group()
@click.version_option(version=__version__, prog_name="idea-gh")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to idea-gh.yml config file.",
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
    click.echo(f"  Team prefix: {config.team_prefix}")
    click.echo(f"  Visibility: {config.default_visibility}")
    click.echo(f"  Teams: {len(config.teams)}")
    click.echo(f"  Repo types: {', '.join(config.repo_types.keys())}")
    click.echo(f"  Required files: {len(config.required_files)}")


@cli.command("audit")
@click.option("--type", "repo_type", default=None, help="Override repo type detection.")
@click.option("--all", "audit_all", is_flag=True, help="Audit all repos in the org.")
@click.option("--verbose", is_flag=True, help="Show all checks including passing.")
@click.pass_context
def audit(ctx: click.Context, repo_type: str | None, audit_all: bool, verbose: bool):
    """Audit repo(s) against the configured standards.

    Run from inside a repo to audit that repo, or use --all to audit
    every repo in the org that matches a known naming pattern.
    """
    from gds_idea_gh_kit.audit import audit_repo, render_report
    from gds_idea_gh_kit.config import ConfigError, load_config
    from gds_idea_gh_kit.github_client import GitHubClient
    from gds_idea_gh_kit.repo_info import RepoInfoError, get_repo_from_remote

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        raise click.ClickException(str(e))

    if repo_type and repo_type not in config.repo_types:
        raise click.ClickException(
            f"Unknown repo type '{repo_type}'. "
            f"Available: {', '.join(config.repo_types.keys())}"
        )

    with GitHubClient(org=config.org) as client:
        if audit_all:
            _audit_all_repos(config, client, repo_type, verbose=verbose)
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
            raise SystemExit(1 if report.failed > 0 else 0)


def _audit_all_repos(
    config: "Config", client: "GitHubClient", repo_type_filter: str | None,
    verbose: bool = False,
):
    """Audit all matching repos in the org."""
    repos = client.list_org_repos(config.org)
    total_passed = 0
    total_failed = 0
    total_warnings = 0
    audited = 0

    from gds_idea_gh_kit.audit import audit_repo, render_report

    for repo_data in repos:
        repo_name = repo_data["name"]
        detected_type = config.detect_repo_type(repo_name)

        if detected_type is None:
            continue

        if repo_type_filter and detected_type != repo_type_filter:
            continue

        report = audit_repo(config.org, repo_name, config, client, detected_type)
        click.echo(render_report(report, verbose=verbose))
        click.echo()

        total_passed += report.passed
        total_failed += report.failed
        total_warnings += report.warnings
        audited += 1

    if audited == 0:
        click.echo("No matching repos found.")
        return

    click.echo("=" * 60)
    click.echo(
        f"Summary: {audited} repo(s) audited. "
        f"{total_passed} passed, {total_failed} failed, {total_warnings} warnings."
    )
    raise SystemExit(1 if total_failed > 0 else 0)


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
    from gds_idea_gh_kit.github_client import GitHubClient
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
        click.confirm(
            f"Rename '{owner}/{repo}' to '{owner}/{new_name}'?", abort=True
        )

    with GitHubClient(org=config.org) as client:
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
    from gds_idea_gh_kit.github_client import GitHubClient
    from gds_idea_gh_kit.repo_info import RepoInfoError, get_repo_from_remote

    if not usernames and not remove_all:
        raise click.ClickException(
            "Provide usernames to remove, or use --all to remove all direct collaborators."
        )

    try:
        config = load_config(ctx.obj["config_path"])
    except ConfigError as e:
        raise click.ClickException(str(e))

    try:
        owner, repo = get_repo_from_remote()
    except RepoInfoError as e:
        raise click.ClickException(str(e))

    with GitHubClient(org=config.org) as client:
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
                raise click.ClickException(
                    f"Not direct collaborators: {', '.join(sorted(unknown))}"
                )
            to_remove = [c for c in collabs if c["login"] in usernames]

        click.echo(f"Will remove {len(to_remove)} direct collaborator(s) from {owner}/{repo}:")
        click.echo()
        for collab in to_remove:
            click.echo(f"  {collab['login']} ({collab.get('role_name', 'unknown')})")
        click.echo()

        if not yes:
            click.confirm(
                "Proceed? They will lose access unless they are also "
                "members of a team with repo access.",
                abort=True,
            )

        for collab in to_remove:
            username = collab["login"]
            client.remove_collaborator(owner, repo, username)
            click.echo(f"  Removed {username}")

        click.echo(f"\nRemoved {len(to_remove)} direct collaborator(s).")
