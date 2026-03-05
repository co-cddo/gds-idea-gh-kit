"""Check that security settings (vulnerability alerts, dependabot) are enabled."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckResult, CheckStatus, SecurityConfig


def audit(
    owner: str, repo: str, expected: SecurityConfig, client: GitHubClient
) -> list[CheckResult]:
    """Check vulnerability alerts and automated security fixes."""
    results = []

    # Vulnerability alerts
    vuln_enabled = client.get_vulnerability_alerts_enabled(owner, repo)
    if vuln_enabled == expected.vulnerability_alerts:
        results.append(
            CheckResult(
                name="security.vulnerability_alerts",
                status=CheckStatus.PASSED,
                message=f"Vulnerability alerts: {vuln_enabled}",
            )
        )
    else:
        results.append(
            CheckResult(
                name="security.vulnerability_alerts",
                status=CheckStatus.FAILED,
                message=(
                    f"Vulnerability alerts: {vuln_enabled} "
                    f"(expected {expected.vulnerability_alerts})"
                ),
                fix_available=expected.vulnerability_alerts,  # can only enable, not disable
            )
        )

    # Automated security fixes
    auto_enabled = client.get_automated_security_fixes_enabled(owner, repo)
    if auto_enabled == expected.automated_security_fixes:
        results.append(
            CheckResult(
                name="security.automated_fixes",
                status=CheckStatus.PASSED,
                message=f"Automated security fixes: {auto_enabled}",
            )
        )
    else:
        results.append(
            CheckResult(
                name="security.automated_fixes",
                status=CheckStatus.FAILED,
                message=(
                    f"Automated security fixes: {auto_enabled} "
                    f"(expected {expected.automated_security_fixes})"
                ),
                fix_available=expected.automated_security_fixes,
            )
        )

    return results


def fix(
    owner: str, repo: str, expected: SecurityConfig, client: GitHubClient
) -> list[str]:
    """Enable security features as needed. Returns list of changes made."""
    changes = []

    if expected.vulnerability_alerts:
        if not client.get_vulnerability_alerts_enabled(owner, repo):
            client.enable_vulnerability_alerts(owner, repo)
            changes.append("Enabled vulnerability alerts")

    if expected.automated_security_fixes:
        if not client.get_automated_security_fixes_enabled(owner, repo):
            client.enable_automated_security_fixes(owner, repo)
            changes.append("Enabled automated security fixes")

    return changes
