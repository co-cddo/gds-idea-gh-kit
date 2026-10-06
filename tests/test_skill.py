"""Tests that the agent skill in skills/idea-gh-usage stays in step with the CLI and the built-in config.

The skill is read by AI agents to decide which commands to run, so a stale command, flag, repo
naming pattern or team name there means agents give wrong instructions.
"""

from __future__ import annotations

import re
from pathlib import Path

import click
import pytest

from gds_idea_gh_kit.cli import cli
from gds_idea_gh_kit.config import load_config

SKILL_DIR = Path(__file__).parent.parent / "skills" / "idea-gh-usage"
SKILL = SKILL_DIR / "SKILL.md"
PROGRAM = "idea-gh"


def _skill_text() -> str:
    return SKILL.read_text()


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n"), "SKILL.md must start with frontmatter"
    block = text.split("\n---\n", 1)[0].removeprefix("---\n")
    return dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(" "))


def _code(text: str) -> list[str]:
    """Every line of code in the skill: fenced blocks and inline `code` spans."""
    blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    without_blocks = re.sub(r"```.*?```", "", text, flags=re.S)
    return [line for block in blocks for line in block.splitlines()] + re.findall(r"`([^`\n]+)`", without_blocks)


def _invocations() -> list[list[str]]:
    """Each ``idea-gh ...`` command line shown in the skill, as tokens (shell comments removed)."""
    found = []
    for line in _code(_skill_text()):
        line = line.split(" #", 1)[0]
        match = re.search(rf"(?:^|\s){PROGRAM}(?:\s+(.*))?$", line.strip())
        if match and match.group(1):
            found.append(match.group(1).split())
    return found


def _options(command: click.Command) -> set[str]:
    return {opt for param in command.params for opt in [*param.opts, *param.secondary_opts]} | {"--help"}


def test_the_skill_exists_and_has_valid_frontmatter():
    fields = _frontmatter(_skill_text())

    assert fields["name"] == SKILL_DIR.name == "idea-gh-usage"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fields["name"])
    assert 0 < len(fields["description"]) <= 1024


def test_the_description_says_when_to_use_the_skill():
    assert "Use when" in _frontmatter(_skill_text())["description"]


def test_the_skill_shows_a_realistic_number_of_commands():
    assert len(_invocations()) >= 15


@pytest.mark.parametrize("tokens", _invocations(), ids=lambda t: " ".join(t)[:50])
def test_every_command_and_flag_shown_in_the_skill_exists(tokens):
    group_options = _options(cli)
    index = 0
    while index < len(tokens) and tokens[index].startswith("-"):  # options of the group, before the command
        assert tokens[index] in group_options, f"unknown global option {tokens[index]}"
        index += 2 if tokens[index] == "--config" else 1
    if index == len(tokens):
        return

    name = tokens[index]
    assert name in cli.commands, f"'{PROGRAM} {name}' is not a command; the commands are {sorted(cli.commands)}"
    allowed = _options(cli.commands[name])
    flags = [t.split("=", 1)[0] for t in tokens[index + 1 :] if t.startswith("--")]
    unknown = [flag for flag in flags if flag not in allowed]
    assert not unknown, f"'{PROGRAM} {name}' has no option(s) {unknown}; it has {sorted(allowed)}"


def test_every_command_is_covered_by_the_skill():
    mentioned = {tokens[0] for tokens in _invocations() if tokens and not tokens[0].startswith("-")}

    assert set(cli.commands) <= mentioned, f"commands the skill never shows: {sorted(set(cli.commands) - mentioned)}"


def test_every_repo_type_is_documented_with_its_naming_pattern_and_branch():
    text = _skill_text()
    config = load_config()

    for name, repo_type in config.repo_types.items():
        assert f"`{name}`" in text, f"repo type {name} is not in the skill"
        assert f"`{repo_type.naming_pattern}`" in text, f"naming pattern {repo_type.naming_pattern} is not in the skill"
        assert f"`{repo_type.default_branch}`" in text, f"default branch {repo_type.default_branch} is not in the skill"
        for marker in repo_type.detection_files:
            assert f"`{marker}`" in text, f"detection file {marker} is not in the skill"


def test_the_teams_and_labels_the_tool_manages_are_named_in_the_skill():
    text = _skill_text()
    config = load_config()

    for team in config.teams:
        assert f"`{team}`" in text, f"team {team} is not in the skill"
    for label in config.labels:
        assert f"`{label.name}`" in text, f"label {label.name} is not in the skill"


def test_the_skill_does_not_carry_the_old_naming_pattern():
    assert "gds-idea-{name}`" not in _skill_text().replace("gds-idea-app-{name}", "").replace("gds-idea-pkg-{name}", "")
