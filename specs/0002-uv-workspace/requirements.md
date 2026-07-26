# Requirements Document: uv Workspace Restructuring

Tracks: PeopleForBikes/brokenspoke-analyzer#1143

## Introduction

`brokenspoke-analyzer` is growing a family of closely related tools
(`bna-batch`, `cache-warmer`, and an in-progress `bna-bench`) that currently
live, or would otherwise have to live, as standalone scripts under `utils/`.
As these tools become more complex, and in some cases required for production
use cases (e.g. `cache-warmer` for the cloud pipeline), they need to become
first-class, independently testable/buildable projects instead of loose
scripts.

This feature restructures the repository into a [uv
workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/), splitting
the existing single package into:

- **`brokenspoke-analyzer-lib`**: the core BNA functionality (currently
  `brokenspoke_analyzer/core/` and its supporting SQL/data assets), with no
  CLI or executable entry points.
- **`brokenspoke-analyzer-cli`**: the current `bna` command-line frontend
  (currently `brokenspoke_analyzer/cli/`), depending on
  `brokenspoke-analyzer-lib`.

The workspace root itself becomes a thin, non-published "virtual" project that
only declares the workspace members — it contains no source code of its own.

This feature covers the structural migration only: reorganizing source,
tests, docs, packaging, `Dockerfile`, `justfile`, and CI so the two packages
build, lint, test, and run exactly as the current single package does today
(`bna run-with compose ...` etc. must keep working unchanged from a user's
point of view). It explicitly does **not** cover:

- Migrating `utils/bna-batch.py` or `utils/cache-warmer.py` into workspace
  members — that happens in subsequent PRs, but this restructuring must leave
  the workspace in a state that makes those migrations straightforward (i.e.
  adding a new `packages/brokenspoke-analyzer-<tool>/` member should require
  no further root-level restructuring).
- Scaffolding `bna-bench` (in progress on another branch) — the workspace
  layout must simply be able to accommodate it as a future member.
- Publishing any package independently to PyPI. All workspace members share a
  single version number (kept in lockstep, as today) and are intended for
  internal/dev use only; each member's `pyproject.toml` should nonetheless
  remain individually valid metadata so independent publishing remains
  possible later without further restructuring.

## Glossary

- **Workspace**: A uv multi-project configuration (`[tool.uv.workspace]`)
  where a single root `pyproject.toml` and lockfile govern multiple member
  packages that can depend on each other via workspace sources.
- **Workspace root**: The top-level `pyproject.toml` that declares
  `[tool.uv.workspace] members`. In this feature it is a virtual project: no
  importable code, no console scripts, not installed/published itself.
- **Workspace member**: An installable package living under `packages/`, each
  with its own `pyproject.toml`, `src/` layout, and test suite.
- **`brokenspoke-analyzer-lib`**: The workspace member containing core BNA
  logic (download, ingest, compute, export, database models, SQL scripts).
  Importable as `brokenspoke_analyzer_lib`. Not executable.
- **`brokenspoke-analyzer-cli`**: The workspace member providing the `bna`
  Typer console script. Importable as `brokenspoke_analyzer_cli`. Depends on
  `brokenspoke-analyzer-lib` via a workspace source.
- **Workspace source**: uv's mechanism (`[tool.uv.sources]` with
  `{ workspace = true }`) for one member to depend on another using the local
  checkout instead of a published version.

## Requirements

### Requirement 1: Workspace root restructuring

**User Story:** As a maintainer, I want the repository root to become a
virtual uv workspace, so that new and existing BNA-related tools can be added
as independent, first-class packages without further root-level
restructuring.

#### Acceptance Criteria

1. WHEN the root `pyproject.toml` is inspected, THE root project SHALL declare
   `[tool.uv.workspace]` with `members` including
   `packages/brokenspoke-analyzer-lib` and `packages/brokenspoke-analyzer-cli`.
2. THE root project SHALL NOT contain importable application source code, and
   SHALL NOT declare any `[project.scripts]` entry points.
3. WHEN `uv sync --all-extras --dev` is run from the repository root, THE
   system SHALL install all workspace members and their dependencies into a
   single environment using a single `uv.lock`.
4. WHERE a new BNA-related tool needs to be added as a workspace member in a
   future PR, THE workspace layout SHALL require only adding a new
   `packages/brokenspoke-analyzer-<tool>/` directory and listing it in
   `members` — no changes to the root project's own structure.

### Requirement 2: `brokenspoke-analyzer-lib` package

**User Story:** As a developer building a new frontend (batch, cache-warmer,
bench), I want a non-executable core library package, so that I can depend on
BNA's core functionality without pulling in CLI-specific dependencies.

#### Acceptance Criteria

1. THE system SHALL move the current contents of `brokenspoke_analyzer/core/`
   (and shared modules it depends on: `database/`, `scripts/`, `datastore.py`,
   `file_utils.py`, `utils.py`, `constant.py`) into
   `packages/brokenspoke-analyzer-lib/src/brokenspoke_analyzer_lib/`.
2. THE `brokenspoke-analyzer-lib` package SHALL declare its own
   `pyproject.toml` with correct name (`brokenspoke-analyzer-lib`), version
   (matching the workspace-wide version), dependencies, and build backend.
3. THE `brokenspoke-analyzer-lib` package SHALL NOT declare any
   `[project.scripts]` entry points.
4. THE `brokenspoke-analyzer-lib` package SHALL include only the dependencies
   required by core functionality (excluding CLI-only dependencies such as
   `typer`, if not otherwise needed at runtime by the core).
5. THE `brokenspoke-analyzer-lib` package SHALL have its own test suite under
   `packages/brokenspoke-analyzer-lib/tests/`, mirroring its `src/` layout.

### Requirement 3: `brokenspoke-analyzer-cli` package

**User Story:** As an existing user of the `bna` command, I want the CLI
frontend to keep working exactly as before after the restructuring, so that
my scripts and workflows are unaffected.

#### Acceptance Criteria

1. THE system SHALL move the current contents of `brokenspoke_analyzer/cli/`
   into `packages/brokenspoke-analyzer-cli/src/brokenspoke_analyzer_cli/`.
2. THE `brokenspoke-analyzer-cli` package SHALL declare its own
   `pyproject.toml` with correct name (`brokenspoke-analyzer-cli`), version
   (matching the workspace-wide version), and a `[project.scripts]` entry
   `bna = "brokenspoke_analyzer_cli.root:app"`.
3. THE `brokenspoke-analyzer-cli` package SHALL depend on
   `brokenspoke-analyzer-lib` via a uv workspace source
   (`{ workspace = true }`), not a path or published-version dependency.
4. WHEN a user runs `uv run bna <command>` from the repository root after the
   restructuring, THE system SHALL behave identically (same subcommands, same
   options, same `DATABASE_URL` requirement) to the pre-restructuring `bna`
   command.
5. THE `brokenspoke-analyzer-cli` package SHALL have its own test suite under
   `packages/brokenspoke-analyzer-cli/tests/`, mirroring its `src/` layout.

### Requirement 4: Shared versioning

**User Story:** As a maintainer, I want all workspace members to share one
version number defined in a single place, so that releases stay simple to
reason about and it is structurally impossible for members to drift apart.

#### Acceptance Criteria

1. THE workspace SHALL define the version string in exactly one location
   (e.g. a single root version file or `hatch-vcs`-derived git tag), not
   independently in each member's `pyproject.toml`.
2. THE root workspace, `brokenspoke-analyzer-lib`, and
   `brokenspoke-analyzer-cli` SHALL each declare `dynamic = ["version"]` and
   resolve their version from that single source at build/sync time (e.g. via
   `[tool.hatch.version]` pointing at a shared file, or `hatch-vcs`).
3. WHEN the project version is bumped, THE process SHALL require editing only
   the single shared version source, and SHALL NOT require editing each
   member's `pyproject.toml` individually.
4. IT SHALL NOT be possible for one workspace member to build with a
   different resolved version than another, since all members resolve their
   version from the same source.

### Requirement 5: Documentation restructuring

**User Story:** As a developer, I want a single documentation site that
covers both packages, so that I don't have to jump between multiple doc
builds to understand the whole project.

#### Acceptance Criteria

1. THE Sphinx documentation SHALL remain rooted at `docs/` (single build,
   single output site).
2. THE documentation SHALL include a distinct section/toctree for
   `brokenspoke-analyzer-lib` and a distinct section/toctree for
   `brokenspoke-analyzer-cli`, each generated (via `autodoc`/`sphinx-apidoc`
   or equivalent) from that member's `src/` package.
3. WHEN `just docs` or `just docs-autobuild` is run, THE system SHALL
   successfully build documentation covering both workspace members without
   further manual configuration.

### Requirement 6: Test suite restructuring

**User Story:** As a developer, I want each workspace member's tests to live
with that member, so that each package is independently testable without
requiring sibling packages' test fixtures.

#### Acceptance Criteria

1. THE existing `tests/` tree SHALL be split so that tests exercising
   `brokenspoke_analyzer/core/*` move under
   `packages/brokenspoke-analyzer-lib/tests/`, and tests exercising
   `brokenspoke_analyzer/cli/*` move under
   `packages/brokenspoke-analyzer-cli/tests/`.
2. EACH workspace member's test directory SHALL mirror that member's `src/`
   package layout, consistent with the project's existing testing convention.
3. WHEN `uv run pytest` is run from within a single workspace member's
   directory, THE system SHALL run only that member's tests successfully
   without requiring the other member to be present.
4. WHEN `just test` is run from the repository root, THE system SHALL run the
   full test suite across all workspace members with combined coverage
   reporting equivalent to today's `--cov=brokenspoke_analyzer`.
5. Doctests (`xdoctest`) currently collected via `pytest` `addopts` SHALL
   continue to be collected and run for both workspace members.

### Requirement 7: Build, lint, and tooling integration

**User Story:** As a maintainer, I want `just`, `Dockerfile`, and CI to work
against the new workspace layout, so that day-to-day development and
deployment are not broken by the restructuring.

#### Acceptance Criteria

1. THE `justfile` recipes (`setup`, `lint`, `lint-python`, `lint-sql`,
   `lint-uv`, `fmt`, `fmt-python`, `test`, `docs`, `docs-autobuild`,
   `docker-build`, `ci`) SHALL be updated to operate correctly across all
   workspace members.
2. THE `Dockerfile` SHALL be updated to build an image that installs and runs
   the `brokenspoke-analyzer-cli` package (and its `brokenspoke-analyzer-lib`
   dependency) via the workspace, producing a working `bna` command in the
   resulting image.
3. THE CI configuration SHALL be updated so that lint, type-check
   (`ty check`), and test jobs run correctly against the new workspace
   layout, with no reduction in coverage compared to pre-restructuring CI.
4. THE `pyproject.toml` `[tool.ruff]`, `[tool.isort]`, `[tool.sqlfluff]`, and
   `[tool.ty]`/mypy configuration SHALL be updated (at the workspace root
   and/or per-member, as appropriate) so linting/type-checking continues to
   cover both members' source and test trees.
5. THE `CLAUDE.md` architecture section SHALL be updated to reflect the new
   workspace layout and package boundaries.
6. THE `.github/CONTRIBUTING.md` "Development Container" section (including
   "Debugging") SHALL be updated to reference the new package names
   (`brokenspoke-analyzer-lib`, `brokenspoke-analyzer-cli`) instead of the
   single `brokenspoke-analyzer` package, with no change to the documented
   commands or VS Code workflow, since `uv sync` from the workspace root
   continues to editable-install all members at once.

## Out of Scope

- Migrating `utils/bna-batch.py` and `utils/cache-warmer.py` into workspace
  members (tracked as subsequent PRs/specs).
- Scaffolding or integrating `bna-bench`.
- Publishing any workspace member independently to PyPI, or setting up
  per-package release/versioning automation.
- Changing the `bna` command's behavior, options, or output in any way beyond
  what is required by the package rename/relocation.
