"""Check that a repo name matches its type's naming convention."""

from __future__ import annotations

from gds_idea_gh_kit.models import CheckResult, CheckStatus, RepoTypeConfig


def audit(repo_name: str, type_config: RepoTypeConfig) -> list[CheckResult]:
    """Check repo name against the naming pattern."""
    if type_config.matches_name(repo_name):
        return [
            CheckResult(
                name="naming",
                status=CheckStatus.PASSED,
                message=f"Name matches pattern '{type_config.naming_pattern}'",
            )
        ]
    return [
        CheckResult(
            name="naming",
            status=CheckStatus.FAILED,
            message=(
                f"Name '{repo_name}' does not match pattern "
                f"'{type_config.naming_pattern}'.\n"
                f"  Auto-fix is not available — renaming breaks existing clones, "
                f"CI/CD pipelines, and cross-repo references.\n"
                f"  To rename manually if you accept the risks, run from inside the repo:\n"
                f"    idea-gh rename <new-name>"
            ),
            fix_available=False,
        )
    ]
