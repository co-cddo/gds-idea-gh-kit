# gds-idea-gh-kit

CLI tool for auditing and enforcing GitHub repo standards for GDS IDEA teams.

Checks repos against a shared configuration and can auto-fix most issues:

- **Naming conventions** per repo type (e.g. `gds-idea-app-{name}`)
- **Repo settings** -- merge strategy, wiki, issues, projects
- **Team permissions** -- expected teams, unexpected teams, direct collaborators
- **Branch protection** via rulesets -- deletion, force push, PRs, linear history, bypass actors
- **Required files** -- `.gitignore`, `LICENSE`, `README.md`, `dependabot.yml`
- **Required workflows** per repo type -- `lint.yml`, `test.yml`, deploy workflows
- **Security** -- vulnerability alerts, automated security fixes

## Prerequisites

Install the [GitHub CLI](https://cli.github.com/) and authenticate:

```bash
brew install gh
gh auth login
```

You need access to the `co-cddo` GitHub organisation.

## Installation

`idea-gh` is installed as a global CLI tool via the [GDS IDEA package index](https://co-cddo.github.io/gds-idea-pypi/).

**Recommended — using `idea-tools`** (see the [index page](https://co-cddo.github.io/gds-idea-pypi/) for one-time setup):

```bash
idea-tools install gds-idea-gh-kit
```

**Alternative — without `idea-tools`:**

```bash
uv tool install gds-idea-gh-kit --index gds-idea=https://co-cddo.github.io/gds-idea-pypi/simple/
```

To upgrade to the latest version:

```bash
idea-tools upgrade gds-idea-gh-kit
# or without idea-tools:
uv tool upgrade gds-idea-gh-kit
```

If you previously installed from a git URL, switch to the index:

```bash
idea-tools install gds-idea-gh-kit --reinstall
```

Verify it's working:

```bash
idea-gh --version
```

## Usage

### Audit a single repo

Run from inside a cloned repo:

```bash
cd gds-idea-app-my-dashboard
idea-gh audit
```

Output is grouped by severity: auto-fixable failures, manual fixes needed, and warnings. Passing checks are hidden by default.

### Audit all repos

Audit every repo in the org that matches a known naming pattern:

```bash
idea-gh audit --all
```

Filter by repo type:

```bash
idea-gh audit --all --type cdk-app
```

### Auto-fix issues

Fix everything that can be fixed automatically (settings, teams, branch rulesets, security):

```bash
idea-gh audit --fix
idea-gh audit --all --fix
```

The tool applies fixes, then re-audits to show the updated state.

### Show all checks

By default, passing checks are hidden. Use `--verbose` to see everything:

```bash
idea-gh audit --verbose
```

### Other commands

```bash
# Validate the configuration
idea-gh check-config

# Rename a repo (run from inside the repo)
idea-gh rename my-new-name

# Remove specific direct collaborators
idea-gh remove-collaborators jane-doe bob-smith

# Remove all direct collaborators
idea-gh remove-collaborators --all

# Show the repo ID for the current directory
idea-gh show-id

# Show the ID of a specific repo in the configured org
idea-gh show-id --repo gds-idea-gh-kit

# Show the configured org's ID (plus the current repo's, if run inside one)
idea-gh show-id --org
```

## What gets fixed

| Check | Auto-fixable | Notes |
|---|---|---|
| Naming convention | No | Too destructive. Use `idea-gh rename` manually |
| Repo settings | Yes | Merge strategy, wiki, issues, projects |
| Team permissions | Yes | Grants/updates expected teams |
| Unexpected teams | No | Warning only -- review and remove manually |
| Direct collaborators | No | Warning only -- use `idea-gh remove-collaborators` |
| Default branch | Yes | Renames the branch |
| Branch rulesets | Yes | Creates or updates rulesets |
| Classic branch protection | Yes | Removes and replaces with rulesets |
| Required files | No | Must be added manually |
| Required workflows | No | Must be added manually |
| Vulnerability alerts | Yes | Enables if disabled |
| Automated security fixes | Yes | Enables if disabled |

## Configuration

A default configuration is bundled with the tool and updates automatically when you upgrade. It defines the standards for `co-cddo` repos.

To use a custom configuration instead:

```bash
idea-gh --config path/to/my-config.yml audit
```

See [`config.example.yml`](config.example.yml) for the full configuration reference. The main sections are:

- **`org`** -- GitHub organisation name
- **`teams`** -- expected teams and their permission levels
- **`repo_settings`** -- merge strategy, wiki, issues, projects
- **`required_files`** -- files that must exist in every repo
- **`security`** -- vulnerability alerts, automated security fixes
- **`repo_types`** -- per-type settings (naming pattern, default branch, branch protection, required workflows)

## Development

```bash
# Clone and install dev dependencies
git clone git@github.com:co-cddo/gds-idea-gh-kit.git
cd gds-idea-gh-kit
uv sync

# Run tests
uv run pytest

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```
