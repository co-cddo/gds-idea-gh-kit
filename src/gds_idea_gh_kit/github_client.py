"""GitHub API client using httpx, authenticated via gh CLI."""

from __future__ import annotations

import subprocess
import time

import httpx

GITHUB_API_BASE = "https://api.github.com"
CONNECTION_TTL = 300  # seconds


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
        self._verified_at: float | None = None
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

    def verify_connection(self) -> None:
        """Check we can reach GitHub and access the configured org.

        Results are cached for CONNECTION_TTL seconds to avoid repeated
        checks within a single command invocation.

        Raises:
            AuthError: if the token is invalid or expired.
            GitHubClientError: if the network is unreachable or the org
                is not accessible.
        """
        if self._verified_at and (time.monotonic() - self._verified_at) < CONNECTION_TTL:
            return

        # Check network + token
        try:
            response = self._client.get("/user")
        except (httpx.ConnectError, httpx.TimeoutException):
            raise GitHubClientError(
                "Cannot reach api.github.com. Check your network connection and VPN."
            )

        if response.status_code == 401:
            raise AuthError(
                "GitHub token is invalid or expired.\n"
                "Run 'gh auth login' to re-authenticate."
            )
        if response.status_code >= 400:
            raise GitHubClientError(
                f"Unexpected error checking GitHub connection: {response.status_code}"
            )

        # Check org access
        if self.org:
            try:
                org_response = self._client.get(f"/orgs/{self.org}")
            except (httpx.ConnectError, httpx.TimeoutException):
                raise GitHubClientError(
                    "Cannot reach api.github.com. Check your network connection and VPN."
                )

            if org_response.status_code in (404, 403):
                raise GitHubClientError(
                    f"Cannot access org '{self.org}'. Check you have access "
                    f"and the org name is correct in your config."
                )

        self._verified_at = time.monotonic()

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

    # --- Collaborators ---

    def list_direct_collaborators(self, owner: str, repo: str) -> list[dict]:
        """List collaborators added directly to a repo (not via team membership).

        Uses affiliation=direct to exclude team-based access.
        """
        return self._request(
            "GET",
            f"/repos/{owner}/{repo}/collaborators",
            params={"affiliation": "direct"},
        ).json()

    def remove_collaborator(self, owner: str, repo: str, username: str) -> None:
        """Remove a direct collaborator from a repo."""
        self._request("DELETE", f"/repos/{owner}/{repo}/collaborators/{username}")

    # --- Teams ---

    def list_repo_teams(self, owner: str, repo: str) -> list[dict]:
        """List all teams with access to a repo."""
        return self._request("GET", f"/repos/{owner}/{repo}/teams").json()

    def get_team_repo_permission(self, org: str, team_slug: str, owner: str, repo: str) -> str | None:
        """Get a team's permission on a repo. Returns None if not set.

        Requires the repository media type header to get a JSON response
        with ``role_name`` instead of a bare 204 No Content.
        """
        try:
            data = self._request(
                "GET",
                f"/orgs/{org}/teams/{team_slug}/repos/{owner}/{repo}",
                headers={"Accept": "application/vnd.github.v3.repository+json"},
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

    def list_team_members(self, org: str, team_slug: str) -> list[dict]:
        """List members of an org team."""
        return self._request("GET", f"/orgs/{org}/teams/{team_slug}/members").json()

    # --- Branch protection (classic — for migration/cleanup) ---

    def get_branch_protection(self, owner: str, repo: str, branch: str) -> dict | None:
        """Get classic branch protection rules. Returns None if not protected."""
        try:
            return self._request(
                "GET", f"/repos/{owner}/{repo}/branches/{branch}/protection"
            ).json()
        except GitHubClientError:
            return None

    def delete_branch_protection(self, owner: str, repo: str, branch: str) -> None:
        """Remove classic branch protection from a branch."""
        self._request("DELETE", f"/repos/{owner}/{repo}/branches/{branch}/protection")

    # --- Rulesets ---

    def list_rulesets(self, owner: str, repo: str) -> list[dict]:
        """List all rulesets for a repo."""
        return self._request("GET", f"/repos/{owner}/{repo}/rulesets").json()

    def get_ruleset(self, owner: str, repo: str, ruleset_id: int) -> dict:
        """Get a specific ruleset by ID."""
        return self._request("GET", f"/repos/{owner}/{repo}/rulesets/{ruleset_id}").json()

    def create_ruleset(self, owner: str, repo: str, payload: dict) -> dict:
        """Create a new ruleset."""
        return self._request("POST", f"/repos/{owner}/{repo}/rulesets", json=payload).json()

    def update_ruleset(self, owner: str, repo: str, ruleset_id: int, payload: dict) -> dict:
        """Update an existing ruleset."""
        return self._request(
            "PUT", f"/repos/{owner}/{repo}/rulesets/{ruleset_id}", json=payload
        ).json()

    def delete_ruleset(self, owner: str, repo: str, ruleset_id: int) -> None:
        """Delete a ruleset."""
        self._request("DELETE", f"/repos/{owner}/{repo}/rulesets/{ruleset_id}")

    def find_ruleset_by_name(self, owner: str, repo: str, name: str) -> dict | None:
        """Find a ruleset by name. Returns None if not found."""
        for rs in self.list_rulesets(owner, repo):
            if rs["name"] == name:
                return self.get_ruleset(owner, repo, rs["id"])
        return None

    # --- Teams ---

    def get_team(self, org: str, team_slug: str) -> dict:
        """Get team details including ID."""
        return self._request("GET", f"/orgs/{org}/teams/{team_slug}").json()

    def get_team_id(self, org: str, team_slug: str) -> int:
        """Look up a team's numeric ID from its slug."""
        return self.get_team(org, team_slug)["id"]

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
        """Rename the default branch of a repo.

        If the target branch already exists (e.g. the repo has both
        ``main`` and ``dev``), we simply set the default branch rather
        than trying to rename.
        """
        repo_data = self.get_repo(owner, repo)
        current = repo_data["default_branch"]
        if current == new_name:
            return repo_data

        # Try renaming first — this works when the target doesn't exist yet
        try:
            return self._request(
                "POST",
                f"/repos/{owner}/{repo}/branches/{current}/rename",
                json={"new_name": new_name},
            ).json()
        except GitHubClientError:
            # Target branch likely already exists — just change the default
            return self.update_repo(owner, repo, default_branch=new_name)

    def create_branch(self, owner: str, repo: str, branch: str, from_branch: str) -> dict:
        """Create a new branch from an existing branch.

        Uses the Git Refs API to create a ref pointing at the same commit
        as *from_branch*.
        """
        # Get the SHA of the source branch
        ref_data = self._request(
            "GET", f"/repos/{owner}/{repo}/git/ref/heads/{from_branch}"
        ).json()
        sha = ref_data["object"]["sha"]

        # Create the new branch ref
        return self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        ).json()

    def compare_branches(self, owner: str, repo: str, base: str, head: str) -> dict:
        """Compare two branches.

        Returns the comparison data including ``ahead_by`` and
        ``behind_by`` counts.  ``ahead_by`` is the number of commits
        in *head* that are not in *base*.
        """
        return self._request(
            "GET", f"/repos/{owner}/{repo}/compare/{base}...{head}"
        ).json()

    def delete_branch(self, owner: str, repo: str, branch: str) -> None:
        """Delete a branch via the Git Refs API."""
        self._request("DELETE", f"/repos/{owner}/{repo}/git/refs/heads/{branch}")
