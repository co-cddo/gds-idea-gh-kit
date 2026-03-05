"""Tests for the audit orchestration, fix orchestration, and report rendering."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.audit import audit_repo, fix_repo, render_report
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import (
    AuditReport,
    BranchProtectionConfig,
    CheckResult,
    CheckStatus,
    Config,
    FixReport,
    RepoSettings,
    RepoTypeConfig,
    SecurityConfig,
)


def _minimal_config() -> Config:
    return Config(
        org="co-cddo",
        teams={"cddo-admins": "admin"},
        repo_settings=RepoSettings(),
        required_files=[".gitignore"],
        security=SecurityConfig(),
        repo_types={
            "cdk-app": RepoTypeConfig(
                naming_pattern="gds-idea-app-{name}",
                default_branch="dev",
                required_workflows=["lint.yml"],
                branch_protection={
                    "dev": BranchProtectionConfig(
                        prevent_deletion=True,
                        prevent_force_push=True,
                    ),
                },
            ),
        },
    )


def _mock_passing_repo(httpx_mock: HTTPXMock):
    """Mock all API calls for a fully compliant repo."""
    base = "https://api.github.com"

    repo_json = {
        "name": "gds-idea-app-foo",
        "default_branch": "dev",
        "visibility": "private",
        "delete_branch_on_merge": True,
        "allow_squash_merge": True,
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "has_issues": True,
        "has_wiki": False,
        "has_projects": False,
    }

    # get_repo is called by settings.audit and branches.audit
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo",
        json=repo_json,
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo",
        json=repo_json,
    )

    # Teams
    httpx_mock.add_response(
        url=f"{base}/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/gds-idea-app-foo",
        json={"role_name": "admin"},
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/teams",
        json=[{"slug": "cddo-admins", "permission": "admin"}],
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/collaborators?affiliation=direct",
        json=[],
    )

    # Branches — classic protection (none)
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/branches/dev/protection",
        status_code=404,
    )

    # Rulesets
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/rulesets",
        json=[{"id": 1, "name": "idea-gh: dev"}],
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/rulesets/1",
        json={
            "id": 1,
            "name": "idea-gh: dev",
            "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/dev"], "exclude": []}},
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {
                    "type": "pull_request",
                    "parameters": {
                        "required_approving_review_count": 1,
                        "dismiss_stale_reviews_on_push": True,
                    },
                },
            ],
            "bypass_actors": [],
        },
    )

    # Files
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/contents/.gitignore",
        json={"name": ".gitignore"},
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/contents/.github/workflows/lint.yml",
        json={"name": "lint.yml"},
    )

    # Security
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/vulnerability-alerts",
        status_code=204,
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/automated-security-fixes",
        json={"enabled": True},
    )


def test_audit_repo_all_pass(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    config = _minimal_config()
    _mock_passing_repo(httpx_mock)

    report = audit_repo("co-cddo", "gds-idea-app-foo", config, gh_client)

    assert report.repo_type == "cdk-app"
    assert report.failed == 0
    assert report.passed > 0


def test_audit_repo_unknown_type(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    config = _minimal_config()
    report = audit_repo("co-cddo", "unknown-repo", config, gh_client)

    assert report.repo_type == "unknown"
    assert len(report.results) == 0


def test_audit_repo_explicit_type(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    config = _minimal_config()
    _mock_passing_repo(httpx_mock)

    # Force type even though the name matches anyway
    report = audit_repo("co-cddo", "gds-idea-app-foo", config, gh_client, repo_type="cdk-app")
    assert report.repo_type == "cdk-app"
    assert report.failed == 0


# --- Report rendering ---


def test_render_report_all_passing():
    """All passing — short summary, no individual checks shown."""
    report = AuditReport(
        repo_name="co-cddo/gds-idea-app-foo",
        repo_type="cdk-app",
        results=[
            CheckResult(name="naming", status=CheckStatus.PASSED, message="Name matches"),
            CheckResult(name="settings.wiki", status=CheckStatus.PASSED, message="Wiki: False"),
        ],
    )
    output = render_report(report)
    assert "co-cddo/gds-idea-app-foo" in output
    assert "cdk-app" in output
    assert "All 2 checks passed" in output
    # Individual checks should NOT appear in default mode
    assert "Name matches" not in output


def test_render_report_all_passing_verbose():
    """Verbose shows individual passing checks."""
    report = AuditReport(
        repo_name="co-cddo/gds-idea-app-foo",
        repo_type="cdk-app",
        results=[
            CheckResult(name="naming", status=CheckStatus.PASSED, message="Name matches"),
            CheckResult(name="settings.wiki", status=CheckStatus.PASSED, message="Wiki: False"),
        ],
    )
    output = render_report(report, verbose=True)
    assert "Name matches" in output
    assert "Wiki: False" in output
    assert "\u2713" in output


def test_render_report_grouped_output():
    """Default output groups by auto-fixable / manual / warnings."""
    report = AuditReport(
        repo_name="co-cddo/gds-idea-app-foo",
        repo_type="cdk-app",
        results=[
            CheckResult(name="naming", status=CheckStatus.PASSED, message="Name matches"),
            CheckResult(
                name="settings.wiki",
                status=CheckStatus.FAILED,
                message="Wiki: True (expected False)",
                fix_available=True,
            ),
            CheckResult(
                name="files.dependabot",
                status=CheckStatus.FAILED,
                message="Required file missing: .github/dependabot.yml",
                fix_available=False,
            ),
            CheckResult(
                name="teams.unexpected",
                status=CheckStatus.WARNING,
                message="Unexpected team found",
            ),
        ],
    )
    output = render_report(report)

    # Sections should appear in order
    assert "Auto-fixable" in output
    assert "Manual fixes needed" in output
    assert "Warnings" in output

    # Passing checks hidden
    assert "Name matches" not in output

    # Summary
    assert "1 passed, 2 failed, 1 warning" in output
    assert "1 issue(s) can be auto-fixed" in output


def test_render_report_only_auto_fixable():
    """Only auto-fixable failures — no manual section shown."""
    report = AuditReport(
        repo_name="co-cddo/gds-idea-app-foo",
        repo_type="cdk-app",
        results=[
            CheckResult(
                name="settings.wiki",
                status=CheckStatus.FAILED,
                message="Wiki: True (expected False)",
                fix_available=True,
            ),
        ],
    )
    output = render_report(report)
    assert "Auto-fixable" in output
    assert "Manual fixes needed" not in output
    assert "Warnings" not in output


def test_render_report_with_warnings_only():
    report = AuditReport(
        repo_name="co-cddo/gds-idea-app-foo",
        repo_type="cdk-app",
        results=[
            CheckResult(
                name="teams.unexpected",
                status=CheckStatus.WARNING,
                message="Unexpected team found",
            ),
        ],
    )
    output = render_report(report)
    assert "0 passed, 0 failed, 1 warning" in output
    assert "Warnings:" in output
    assert "!" in output


def test_render_report_unknown_type():
    report = AuditReport(
        repo_name="co-cddo/unknown-repo",
        repo_type="unknown",
        results=[],
    )
    output = render_report(report)
    assert "not recognised" in output


def test_render_report_multiline_message():
    report = AuditReport(
        repo_name="co-cddo/gds-idea-app-foo",
        repo_type="cdk-app",
        results=[
            CheckResult(
                name="naming",
                status=CheckStatus.FAILED,
                message="Name mismatch.\n  Run: idea-gh rename <new-name>",
            ),
        ],
    )
    output = render_report(report)
    assert "Run: idea-gh rename" in output


# --- fix_repo ---


def _mock_fixable_repo(httpx_mock: HTTPXMock):
    """Mock API calls for a repo with fixable settings and security issues."""
    base = "https://api.github.com"

    bad_repo = {
        "name": "gds-idea-app-foo",
        "default_branch": "dev",
        "visibility": "private",
        "delete_branch_on_merge": True,
        "allow_squash_merge": True,
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "has_issues": True,
        "has_wiki": True,  # wrong — should be False
        "has_projects": False,
    }

    # settings.fix calls get_repo, then PATCH
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo",
        json=bad_repo,
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo",
        method="PATCH",
        json={**bad_repo, "has_wiki": False},
    )

    # teams.fix: both teams already correct → no changes
    httpx_mock.add_response(
        url=f"{base}/orgs/co-cddo/teams/cddo-admins/repos/co-cddo/gds-idea-app-foo",
        json={"role_name": "admin"},
    )

    # branches.fix: get_repo for default branch check
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo",
        json=bad_repo,
    )
    # classic protection check
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/branches/dev/protection",
        status_code=404,
    )
    # find_ruleset_by_name: list rulesets, get ruleset detail
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/rulesets",
        json=[{"id": 1, "name": "idea-gh: dev"}],
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/rulesets/1",
        json={
            "id": 1,
            "name": "idea-gh: dev",
            "enforcement": "active",
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {
                    "type": "pull_request",
                    "parameters": {
                        "required_approving_review_count": 1,
                        "dismiss_stale_reviews_on_push": True,
                    },
                },
            ],
            "bypass_actors": [],
        },
    )
    # update_ruleset (PUT) — branches.fix always updates existing rulesets
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/rulesets/1",
        method="PUT",
        json={"id": 1, "name": "idea-gh: dev"},
    )

    # security.fix: vuln alerts disabled, automated fixes disabled
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/vulnerability-alerts",
        method="GET",
        status_code=404,  # not enabled
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/vulnerability-alerts",
        method="PUT",
        status_code=204,
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/automated-security-fixes",
        method="GET",
        json={"enabled": False},
    )
    httpx_mock.add_response(
        url=f"{base}/repos/co-cddo/gds-idea-app-foo/automated-security-fixes",
        method="PUT",
        status_code=204,
    )


def test_fix_repo_applies_changes(httpx_mock: HTTPXMock, gh_client: GitHubClient):
    config = _minimal_config()
    _mock_fixable_repo(httpx_mock)

    result = fix_repo("co-cddo", "gds-idea-app-foo", config, gh_client, "cdk-app")

    assert isinstance(result, FixReport)
    assert result.repo_type == "cdk-app"
    assert len(result.errors) == 0

    # Should have settings, branches, and security changes
    change_text = "\n".join(result.changes)
    assert "settings: has_wiki" in change_text
    assert "branches: Updated ruleset" in change_text
    assert "security: Enabled vulnerability alerts" in change_text
    assert "security: Enabled automated security fixes" in change_text


def test_fix_repo_unknown_type(gh_client: GitHubClient):
    config = _minimal_config()
    result = fix_repo("co-cddo", "unknown-repo", config, gh_client)

    assert result.repo_type == "unknown"
    assert len(result.errors) == 1
    assert "not recognised" in result.errors[0]
    assert len(result.changes) == 0
