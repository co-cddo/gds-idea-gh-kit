"""Tests for cli.py helper functions (not full CLI invocations)."""

from __future__ import annotations

from unittest.mock import MagicMock

from gds_idea_gh_kit.cli import (
    _handle_branch_rename_migration,
    _handle_stale_branches,
    _run_git_step,
    _warn_stale_branches,
)
from gds_idea_gh_kit.github_client import GitHubClientError
from gds_idea_gh_kit.models import FixReport, StaleBranch


def _fix_result_with_stale(branch: str = "main", default_branch: str = "dev", ahead_by: int = 0) -> FixReport:
    return FixReport(
        repo_name="my-repo",
        repo_type="cdk-app",
        stale_branches=[StaleBranch(branch=branch, default_branch=default_branch, ahead_by=ahead_by)],
    )


def _fix_result_with_rename(old: str = "main", new: str = "dev") -> FixReport:
    return FixReport(repo_name="my-repo", repo_type="cdk-app", branch_rename=(old, new))


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


# --- _run_git_step ---


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_git_step_success(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _FakeCompletedProcess(stdout="ok\n"))

    ok, output = _run_git_step("fetch", "origin")

    assert ok is True
    assert output == "ok"


def test_run_git_step_failure(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: _FakeCompletedProcess(returncode=1, stderr="fatal: error\n"))

    ok, output = _run_git_step("branch", "-m", "main", "dev")

    assert ok is False
    assert "fatal: error" in output


def test_run_git_step_never_raises_when_git_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr("subprocess.run", fake_run)

    ok, output = _run_git_step("fetch", "origin")  # should not raise

    assert ok is False


# --- _handle_branch_rename_migration ---


def test_handle_branch_rename_migration_noop_when_no_rename(capsys):
    fix_result = FixReport(repo_name="my-repo", repo_type="cdk-app")

    _handle_branch_rename_migration(fix_result)

    assert capsys.readouterr().out == ""


def test_handle_branch_rename_migration_asks_before_doing_anything(monkeypatch, capsys):
    """The migration is always asked for, never automatic."""
    confirm_called = False

    def fake_confirm(*args, **kwargs):
        nonlocal confirm_called
        confirm_called = True
        return False

    monkeypatch.setattr("click.confirm", fake_confirm)
    run_calls = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: run_calls.append(a))

    fix_result = _fix_result_with_rename()
    _handle_branch_rename_migration(fix_result)

    assert confirm_called is True
    assert run_calls == []  # declined, so no git commands were run
    out = capsys.readouterr().out
    assert "Leaving local clone on 'main'" in out
    assert "git branch -m main dev" in out


def test_handle_branch_rename_migration_runs_all_steps_when_confirmed(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeCompletedProcess()

    monkeypatch.setattr("click.confirm", lambda *a, **k: True)
    monkeypatch.setattr("subprocess.run", fake_run)

    fix_result = _fix_result_with_rename()
    _handle_branch_rename_migration(fix_result)

    assert calls == [
        ["git", "branch", "-m", "main", "dev"],
        ["git", "fetch", "origin"],
        ["git", "branch", "-u", "origin/dev", "dev"],
        ["git", "remote", "set-head", "origin", "-a"],
    ]


def test_handle_branch_rename_migration_stops_on_first_failure(monkeypatch, capsys):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        # First step fails; later steps (if reached) would succeed.
        return _FakeCompletedProcess(returncode=1 if len(calls) == 1 else 0, stderr="boom")

    monkeypatch.setattr("click.confirm", lambda *a, **k: True)
    monkeypatch.setattr("subprocess.run", fake_run)

    fix_result = _fix_result_with_rename()
    _handle_branch_rename_migration(fix_result)  # should not raise

    assert len(calls) == 1
    out = capsys.readouterr().out
    assert "failed" in out
    assert "Stopping local migration" in out
