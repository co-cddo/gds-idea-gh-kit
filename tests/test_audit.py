"""Tests for the audit orchestration and report rendering."""

from pytest_httpx import HTTPXMock

from gds_idea_gh_kit.audit import audit_repo, render_report
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import (
    AuditReport,
    BranchProtectionConfig,
    CheckResult,
    CheckStatus,
    Config,
    RepoSettings,
    RepoTypeConfig,
    SecurityConfig,
)


def _minimal_config() -> Config:
    return Config(
        org="co-cddo",
        team_prefix="cddo",
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
                        require_status_checks=["lint"],
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
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [{"context": "lint"}],
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


def test_render_report_passing():
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
    assert "2 passed, 0 failed, 0 warnings" in output
    assert "\u2713" in output


def test_render_report_with_failures():
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
        ],
    )
    output = render_report(report)
    assert "1 passed, 1 failed, 0 warnings" in output
    assert "1 issue(s) can be auto-fixed" in output
    assert "\u2717" in output


def test_render_report_with_warnings():
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
    assert "0 passed, 0 failed, 1 warnings" in output
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
    # Multi-line messages should be indented
    assert "    Run: idea-gh rename" in output
