"""Tests for config loading and pydantic validation."""

import pytest
from pydantic import ValidationError

from gds_idea_gh_kit.config import ConfigError, load_config
from gds_idea_gh_kit.models import Config, RepoTypeConfig

# --- Loading from file ---


def test_load_bundled_config():
    """Loading with no path should use the bundled config."""
    config = load_config()
    assert config.org == "co-cddo"
    assert len(config.repo_types) > 0
    assert len(config.repo_prefixes) > 0
    # Each repo type should have detection files (except name-only types like econ)
    name_only_types = {"econ"}
    for type_name, type_config in config.repo_types.items():
        if type_name not in name_only_types:
            assert len(type_config.detection_files) > 0, f"{type_name} has no detection_files"


def test_load_custom_config(tmp_path):
    """A custom config file should load when passed explicitly."""
    config_file = tmp_path / "idea-gh.yml"
    config_file.write_text(
        """\
org: co-cddo
default_visibility: private
teams:
  cddo-idea-admins: admin
  cddo-idea-developers: write
repo_settings:
  delete_branch_on_merge: true
  allow_squash_merge: true
required_files:
  - .gitignore
  - LICENSE
security:
  vulnerability_alerts: true
repo_types:
  cdk-app:
    naming_pattern: "gds-idea-app-{name}"
    default_branch: dev
    branch_protection:
      dev:
        require_pr: true
        required_approvals: 1
"""
    )
    config = load_config(config_file)
    assert config.org == "co-cddo"
    assert "cddo-idea-admins" in config.teams
    assert "cdk-app" in config.repo_types
    assert config.repo_types["cdk-app"].default_branch == "dev"


def test_load_minimal_config(tmp_path):
    """Only org is truly required."""
    config_file = tmp_path / "idea-gh.yml"
    config_file.write_text(
        """\
org: myorg
"""
    )
    config = load_config(config_file)
    assert config.org == "myorg"
    assert config.default_visibility == "private"  # default


def test_load_missing_file():
    """Should raise ConfigError for a nonexistent path."""
    from pathlib import Path

    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(Path("/nonexistent/idea-gh.yml"))


def test_load_empty_file(tmp_path):
    """An empty YAML file should raise ConfigError."""
    config_file = tmp_path / "idea-gh.yml"
    config_file.write_text("")
    with pytest.raises(ConfigError, match="YAML mapping"):
        load_config(config_file)


# --- Validation ---


def test_missing_org():
    with pytest.raises(ValidationError, match="org"):
        Config()


def test_invalid_visibility():
    with pytest.raises(ValidationError, match="public.*private.*internal"):
        Config(org="co-cddo", default_visibility="secret")


def test_invalid_team_permission():
    with pytest.raises(ValidationError, match="invalid permission"):
        Config(org="co-cddo", teams={"myteam": "superadmin"})


def test_naming_pattern_requires_placeholder():
    with pytest.raises(ValidationError, match="\\{name\\}"):
        RepoTypeConfig(naming_pattern="no-placeholder", default_branch="main")


def test_invalid_extra_team_permission():
    with pytest.raises(ValidationError, match="invalid permission"):
        RepoTypeConfig(
            naming_pattern="gds-idea-econ-{name}",
            default_branch="main",
            extra_teams={"gds-idea-econ": "superadmin"},
        )


def test_extra_fields_rejected():
    with pytest.raises(ValidationError, match="extra"):
        Config(org="co-cddo", bogus_field="oops")


# --- RepoTypeConfig matching ---


def test_matches_name():
    rt = RepoTypeConfig(naming_pattern="gds-idea-app-{name}", default_branch="dev")
    assert rt.matches_name("gds-idea-app-my-dashboard") is True
    assert rt.matches_name("gds-idea-app-x") is True
    assert rt.matches_name("gds-idea-app-") is False
    assert rt.matches_name("other-repo") is False


def test_extract_name():
    rt = RepoTypeConfig(naming_pattern="gds-idea-app-{name}", default_branch="dev")
    assert rt.extract_name("gds-idea-app-my-dashboard") == "my-dashboard"
    assert rt.extract_name("other-repo") is None


def test_econ_naming_pattern():
    rt = RepoTypeConfig(naming_pattern="gds-idea-econ-{name}", default_branch="main")
    assert rt.matches_name("gds-idea-econ-housing") is True
    assert rt.matches_name("gds-idea-econ-trade-model") is True
    assert rt.matches_name("gds-idea-econ-") is False
    assert rt.matches_name("gds-idea-app-foo") is False
    assert rt.matches_name("gds-idea-housing") is False
    assert rt.extract_name("gds-idea-econ-housing") == "housing"


def test_has_known_prefix():
    config = Config(
        org="co-cddo",
        repo_prefixes=["gds-idea-"],
        repo_types={
            "cdk-app": RepoTypeConfig(naming_pattern="gds-idea-app-{name}", default_branch="dev"),
            "python-package": RepoTypeConfig(naming_pattern="gds-idea-pkg-{name}", default_branch="main"),
        },
    )
    assert config.has_known_prefix("gds-idea-app-foo") is True
    assert config.has_known_prefix("gds-idea-pkg-utils") is True
    assert config.has_known_prefix("gds-idea-chai") is True
    assert config.has_known_prefix("random-repo") is False
    assert config.has_known_prefix("something-else") is False
