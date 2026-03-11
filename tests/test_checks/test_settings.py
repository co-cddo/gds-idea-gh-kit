"""Tests for the settings check."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.checks import settings
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckStatus, RepoSettings

REPO_RESPONSE = {
    "name": "gds-idea-app-foo",
    "delete_branch_on_merge": True,
    "allow_squash_merge": True,
    "allow_merge_commit": False,
    "allow_rebase_merge": False,
    "has_issues": True,
    "has_wiki": False,
    "has_projects": False,
}


def test_all_settings_match(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/gds-idea-app-foo",
        json=REPO_RESPONSE,
    )
    expected = RepoSettings()  # defaults match REPO_RESPONSE
    results = settings.audit("co-cddo", "gds-idea-app-foo", expected, gh_client)
    assert all(r.status == CheckStatus.PASSED for r in results)
    assert len(results) == 7


def test_settings_mismatch(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    bad_repo = {**REPO_RESPONSE, "has_wiki": True, "allow_merge_commit": True}
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/gds-idea-app-foo",
        json=bad_repo,
    )
    expected = RepoSettings()
    results = settings.audit("co-cddo", "gds-idea-app-foo", expected, gh_client)

    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(failed) == 2
    names = {r.name for r in failed}
    assert "settings.has_wiki" in names
    assert "settings.allow_merge_commit" in names
    assert all(r.fix_available for r in failed)


def test_fix_applies_changes(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    bad_repo = {**REPO_RESPONSE, "has_wiki": True}
    # get_repo called twice: once in audit within fix, once for the PATCH
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/gds-idea-app-foo",
        json=bad_repo,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/gds-idea-app-foo",
        method="PATCH",
        json={**REPO_RESPONSE},
    )
    expected = RepoSettings()
    changes = settings.fix("co-cddo", "gds-idea-app-foo", expected, gh_client)
    assert len(changes) == 1
    assert "has_wiki" in changes[0]
