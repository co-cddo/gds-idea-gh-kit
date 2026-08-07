"""Tests for cli.py helper functions (not full CLI invocations)."""

from __future__ import annotations

from unittest.mock import MagicMock

from gds_idea_gh_kit.cli import _handle_stale_branches, _warn_stale_branches
from gds_idea_gh_kit.github_client import GitHubClientError
from gds_idea_gh_kit.models import FixReport, StaleBranch


def _fix_result_with_stale(branch: str = "main", default_branch: str = "dev", ahead_by: int = 0) -> FixReport:
    return FixReport(
        repo_name="my-repo",
        repo_type="cdk-app",
        stale_branches=[StaleBranch(branch=branch, default_branch=default_branch, ahead_by=ahead_by)],
    )


# --- _handle_stale_branches ---


def test_handle_stale_branches_skips_already_deleted_branch(monkeypatch, capsys):
    """GitHub's rename is async — if the branch is already gone, don't prompt or crash."""
    client = MagicMock()
    client.branch_exists.return_value = False

    confirm_called = False

    def fake_confirm(*args, **kwargs):
        nonlocal confirm_called
        confirm_called = True
        return True

    monkeypatch.setattr("click.confirm", fake_confirm)

    fix_result = _fix_result_with_stale()
    _handle_stale_branches(fix_result, "co-cddo", "my-repo", client)

    assert confirm_called is False
    client.delete_branch.assert_not_called()
    assert "no longer exists" in capsys.readouterr().out


def test_handle_stale_branches_deletes_merged_branch(monkeypatch):
    client = MagicMock()
    client.branch_exists.return_value = True
    monkeypatch.setattr("click.confirm", lambda *a, **k: True)

    fix_result = _fix_result_with_stale()
    _handle_stale_branches(fix_result, "co-cddo", "my-repo", client)

    client.delete_branch.assert_called_once_with("co-cddo", "my-repo", "main")


def test_handle_stale_branches_declines_deletion(monkeypatch):
    client = MagicMock()
    client.branch_exists.return_value = True
    monkeypatch.setattr("click.confirm", lambda *a, **k: False)

    fix_result = _fix_result_with_stale()
    _handle_stale_branches(fix_result, "co-cddo", "my-repo", client)

    client.delete_branch.assert_not_called()


def test_handle_stale_branches_survives_late_delete_failure(monkeypatch, capsys):
    """branch_exists said True, but delete races with GitHub's async rename and 404s."""
    client = MagicMock()
    client.branch_exists.return_value = True
    client.delete_branch.side_effect = GitHubClientError("Not found")
    monkeypatch.setattr("click.confirm", lambda *a, **k: True)

    fix_result = _fix_result_with_stale()
    _handle_stale_branches(fix_result, "co-cddo", "my-repo", client)  # should not raise

    assert "already removed" in capsys.readouterr().out


def test_handle_stale_branches_unmerged_branch_prompt(monkeypatch):
    client = MagicMock()
    client.branch_exists.return_value = True
    monkeypatch.setattr("click.confirm", lambda *a, **k: True)

    fix_result = _fix_result_with_stale(ahead_by=3)
    _handle_stale_branches(fix_result, "co-cddo", "my-repo", client)

    client.delete_branch.assert_called_once_with("co-cddo", "my-repo", "main")


# --- _warn_stale_branches ---


def test_warn_stale_branches_skips_already_deleted_branch(capsys):
    client = MagicMock()
    client.branch_exists.return_value = False

    fix_result = _fix_result_with_stale()
    _warn_stale_branches(fix_result, "co-cddo", "my-repo", client)

    assert capsys.readouterr().out == ""


def test_warn_stale_branches_warns_for_existing_merged_branch(capsys):
    client = MagicMock()
    client.branch_exists.return_value = True

    fix_result = _fix_result_with_stale()
    _warn_stale_branches(fix_result, "co-cddo", "my-repo", client)

    out = capsys.readouterr().out
    assert "fully merged" in out
    assert "main" in out
