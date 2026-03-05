"""Config loading helpers."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from gds_idea_gh_kit.models import Config

DEFAULT_CONFIG_FILENAME = "idea-gh.yml"


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def find_config(path: Path | None = None) -> Path:
    """Find the config file, searching standard locations."""
    if path is not None:
        if path.is_file():
            return path
        raise ConfigError(f"Config file not found: {path}")

    candidates = [
        Path.cwd() / DEFAULT_CONFIG_FILENAME,
        Path.home() / f".config/idea-gh/{DEFAULT_CONFIG_FILENAME}",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise ConfigError(
        f"No config file found. Searched:\n"
        + "\n".join(f"  - {c}" for c in candidates)
        + f"\n\nCreate an {DEFAULT_CONFIG_FILENAME} file or pass --config <path>."
    )


def load_config(path: Path | None = None) -> Config:
    """Load config from a YAML file. Pydantic handles all validation."""
    config_path = find_config(path)

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file must be a YAML mapping, got {type(raw).__name__}")

    try:
        return Config(**raw)
    except ValidationError as e:
        raise ConfigError(f"Invalid config:\n{e}") from e
