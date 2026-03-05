"""Tests for repo_info utility."""

import pytest

from gds_idea_gh_kit.repo_info import RepoInfoError, _parse_github_remote


def test_parse_ssh_remote():
    owner, repo = _parse_github_remote("git@github.com:co-cddo/gds-idea-app-foo.git")
    assert owner == "co-cddo"
    assert repo == "gds-idea-app-foo"


def test_parse_ssh_remote_no_git_suffix():
    owner, repo = _parse_github_remote("git@github.com:co-cddo/gds-idea-app-foo")
    assert owner == "co-cddo"
    assert repo == "gds-idea-app-foo"


def test_parse_https_remote():
    owner, repo = _parse_github_remote("https://github.com/co-cddo/gds-idea-app-foo.git")
    assert owner == "co-cddo"
    assert repo == "gds-idea-app-foo"


def test_parse_https_remote_no_git_suffix():
    owner, repo = _parse_github_remote("https://github.com/co-cddo/gds-idea-app-foo")
    assert owner == "co-cddo"
    assert repo == "gds-idea-app-foo"


def test_parse_non_github_remote():
    with pytest.raises(RepoInfoError, match="Could not parse"):
        _parse_github_remote("git@gitlab.com:co-cddo/foo.git")
