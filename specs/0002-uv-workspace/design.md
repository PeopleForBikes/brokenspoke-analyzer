# Design Document: uv Workspace Restructuring

> **Implementation note:** this document describes the workspace as built.
> [deviations.md](deviations.md) records where, and why, the implementation
> departed from the original version of this design.

## Overview

The repository moves from a single flat-layout package (`brokenspoke_analyzer/`)
to a `uv` workspace rooted at `pyproject.toml`, with two `src/`-layout members
under `packages/`: `brokenspoke-analyzer-lib` (core, non-executable) and
`brokenspoke-analyzer-cli` (the `bna` Typer app). The workspace root becomes a
virtual project — it declares `[tool.uv.workspace]` and shared tool
configuration, but has no importable source and is never itself built or
installed.

The root and both members resolve their version from a single shared source (a
root `VERSION` file read via hatchling's regex version source), so there is
exactly one place to bump a release. `brokenspoke-analyzer-cli` depends on
`brokenspoke-analyzer-lib` via `{ workspace = true }`, resolved locally by `uv`
from the same lockfile — no publishing step is required for the two packages to
interoperate.

Everything that currently assumes a single package (`justfile`, `Dockerfile`,
CI, Sphinx docs, coverage config, ruff/isort/ sqlfluff/ty config) is updated to
operate across both members. Where CI wraps **external reusable workflows**
owned by `PeopleForBikes/.github` (`ci-python-uv.yml`, `release-python-uv.yml`),
this design calls out where those workflows' single-package assumptions may not
hold, since that repo is out of scope for this feature to modify.

## Architecture

```text
brokenspoke-analyzer/                          # workspace root (virtual project)
├── pyproject.toml                              # [tool.uv.workspace], shared tool config
├── VERSION                                     # single version source, e.g. "3.3.0"
├── uv.lock                                      # single lockfile for the whole workspace
├── justfile
├── Dockerfile
├── docs/                                        # single Sphinx site, root-level
│   └── source/
│       ├── index.rst
│       ├── lib/                                 # autodoc section for the lib
│       └── cli/                                 # autodoc section for the cli
├── packages/
│   ├── brokenspoke-analyzer-lib/
│   │   ├── pyproject.toml                       # dynamic version -> ../../VERSION
│   │   ├── src/
│   │   │   └── brokenspoke_analyzer_lib/
│   │   │       ├── __init__.py
│   │   │       ├── core/                        # pipeline modules only: analysis,
│   │   │       │                                # compute, datasource, downloader,
│   │   │       │                                # exporter, ingestor, runner
│   │   │       ├── database/                    # was core/database/
│   │   │       ├── scripts/                     # SQL, osm2pgrouting/osm2pgsql config
│   │   │       ├── datastore.py                 # was core/datastore.py
│   │   │       ├── file_utils.py                # was core/file_utils.py
│   │   │       ├── utils.py                     # was core/utils.py
│   │   │       └── constant.py                  # was core/constant.py, + shared DEFAULT_*
│   │   └── tests/
│   │       └── brokenspoke_analyzer_lib/         # mirrors src/ layout
│   └── brokenspoke-analyzer-cli/
│       ├── pyproject.toml                        # dynamic version -> ../../VERSION
│       │                                          # [tool.uv.sources] lib -> workspace
│       ├── src/
│       │   └── brokenspoke_analyzer_cli/
│       │       ├── __init__.py
│       │       ├── __main__.py                   # replaces main.py (python -m, VS Code)
│       │       ├── root.py                       # Typer app entrypoint (bna)
│       │       ├── common.py                     # Typer arguments/options, CLI defaults
│       │       ├── prepare.py
│       │       ├── configure.py
│       │       ├── importer.py
│       │       ├── compute.py
│       │       ├── export.py
│       │       ├── run.py
│       │       ├── run_with.py
│       │       └── cache.py
│       └── tests/
│           └── brokenspoke_analyzer_cli/         # mirrors src/ layout
├── tests/                                        # removed; content moved into member tests/
├── integration/                                  # unchanged: e2e fixtures, invokes `bna`
└── utils/                                        # unchanged in this feature (bna-batch.py,
                                                    # cache-warmer.py migrate in later PRs)
```

The top-level `brokenspoke_analyzer/` package and `main.py` are retired;
anything still importing `brokenspoke_analyzer.core.*` or
`brokenspoke_analyzer.cli.*` is updated to `brokenspoke_analyzer_lib.*` /
`brokenspoke_analyzer_cli.*`. The debug entry point `main.py` is replaced by
`brokenspoke_analyzer_cli/__main__.py` (which also enables
`python -m brokenspoke_analyzer_cli`), and `.vscode/launch.json` runs it with
`"module": "brokenspoke_analyzer_cli"`.

There is no `pyrosm/` package in the library: `pyrosm` is only a third-party
dependency, so its old exclusions in the ruff, ty and coverage configuration are
dropped rather than rewritten.

**Package boundary.** The library must never import from the CLI. Before the
split, `core/compute.py`, `core/ingestor.py` and `core/datastore.py` imported
`brokenspoke_analyzer.cli.common`, so `common.py` is split:

- The defaults both sides need (`DEFAULT_BUFFER`, `DEFAULT_CITY_FIPS_CODE`,
  `DEFAULT_COMPUTE_PARTS`, `DEFAULT_MAX_TRIP_DISTANCE`) move to
  `brokenspoke_analyzer_lib.constant`. `brokenspoke_analyzer_cli.common`
  re-exports them under their existing names, so no CLI call site changes.
- CLI-only defaults and every Typer `Annotated` alias stay in
  `brokenspoke_analyzer_cli.common`.
- `core/compute.py`'s `all_` and `parts` drop their (inert) Typer annotations in
  favour of plain types: `str`, `int`, `int` and
  `list[constant.ComputePart] | None`. The Typer commands themselves are
  declared in `brokenspoke_analyzer_cli.compute`.

## Components and Interfaces

### Workspace root `pyproject.toml`

```toml
[project]
name = "brokenspoke-analyzer"
dynamic = ["version"]
description = "Run a BNA analysis locally."
requires-python = "~=3.13.0"
license = "MIT"

[tool.uv.workspace]
members = [
  "packages/brokenspoke-analyzer-lib",
  "packages/brokenspoke-analyzer-cli",
]

[tool.uv]
package = false  # root is virtual: not built or installed as a distribution

[tool.uv.sources]
brokenspoke-analyzer-lib = { workspace = true }
brokenspoke-analyzer-cli = { workspace = true }

[dependency-groups]
dev = [
  "brokenspoke-analyzer-cli",
  "brokenspoke-analyzer-lib",
  "...same dev tools as today, shared across the workspace...",
]

[tool.hatch.version]
path = "VERSION"
pattern = "(?P<version>.+)"

# Shared lint/format/type-check config (ruff, isort, sqlfluff, ty) plus the
# root pytest/coverage config live here (see below).

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`tool.uv.package = false` is the mechanism that makes the root "virtual":
`uv sync` still creates one environment and one `uv.lock` for every member, but
the root itself is never packaged. The root declares `dynamic = ["version"]`
from `VERSION` (Requirement 4.2) rather than a static literal, which would be a
second version location. Because the root is never installed, the members get
into the environment through the `dev` group, which lists both of them as
workspace sources. Root-level dev dependencies remain declared once at the root
(`[dependency-groups] dev`).

Shared tool configuration at the root:

- `[tool.isort] known_first_party` and `[tool.ruff] src` plus
  `[tool.ruff.lint.isort] known-first-party` name both import packages
  explicitly; with the code under `packages/*/src` neither tool auto-detects
  them, and the two disagreed on import grouping.
- ruff now lints the test trees too, with a `[tool.ruff.lint.per-file-ignores]`
  block for `**/tests/**` covering the conventional test exemptions (`S101`,
  `D101`–`D107`, `ANN201`, `PLR2004`, `PYI034`, `T201`).
- `[tool.sqlfluff]` is unchanged; the SQL path is passed by the `justfile`.
- `[tool.ty.src]` keeps its third-party exclusions, minus `pyrosm`.
  `[tool.ty.environment] root` lists both members' `src/`, for the same reason
  as ruff's `src`, so ty resolves first-party imports in the source and test
  trees without relying on the editable installs.

### `packages/brokenspoke-analyzer-lib/pyproject.toml`

```toml
[project]
name = "brokenspoke-analyzer-lib"
dynamic = ["version"]
description = "Core BNA analysis functionality."
requires-python = "~=3.13.0"
license = "MIT"
dependencies = [
  # aiohttp, beautifulsoup4, boto3, geopandas, loguru, numpy, obstore, osmnx,
  # platformdirs, pyrosm, python-slugify, rasterio, shapely,
  # sqlalchemy[asyncio,postgresql_psycopg], us, yarl
]

[tool.hatch.version]
path = "../../VERSION"
pattern = "(?P<version>.+)"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

No `[project.scripts]`. The dependency split was decided by inspecting actual
imports:

- `rich`, `pycountry` and `typer` are imported only by the CLI, so they live
  there.
- `aiohttp`, `geopandas` and `loguru` are imported directly by both members, so
  both declare them.
- `us` is imported by `core/analysis.py`, so it lives in the library.
- `python-dotenv` and `tenacity` were declared but never imported, and are
  dropped. `pygris` was never a declared dependency.

### `packages/brokenspoke-analyzer-cli/pyproject.toml`

```toml
[project]
name = "brokenspoke-analyzer-cli"
dynamic = ["version"]
description = "Command-line frontend for the BNA analysis."
requires-python = "~=3.13.0"
license = "MIT"
dependencies = [
  "aiohttp>=3.14.3,<4",
  "brokenspoke-analyzer-lib",
  "geopandas>=1.1.4,<2",
  "loguru>=0.7.3,<0.8",
  "pycountry>=26.2.16",
  "rich>=15.0.0,<16",
  "typer>=0.27.2,<0.28",
]

[project.scripts]
bna = "brokenspoke_analyzer_cli.root:app"

[tool.uv.sources]
brokenspoke-analyzer-lib = { workspace = true }

[tool.hatch.version]
path = "../../VERSION"
pattern = "(?P<version>.+)"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Version pins follow `main` and Dependabot; the ones above are illustrative.

### Shared version source

- A root `VERSION` file contains only the version string (e.g. `3.3.0`), no
  quotes, no key.
- `[tool.hatch.version] path = "../../VERSION"` (`path = "VERSION"` at the root)
  with `pattern = "(?P<version>.+)"` (hatchling's regex version source, pointed
  at a plain-text file) makes the root and both members resolve the same version
  at build/sync time. `pattern` is overridden from hatchling's default
  `__version__ = "..."` form because `VERSION` is a bare string, not a Python
  assignment.
- Bumping a release is: edit `VERSION`, run `uv lock`, commit. No file elsewhere
  carries a version literal.
- `docs/source/conf.py` reads `metadata.version("brokenspoke-analyzer-cli")` via
  `importlib.metadata`, since the root package is no longer installed. The
  user-visible `bna --version` string is unchanged.
- **Known limitation:** hatchling cannot include a file outside the project root
  in an sdist, so member sdists do not contain `VERSION`. Their `PKG-INFO`
  carries the right version, but rebuilding a wheel from a member sdist fails.
  This is inert while nothing is published (out of scope); it must be solved
  before any member is published independently, most likely by switching to a
  `hatch-vcs` git-tag source, which Requirement 4.1 allows.

### Test layout

- `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/...` — moved
  from `tests/brokenspoke_analyzer/core/...`. Only that tree held tracked tests;
  `tests/core/` contained nothing but stale `__pycache__` artefacts, so there
  was no duplication to consolidate.
  - `tests/brokenspoke_analyzer/core/test_analysis.py` →
    `.../core/test_analysis.py`.
  - `tests/test_cache_warmer.py` → `.../test_datastore.py`, renamed to mirror
    the `brokenspoke_analyzer_lib.datastore` module it exercises.
- `packages/brokenspoke-analyzer-cli/tests/brokenspoke_analyzer_cli/test_root.py`
  replaces the placeholder `tests/test_brokenspoke_analyzer.py` (`assert True`):
  it asserts that `bna --help` exits cleanly and advertises every pipeline
  stage.
- Each member's `pyproject.toml` carries its own `[tool.pytest.ini_options]`
  (markers, `addopts` with `--xdoctest`, `--cov-report`) and
  `[tool.coverage.run] omit` list, so `uv run pytest` works standalone inside
  either `packages/*` directory (Requirement 6.3).
- The root `pyproject.toml` carries a third `[tool.pytest.ini_options]` with
  `testpaths` pointing at both members' `tests/`, plus a combined
  `[tool.coverage.run] omit`, because pytest resolves a single `configfile` and
  `just test` runs from the root (Requirement 6.4). The duplicated markers and
  `addopts` are an accepted maintenance cost.
- `integration/` stays at the root unchanged — it drives the built `bna` command
  end-to-end and doesn't care which package provides it.

### Documentation layout

- `docs/` stays at the root with one Sphinx build.
- `docs/source/conf.py` inserts `packages/brokenspoke-analyzer-lib/src` and
  `packages/brokenspoke-analyzer-cli/src` into `sys.path`, so autodoc works even
  when the members are not installed.
- `docs/source/lib/` and `docs/source/cli/` hold one `automodule` page per
  module plus an `index.rst`; `docs/source/index.rst`'s toctree gains
  `lib/index` and `cli/index`. Existing narrative docs (`commands.md`,
  `workflow.md`, `about.md`, etc.) stay where they are and are re-linked if they
  reference now-renamed import paths.
- The root `.gitignore` anchors `lib/` and `lib64/` as `/lib/` and `/lib64/`;
  unanchored, they silently ignored `docs/source/lib/`. `build/` stays
  unanchored because `docs/build/` relies on it.
- The docs build with `-W`. Importing the packages through autodoc surfaced one
  malformed docstring list (`OSMAdapter.map_region_name`, fixed at the source)
  and three warnings from `obstore`'s Rust-backed re-exports, which are not
  actionable here; `conf.py`'s `suppress_warnings` lists
  `sphinx_autodoc_typehints.forward_reference` and
  `sphinx_autodoc_typehints.guarded_import`, keeping `-W` for everything else.

### Dockerfile

- `builder` stage: `COPY . .` still works (whole repo). Against a virtual root,
  a plain `uv export` resolves the root's own (empty) dependency list, so the
  export runs as
  `uv export --all-packages --no-emit-workspace --format requirements-txt --all-extras --no-group dev --no-hashes`:
  `--all-packages` takes the union of both members' runtime dependencies, and
  `--no-emit-workspace` keeps the members themselves out of the requirements
  file. The wheels are built with `uv build --all-packages --wheel`.
- `main` stage: installs the vendored dependency wheels, then both member wheels
  (`brokenspoke_analyzer_lib-*.whl` and `brokenspoke_analyzer_cli-*.whl`) in a
  single `pip install`, so the cli → lib dependency resolves locally.
  `ENTRYPOINT ["bna"]` is unchanged since the console script name doesn't
  change.
- `.dockerignore` gains `packages/*/tests`, which the root-anchored `tests`
  entry no longer matches.

### `justfile`

- `lib_pkg`/`cli_pkg` variables derive `src_dirs`
  (`packages/brokenspoke-analyzer-lib/src packages/brokenspoke-analyzer-cli/src`),
  `test_dirs` (the matching `tests/`) and `sql_dir`
  (`.../brokenspoke_analyzer_lib/scripts/sql`).
- `lint-python`, `fmt-python`: one invocation each of `ruff format` and
  `ruff check` over `src_dirs`, `test_dirs` and `utils`; `ty check` over
  `src_dirs` and `test_dirs`.
- `lint-sql`: `sqlfluff lint {{ sql_dir }}`.
- `test`: one `uv run pytest` invocation at the root, using the root
  `testpaths`, with
  `--cov=brokenspoke_analyzer_lib --cov=brokenspoke_analyzer_cli`. The
  per-member `coverage combine` alternative was not needed.
- `docker-build`, `compose-up/down`: unchanged.
- `docker-prepare-all`: runs the `{{ docker_image }}:dev` image built by
  `docker-build-devcontainer`, instead of the hard-coded
  `peopleforbikes/brokenspoke-analyzer:latest`, so it unambiguously exercises
  the image built from the working tree.

## Data Models

Not applicable — this feature is a structural/packaging change with no new
runtime data models. The only "schema" introduced is the shared `VERSION` file
format (a single line, semver string, no surrounding markup).

## Correctness Properties

1. **Single version source of truth**: for any commit,
   `uv build --package brokenspoke-analyzer-lib` and
   `uv build --package brokenspoke-analyzer-cli` produce wheels reporting the
   identical version string, and that string equals the contents of the root
   `VERSION` file.
2. **No root package**: `packages/brokenspoke-analyzer-lib` and
   `packages/brokenspoke-analyzer-cli` are independently buildable and
   installable; the workspace root produces no distribution artifact.
3. **CLI behavior parity**: for any `bna` invocation supported before this
   restructuring, the same invocation after restructuring produces the same exit
   code, stdout/stderr shape, and side effects (verified by the existing test
   suite and `integration/` fixtures continuing to pass unmodified).
4. **Independent buildability**: `brokenspoke-analyzer-lib` builds and its tests
   run with no `brokenspoke-analyzer-cli` code present (no cyclic or accidental
   cross-member imports from lib into cli).
5. **Additive extensibility**: adding a third workspace member (e.g. a future
   `brokenspoke-analyzer-bench`) requires only a new `packages/...` directory
   and one new line in root `[tool.uv.workspace] members` — no change to
   `brokenspoke-analyzer-lib` or `brokenspoke-analyzer-cli`.

## Error Handling

- **Version file missing/malformed**: `uv sync`/`uv build` fails fast with
  hatchling's version-resolution error (file not found / pattern doesn't match)
  rather than silently defaulting to `0.0.0` — this is hatchling's existing
  behavior for regex-sourced versions, no custom handling needed.
- **Workspace member misconfiguration** (e.g. `brokenspoke-analyzer-cli` missing
  the `tool.uv.sources` workspace pointer, causing uv to try to resolve
  `brokenspoke-analyzer-lib` from PyPI): `uv lock`/`uv sync` fails with a clear
  "package not found" error since `brokenspoke-analyzer-lib` is never published;
  this is an acceptable fail-fast signal a developer would immediately notice in
  CI/local dev, not something to suppress.
- **External reusable CI workflows and workspaces**: `ci-python-uv.yml` and
  `release-python-uv.yml` (owned by `PeopleForBikes/.github`) were written for a
  single-package `uv` project. Both were read: neither invokes `uv build` or
  `uv publish`; they only call `uv sync`, `uv lock --check` and `just` recipes
  (`lint-md`, `lint-python`, `docs`, `test`), so they work unchanged against the
  virtual root. No local workaround is needed, and the separately tracked
  shared-workflow issue does not block this feature. The only CI change is in
  this repository's own `release.yaml` (see Deployment Considerations).

## Integration

- **`integration/` e2e suite**: unaffected in structure; it shells out to the
  `bna` command, which continues to exist regardless of which package provides
  it.
- **Docker Compose / `compose.yml`**: unaffected; it references the built Docker
  image, not the Python package layout directly.
- **`AGENTS.md` / `CLAUDE.md`**: updated to describe the new
  `packages/brokenspoke-analyzer-lib` / `packages/brokenspoke-analyzer-cli`
  layout and import names, per Requirement 7.5.
- **Future workspace members** (`bna-batch`, `cache-warmer`, `bna-bench`): not
  built in this feature, but this design's `packages/` convention, shared
  `VERSION` file, and root virtual-project pattern are exactly what they will
  plug into.

### Development Container

- `.devcontainer/devcontainer.json` mounts the full repo at `/usr/src/app`
  (`workspaceFolder`) and uses the `dev` target of `Dockerfile` via
  `compose.yml`'s `bna-dev` service — neither references package names directly,
  so no change is required to either file.
- The debugging workflow documented in `.github/CONTRIBUTING.md`'s "Development
  Container" → "Debugging" section relies on running `uv sync` inside the
  container to create a local `.venv` with an editable install that shadows the
  image's site-packages install, then pointing VS Code's
  `Python: Select Interpreter` at `./.venv/bin/python`. Run from the workspace
  root, `uv sync` performs editable installs of **all** workspace members at
  once, so this continues to work exactly as before with no procedural change —
  the only update needed is wording, since the doc currently refers to "the
  `brokenspoke-analyzer` package" installed in site-packages, which becomes two
  packages (`brokenspoke-analyzer-lib`/`brokenspoke-analyzer-cli`) after this
  feature.
- `.github/CONTRIBUTING.md` is updated to reflect the new package names in this
  section (both the site-packages-vs-editable explanation and any mention of
  import paths), with no change to the documented commands
  (`bna -vv configure ...`, `bna -vv run ...`, `uv sync`) or to the
  rebuild/reopen-in-container VS Code flow.
- The tracked `.vscode/launch.json` debug configuration runs
  `"module": "brokenspoke_analyzer_cli"` (the new `__main__.py`) instead of the
  retired `main.py` file path, so the documented debugging flow keeps working.

## Testing Strategy

- **Unit tests**: the existing `tests/brokenspoke_analyzer/core/*` tests move to
  `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/*`, with
  import paths updated from `brokenspoke_analyzer.core` to
  `brokenspoke_analyzer_lib`, and `test_cache_warmer.py` renamed to
  `test_datastore.py`. No test logic changes — this is a mechanical move plus
  import-path rewrite, verified by an unchanged pass/fail set before and after.
- **CLI tests**: the placeholder `tests/test_brokenspoke_analyzer.py` is
  replaced by
  `packages/brokenspoke-analyzer-cli/tests/brokenspoke_analyzer_cli/test_root.py`
  (a `bna --help` smoke test).
- **CLI parity**: the help text of all 15 `bna` command and subcommand screens
  is byte-identical before and after the restructuring, once cwd-derived default
  paths are normalised.
- **Coverage**: the old `[tool.coverage.run] omit` list (naming
  `brokenspoke_analyzer/cli/*`, `brokenspoke_analyzer/core/constant.py`, etc.)
  is rewritten under the new import names at the root (combined report) and
  split per member (standalone runs). The CLI stays omitted from coverage, as
  before.
- **Manual verification checklist** (executed once restructuring is implemented,
  before merge):
  1. `uv sync --all-extras --dev` succeeds from a clean checkout.
  2. `uv run bna --help` and one representative subcommand (e.g.
     `bna prepare --help`) behave identically to `main` branch.
  3. `just lint`, `just test`, `just docs`, `just docker-build` all succeed.
  4. A local `docker run` of the built image executes a `bna` command
     successfully.
  5. `uv build --package brokenspoke-analyzer-lib --wheel` succeeds with no
     `brokenspoke-analyzer-cli`/typer code importable from within it.

## Deployment Considerations

- No environment variable changes; `BNA_OSMNX_CACHE`, `BNA_PYGRIS_CACHE`,
  `DATABASE_URL`, AWS credentials, etc. are all read the same way regardless of
  which package the reading code lives in.
- Docker image tag/entrypoint (`bna`) unchanged from a consumer's perspective;
  only the internal build steps (multi-package wheel build) change.
- Release process: bump `VERSION` once, tag as today (`[0-9]+.[0-9]+.[0-9]+`);
  `release.yaml`'s `release-dist` job runs
  `uv build --all-packages --sdist --wheel` (updated from a bare
  `uv build --sdist --wheel`, which fails at a virtual root) so both members'
  artifacts are attached to the GitHub release.

## Dependencies

- No new third-party runtime dependencies. Build-time reliance on hatchling's
  regex/file-based dynamic versioning is already available in the existing
  `hatchling` build-system requirement — no hatchling bump was needed.
- `uv` itself must support workspaces with a virtual (`package = false`) root
  and `--package`/`--all-packages` build selection — both are stable, current
  `uv` features (already the minimum implied by `astral-sh/setup-uv` used in
  CI).
