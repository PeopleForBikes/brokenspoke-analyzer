# Design Document: uv Workspace Restructuring

> **Implementation note:** the implementation departs from this document in a
> number of places. See [deviations.md](deviations.md) for the full delta and
> the reasoning behind each one.

## Overview

The repository moves from a single flat-layout package (`brokenspoke_analyzer/`)
to a `uv` workspace rooted at `pyproject.toml`, with two `src/`-layout members
under `packages/`: `brokenspoke-analyzer-lib` (core, non-executable) and
`brokenspoke-analyzer-cli` (the `bna` Typer app). The workspace root becomes a
virtual project — it declares `[tool.uv.workspace]` and shared tool
configuration, but has no importable source and is never itself built or
installed.

Both members resolve their version from a single shared source (a root `VERSION`
file read via a small hatchling version hook), so there is exactly one place to
bump a release. `brokenspoke-analyzer-cli` depends on `brokenspoke-analyzer-lib`
via `{ workspace = true }`, resolved locally by `uv` from the same lockfile — no
publishing step is required for the two packages to interoperate.

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
├── VERSION                                     # single version source, e.g. "3.1.1"
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
│   │   │       ├── core/                        # download/ingest/compute/export/etc.
│   │   │       ├── database/
│   │   │       ├── scripts/                     # SQL
│   │   │       ├── pyrosm/
│   │   │       ├── datastore.py
│   │   │       ├── file_utils.py
│   │   │       ├── utils.py
│   │   │       └── constant.py
│   │   └── tests/
│   │       └── brokenspoke_analyzer_lib/         # mirrors src/ layout
│   └── brokenspoke-analyzer-cli/
│       ├── pyproject.toml                        # dynamic version -> ../../VERSION
│       │                                          # [tool.uv.sources] lib -> workspace
│       ├── src/
│       │   └── brokenspoke_analyzer_cli/
│       │       ├── __init__.py
│       │       ├── root.py                       # Typer app entrypoint (bna)
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

`main.py` and the top-level `brokenspoke_analyzer/` package are retired;
anything still importing `brokenspoke_analyzer.core.*` or
`brokenspoke_analyzer.cli.*` is updated to `brokenspoke_analyzer_lib.*` /
`brokenspoke_analyzer_cli.*`.

## Components and Interfaces

### Workspace root `pyproject.toml`

```toml
[project]
name = "brokenspoke-analyzer"
version = "3.1.1"  # kept for tools reading root metadata; not built/installed
description = "Run a BNA analysis locally."
requires-python = "~=3.13.0"
license = "MIT"

[tool.uv.workspace]
members = [
  "packages/brokenspoke-analyzer-lib",
  "packages/brokenspoke-analyzer-cli",
]

[dependency-groups]
dev = [ "...same dev tools as today, shared across the workspace..." ]

[tool.uv]
package = false  # root is virtual: not built or installed as a distribution

# Shared lint/format/type-check config (ruff, isort, sqlfluff, ty) moves here,
# with paths updated to cover packages/*/src and packages/*/tests.

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

`tool.uv.package = false` is the mechanism that makes the root "virtual":
`uv sync` still creates one environment and one `uv.lock` for every member, but
the root itself is never packaged. Root-level dev dependencies remain declared
once at the root (`[dependency-groups] dev`), inherited by the whole workspace
per `uv`'s workspace dependency-group behavior.

### `packages/brokenspoke-analyzer-lib/pyproject.toml`

```toml
[project]
name = "brokenspoke-analyzer-lib"
dynamic = ["version"]
description = "Core BNA analysis functionality."
requires-python = "~=3.13.0"
license = "MIT"
dependencies = [
  # everything except typer/CLI-only deps: aiohttp, beautifulsoup4, boto3,
  # geopandas, loguru, numpy, obstore, osmnx, platformdirs, pygris, pyrosm,
  # python-dotenv, python-slugify, rasterio, rich, shapely,
  # sqlalchemy[asyncio,postgresql_psycopg], tenacity, trio, us, yarl
]

[tool.hatch.version]
path = "../../VERSION"
pattern = "(?P<version>.+)"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

No `[project.scripts]`. `rich` stays if core logging/progress output uses it
directly; otherwise it moves to the cli package — confirmed during
implementation by checking actual imports in `core/`.

### `packages/brokenspoke-analyzer-cli/pyproject.toml`

```toml
[project]
name = "brokenspoke-analyzer-cli"
dynamic = ["version"]
description = "Command-line frontend for the BNA analysis."
requires-python = "~=3.13.0"
license = "MIT"
dependencies = [
  "brokenspoke-analyzer-lib",
  "typer>=0.26.8,<0.27",
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

### Shared version source

- A root `VERSION` file contains only the version string (e.g. `3.1.1`), no
  quotes, no key.
- `[tool.hatch.version] path = "../../VERSION"` with
  `pattern = "(?P<version>.+)"` (hatchling's regex version source, pointed at a
  plain-text file) makes both members resolve the same version at build/sync
  time. `pattern` is overridden from hatchling's default `__version__ = "..."`
  form because `VERSION` is a bare string, not a Python assignment.
- Bumping a release is: edit `VERSION`, run `uv lock`, commit. No file elsewhere
  carries a version literal.
- `docs/source/conf.py` currently reads
  `metadata.version("brokenspoke-analyzer")` via `importlib.metadata`; this
  changes to read `metadata.version("brokenspoke-analyzer-cli")` (or read
  `VERSION` directly) since the root package is no longer installed.

### Test layout

- `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/...` — moved
  from `tests/brokenspoke_analyzer/core/...` and `tests/core/...` (existing
  duplication under `tests/core/cache/` and `tests/brokenspoke_analyzer/core/`
  is consolidated into one tree during the move — flagged as a cleanup
  opportunity, not a new requirement).
- `packages/brokenspoke-analyzer-cli/tests/brokenspoke_analyzer_cli/...` — new
  location for any CLI-level tests (currently thin/absent; structure is prepared
  regardless).
- Each member's `pyproject.toml` carries its own `[tool.pytest.ini_options]`
  (markers, `addopts` with `--xdoctest`, `--cov-report`) so `uv run pytest`
  works standalone inside either `packages/*` directory.
- `integration/` stays at the root unchanged — it drives the built `bna` command
  end-to-end and doesn't care which package provides it.

### Documentation layout

- `docs/` stays at the root with one Sphinx build.
- `docs/source/conf.py`'s `sys.path`/autodoc setup is extended to include both
  `packages/brokenspoke-analyzer-lib/src` and
  `packages/brokenspoke-analyzer-cli/src`.
- New `docs/source/lib/` and `docs/source/cli/` directories hold
  `sphinx-apidoc`-generated (or hand-written `automodule`) `.rst`/`.md` pages
  for each member; `docs/source/index.rst`'s toctree gains two subsections
  pointing at them. Existing narrative docs (`commands.md`, `workflow.md`,
  `about.md`, etc.) stay where they are and are re-linked if they reference
  now-renamed import paths.

### Dockerfile

- `builder` stage: `COPY . .` still works (whole repo), but `uv export` /
  `uv build --wheel` must target the `brokenspoke-analyzer-cli` package
  specifically (uv workspace builds require selecting a member, e.g.
  `uv build --package brokenspoke-analyzer-cli --wheel`), which pulls in
  `brokenspoke-analyzer-lib` as a workspace dependency and needs its wheel built
  too (`uv build --package brokenspoke-analyzer-lib --wheel`, or
  `uv build --all-packages --wheel` and install both).
- `main` stage: installs both resulting wheels (`brokenspoke_analyzer_lib-*.whl`
  and `brokenspoke_analyzer_cli-*.whl`) instead of the single
  `brokenspoke_analyzer-*.whl`. `ENTRYPOINT ["bna"]` is unchanged since the
  console script name doesn't change.

### `justfile`

- `src_dir` becomes two paths (or a list):
  `packages/brokenspoke-analyzer-lib/src packages/brokenspoke-analyzer-cli/src`,
  likewise for each member's `tests/`.
- `lint-python`, `fmt-python`: run `isort`/`ruff`/`ty` across both members'
  `src/` and `tests/` trees (either as one invocation with both paths, or one
  recipe iterating members — implementation detail decided during coding, not
  both required by design).
- `test`: runs pytest across both members with combined coverage. Two reasonable
  implementations, either acceptable:
  1. One `uv run pytest` invocation at the root covering both members' `tests/`
     with `--cov` targeting both `src/` trees.
  2. Per-member `uv run pytest` (`--project packages/...`) with
     `coverage combine` merging results. Given the existing single
     `--cov-report html`/`term-missing` expectation, option 1 is simpler and
     preferred unless workspace/pytest interaction forces option 2.
- `docker-build`, `compose-up/down`, `docker-prepare-all`: unchanged.

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
  `release-python-uv.yml` (owned by `PeopleForBikes/.github`) were written
  assuming a single-package `uv` project. If they invoke bare
  `uv build`/`uv publish` without a `--package`/`--all-packages` flag, behavior
  against a virtual root is undefined or may only build one member. **This is
  tracked as a separate issue** (a new/updated shared workflow in
  `PeopleForBikes/.github` supporting `uv` workspaces) to be tackled in its own
  working session and PR — out of scope for this feature's implementation. Until
  that lands, this repo's `ci.yaml`/`release.yaml` may need a temporary local
  workaround (e.g. inline steps instead of the reusable workflow call) so this
  feature isn't blocked on the shared workflow's timeline; that workaround, if
  needed, is itself a task in `tasks.md` and should be easy to revert once the
  shared workflow supports workspaces.

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

## Testing Strategy

- **Unit tests**: existing `tests/brokenspoke_analyzer/core/*` (and the
  duplicate `tests/core/*` tree) move to
  `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/*`, with
  import paths updated from `brokenspoke_analyzer.core` to
  `brokenspoke_analyzer_lib`. No test logic changes — this is a mechanical move
  plus import-path rewrite, verified by an unchanged pass/fail set before and
  after.
- **CLI tests**: moved to
  `packages/brokenspoke-analyzer-cli/tests/brokenspoke_analyzer_cli/*` (import
  path `brokenspoke_analyzer.cli` → `brokenspoke_analyzer_cli`).
- **Coverage**: `[tool.coverage.run] omit` list (currently naming
  `brokenspoke_analyzer/cli/*`, `brokenspoke_analyzer/core/constant.py`, etc.)
  is split, with each member's own `pyproject.toml` (or a root
  `[tool.coverage.run]` with updated paths, if a single combined report is kept)
  reflecting its own omit rules under the new import names.
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
  `uv build --all-packages --sdist --wheel` (updated from a bare `uv build`) so
  both members' artifacts are attached to the GitHub release.

## Dependencies

- No new third-party runtime dependencies. Build-time reliance on hatchling's
  regex/file-based dynamic versioning is already available in the existing
  `hatchling` build-system requirement — no version bump needed unless the
  currently pinned hatchling predates regex-file version sources (to confirm
  during implementation).
- `uv` itself must support workspaces with a virtual (`package = false`) root
  and `--package`/`--all-packages` build selection — both are stable, current
  `uv` features (already the minimum implied by `astral-sh/setup-uv` used in
  CI).
