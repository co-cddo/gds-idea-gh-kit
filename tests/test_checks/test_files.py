"""Tests for the files check."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.checks import files
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckStatus


def test_all_files_exist(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/.gitignore",
        json={"name": ".gitignore"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/LICENSE",
        json={"name": "LICENSE"},
    )

    results = files.audit("co-cddo", "my-repo", [".gitignore", "LICENSE"], gh_client)
    assert len(results) == 2
    assert all(r.status == CheckStatus.PASSED for r in results)


def test_file_missing(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/.gitignore",
        json={"name": ".gitignore"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/CODEOWNERS",
        status_code=404,
    )

    results = files.audit("co-cddo", "my-repo", [".gitignore", "CODEOWNERS"], gh_client)
    passed = [r for r in results if r.status == CheckStatus.PASSED]
    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(passed) == 1
    assert len(failed) == 1
    assert "CODEOWNERS" in failed[0].message
    assert failed[0].fix_available is False  # can't auto-create files


def test_empty_required_files(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    results = files.audit("co-cddo", "my-repo", [], gh_client)
    assert len(results) == 0
