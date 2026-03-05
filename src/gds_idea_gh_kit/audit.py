"""Orchestrate all checks for a single repo and produce an AuditReport."""

from __future__ import annotations

from gds_idea_gh_kit.checks import branches, files, naming, security, settings, teams
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import AuditReport, Config, RepoTypeConfig


def audit_repo(
    owner: str,
    repo: str,
    config: Config,
    client: GitHubClient,
    repo_type: str | None = None,
) -> AuditReport:
    """Run all checks against a single repo.

    Args:
        owner: GitHub org/owner.
        repo: Repo name.
        config: Loaded tool config.
        client: Authenticated GitHub client.
        repo_type: Override repo type detection. If None, detected from name.

    Returns:
        AuditReport with all check results.
    """
    # Detect or validate repo type
    if repo_type is None:
        repo_type = config.detect_repo_type(repo)

    if repo_type is None:
        return AuditReport(
            repo_name=f"{owner}/{repo}",
            repo_type="unknown",
            results=[],
        )

    type_config = config.repo_types[repo_type]

    report = AuditReport(
        repo_name=f"{owner}/{repo}",
        repo_type=repo_type,
    )

    # 1. Naming
    report.results.extend(naming.audit(repo, type_config))

    # 2. Settings
    report.results.extend(
        settings.audit(owner, repo, config.repo_settings, client)
    )

    # 3. Teams
    report.results.extend(
        teams.audit(owner, repo, config.teams, client)
    )

    # 4. Branches (default branch + rulesets)
    report.results.extend(
        branches.audit(owner, repo, type_config, client)
    )

    # 5. Files + workflows
    report.results.extend(
        files.audit(owner, repo, config.required_files, type_config.required_workflows, client)
    )

    # 6. Security
    report.results.extend(
        security.audit(owner, repo, config.security, client)
    )

    return report


def render_report(report: AuditReport) -> str:
    """Render an AuditReport as a human-readable string."""
    lines = [
        f"Auditing {report.repo_name} (type: {report.repo_type})",
        "",
    ]

    if not report.results:
        lines.append("  No checks to run (repo type not recognised).")
        return "\n".join(lines)

    for result in report.results:
        # Indent multi-line messages
        message_lines = result.message.split("\n")
        first_line = f"  {result.symbol} {message_lines[0]}"
        lines.append(first_line)
        for extra_line in message_lines[1:]:
            lines.append(f"    {extra_line}")

    lines.append("")
    lines.append(
        f"  Result: {report.passed} passed, {report.failed} failed, "
        f"{report.warnings} warnings"
    )

    if report.fixable:
        lines.append(f"  {len(report.fixable)} issue(s) can be auto-fixed with --fix")

    return "\n".join(lines)
