"""Data models for repo configuration and audit results."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --- Audit result models (plain pydantic, not settings) ---


class CheckStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


SYMBOLS = {
    CheckStatus.PASSED: "\u2713",
    CheckStatus.FAILED: "\u2717",
    CheckStatus.WARNING: "!",
    CheckStatus.SKIPPED: "-",
}


class CheckResult(BaseModel):
    name: str
    status: CheckStatus
    message: str
    fix_available: bool = False

    @property
    def symbol(self) -> str:
        return SYMBOLS[self.status]


class AuditReport(BaseModel):
    repo_name: str
    repo_type: str
    results: list[CheckResult] = Field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.FAILED)

    @property
    def warnings(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.WARNING)

    @property
    def fixable(self) -> list[CheckResult]:
        return [r for r in self.results if r.status == CheckStatus.FAILED and r.fix_available]


# --- Config models loaded from YAML ---


class BranchProtectionConfig(BaseModel):
    require_pr: bool = True
    required_approvals: int = 1
    dismiss_stale_reviews: bool = True
    require_status_checks: list[str] = Field(default_factory=list)
    require_linear_history: bool = False
    required_review_teams: list[str] = Field(default_factory=list)
    """Teams that must review PRs to this branch (by slug, e.g. 'cddo-idea-admins')."""
    prevent_deletion: bool = True
    prevent_force_push: bool = True
    bypass_teams: list[str] = Field(default_factory=list)
    """Teams that can bypass rules on this branch (by slug)."""
    bypass_mode: str = "pull_request"
    """When bypass teams can bypass: 'always' or 'pull_request'."""

    @field_validator("bypass_mode")
    @classmethod
    def bypass_mode_must_be_valid(cls, v: str) -> str:
        if v not in ("always", "pull_request"):
            raise ValueError(f"bypass_mode must be 'always' or 'pull_request', got '{v}'")
        return v


class RepoTypeConfig(BaseModel):
    naming_pattern: str
    default_branch: str
    branch_protection: dict[str, BranchProtectionConfig] = Field(default_factory=dict)

    @field_validator("naming_pattern")
    @classmethod
    def pattern_must_have_placeholder(cls, v: str) -> str:
        if "{name}" not in v:
            raise ValueError("naming_pattern must contain '{name}' placeholder")
        return v

    def matches_name(self, repo_name: str) -> bool:
        regex = re.escape(self.naming_pattern).replace(r"\{name\}", r"[a-z0-9][a-z0-9-]*")
        return bool(re.fullmatch(regex, repo_name))

    def extract_name(self, repo_name: str) -> str | None:
        regex = re.escape(self.naming_pattern).replace(r"\{name\}", r"([a-z0-9][a-z0-9-]*)")
        match = re.fullmatch(regex, repo_name)
        return match.group(1) if match else None


class RepoSettings(BaseModel):
    delete_branch_on_merge: bool = True
    allow_squash_merge: bool = True
    allow_merge_commit: bool = False
    allow_rebase_merge: bool = False
    has_issues: bool = True
    has_wiki: bool = False
    has_projects: bool = False


class SecurityConfig(BaseModel):
    vulnerability_alerts: bool = True
    automated_security_fixes: bool = True


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    org: str
    team_prefix: str
    default_visibility: str = "private"
    teams: dict[str, str] = Field(default_factory=dict)
    repo_settings: RepoSettings = Field(default_factory=RepoSettings)
    required_files: list[str] = Field(default_factory=list)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    repo_types: dict[str, RepoTypeConfig] = Field(default_factory=dict)

    @field_validator("default_visibility")
    @classmethod
    def visibility_must_be_valid(cls, v: str) -> str:
        if v not in ("public", "private", "internal"):
            raise ValueError(f"Must be 'public', 'private', or 'internal', got '{v}'")
        return v

    @field_validator("teams")
    @classmethod
    def team_permissions_must_be_valid(cls, v: dict[str, str]) -> dict[str, str]:
        valid = {"admin", "write", "read", "maintain", "triage"}
        for team, perm in v.items():
            if perm not in valid:
                raise ValueError(
                    f"Team '{team}' has invalid permission '{perm}'. "
                    f"Must be one of: {', '.join(sorted(valid))}"
                )
        return v

    def detect_repo_type(self, repo_name: str) -> str | None:
        for type_name, type_config in self.repo_types.items():
            if type_config.matches_name(repo_name):
                return type_name
        return None
