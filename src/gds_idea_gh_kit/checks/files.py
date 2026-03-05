"""Check that required files and workflows exist in the repo."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckResult, CheckStatus


def audit(
    owner: str,
    repo: str,
    required_files: list[str],
    required_workflows: list[str],
    client: GitHubClient,
) -> list[CheckResult]:
    """Check that each required file and workflow exists in the repo."""
    results = []

    for filepath in required_files:
        if client.file_exists(owner, repo, filepath):
            results.append(
                CheckResult(
                    name=f"files.{filepath}",
                    status=CheckStatus.PASSED,
                    message=f"Required file exists: {filepath}",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"files.{filepath}",
                    status=CheckStatus.FAILED,
                    message=f"Required file missing: {filepath}",
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
