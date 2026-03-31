"""Check that required files and workflows exist in the repo."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckResult, CheckStatus


def _is_excluded(entry: str | list[str], excluded_files: list[str]) -> bool:
    """Check whether a required_files entry should be skipped.

    For a plain string, it's excluded if it appears in *excluded_files*.
    For an OR-style list, it's excluded if **any** alternative appears in
    *excluded_files* (the whole group is dropped).
    """
    if isinstance(entry, list):
        return any(f in excluded_files for f in entry)
    return entry in excluded_files


def audit(
    owner: str,
    repo: str,
    required_files: list[str | list[str]],
    required_workflows: list[str],
    client: GitHubClient,
    excluded_files: list[str] | None = None,
) -> list[CheckResult]:
    """Check that each required file and workflow exists in the repo.

    Entries in ``required_files`` can be a plain string (file must exist)
    or a list of strings (at least one must exist — OR logic).

    Any entry matching *excluded_files* is silently skipped.
    """
    excluded = excluded_files or []
    results = []

    for entry in required_files:
        if _is_excluded(entry, excluded):
            continue
        if isinstance(entry, list):
            # OR logic: pass if any alternative exists
            found = None
            for filepath in entry:
                if client.file_exists(owner, repo, filepath):
                    found = filepath
                    break
            label = " or ".join(entry)
            if found:
                results.append(
                    CheckResult(
                        name=f"files.{label}",
                        status=CheckStatus.PASSED,
                        message=f"Required file exists: {found}",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"files.{label}",
                        status=CheckStatus.FAILED,
                        message=f"Required file missing: none of {', '.join(entry)} found",
                        fix_available=False,
                    )
                )
        else:
            if client.file_exists(owner, repo, entry):
                results.append(
                    CheckResult(
                        name=f"files.{entry}",
                        status=CheckStatus.PASSED,
                        message=f"Required file exists: {entry}",
                    )
                )
            else:
                results.append(
                    CheckResult(
                        name=f"files.{entry}",
                        status=CheckStatus.FAILED,
                        message=f"Required file missing: {entry}",
                        fix_available=False,
                    )
                )

    for workflow in required_workflows:
        workflow_path = f".github/workflows/{workflow}"
        if client.file_exists(owner, repo, workflow_path):
            results.append(
                CheckResult(
                    name=f"files.workflow.{workflow}",
                    status=CheckStatus.PASSED,
                    message=f"Workflow exists: {workflow_path}",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"files.workflow.{workflow}",
                    status=CheckStatus.FAILED,
                    message=f"Workflow missing: {workflow_path}",
                    fix_available=False,
                )
            )

    return results
