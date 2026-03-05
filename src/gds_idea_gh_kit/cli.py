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
