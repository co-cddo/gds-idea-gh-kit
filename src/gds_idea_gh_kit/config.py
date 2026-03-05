"""Config loading helpers."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from gds_idea_gh_kit.models import Config

_BUNDLED_CONFIG = Path(__file__).parent / "config.yml"


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def find_config(path: Path | None = None) -> Path:
    """Find the config file.

    If an explicit path is given, use it (or raise if missing).
    Otherwise fall back to the config bundled with the package.
    """
    if path is not None:
        if path.is_file():
            return path
        raise ConfigError(f"Config file not found: {path}")

    return _BUNDLED_CONFIG


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
