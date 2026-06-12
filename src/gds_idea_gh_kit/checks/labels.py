"""Check that required labels exist on the repository."""

from __future__ import annotations

from gds_idea_gh_kit.github_client import GitHubClient
from gds_idea_gh_kit.models import CheckResult, CheckStatus, LabelConfig


def audit(owner: str, repo: str, labels: list[LabelConfig], client: GitHubClient) -> list[CheckResult]:
    """Check that each required label exists on the repo (name only).

    Args:
        owner: Repository owner (org name).
        repo: Repository name.
        labels: Required labels from config.
        client: GitHub API client.

    Returns:
        One CheckResult per required label.
    """
    if not labels:
        return []

    existing = {label["name"] for label in client.list_labels(owner, repo)}
    results = []

    for label in labels:
        if label.name in existing:
            results.append(
                CheckResult(
                    name=f"labels.{label.name}",
                    status=CheckStatus.PASSED,
                    message=f"Label '{label.name}' exists",
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"labels.{label.name}",
                    status=CheckStatus.FAILED,
                    message=f"Label '{label.name}' is missing",
                    fix_available=True,
                )
            )

    return results


def fix(owner: str, repo: str, labels: list[LabelConfig], client: GitHubClient) -> list[str]:
    """Create missing labels and update existing ones to match config.

    Args:
        owner: Repository owner (org name).
        repo: Repository name.
        labels: Required labels from config.
        client: GitHub API client.

    Returns:
        List of changes made.
    """
    if not labels:
        return []

    existing = {label["name"]: label for label in client.list_labels(owner, repo)}
    changes = []

    for label in labels:
        if label.name not in existing:
            client.create_label(owner, repo, label.name, label.color, label.description)
            changes.append(f"Created label '{label.name}'")
        else:
            current = existing[label.name]
            if current.get("color") != label.color or current.get("description", "") != label.description:
                client.update_label(owner, repo, label.name, label.color, label.description)
                changes.append(f"Updated label '{label.name}'")

    return changes
