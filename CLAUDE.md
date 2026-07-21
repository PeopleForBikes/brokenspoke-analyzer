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
- `just test` — `uv run pytest --cov=brokenspoke_analyzer -x`
  - Run a single test: `uv run pytest path/to/test_file.py::test_name -x`
  - Tests use `xdoctest` (via `addopts`), so doctests in source files are also
    collected and run.
- `just docs` — build Sphinx docs; `just docs-autobuild` for live reload
- `just docker-build` — build the local Docker image
- `just compose-up` / `just compose-down` — start/stop the PostGIS database via
  Docker Compose
- `just test-e2e-prepare` — regenerate `integration/e2e-cities-*.csv` splits and
  `integration/README.md` from `integration/e2e-cities.csv`
- `just ci` runs all the CI tasks local. This is to be run before commiting
  code.

Individual linters/formatters can be run directly with `uv run <tool>`, e.g.
`uv run ruff check brokenspoke_analyzer utils`, `uv run ty check
brokenspoke_analyzer`, `uv run sqlfluff lint brokenspoke_analyzer/scripts/sql/`.

## Running the CLI

The package installs a `bna` console script (`brokenspoke_analyzer.cli.root:app`,
a Typer app). During development, invoke it as `uv run bna <command>`.
Requires `DATABASE_URL` to be set. Top-level subcommands (each its own Typer
app under `brokenspoke_analyzer/cli/`): `cache`, `compute`, `configure`,
`export`, `import`, `prepare`, `run`, `run-with`.

`bna run-with compose <country> <city> <region> <fips_code>` is the common
end-to-end entry point: it starts/stops the Docker Compose PostGIS database,
runs the full analysis pipeline, and exports results.

## Architecture

The pipeline is: **prepare → configure → import → compute → export**, and
`run` / `run-with` orchestrate all of these steps together.

- `brokenspoke_analyzer/cli/` — one Typer sub-app per pipeline stage
  (`prepare.py`, `configure.py`, `importer.py`, `compute.py`, `export.py`,
  `run.py`, `run_with.py`, `cache.py`), wired together in `root.py`. CLI
  modules are thin wrappers that parse options and delegate to `core/`.
- `brokenspoke_analyzer/core/` — the actual logic:
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
  - `datastore.py`, `file_utils.py`, `utils.py`, `constant.py` — shared
    helpers and constants (city/region naming, paths, etc.)
- `brokenspoke_analyzer/scripts/sql/` — the GIS SQL itself, split into
  `connectivity/`, `features/`, `stress/`. These are templated with
  `sqlfluff`'s placeholder templater (`:param` style) — placeholder values used
  for linting are defined under `[tool.sqlfluff.templater.placeholder]` in
  `pyproject.toml`; do not treat those as runtime defaults.
- `data/<city-slug>` and `results/<country>/<region>/<city>/<version>/` are
  the on-disk working/output directories used by a full run.
- `tests/` mirrors the `brokenspoke_analyzer` package layout for unit tests;
  `integration/` holds end-to-end city fixtures (`e2e-cities*.csv`/`.json`,
  split by size) and their generation script (`x.py`).
- `utils/` — standalone maintenance scripts, linted/formatted alongside the
  main package but not part of the installed package.

## Conventions

- Package/dependency management is via `uv`; do not hand-edit `uv.lock`.
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
  `brokenspoke_analyzer/scripts/sql/`.
- New repeatable, team-facing operations should become a `just` recipe named
  `verb-noun`, following the existing style; one-off commands don't need one.
