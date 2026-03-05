"""Tests for the security check."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.checks import security
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckStatus, SecurityConfig


def test_all_security_enabled(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    # vulnerability alerts: 204 means enabled
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/vulnerability-alerts",
        status_code=204,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/automated-security-fixes",
        json={"enabled": True},
    )

    expected = SecurityConfig(vulnerability_alerts=True, automated_security_fixes=True)
    results = security.audit("co-cddo", "my-repo", expected, gh_client)
    assert len(results) == 2
    assert all(r.status == CheckStatus.PASSED for r in results)


def test_vulnerability_alerts_disabled(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    # 404 means disabled
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/vulnerability-alerts",
        status_code=404,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/automated-security-fixes",
        json={"enabled": True},
    )

    expected = SecurityConfig(vulnerability_alerts=True, automated_security_fixes=True)
    results = security.audit("co-cddo", "my-repo", expected, gh_client)
    vuln_result = [r for r in results if "vulnerability" in r.name][0]
    assert vuln_result.status == CheckStatus.FAILED
    assert vuln_result.fix_available is True


def test_automated_fixes_disabled(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/vulnerability-alerts",
        status_code=204,
    )
    httpx_mock.add_response(
        url="https://api.github.com/repos/co-cddo/my-repo/automated-security-fixes",
        json={"enabled": False},
    )

    expected = SecurityConfig(vulnerability_alerts=True, automated_security_fixes=True)
    results = security.audit("co-cddo", "my-repo", expected, gh_client)
    auto_result = [r for r in results if "automated" in r.name][0]
    assert auto_result.status == CheckStatus.FAILED
    assert auto_result.fix_available is True
