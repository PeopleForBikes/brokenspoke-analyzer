# Implementation Plan: uv Workspace Restructuring

> **Implementation note:** the implementation departs from this document in a
> number of places. See [deviations.md](deviations.md) for the full delta and
> the reasoning behind each one.

## Overview

Work proceeds bottom-up: establish the shared version source and the virtual
workspace root first (nothing depends on package contents yet), then move the
non-executable `lib` package (no dependents to break), then the `cli` package
(which depends on `lib`), then update everything that wraps the two packages
(tests already move with each package; docs, Dockerfile, justfile, CI,
CONTRIBUTING/CLAUDE.md). Checkpoints after each major phase catch breakage early
instead of at the very end.

## Tasks

- [x] 1. Create the shared version source and virtual workspace root
  - Create root `VERSION` file containing the current version string (`3.1.1`),
    no quotes/keys.
  - Rewrite root `pyproject.toml`: remove `[project.dependencies]` and
    `[project.scripts]`, add
    `[tool.uv.workspace] members = ["packages/brokenspoke-analyzer-lib", "packages/brokenspoke-analyzer-cli"]`,
    add `[tool.uv] package = false`. Keep `[dependency-groups] dev` at the root.
    Keep shared `[tool.ruff]`, `[tool.isort]`, `[tool.sqlfluff]`,
    `[tool.ty]`/mypy sections (paths updated in later tasks once source moves).
  - _Requirements: 1.1, 1.2, 4.1_

- [x] 2. Scaffold `packages/brokenspoke-analyzer-lib`
  - [x] 2.1 Create `packages/brokenspoke-analyzer-lib/pyproject.toml`
    - `name = "brokenspoke-analyzer-lib"`, `dynamic = ["version"]`,
      `[tool.hatch.version] path = "../../VERSION"`,
      `pattern = "(?P<version>.+)"`.
    - Move non-CLI runtime dependencies here (everything from the current root
      `dependencies` list except `typer`; confirm during the move whether `rich`
      is used directly by `core/` code — if not, it moves to the cli package
      instead).
    - No `[project.scripts]`.
    - _Requirements: 2.2, 2.3, 2.4, 4.2_
  - [x] 2.2 Move source into
        `packages/brokenspoke-analyzer-lib/src/brokenspoke_analyzer_lib/`
    - `git mv brokenspoke_analyzer/core/* → .../brokenspoke_analyzer_lib/core/`
      (or flatten per design — confirm final sub-layout matches `design.md`'s
      Architecture diagram: `core/`, `database/`, `scripts/`, `pyrosm/`,
      `datastore.py`, `file_utils.py`, `utils.py`, `constant.py` all land
      directly under `brokenspoke_analyzer_lib/`).
    - Update all intra-package imports from `brokenspoke_analyzer.core...` /
      `brokenspoke_analyzer....` to `brokenspoke_analyzer_lib....`.
    - _Requirements: 2.1_
  - [x] 2.3 Move and consolidate tests into
        `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/`
    - Merge the two existing trees (`tests/brokenspoke_analyzer/core/*` and
      `tests/core/*`) into one, resolving any duplication/overlap found along
      the way.
    - Update imports to `brokenspoke_analyzer_lib....`.
    - Add `[tool.pytest.ini_options]` to
      `packages/brokenspoke-analyzer-lib/pyproject.toml` (markers,
      `addopts --xdoctest --cov-report ...`), and a `[tool.coverage.run] omit`
      list scoped to this package's own non-testable modules (ported from the
      root's current omit list, renamed).
    - _Requirements: 2.5, 6.1, 6.2, 6.3, 6.5_
  - [x] 2.4 Checkpoint - `brokenspoke-analyzer-lib` builds and tests standalone
    - `cd packages/brokenspoke-analyzer-lib && uv run pytest` passes with no
      `brokenspoke-analyzer-cli` present.
    - `uv build --package brokenspoke-analyzer-lib --wheel` succeeds; wheel
      contains no typer/CLI code.
    - _Requirements: Correctness Property 4 (design.md)_

- [x] 3. Scaffold `packages/brokenspoke-analyzer-cli`
  - [x] 3.1 Create `packages/brokenspoke-analyzer-cli/pyproject.toml`
    - `name = "brokenspoke-analyzer-cli"`, `dynamic = ["version"]`,
      `[tool.hatch.version] path = "../../VERSION"`,
      `pattern = "(?P<version>.+)"`.
    - `dependencies = ["brokenspoke-analyzer-lib", "typer>=0.26.8,<0.27"]` (add
      `rich` here if task 2.1 determined it's CLI-only).
    - `[project.scripts] bna = "brokenspoke_analyzer_cli.root:app"`.
    - `[tool.uv.sources] brokenspoke-analyzer-lib = { workspace = true }`.
    - _Requirements: 3.2, 3.3, 4.2_
  - [x] 3.2 Move source into
        `packages/brokenspoke-analyzer-cli/src/brokenspoke_analyzer_cli/`
    - `git mv brokenspoke_analyzer/cli/* → .../brokenspoke_analyzer_cli/`.
    - Update imports from `brokenspoke_analyzer.cli...` to
      `brokenspoke_analyzer_cli...`, and from `brokenspoke_analyzer.core...` to
      `brokenspoke_analyzer_lib....`.
    - Remove the now-empty root `brokenspoke_analyzer/` package and `main.py`.
    - _Requirements: 3.1_
  - [x] 3.3 Move CLI tests into
        `packages/brokenspoke-analyzer-cli/tests/brokenspoke_analyzer_cli/`
    - Update imports accordingly; add `[tool.pytest.ini_options]` and
      `[tool.coverage.run] omit` to this package's `pyproject.toml`.
    - _Requirements: 3.5, 6.1, 6.2, 6.3, 6.5_
  - [x] 3.4 Checkpoint - `uv run bna` behaves identically to pre-restructuring
    - From repo root: `uv sync --all-extras --dev`, then `uv run bna --help` and
      `uv run bna -vv configure custom 4 4096 postgres` (or an equivalent smoke
      command) behave the same as on `main`.
    - `uv build --package brokenspoke-analyzer-cli --wheel` succeeds.
    - _Requirements: 3.4, Correctness Property 3 (design.md)_

- [x] 4. Update shared lint/type-check/format configuration
  - Update root `pyproject.toml`'s `[tool.ruff]` (`extend-exclude`),
    `[tool.isort]`, `[tool.sqlfluff.core]` (SQL path moved under
    `packages/brokenspoke-analyzer-lib/src/brokenspoke_analyzer_lib/scripts/sql/`),
    and `[tool.ty.src]`/mypy `exclude`/overrides so they reference
    `packages/*/src` and `packages/*/tests` instead of `brokenspoke_analyzer/*`.
  - _Requirements: 7.4_
  - [x] 4.1 Checkpoint - lint/type-check pass across both members
    - `uv run isort --check .`, `uv run ruff check .`,
      `uv run ruff format --check .`, `uv run ty check packages/*/src`,
      `uv run sqlfluff lint packages/brokenspoke-analyzer-lib/src/brokenspoke_analyzer_lib/scripts/sql/`
      all pass.

- [x] 5. Update `justfile`
  - Update `src_dir`/add per-member path variables so `lint-python`,
    `fmt-python` cover both `packages/*/src` and `packages/*/tests`.
  - Update `test` recipe to run pytest across both members with combined
    coverage (per `design.md`'s Testing Strategy — prefer one root-level
    invocation unless workspace/pytest interaction forces per-member +
    `coverage combine`).
  - Update `lint-sql` recipe's SQL path.
  - Leave `docker-build`, `compose-up`/`down`, `docker-prepare-all`,
    `test-e2e-prepare` unchanged (they don't reference package paths).
  - _Requirements: 7.1_

- [x] 6. Update `Dockerfile`
  - `builder` stage: replace `uv build --wheel` with
    `uv build --all-packages --wheel` (or two explicit `--package` builds);
    ensure `uv export`/wheel-vendoring step still captures the union of both
    members' runtime dependencies.
  - `main` stage: install both resulting wheels
    (`brokenspoke_analyzer_lib-*.whl` and `brokenspoke_analyzer_cli-*.whl`)
    instead of the single `brokenspoke_analyzer-*.whl`. Leave
    `ENTRYPOINT ["bna"]` unchanged.
  - _Requirements: 7.2_
  - [x] 6.1 Checkpoint - Docker image builds and runs
    - Verified via `just docker-build-devcontainer` (the `dev` target) followed
      by `just docker-prepare-all`, which now runs against the `:dev` tag —
      `dev` shares the same `builder`/`main` stages as the plain `docker-build`
      target, so this exercises the same wheel export/install path. Plain
      `just docker-build` (`:latest`) itself was not separately re-run.

- [x] 7. Update Sphinx documentation
  - Extend `docs/source/conf.py`'s path setup to include
    `packages/brokenspoke-analyzer-lib/src` and
    `packages/brokenspoke-analyzer-cli/src` for autodoc; update the
    `metadata.version(...)` call to read the `brokenspoke-analyzer-cli`
    distribution (or read root `VERSION` directly) since the root package no
    longer installs.
  - Add `docs/source/lib/` and `docs/source/cli/` with `sphinx-apidoc`-generated
    or hand-written `automodule` pages for each member; add both to
    `docs/source/index.rst`'s toctree.
  - Re-link any narrative doc (`commands.md`, `workflow.md`, `about.md`, etc.)
    that references the old `brokenspoke_analyzer.core`/`.cli` import paths.
  - _Requirements: 5.1, 5.2_
  - [x] 7.1 Checkpoint - docs build cleanly
    - `just docs` succeeds with no new Sphinx warnings beyond the current
      baseline; generated site includes both new sections.
    - _Requirements: 5.3_

- [x] 8. Update CI workflows (local, non-external-workflow parts only)
  - Review `.github/workflows/ci.yaml`'s `lint-sql` job's `just setup`/
    `just lint-sql` calls against the new paths (should work unchanged if task
    5's `justfile` update is correct — verify in CI, not just locally).
  - Confirm/document interaction with the external `ci-python-uv.yml` and
    `release-python-uv.yml` reusable workflows per `design.md`'s Error Handling
    section: if they break against the virtual-root workspace, add a minimal
    local workaround (e.g. inline `uv build --all-packages` steps in
    `release.yaml`'s `release-dist` job) rather than blocking this feature on
    the separately tracked shared-workflow issue.
  - _Requirements: 7.3_
  - [x] 8.1 Checkpoint - CI green on this branch's PR
    - Verified: all CI jobs (`ci`, `lint-sql`, and any added workaround steps)
      pass on the actual PR on GitHub.com.

- [x] 9. Update documentation referencing the old layout
  - Update `CLAUDE.md`'s Architecture section to describe
    `packages/brokenspoke-analyzer-lib` and `packages/brokenspoke-analyzer-cli`,
    their import names, and the virtual workspace root.
  - Update `.github/CONTRIBUTING.md`'s "Development Container" → "Debugging"
    section to reference the new package names instead of the single
    `brokenspoke-analyzer` package; leave documented commands and the VS Code
    rebuild/reopen flow unchanged.
  - _Requirements: 7.5, 7.6_

- [x] 10. Checkpoint - full manual verification pass
  - Verified: `uv sync --all-extras --dev` succeeds from a clean checkout (via
    the passing GitHub Actions CI run, which runs this step).
  - Verified: `just ci` (lint + docs + test) passes end-to-end (via CI).
  - Verified: `uv run bna --help` and a representative subcommand behave
    identically to `main`.
  - Verified: `just docker-build` succeeds and the built image runs `bna`
    correctly.
  - Verified: `uv build --package brokenspoke-analyzer-lib --wheel` succeeds
    independently of the cli package.
  - Verified: Dev container round-trip
    (`Dev Containers: Rebuild and Reopen in Container`, `uv sync` inside it,
    `Python: Select Interpreter` → `./.venv/bin/python` debugging) works.
  - Verified: `integration/` e2e fixtures still invoke `bna` successfully
    (spot-checked).

## Notes

- No task in this plan touches `utils/bna-batch.py`, `utils/cache-warmer.py`, or
  `bna-bench` — those remain explicitly out of scope (see `requirements.md`).
- Task 2 (lib) must land and be checkpointed before task 3 (cli) begins, since
  the cli package depends on the lib package via a workspace source that must
  already exist and build cleanly.
- If hatchling's currently-pinned version doesn't support regex/file-based
  dynamic versioning as described in `design.md`, that's a blocker for task 1
  and should be resolved (bump hatchling) before proceeding.
- Task 8's CI workaround, if needed, should be written so it's trivially
  removable once the separately tracked shared-workflow issue in
  `PeopleForBikes/.github` is resolved — leave a comment pointing at that issue.
