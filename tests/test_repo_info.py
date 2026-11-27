"""Tests for repo_info utility."""

import pytest

from gds_idea_gh_kit.repo_info import RepoInfoError, parse_github_remote, rewrite_remote_owner


def test_parse_ssh_remote():
    owner, repo = parse_github_remote("git@github.com:co-cddo/gds-idea-app-foo.git")
    assert owner == "co-cddo"
    assert repo == "gds-idea-app-foo"


def test_parse_ssh_remote_no_git_suffix():
    owner, repo = parse_github_remote("git@github.com:co-cddo/gds-idea-app-foo")
    assert owner == "co-cddo"
    assert repo == "gds-idea-app-foo"


def test_parse_https_remote():
    owner, repo = parse_github_remote("https://github.com/co-cddo/gds-idea-app-foo.git")
    assert owner == "co-cddo"
    assert repo == "gds-idea-app-foo"


def test_parse_https_remote_no_git_suffix():
    owner, repo = parse_github_remote("https://github.com/co-cddo/gds-idea-app-foo")
    assert owner == "co-cddo"
    assert repo == "gds-idea-app-foo"


def test_parse_non_github_remote():
    with pytest.raises(RepoInfoError, match="Could not parse"):
        parse_github_remote("git@gitlab.com:co-cddo/foo.git")


def test_rewrite_remote_owner_ssh():
    url = rewrite_remote_owner("git@github.com:co-cddo/gds-idea-app-foo.git", "gds-dtx")
    assert url == "git@github.com:gds-dtx/gds-idea-app-foo.git"


def test_rewrite_remote_owner_https_with_git_suffix():
    url = rewrite_remote_owner("https://github.com/co-cddo/gds-idea-app-foo.git", "gds-dtx")
    assert url == "https://github.com/gds-dtx/gds-idea-app-foo.git"


def test_rewrite_remote_owner_https_without_git_suffix():
    url = rewrite_remote_owner("https://github.com/co-cddo/gds-idea-app-foo", "gds-dtx")
    assert url == "https://github.com/gds-dtx/gds-idea-app-foo"
