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

    results = files.audit("co-cddo", "my-repo", [".gitignore", "LICENSE"], [], gh_client)
    assert len(results) == 2
    assert all(r.status == CheckStatus.PASSED for r in results)


def test_file_missing(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/.gitignore",
        json={"name": ".gitignore"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/README.md",
        status_code=404,
    )

    results = files.audit("co-cddo", "my-repo", [".gitignore", "README.md"], [], gh_client)
    passed = [r for r in results if r.status == CheckStatus.PASSED]
    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(passed) == 1
    assert len(failed) == 1
    assert "README.md" in failed[0].message
    assert failed[0].fix_available is False


def test_empty_required_files(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    results = files.audit("co-cddo", "my-repo", [], [], gh_client)
    assert len(results) == 0


def test_workflows_exist(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/.github/workflows/lint.yml",
        json={"name": "lint.yml"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/.github/workflows/test.yml",
        json={"name": "test.yml"},
    )

    results = files.audit("co-cddo", "my-repo", [], ["lint.yml", "test.yml"], gh_client)
    assert len(results) == 2
    assert all(r.status == CheckStatus.PASSED for r in results)
    assert all("workflow" in r.name for r in results)


def test_workflow_missing(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/.github/workflows/lint.yml",
        json={"name": "lint.yml"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/.github/workflows/cdk-deploy-dev.yml",
        status_code=404,
    )

    results = files.audit(
        "co-cddo", "my-repo", [], ["lint.yml", "cdk-deploy-dev.yml"], gh_client
    )
    passed = [r for r in results if r.status == CheckStatus.PASSED]
    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(passed) == 1
    assert len(failed) == 1
    assert "cdk-deploy-dev.yml" in failed[0].message
    assert ".github/workflows/" in failed[0].message


def test_files_and_workflows_combined(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/README.md",
        json={"name": "README.md"},
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/contents/.github/workflows/lint.yml",
        json={"name": "lint.yml"},
    )

    results = files.audit("co-cddo", "my-repo", ["README.md"], ["lint.yml"], gh_client)
    assert len(results) == 2
    assert all(r.status == CheckStatus.PASSED for r in results)
