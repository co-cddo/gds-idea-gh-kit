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
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def remove_collaborators(ctx: click.Context, yes: bool):
    """Remove all direct collaborators from the current repo.

    Lists individual users who have been granted access directly
    (not via a team) and removes them after confirmation.
    Run from inside the repo.
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

    with GitHubClient(org=config.org) as client:
        collabs = client.list_direct_collaborators(owner, repo)

        if not collabs:
            click.echo("No direct collaborators found.")
            return

        click.echo(f"Found {len(collabs)} direct collaborator(s) on {owner}/{repo}:")
        click.echo()
        for collab in collabs:
            username = collab["login"]
            permission = collab.get("role_name", "unknown")
            click.echo(f"  {username} ({permission})")
        click.echo()

        if not yes:
            click.confirm(
                "Remove all direct collaborators? They will lose access "
                "unless they are also members of a team with repo access.",
                abort=True,
            )

        for collab in collabs:
            username = collab["login"]
            client.remove_collaborator(owner, repo, username)
            click.echo(f"  Removed {username}")

        click.echo(f"\nRemoved {len(collabs)} direct collaborator(s).")
