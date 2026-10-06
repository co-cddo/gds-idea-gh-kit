---
name: idea-gh-usage
description: Use the idea-gh CLI to audit, fix, create and rename GitHub repositories so they follow GDS IDEA standards. Use when creating a new repo in co-cddo, checking whether a repo meets the standards, fixing repo settings, teams, branch protection or labels, or renaming a repo.
license: MIT
---

# Skill: idea-gh-usage

## What idea-gh does

`idea-gh` is a CLI tool that audits GitHub repositories in the `co-cddo` organisation against a shared configuration, reports what does not comply, and fixes most of it automatically. It enforces naming conventions, repo settings, team permissions, branch protection (as rulesets), required files and workflows, release labels and security settings.

## When to use it

- Creating a new repository: use `idea-gh init` (do not create and configure it by hand).
- Checking a repo, or the whole org, against the standards: `idea-gh audit`.
- Settings, teams, rulesets, labels or security alerts have drifted: `idea-gh audit --fix`.
- Renaming a repo or removing people who were added directly rather than through a team.

Do not use it to change code or CI in a repo: it only manages GitHub-side configuration.

## Prerequisites

- `gh` CLI installed and authenticated (`gh auth login`).
- `uv` for installation (`brew install uv` or equivalent).
- Admin access to any repo you want to fix with `--fix`, `init`, `rename` or `remove-collaborators`.

## Installation

```bash
# Via the GDS IDEA tools installer (preferred)
idea-tools install gds-idea-gh-kit

# Or directly with uv
uv tool install gds-idea-gh-kit --index gds-idea=https://co-cddo.github.io/gds-idea-pypi/simple/
```

To upgrade: `idea-tools upgrade gds-idea-gh-kit`. `audit` and `init` check for a newer version and tell you if there is one.

## Commands

### idea-gh audit

Audit the repo you are in (run it from inside a clone, with `origin` pointing at `github.com/co-cddo/...`):

```bash
idea-gh audit                    # type is detected from marker files
idea-gh audit --type cdk-app     # or state the type explicitly
idea-gh audit --verbose          # also show passing checks
idea-gh audit --fix              # fix everything that can be fixed automatically
```

Audit every repo in the org whose name starts with a known prefix (`gds-idea-`):

```bash
idea-gh audit --all
idea-gh audit --all --type cdk-app   # only repos of one type
idea-gh audit --all --fix
```

Failures are grouped as auto-fixable, needs a manual fix, and warnings. `--fix` applies the fixes and then audits again to show the result.

### idea-gh init

Create a new GitHub repo and configure it fully:

```bash
idea-gh init --type <repo-type>
```

Run it from inside a local git repo that has at least one commit. The repo's directory name must match the naming pattern for the type. In order, it:

1. Creates the repo in `co-cddo` (private by default) and pushes. If `origin` already points at that repo, for example after `gh repo create --source . --push`, it uses the existing repo instead.
2. Applies the standard repo settings.
3. Renames the default branch if the type needs a different one (`main` to `dev` for `cdk-app`).
4. Creates any extra branches the type needs (`prod` for `cdk-app`).
5. Attaches the teams with the right permissions.
6. Creates the branch protection rulesets.
7. Enables vulnerability alerts and automated security fixes.
8. Creates the `bump:major`, `bump:minor` and `bump:patch` labels.

Note: `init` creates repos **private**. A `python-package` that should appear on the public package index must be public, so create that one with `gh repo create ... --public --source . --push` first and then run `idea-gh init`.

### idea-gh check-config

Validate the configuration file:

```bash
idea-gh check-config
idea-gh --config ./my-config.yml check-config
```

### idea-gh rename

Rename the current repo (run it from inside the repo):

```bash
idea-gh rename new-repo-name
idea-gh rename new-repo-name --yes   # skip the confirmation
```

This renames the repo on GitHub only. It does **not** update any clone's remote, so every existing clone (including yours) needs `git remote set-url origin <new url>`. It also breaks CI/CD pipelines that use the old name and cross-repo references. GitHub redirects the old URL, but not permanently. It prints these warnings and asks for confirmation.

### idea-gh remove-collaborators

Remove people who were added directly rather than through a team:

```bash
idea-gh remove-collaborators user1 user2
idea-gh remove-collaborators --all
idea-gh remove-collaborators --all --yes   # skip the confirmation
```

### idea-gh show-id

Show the numeric IDs that AWS OIDC trust policies need:

```bash
idea-gh show-id                          # this repo's ID and its OIDC sub claim prefix
idea-gh show-id --repo gds-idea-gh-kit   # another repo in the configured org
idea-gh show-id --org                    # the organisation's ID
idea-gh show-id --repo gds-idea-gh-kit --org
```

### Global options

```bash
idea-gh --config <path>    # use a custom config file instead of the built-in one
idea-gh --version
```

## Repo types

| Type | Name must match | Detected by | Default branch | Branch protection |
|------|-----------------|-------------|----------------|-------------------|
| `cdk-app` | `gds-idea-app-{name}` | `cdk.json` | `dev` (plus `prod`) | `dev`: PR, 1 approval from `gds-idea-ds`, squash only. `prod`: PR, 1 approval from `gds-idea-senior-ds`, merge only. |
| `python-package` | `gds-idea-pkg-{name}` | `pyproject.toml` | `main` | PR, 1 approval from `gds-idea-ds`, squash only |
| `econ` | `gds-idea-econ-{name}` | (none, pass `--type econ`) | `main` | PR, no approvals required |

Detection checks the types in the order above and the first marker file found wins, so a CDK app (which also has a `pyproject.toml`) is detected as `cdk-app`. Use `--type` to override; `pkg` is accepted as short for `python-package`.

Repos that do not follow the naming pattern, such as the older `gds-idea-app-kit` and `gds-idea-gh-kit`, fail the naming check. That is expected and cannot be auto-fixed.

## What gets checked

| Category | What is checked | Auto-fixable |
|----------|-----------------|--------------|
| **Naming** | Repo name matches the type's pattern | No |
| **Settings** | Squash merge on, rebase merge off, branch deleted on merge, issues on, wiki and projects off | Yes |
| **Teams** | `gds-idea-all` read, `gds-idea-ds` maintain, `gds-idea-senior-ds` and `gds-idea-super-admin` admin (plus type-specific teams); unexpected teams are flagged | Yes (the expected ones) |
| **Branches** | Default branch name, and a ruleset per protected branch: PRs, approvals, linear history, allowed merge methods, no deletion, no force push, bypass actors | Yes |
| **Files** | `.gitignore`, `LICENSE` or `LICENCE`, `README.md`, `.github/dependabot.yml`, and the type's required workflows (`ci.yml` and `release.yml` for `python-package`) | No |
| **Labels** | `bump:major`, `bump:minor`, `bump:patch` exist | Yes |
| **Security** | Vulnerability alerts and automated security fixes enabled | Yes |

`audit --fix` may also offer to delete a stale branch left after a default branch rename, and to update your local clone. It always asks first.

## Typical workflows

### Creating a new repo

```bash
# Scaffold the project (idea-app init creates the git repo and the first commit)
idea-app init streamlit my-dashboard
cd gds-idea-app-my-dashboard

# Create and configure the GitHub repo
idea-gh init --type cdk-app
```

For a Python package that should be on the package index (public):

```bash
idea-app init python my-tool
cd gds-idea-pkg-my-tool
gh repo create co-cddo/gds-idea-pkg-my-tool --public --source . --push
idea-gh init --type python-package
```

### Auditing and fixing a repo

```bash
cd /path/to/gds-idea-app-my-project
idea-gh audit            # see what is wrong
idea-gh audit --fix      # fix what can be fixed automatically
```

Naming and missing files are reported but must be fixed by hand.

### Auditing the whole org

```bash
idea-gh audit --all           # report only
idea-gh audit --all --fix     # fix everything
```

## Troubleshooting

### Authentication errors

The tool uses `gh auth token`. Messages such as "gh auth token returned empty output", "gh CLI not found" and "GitHub token is invalid or expired" all mean the same thing: check and renew your login.

```bash
gh auth status   # should show you are logged in
gh auth login    # if not, or if the token has expired
```

### "Could not detect repo type for '<repo>'"

None of the types' marker files were found. Either add the marker file (for example `cdk.json` for `cdk-app`) or pass `--type <type>`. With `--all`, repos whose type cannot be detected are reported as skipped.

### "Unknown repo type '<type>'"

`--type` must be one of the types in the config (`cdk-app`, `python-package`, `econ`) or the alias `pkg`.

### Config validation errors

Run `idea-gh check-config`. The config is validated strictly and unknown keys are rejected.

### "Could not read git remote 'origin'"

`audit` without `--all`, `rename`, `remove-collaborators` and `init` expect to run inside a git repo with an `origin` remote pointing at `github.com/co-cddo/...`. "Could not parse GitHub owner/repo from remote URL" means `origin` points somewhere else.

### "This repo already has a remote 'origin' pointing to ..."

`init` found a different `origin` from the repo it would create. Use `idea-gh audit --fix` to configure that repo instead, or remove the remote and re-run `init`.
