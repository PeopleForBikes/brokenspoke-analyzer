# Implementation Plan: uv Workspace Restructuring

> **Implementation note:** this plan reflects the work as built.
> [deviations.md](deviations.md) records where, and why, the implementation
> departed from the original version of this plan.

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
  - Create root `VERSION` file containing the current version string (`3.2.5`
    when the work started), no quotes/keys.
  - Rewrite root `pyproject.toml`: remove `[project.dependencies]` and
    `[project.scripts]`, add
    `[tool.uv.workspace] members = ["packages/brokenspoke-analyzer-lib", "packages/brokenspoke-analyzer-cli"]`,
    add `[tool.uv] package = false`. Keep `[dependency-groups] dev` at the root.
    Keep shared `[tool.ruff]`, `[tool.isort]`, `[tool.sqlfluff]`,
    `[tool.ty]`/mypy sections (paths updated in later tasks once source moves).
  - Replace the root's static version with `dynamic = ["version"]` and
    `[tool.hatch.version] path = "VERSION"`, `pattern = "(?P<version>.+)"`.
  - Add root `[tool.uv.sources]` entries for both members and list both members
    in the `dev` group, so `uv sync` installs them into the single environment.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1, 4.2, 4.3_

- [x] 2. Scaffold `packages/brokenspoke-analyzer-lib`
  - [x] 2.1 Create `packages/brokenspoke-analyzer-lib/pyproject.toml`
    - `name = "brokenspoke-analyzer-lib"`, `dynamic = ["version"]`,
      `[tool.hatch.version] path = "../../VERSION"`,
      `pattern = "(?P<version>.+)"`.
    - Move non-CLI runtime dependencies here, decided by actual imports: `rich`
      and `pycountry` are CLI-only and move to the cli package; `aiohttp`,
      `geopandas` and `loguru` are declared by both members; `us` stays in the
      library.
    - Drop `python-dotenv` and `tenacity`, which were declared but never
      imported.
    - No `[project.scripts]`.
    - _Requirements: 2.2, 2.3, 2.4, 4.2_
  - [x] 2.2 Move source into
        `packages/brokenspoke-analyzer-lib/src/brokenspoke_analyzer_lib/`
    - `git mv` following `design.md`'s Architecture diagram: `core/` keeps the
      pipeline modules only; `database/`, `scripts/`, `datastore.py`,
      `file_utils.py`, `utils.py`, `constant.py` land directly under
      `brokenspoke_analyzer_lib/`. (There is no `pyrosm/` package to move.)
    - Update all intra-package imports from `brokenspoke_analyzer.core...` /
      `brokenspoke_analyzer....` to `brokenspoke_analyzer_lib....`.
    - _Requirements: 2.1_
  - [x] 2.3 Move tests into
        `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/`
    - Move `tests/brokenspoke_analyzer/core/*`. ~~Merge it with `tests/core/*`~~
      — dropped: `tests/core/` held only stale `__pycache__` artefacts, no
      tracked tests.
    - Rename `tests/test_cache_warmer.py` to `test_datastore.py` so the tree
      mirrors `src/`.
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
    - _Requirements: 4.4, Correctness Property 4 (design.md)_

- [x] 3. Scaffold `packages/brokenspoke-analyzer-cli`
  - [x] 3.1 Create `packages/brokenspoke-analyzer-cli/pyproject.toml`
    - `name = "brokenspoke-analyzer-cli"`, `dynamic = ["version"]`,
      `[tool.hatch.version] path = "../../VERSION"`,
      `pattern = "(?P<version>.+)"`.
    - `dependencies`: `brokenspoke-analyzer-lib`, `typer` (pinned as on `main`),
      plus `rich`, `pycountry`, `aiohttp`, `geopandas`, `loguru` per task 2.1.
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
  - [x] 3.2.1 Break the lib → cli import cycle
    - Move `DEFAULT_BUFFER`, `DEFAULT_CITY_FIPS_CODE`, `DEFAULT_COMPUTE_PARTS`
      and `DEFAULT_MAX_TRIP_DISTANCE` from `cli/common.py` to
      `brokenspoke_analyzer_lib.constant`; re-export them from
      `brokenspoke_analyzer_cli.common` under their existing names.
    - Replace the Typer `Annotated` aliases on `core/compute.py`'s `all_` and
      `parts` with plain types.
    - Remove every `brokenspoke_analyzer_cli` import from `core/compute.py`,
      `core/ingestor.py` and `datastore.py`.
    - _Requirements: 2.4, Correctness Property 4 (design.md)_
  - [x] 3.2.2 Replace `main.py` with `brokenspoke_analyzer_cli/__main__.py`
    - Point `.vscode/launch.json` at `"module": "brokenspoke_analyzer_cli"`.
    - _Requirements: 7.6_
  - [x] 3.3 Move CLI tests into
        `packages/brokenspoke-analyzer-cli/tests/brokenspoke_analyzer_cli/`
    - Replace the placeholder `tests/test_brokenspoke_analyzer.py`
      (`assert True`) with `test_root.py`, asserting `bna --help` exits cleanly
      and lists every pipeline stage; delete `tests/__init__.py`.
    - Add `[tool.pytest.ini_options]` and `[tool.coverage.run] omit` to this
      package's `pyproject.toml`.
    - _Requirements: 3.5, 6.1, 6.2, 6.3, 6.5_
  - [x] 3.4 Checkpoint - `uv run bna` behaves identically to pre-restructuring
    - From repo root: `uv sync --all-extras --dev`, then `uv run bna --help` and
      `uv run bna -vv configure custom 4 4096 postgres` (or an equivalent smoke
      command) behave the same as on `main`.
    - Verified: the help text of all 15 command/subcommand screens is
      byte-identical before and after (cwd-derived default paths normalised).
    - `uv build --package brokenspoke-analyzer-cli --wheel` succeeds.
    - _Requirements: 3.4, 4.4, Correctness Property 3 (design.md)_

- [x] 4. Update shared lint/type-check/format configuration
  - Update root `pyproject.toml`'s `[tool.ruff]`, `[tool.isort]`,
    `[tool.sqlfluff.core]` and `[tool.ty.src]`/mypy configuration so they
    reference `packages/*/src` and `packages/*/tests` instead of
    `brokenspoke_analyzer/*`. Drop the `pyrosm` exclusions.
  - Declare first-party packages explicitly: isort `known_first_party`, ruff
    `src` and `[tool.ruff.lint.isort] known-first-party`.
  - Lint the test trees with ruff, adding a `**/tests/**` per-file-ignores block
    for the conventional test exemptions; fix the one genuine finding (`TC003`).
  - Add a root `[tool.pytest.ini_options]` (with `testpaths` for both members)
    and a combined `[tool.coverage.run] omit` for `just test`.
  - _Requirements: 6.4, 7.4_
  - [x] 4.1 Checkpoint - lint/type-check pass across both members
    - `uv run isort --check .`, `uv run ruff check .`,
      `uv run ruff format --check .`, `uv run ty check packages/*/src`,
      `uv run sqlfluff lint packages/brokenspoke-analyzer-lib/src/brokenspoke_analyzer_lib/scripts/sql/`
      all pass.
  - [x] 4.2 Type-check the test trees
    - Add `[tool.ty.environment] root` listing both members' `src/`, so ty
      resolves first-party imports without relying on the editable installs
      being current.
    - Add `{{ test_dirs }}` to `lint-python`'s `ty check`.
    - Fix the one genuine finding: `test_datastore.py` passes its `DummySession`
      test double through `cast("aiohttp.ClientSession", ...)`.
    - _Requirements: 7.4_

- [x] 5. Update `justfile`
  - Add `lib_pkg`/`cli_pkg` variables and derive `src_dirs`, `test_dirs` and
    `sql_dir`, so `lint-python`, `fmt-python` cover both `packages/*/src` and
    `packages/*/tests`.
  - Update `test` recipe to run one root-level pytest across both members with
    `--cov=brokenspoke_analyzer_lib --cov=brokenspoke_analyzer_cli`.
  - Update `lint-sql` recipe's SQL path.
  - Leave `docker-build`, `compose-up`/`down`, `test-e2e-prepare` unchanged
    (they don't reference package paths).
  - Retarget `docker-prepare-all` from the hard-coded
    `peopleforbikes/brokenspoke-analyzer:latest` to `{{ docker_image }}:dev`, so
    it runs the image built from the working tree.
  - _Requirements: 6.4, 7.1_

- [x] 6. Update `Dockerfile`
  - [x] `builder` stage: export with
        `uv export --all-packages --no-emit-workspace ...` (a plain `uv export`
        produces an empty requirements file at a virtual root), and build with
        `uv build --all-packages --wheel`.
  - [x] `main` stage: install both resulting wheels
        (`brokenspoke_analyzer_lib-*.whl` and `brokenspoke_analyzer_cli-*.whl`)
        in a single `pip install` instead of the single
        `brokenspoke_analyzer-*.whl`. Leave `ENTRYPOINT ["bna"]` unchanged.
  - [x] Add `packages/*/tests` to `.dockerignore`.
  - _Requirements: 7.2_
  - [x] 6.1 Checkpoint - Docker image builds and runs
    - [x] `just docker-build-devcontainer` (the `dev` target) followed by
          `just docker-prepare-all` succeeds. `dev` shares the `builder`/`main`
          stages with the plain target.
    - [x] `just docker-build` (`:latest`) succeeds (verified on 2026-10-29).
    - [x] The `:latest` image runs `bna` correctly
          (`docker run --rm ghcr.io/peopleforbikes/brokenspoke-analyzer --help`
          lists every pipeline stage; verified on 2026-10-29).

- [x] 7. Update Sphinx documentation
  - Extend `docs/source/conf.py`'s path setup to include
    `packages/brokenspoke-analyzer-lib/src` and
    `packages/brokenspoke-analyzer-cli/src` for autodoc; update the
    `metadata.version(...)` call to read the `brokenspoke-analyzer-cli`
    distribution.
  - Add `docs/source/lib/` and `docs/source/cli/` with hand-written `automodule`
    pages for each member; add both to `docs/source/index.rst`'s toctree.
  - Anchor `.gitignore`'s `lib/` and `lib64/` patterns (`/lib/`, `/lib64/`) so
    `docs/source/lib/` is tracked.
  - Fix the malformed bullet list in `OSMAdapter.map_region_name`'s docstring;
    add `sphinx_autodoc_typehints.forward_reference` and
    `sphinx_autodoc_typehints.guarded_import` to `suppress_warnings` for the
    non-actionable `obstore` warnings.
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
  - Confirm the external `ci-python-uv.yml` and `release-python-uv.yml` reusable
    workflows work against the virtual-root workspace: they only call `uv sync`,
    `uv lock --check` and `just` recipes, so they need no change. ~~Add a
    minimal local workaround~~ — dropped: not needed.
  - Change `release.yaml`'s `release-dist` job from `uv build --sdist --wheel`
    to `uv build --all-packages --sdist --wheel`.
  - _Requirements: 7.3_
  - [x] 8.1 Checkpoint - CI green on this branch's PR
    - Verified: all CI jobs (`ci`, `lint-sql`) pass on the actual PR on
      GitHub.com.

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
  - [x] `uv sync --all-extras --dev` succeeds from a clean checkout (via the
        passing GitHub Actions CI run, which runs this step).
  - [x] `just ci` (lint + docs + test) passes end-to-end (via CI).
  - [x] `uv run bna --help` and a representative subcommand behave identically
        to `main`.
  - [x] `just docker-build` succeeds (see task 6.1).
  - [x] The image built by `just docker-build` runs `bna` correctly (see task
        6.1).
  - [x] `uv build --package brokenspoke-analyzer-lib --wheel` succeeds
        independently of the cli package.
  - [x] Dev container round-trip
        (`Dev Containers: Rebuild and Reopen in Container`, `uv sync` inside it,
        `Python: Select Interpreter` → `./.venv/bin/python` debugging) works.
  - [x] `integration/` e2e fixtures still invoke `bna` successfully
        (spot-checked).
  - _Requirements: 1.3, 3.4, 7.1, 7.2_

- [ ] 11. Rebase onto `main`
  - [x] Port `main`'s changes to the old `brokenspoke_analyzer/` paths into
        `packages/` (`cli/common.py`, `cli/prepare.py`, `cli/run.py`,
        `cli/run_with.py`, `core/compute.py`, the `features/` SQL scripts), and
        reconcile `pyproject.toml`, `uv.lock`, `ci.yaml`, `e2e.yaml`,
        `release.yaml` with this branch. Git carried the code changes through
        the renames; `main`'s dependency pins were split between the two
        members' `pyproject.toml`; the branch's own changes are identical before
        and after the rebase.
  - [x] Set `VERSION` to `main`'s released version (`3.3.0`) and re-run
        `uv lock` (`uv lock --check` passes; only the workspace entries changed
        relative to `main`'s lockfile).
  - [x] Drop `Sync uv.lock metadata with bumped dependency pins`, which became
        empty once the lock was regenerated on top of `main`.
  - [ ] Re-run tasks 4.1, 6.1 and 10 after the rebase.
    - [x] In a clean worktree: `just lint-python` (ruff, isort, ty over `src`
          and `tests`), `uv lock --check`, `just docs`, `just test` (all but the
          network-bound `test_osmnx_query_multipolygon`), `bna --version`
          (`3.3.0`), `uv build --all-packages --wheel`.
    - [x] `just lint-sql` passes (verified on 2026-10-29).
    - [x] `just lint-md`: its one finding (an over-long inline `uv export`
          command in `design.md`) was moved into a code block; re-run after the
          fix pending.
    - [ ] The network-bound test, and CI green on the PR after the force-push.
    - [x] `just docker-build` and `docker run ... --help` on the rebased branch
          (verified on 2026-10-29).
  - _Requirements: 3.4, 4.1, 4.3_

## Notes

- No task in this plan touches `utils/bna-batch.py`, `utils/cache-warmer.py`, or
  `bna-bench` — those remain explicitly out of scope (see `requirements.md`).
- Task 2 (lib) must land and be checkpointed before task 3 (cli) begins, since
  the cli package depends on the lib package via a workspace source that must
  already exist and build cleanly.
- The pinned hatchling already supports the regex/file-based dynamic versioning
  described in `design.md`; no bump was needed.
- Task 8's CI workaround turned out to be unnecessary, so nothing needs
  reverting once the separately tracked shared-workflow issue in
  `PeopleForBikes/.github` is resolved.
- Member sdists do not contain `VERSION` (see `design.md`, Shared version
  source); this must be solved before any member is published independently.
