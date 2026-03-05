"""Check that required files exist in the repo."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckResult, CheckStatus


def audit(
    owner: str, repo: str, required_files: list[str], client: GitHubClient
) -> list[CheckResult]:
    """Check that each required file exists in the repo's default branch."""
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
                    fix_available=False,  # we can't auto-create repo content
                )
            )

    return results
