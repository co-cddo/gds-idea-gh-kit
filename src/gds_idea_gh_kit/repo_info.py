"""Utilities for inferring repo info from the local git checkout."""

from __future__ import annotations

import re
import subprocess


class RepoInfoError(Exception):
    """Raised when we can't determine repo info from the local checkout."""


def get_repo_from_remote() -> tuple[str, str]:
    """Infer the GitHub owner and repo name from the current directory's git remote.

    Returns (owner, repo) e.g. ("co-cddo", "gds-idea-app-my-dashboard").
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except FileNotFoundError:
        raise RepoInfoError("git is not installed or not on PATH.")
    except subprocess.CalledProcessError:
        raise RepoInfoError("Could not read git remote 'origin'. Are you inside a git repo with a remote configured?")

    url = result.stdout.strip()
    return parse_github_remote(url)


def parse_github_remote(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub remote URL.

    Supports:
        git@github.com:co-cddo/gds-idea-app-foo.git
        https://github.com/co-cddo/gds-idea-app-foo.git
        https://github.com/co-cddo/gds-idea-app-foo
    """
    # SSH format
    match = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if match:
        return match.group(1), match.group(2)

    # HTTPS format
    match = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if match:
        return match.group(1), match.group(2)

    raise RepoInfoError(f"Could not parse GitHub owner/repo from remote URL: {url}")


def rewrite_remote_owner(url: str, new_owner: str) -> str:
    """Return `url` with its owner replaced by `new_owner`, preserving format.

    Supports the same SSH and HTTPS forms as `parse_github_remote`.
    """
    _, repo = parse_github_remote(url)

    if url.startswith("git@github.com:"):
        return f"git@github.com:{new_owner}/{repo}.git"

    suffix = ".git" if url.endswith(".git") else ""
    return f"https://github.com/{new_owner}/{repo}{suffix}"
