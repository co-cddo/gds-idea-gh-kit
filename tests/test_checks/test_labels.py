"""Tests for the labels check."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.checks import labels
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckStatus, LabelConfig

BASE = "https://api.github.com"

_CONFIGURED = [
    LabelConfig(name="bump:major", color="d73a4a", description="Release: major version bump"),
    LabelConfig(name="bump:minor", color="0e8a16", description="Release: minor version bump"),
    LabelConfig(name="bump:patch", color="e4e669", description="Release: patch version bump (default)"),
]


def test_all_labels_present(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """All configured labels exist -> all pass."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/labels",
        json=[
            {"name": "bump:major", "color": "d73a4a", "description": "Release: major version bump"},
            {"name": "bump:minor", "color": "0e8a16", "description": "Release: minor version bump"},
            {"name": "bump:patch", "color": "e4e669", "description": "Release: patch version bump (default)"},
        ],
    )

    results = labels.audit("co-cddo", "my-repo", _CONFIGURED, gh_client)
    assert len(results) == 3
    assert all(r.status == CheckStatus.PASSED for r in results)


def test_missing_label_fails(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """A missing label produces a FAILED result with fix_available=True."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/labels",
        json=[
            {"name": "bump:minor", "color": "0e8a16", "description": ""},
            {"name": "bump:patch", "color": "e4e669", "description": ""},
        ],
    )

    results = labels.audit("co-cddo", "my-repo", _CONFIGURED, gh_client)
    failed = [r for r in results if r.status == CheckStatus.FAILED]
    assert len(failed) == 1
    assert "bump:major" in failed[0].name
    assert failed[0].fix_available is True


def test_all_labels_missing(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """All labels missing -> all fail with fix_available."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/labels",
        json=[],
    )

    results = labels.audit("co-cddo", "my-repo", _CONFIGURED, gh_client)
    assert len(results) == 3
    assert all(r.status == CheckStatus.FAILED for r in results)
    assert all(r.fix_available for r in results)


def test_no_configured_labels_returns_empty(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """Empty label config -> no API call, no results."""
    results = labels.audit("co-cddo", "my-repo", [], gh_client)
    assert results == []


def test_fix_creates_missing_labels(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """fix() creates labels that are missing."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/labels",
        json=[
            {"name": "bump:minor", "color": "0e8a16", "description": "Release: minor version bump"},
            {"name": "bump:patch", "color": "e4e669", "description": "Release: patch version bump (default)"},
        ],
    )
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/labels",
        method="POST",
        json={"name": "bump:major", "color": "d73a4a", "description": "Release: major version bump"},
        status_code=201,
    )

    changes = labels.fix("co-cddo", "my-repo", _CONFIGURED, gh_client)
    assert len(changes) == 1
    assert "bump:major" in changes[0]
    assert "Created" in changes[0]


def test_fix_updates_label_with_wrong_colour(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """fix() updates labels whose colour doesn't match config."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/labels",
        json=[
            {"name": "bump:major", "color": "ffffff", "description": "Release: major version bump"},
            {"name": "bump:minor", "color": "0e8a16", "description": "Release: minor version bump"},
            {"name": "bump:patch", "color": "e4e669", "description": "Release: patch version bump (default)"},
        ],
    )
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/labels/bump:major",
        method="PATCH",
        json={"name": "bump:major", "color": "d73a4a", "description": "Release: major version bump"},
    )

    changes = labels.fix("co-cddo", "my-repo", _CONFIGURED, gh_client)
    assert len(changes) == 1
    assert "bump:major" in changes[0]
    assert "Updated" in changes[0]


def test_fix_no_changes_when_all_match(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """fix() returns empty list when all labels already match."""
    httpx_mock.add_response(
        url=f"{BASE}/repos/co-cddo/my-repo/labels",
        json=[
            {"name": "bump:major", "color": "d73a4a", "description": "Release: major version bump"},
            {"name": "bump:minor", "color": "0e8a16", "description": "Release: minor version bump"},
            {"name": "bump:patch", "color": "e4e669", "description": "Release: patch version bump (default)"},
        ],
    )

    changes = labels.fix("co-cddo", "my-repo", _CONFIGURED, gh_client)
    assert changes == []


def test_fix_empty_config_returns_empty(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    """fix() with no configured labels -> no API calls, no changes."""
    changes = labels.fix("co-cddo", "my-repo", [], gh_client)
    assert changes == []
