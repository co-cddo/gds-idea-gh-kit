"""GitHub API client using httpx, authenticated via gh CLI."""

from __future__ import annotations

import subprocess

import httpx

GITHUB_API_BASE = "https://api.github.com"


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""


class AuthError(GitHubClientError):
    """Raised when authentication fails."""


def get_gh_token() -> str:
    """Get a GitHub token from the gh CLI.

    Requires `gh` to be installed and authenticated (`gh auth login`).
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        token = result.stdout.strip()
        if not token:
            raise AuthError("gh auth token returned empty output. Run 'gh auth login' first.")
        return token
    except FileNotFoundError:
        raise AuthError(
            "gh CLI not found. Install it: https://cli.github.com/\n"
            "Then authenticate: gh auth login"
        )
    except subprocess.CalledProcessError as e:
        raise AuthError(
            f"gh auth token failed: {e.stderr.strip()}\n"
            "Run 'gh auth login' to authenticate."
        )


class GitHubClient:
    """Thin wrapper around GitHub REST API using httpx."""

    def __init__(self, token: str | None = None, org: str | None = None):
        self.token = token or get_gh_token()
        self.org = org
        self._client = httpx.Client(
            base_url=GITHUB_API_BASE,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make an API request and raise on error."""
        response = self._client.request(method, path, **kwargs)
        if response.status_code == 404:
            raise GitHubClientError(f"Not found: {path}")
        if response.status_code == 403:
            raise GitHubClientError(
                f"Permission denied: {path}. Check your token has the required scopes."
            )
        if response.status_code >= 400:
            body = response.text
            raise GitHubClientError(
                f"GitHub API error {response.status_code} on {method} {path}: {body}"
            )
        return response

    # --- Repository ---

    def get_repo(self, owner: str, repo: str) -> dict:
        """Get repository details."""
        return self._request("GET", f"/repos/{owner}/{repo}").json()

    def update_repo(self, owner: str, repo: str, **settings) -> dict:
        """Update repository settings."""
        return self._request("PATCH", f"/repos/{owner}/{repo}", json=settings).json()

    def create_repo(self, org: str, name: str, **settings) -> dict:
        """Create a new repository in an org."""
        payload = {"name": name, **settings}
        return self._request("POST", f"/orgs/{org}/repos", json=payload).json()

    def list_org_repos(self, org: str, per_page: int = 100) -> list[dict]:
        """List all repositories in an org (handles pagination)."""
        repos = []
        page = 1
        while True:
            response = self._request(
                "GET", f"/orgs/{org}/repos", params={"per_page": per_page, "page": page}
            )
            batch = response.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
        return repos

    # --- Teams ---

    def get_team_repo_permission(self, org: str, team_slug: str, owner: str, repo: str) -> str | None:
        """Get a team's permission on a repo. Returns None if not set."""
        try:
            data = self._request(
                "GET", f"/orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}"
            ).json()
            return data.get("role_name")
        except GitHubClientError:
            return None

    def set_team_repo_permission(
        self, org: str, team_slug: str, owner: str, repo: str, permission: str
    ) -> None:
        """Set a team's permission on a repo."""
        self._request(
            "PUT",
            f"/orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}",
            json={"permission": permission},
        )

    # --- Branch protection ---

    def get_branch_protection(self, owner: str, repo: str, branch: str) -> dict | None:
        """Get branch protection rules. Returns None if not protected."""
        try:
            return self._request(
                "GET", f"/repos/{owner}/{repo}/branches/{branch}/protection"
            ).json()
        except GitHubClientError:
            return None

    def set_branch_protection(self, owner: str, repo: str, branch: str, **rules) -> dict:
        """Set branch protection rules."""
        return self._request(
            "PUT", f"/repos/{owner}/{repo}/branches/{branch}/protection", json=rules
        ).json()

    # --- Contents (for required files check) ---

    def file_exists(self, owner: str, repo: str, path: str, ref: str | None = None) -> bool:
        """Check if a file exists in the repo."""
        params = {"ref": ref} if ref else {}
        try:
            self._request("GET", f"/repos/{owner}/{repo}/contents/{path}", params=params)
            return True
        except GitHubClientError:
            return False

    # --- Vulnerability alerts ---

    def get_vulnerability_alerts_enabled(self, owner: str, repo: str) -> bool:
        """Check if vulnerability alerts are enabled."""
        response = self._client.get(f"/repos/{owner}/{repo}/vulnerability-alerts")
        return response.status_code == 204

    def enable_vulnerability_alerts(self, owner: str, repo: str) -> None:
        """Enable vulnerability alerts."""
        self._request("PUT", f"/repos/{owner}/{repo}/vulnerability-alerts")

    def get_automated_security_fixes_enabled(self, owner: str, repo: str) -> bool:
        """Check if automated security fixes are enabled."""
        response = self._client.get(
            f"/repos/{owner}/{repo}/automated-security-fixes"
        )
        if response.status_code == 200:
            return response.json().get("enabled", False)
        return False

    def enable_automated_security_fixes(self, owner: str, repo: str) -> None:
        """Enable automated security fixes."""
        self._request("PUT", f"/repos/{owner}/{repo}/automated-security-fixes")

    # --- Default branch ---

    def rename_default_branch(self, owner: str, repo: str, new_name: str) -> dict:
        """Rename the default branch of a repo."""
        # First get current default branch
        repo_data = self.get_repo(owner, repo)
        current = repo_data["default_branch"]
        if current == new_name:
            return repo_data
        # Rename the branch
        return self._request(
            "POST",
            f"/repos/{owner}/{repo}/branches/{current}/rename",
            json={"new_name": new_name},
        ).json()
