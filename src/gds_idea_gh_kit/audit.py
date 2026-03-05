"""Orchestrate all checks for a single repo and produce an AuditReport."""

from __future__ import annotations

from gds_idea_gh_kit.checks import branches, files, naming, security, settings, teams
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import AuditReport, CheckResult, CheckStatus, Config, RepoTypeConfig


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


def _render_result_lines(result: CheckResult, indent: str = "    ") -> list[str]:
    """Render a single CheckResult as indented lines."""
    message_lines = result.message.split("\n")
    lines = [f"{indent}{result.symbol} {message_lines[0]}"]
    for extra_line in message_lines[1:]:
        lines.append(f"{indent}  {extra_line}")
    return lines


def render_report(report: AuditReport, verbose: bool = False) -> str:
    """Render an AuditReport as a human-readable string.

    Default: grouped by fixable/manual/warnings, passing checks hidden.
    Verbose: all checks in original order.
    """
    lines = [
        f"Auditing {report.repo_name} (type: {report.repo_type})",
        "",
    ]

    if not report.results:
        lines.append("  No checks to run (repo type not recognised).")
        return "\n".join(lines)

    if verbose:
        for result in report.results:
            lines.extend(_render_result_lines(result, indent="  "))
    else:
        # All passing — short summary
        if report.failed == 0 and report.warnings == 0:
            lines.append(f"  All {report.passed} checks passed.")
            return "\n".join(lines)

        # Group results
        auto_fixable = [r for r in report.results if r.status == CheckStatus.FAILED and r.fix_available]
        manual_fix = [r for r in report.results if r.status == CheckStatus.FAILED and not r.fix_available]
        warnings = [r for r in report.results if r.status == CheckStatus.WARNING]

        if auto_fixable:
            lines.append("  Auto-fixable (run with --fix):")
            for result in auto_fixable:
                lines.extend(_render_result_lines(result))
            lines.append("")

        if manual_fix:
            lines.append("  Manual fixes needed:")
            for result in manual_fix:
                lines.extend(_render_result_lines(result))
            lines.append("")

        if warnings:
            lines.append("  Warnings:")
            for result in warnings:
                lines.extend(_render_result_lines(result))
            lines.append("")

    lines.append(
        f"  Result: {report.passed} passed, {report.failed} failed, "
        f"{report.warnings} warning(s)"
    )

    if report.fixable:
        lines.append(f"  {len(report.fixable)} issue(s) can be auto-fixed with --fix")

    return "\n".join(lines)
