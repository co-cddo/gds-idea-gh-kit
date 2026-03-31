"""Orchestrate all checks for a single repo and produce an AuditReport."""

from __future__ import annotations

from gds_idea_gh_kit.checks import branches, files, naming, security, settings, teams
from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import (
    AuditReport,
    CheckResult,
    CheckStatus,
    Config,
    FixReport,
)


def detect_repo_type(
    owner: str,
    repo: str,
    config: Config,
    client: GitHubClient,
) -> str | None:
    """Detect repo type by checking for marker files via the GitHub API.

    Iterates repo types in config order.  For each type, checks whether
    ANY of its ``detection_files`` exist in the repo.  The first type
    with a matching file wins.

    Returns:
        The repo type name (e.g. ``"cdk-app"``), or ``None`` if no type
        matched.
    """
    for type_name, type_config in config.repo_types.items():
        if not type_config.detection_files:
            continue
        for detection_file in type_config.detection_files:
            if client.file_exists(owner, repo, detection_file):
                return type_name
    return None


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
        repo_type: Override repo type detection. If None, detected from
            files present in the repo.

    Returns:
        AuditReport with all check results.
    """
    # Detect or validate repo type
    if repo_type is None:
        repo_type = detect_repo_type(owner, repo, config, client)

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
    report.results.extend(settings.audit(owner, repo, config.repo_settings, client))

    # 3. Teams (global + type-specific extra teams)
    all_teams = {**config.teams, **type_config.extra_teams}
    report.results.extend(teams.audit(owner, repo, all_teams, client))

    # 4. Branches (default branch + rulesets)
    report.results.extend(branches.audit(owner, repo, type_config, client))

    # 5. Files + workflows
    report.results.extend(
        files.audit(
            owner,
            repo,
            config.required_files,
            type_config.required_workflows,
            client,
            excluded_files=type_config.excluded_files,
        )
    )

    # 6. Security
    report.results.extend(security.audit(owner, repo, config.security, client))

    return report


def fix_repo(
    owner: str,
    repo: str,
    config: Config,
    client: GitHubClient,
    repo_type: str | None = None,
) -> FixReport:
    """Apply auto-fixes for a single repo.

    Calls fix() on each module that supports it (settings, teams,
    branches, security).  Files and naming have no auto-fix.

    Returns:
        FixReport with the list of changes made and any errors.
    """
    if repo_type is None:
        repo_type = detect_repo_type(owner, repo, config, client)

    fix_report = FixReport(
        repo_name=f"{owner}/{repo}",
        repo_type=repo_type or "unknown",
    )

    if repo_type is None:
        fix_report.errors.append("Cannot fix: repo type not recognised.")
        return fix_report

    type_config = config.repo_types[repo_type]

    # Settings
    try:
        changes = settings.fix(owner, repo, config.repo_settings, client)
        fix_report.changes.extend(f"settings: {c}" for c in changes)
    except Exception as e:
        fix_report.errors.append(f"settings fix failed: {e}")

    # Teams (global + type-specific extra teams)
    try:
        all_teams = {**config.teams, **type_config.extra_teams}
        changes = teams.fix(owner, repo, all_teams, client)
        fix_report.changes.extend(f"teams: {c}" for c in changes)
    except Exception as e:
        fix_report.errors.append(f"teams fix failed: {e}")

    # Branches (default branch + rulesets)
    try:
        changes, stale = branches.fix(owner, repo, type_config, client)
        fix_report.changes.extend(f"branches: {c}" for c in changes)
        fix_report.stale_branches.extend(stale)
    except Exception as e:
        fix_report.errors.append(f"branches fix failed: {e}")

    # Security
    try:
        changes = security.fix(owner, repo, config.security, client)
        fix_report.changes.extend(f"security: {c}" for c in changes)
    except Exception as e:
        fix_report.errors.append(f"security fix failed: {e}")

    return fix_report


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
        if report.failed == 0 and report.warnings == 0 and report.skipped == 0:
            lines.append(f"  All {report.passed} checks passed.")
            return "\n".join(lines)

        # Group results
        skipped = [r for r in report.results if r.status == CheckStatus.SKIPPED]
        auto_fixable = [r for r in report.results if r.status == CheckStatus.FAILED and r.fix_available]
        manual_fix = [r for r in report.results if r.status == CheckStatus.FAILED and not r.fix_available]
        warnings = [r for r in report.results if r.status == CheckStatus.WARNING]

        if skipped:
            lines.append("  Skipped (admin access required):")
            for result in skipped:
                lines.extend(_render_result_lines(result))
            lines.append("")

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

    summary = f"  Result: {report.passed} passed, {report.failed} failed, {report.warnings} warning(s)"
    if report.skipped:
        summary += f", {report.skipped} skipped"
    lines.append(summary)

    if report.fixable:
        lines.append(f"  {len(report.fixable)} issue(s) can be auto-fixed with --fix")

    return "\n".join(lines)
