# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## What this is

The Brokenspoke Analyzer runs the PeopleForBikes Bicycle Network Analysis (BNA)
locally. It downloads OSM data, US Census boundaries and jobs data for a
city/region, then computes connectivity and stress metrics in pure Python
(`geopandas`/`networkx`) and exports the results. **No database is involved**:
the PostGIS/pgRouting implementation was migrated to Python in
`specs/0003-sql-to-python-migration/` and deleted.

## Commands (via `just`)

- `just setup` — `uv sync --all-extras --dev`
- `just lint` — runs `lint-md`, `lint-python`, `lint-uv`
- `just fmt` — runs `fmt-md`, `fmt-python`, `fmt-just`
- `just test` — `uv run pytest --cov=brokenspoke_analyzer -x`
  - Run a single test: `uv run pytest path/to/test_file.py::test_name -x`
  - Tests use `xdoctest` (via `addopts`), so doctests in source files are also
    collected and run.
- `just docs` — build Sphinx docs; `just docs-autobuild` for live reload
- `just docker-build` — build the local Docker image
- `just validate-parity [city...]` — compare the pipeline's output against the
  `results/**` baselines (`--size XS --size S --size M` is the pre-ship gate)
- `just test-e2e-prepare` — regenerate `integration/e2e-cities-*.csv` splits and
  `integration/README.md` from `integration/e2e-cities.csv`
- `just ci` runs all the CI tasks local. This is to be run before commiting
  code.

Individual linters/formatters can be run directly with `uv run <tool>`, e.g.
`uv run ruff check brokenspoke_analyzer utils`,
`uv run ty check brokenspoke_analyzer`.

## Running the CLI

The package installs a `bna` console script
(`brokenspoke_analyzer.cli.root:app`, a Typer app). During development, invoke
it as `uv run bna <command>`. No environment variables are required. Top-level
subcommands (each its own Typer app under `brokenspoke_analyzer/cli/`): `cache`,
`prepare`, `run`.

`bna run <country> <city> <region> <fips_code>` is the end-to-end entry point:
it downloads the data, runs every analysis stage in-process, and exports the
results. `--skip-prepare` re-runs the analysis against files already on disk.

## Architecture

The pipeline is **prepare → ingest → features → stress → network → scoring →
export**, chained by `core/pipeline/orchestrator.py` and driven by `bna run`.

- `brokenspoke_analyzer/cli/` — one Typer sub-app per entry point (`prepare.py`,
  `run.py`, `cache.py`), wired together in `root.py`. CLI modules are thin
  wrappers that parse options and delegate to `core/`.
- `brokenspoke_analyzer/core/pipeline/` — **the analysis itself**, one module
  per stage: `ingest.py` (OSM/census reading and the `osm2pgrouting`
  segmentation rule), `features.py` (per-way attributes), `stress.py` (segment
  and intersection stress), `network.py` (turn-expanded graph and reachability),
  `scoring.py` (destinations, access, the headline scores), `export.py` (the
  published file set), plus `config.py`, `errors.py` and `orchestrator.py`.
- `brokenspoke_analyzer/core/` — supporting logic:
  - `downloader.py` / `datasource.py` / `analysis.py` — fetch OSM extracts, US
    Census boundary and jobs data (the `prepare` stage, unchanged by the
    migration)
  - `runner.py` — thin subprocess wrapper for `osmium`/`osmconvert`
  - `exporter.py` — calver output directories, bundling, S3/R2 upload
  - `datastore.py`, `file_utils.py`, `utils.py`, `constant.py` — shared helpers
    and constants (city/region naming, paths, etc.)
- `data/<city-slug>` and `results/<country>/<region>/<city>/<version>/` are the
  on-disk working/output directories used by a full run.
- `tests/` mirrors the `brokenspoke_analyzer` package layout for unit tests;
  `integration/` holds end-to-end city fixtures (`e2e-cities*.csv`/`.json`,
  split by size) and their generation script (`x.py`).
- `utils/` — standalone maintenance scripts, linted/formatted alongside the main
  package but not part of the installed package.

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
- Coordinate systems matter: every length, azimuth and buffer is computed in the
  projected output CRS, never EPSG:4326, and `network.py` rejects a geographic
  CRS outright.
- **Read `specs/0003-sql-to-python-migration/findings.md` before changing a
  pipeline rule.** It records why each rule is what it is — several look like
  bugs unless you know they reproduce the SQL deliberately — and the SQL it
  describes no longer exists to check against.
- New repeatable, team-facing operations should become a `just` recipe named
  `verb-noun`, following the existing style; one-off commands don't need one.
