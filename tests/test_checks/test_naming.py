"""Tests for the naming check."""

from gds_idea_gh_kit.checks import naming
from gds_idea_gh_kit.models import CheckStatus, RepoTypeConfig


def test_name_matches_pattern():
    rt = RepoTypeConfig(naming_pattern="gds-idea-app-{name}", default_branch="dev")
    results = naming.audit("gds-idea-app-my-dashboard", rt)
    assert len(results) == 1
    assert results[0].status == CheckStatus.PASSED


def test_name_does_not_match():
    rt = RepoTypeConfig(naming_pattern="gds-idea-app-{name}", default_branch="dev")
    results = naming.audit("random-repo-name", rt)
    assert len(results) == 1
    assert results[0].status == CheckStatus.FAILED
    assert results[0].fix_available is False
    assert "random-repo-name" in results[0].message
    assert "idea-gh rename" in results[0].message
    assert "breaks existing clones" in results[0].message


def test_python_package_pattern():
    rt = RepoTypeConfig(naming_pattern="gds-idea-{name}", default_branch="main")
    results = naming.audit("gds-idea-utils", rt)
    assert results[0].status == CheckStatus.PASSED

    results = naming.audit("some-other-repo", rt)
    assert results[0].status == CheckStatus.FAILED
