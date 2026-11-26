# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## What this is

The Brokenspoke Analyzer runs the PeopleForBikes Bicycle Network Analysis (BNA)
locally. It downloads OSM data, US Census boundaries and jobs data for a
city/region, ingests them into a PostGIS database via `osm2pgrouting`, runs SQL
scripts to compute connectivity and stress metrics, then exports the results.

## Commands (via `just`)

- `just setup` — `uv sync --all-extras --dev`
- `just lint` — runs `lint-md`, `lint-python`, `lint-sql`, `lint-uv`
- `just fmt` — runs `fmt-md`, `fmt-python`, `fmt-just`
- `just test` — pytest across every workspace member, with combined coverage
  (one `--cov=<importable package>` per member, e.g. `--cov=bna.lib`)
  - Run a single test: `uv run pytest path/to/test_file.py::test_name -x`
  - Tests use `xdoctest` (via `addopts`), so doctests in source files are also
    collected and run.
- `just docs` — build Sphinx docs; `just docs-autobuild` for live reload
- `just docker-build` — build the local Docker image
- `just compose-up` / `just compose-down` — start/stop the PostGIS database via
  Docker Compose
- `just test-e2e-prepare` — regenerate `integration/e2e-cities-*.csv` splits and
  `integration/README.md` from `integration/e2e-cities.csv`
- `just check-wheels` — build every member's wheel and check its contents
  (`utils/check_wheels.py`: no `bna/__init__.py`, exactly the member's source
  files)
- `just ci` runs all the CI tasks local (`lint`, `docs`, `test`,
  `check-wheels`). This is to be run before commiting code.

Individual linters/formatters can be run directly with `uv run <tool>`, e.g.
`uv run ruff check packages/*/src utils`, `uv run ty check packages/*/src`,
`uv run sqlfluff lint packages/lib/src/bna/lib/scripts/sql/`. Run sqlfluff
through `just lint-sql` though: it passes
`--ignore-local-config --config pyproject.toml --processes 1` so that sqlfluff
neither lists the directories above the repository nor needs POSIX semaphores,
both of which sandboxes such as nono deny.

## Running the CLI

`bna-cli` installs a `bna` console script (`bna.cli.root:app`, a Typer app).
During development, invoke it as `uv run bna <command>`. Requires `DATABASE_URL`
to be set. Top-level subcommands (each its own Typer app under
`packages/cli/src/bna/cli/`): `cache`, `compute`, `configure`, `export`,
`import`, `prepare`, `run`, `run-with`.

`bna run-with compose <country> <city> <region> <fips_code>` is the common
end-to-end entry point: it starts/stops the Docker Compose PostGIS database,
runs the full analysis pipeline, and exports results.

## Architecture

The repository is a
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/). The
root `pyproject.toml` is a **virtual project** (`[tool.uv] package = false`): it
declares the members, the shared dev dependency group and the shared tooling
configuration, but holds no importable code and is never built or installed.
Every member shares a single version, read from the root `VERSION` file via
`[tool.hatch.version]`, and a single `uv.lock`. Adding a new tool means adding
`packages/<tool>/` (distribution `bna-<tool>`, code in `src/bna/<tool>/`, and
`[tool.hatch.build.targets.wheel] packages = ["src/bna"]` in its
`pyproject.toml`), listing it in `[tool.uv.workspace] members`, and adding its
`src`/`tests` paths to the root path lists (`testpaths`, ruff `src`, ty `root`).

The pipeline is: **prepare → configure → import → compute → export**, and `run`
/ `run-with` orchestrate all of these steps together.

- `packages/lib/` (`bna-lib`) — the core library, importable as `bna.lib`. No
  console scripts, and no dependency on the CLI (or on `typer`). Under
  `src/bna/lib/`:
  - `core/` — the pipeline logic:
    - `downloader.py` / `datasource.py` — fetch OSM extracts, US Census boundary
      and jobs data
    - `ingestor.py` — loads downloaded data into PostGIS (via `osm2pgrouting`,
      `osm2pgsql`)
    - `runner.py` — thin subprocess wrapper for external GIS tools (`osmium`,
      `osm2pgrouting`, etc.), plus one async worker per pipeline step
    - `analysis.py` / `compute.py` — run the SQL scripts that compute
      connectivity/stress scores
    - `exporter.py` — export result tables (locally or to S3 via `boto3`)
  - `database/` — SQLAlchemy models/session helpers for the PostGIS schema
  - `datastore.py`, `file_utils.py`, `utils.py`, `constant.py` — shared helpers
    and constants (city/region naming, paths, defaults shared with the CLI)
  - `scripts/sql/` — the GIS SQL itself, split into `connectivity/`,
    `features/`, `stress/`. These are templated with `sqlfluff`'s placeholder
    templater (`:param` style) — placeholder values used for linting are defined
    under `[tool.sqlfluff.templater.placeholder]` in the root `pyproject.toml`;
    do not treat those as runtime defaults.
- `packages/cli/` (`bna-cli`) — the `bna` frontend, importable as `bna.cli`,
  depending on `bna-lib` through a uv workspace source. Under `src/bna/cli/`:
  one Typer sub-app per pipeline stage (`prepare.py`, `configure.py`,
  `importer.py`, `compute.py`, `export.py`, `run.py`, `run_with.py`,
  `cache.py`), wired together in `root.py`, plus `common.py` for the shared
  Typer arguments/options. CLI modules are thin wrappers that parse options and
  delegate to the library.
- `packages/cache-warmer/` (`bna-cache-warmer`) — pre-populates the analyzer
  cache (locally or in S3), importable as `bna.cache_warmer` and installed as
  the `bna-cache-warmer` console script (`local` and `s3` subcommands, and
  `--version`). Depends on both the library and the CLI through uv workspace
  sources.
- `packages/batch/` (`bna-batch`) — runs `bna run-with compose` for every city
  of a CSV file (used by the `integration/` end-to-end suites), importable as
  `bna.batch` and installed as the `bna-batch` console script (with
  `--version`). Depends on both the library and the CLI through uv workspace
  sources.
- Each member owns its tests under `packages/<member>/tests/`, mirroring the
  layout below its `src/bna/<member>/` (e.g.
  `packages/lib/tests/core/test_analysis.py`), and each is independently
  runnable (`cd packages/<member> && uv run pytest`).
- `data/<city-slug>` and `results/<country>/<region>/<city>/<version>/` are the
  on-disk working/output directories used by a full run.
- `integration/` holds end-to-end city fixtures (`e2e-cities*.csv`/`.json`,
  split by size) and their generation script (`x.py`). It drives the `bna`
  command, so it is unaffected by the package split.
- `utils/` — standalone maintenance scripts, linted/formatted alongside the
  members but not part of any installed package.
- `specs/learnings/` (at the root and in workspace members) — documented
  solutions to past problems and team decisions, by category, with frontmatter
  (`modules`, `tags`); relevant when working in those areas.

## Conventions

- Package/dependency management is via `uv`; do not hand-edit `uv.lock`. Runtime
  dependencies belong to the member that imports them, never to the root; the
  shared dev tooling stays in the root `[dependency-groups] dev`.
- Bumping the version means editing the root `VERSION` file and re-running
  `uv lock`; no member's `pyproject.toml` carries a version literal.
- Changing the Python version means editing `requires-python` in the root
  `pyproject.toml` and in every member, then re-running `uv lock`: uv cannot
  make members inherit `[project]` fields, and a member without it builds
  `py2.py3` wheels with no `Requires-Python`.
  `packages/lib/tests/test_workspace.py` fails when a member differs from the
  root.
- `bna` is a PEP 420 namespace package shared by every member: never add a
  `src/bna/__init__.py` to any member. It would make `bna` a regular package
  rooted in that one member, and the other members' `bna.*` subpackages could no
  longer be imported. `packages/lib/tests/test_namespace.py` guards this.
- The library must never import from the CLI. Values both need (such as the
  `DEFAULT_*` pipeline defaults) live in `bna.lib.constant` and are re-exported
  by `bna.cli.common`. `bna.cli.common.version_callback` builds the `--version`
  option callback of every console script except `bna` itself; it only reads the
  distribution metadata when the flag is given.
- Python: full type hints, ruff (`select = ["ALL"]`, see `pyproject.toml` for
  the ignore list) for lint/format, `isort` (profile `black`,
  `force_grid_wrap = 2`) for imports, `ty` for type checking (mypy config also
  present in `pyproject.toml` but `ty` is the actively-used checker per
  `justfile`).
- Docstrings should use pep257 convention with **Parameters**/**Returns**/
  **Raises** sections; add doctests (xdoctest syntax) for the happy path where
  practical.
- SQL is linted/fixed with `sqlfluff` (postgres dialect); coordinate systems,
  geometry vs geography, and SRID correctness matter — most SQL lives in
  `packages/lib/src/bna/lib/scripts/sql/`.
- New repeatable, team-facing operations should become a `just` recipe named
  `verb-noun`, following the existing style; one-off commands don't need one.
- Markdown (including this file and `specs/`) is Prettier-checked; after editing
  it, run `npx prettier --write --prose-wrap always <file>`.
