# Design Document: Shared `bna` Namespace for Workspace Members

## Overview

The feature is a structural rename with no behavioral change. Each member
directory moves from `packages/brokenspoke-analyzer-<member>/` to
`packages/<member>/`, and each member's top-level package moves from
`src/brokenspoke_analyzer_<member>/` to `src/bna/<member>/`. `bna/` itself
receives no `__init__.py` in any member, which makes it a PEP 420 namespace
package that Python assembles from every member's `src/bna/` directory at import
time. Distribution names become `bna-<member>`.

The work splits into three kinds of change:

1. **Moves**: directories and files are relocated with `git mv` and nothing
   else, so git sees each one as a pure rename.
2. **Reference updates**: every place that names a member directory, a
   distribution or an import path is rewritten. The mapping is mechanical (see
   [Data Models](#data-models)).
3. **Guardrail**: a new test module in the library member checks that the
   namespace is intact.

The approach was validated with a two-member prototype workspace using the same
toolchain (uv workspace, hatchling, `--import-mode=importlib`, xdoctest,
pytest-cov, ruff with `select = ["ALL"]`, ty). Editable installs merge both
`src/bna/` directories, ty resolves cross-member imports, `--cov=bna.lib`
reports correctly, ruff raises no `INP001`, and each wheel contains only
`bna/<member>/…`.

## Architecture

### Layout before

```text
packages/
├── brokenspoke-analyzer-lib/
│   ├── pyproject.toml                       # name = "brokenspoke-analyzer-lib"
│   ├── src/brokenspoke_analyzer_lib/        # regular package
│   │   ├── __init__.py
│   │   ├── constant.py, datastore.py, file_utils.py, utils.py
│   │   ├── core/ … database/ … scripts/ (sql/, *.xml, pfb.style)
│   └── tests/brokenspoke_analyzer_lib/
│       ├── test_datastore.py
│       └── core/test_analysis.py
├── brokenspoke-analyzer-cli/
│   ├── src/brokenspoke_analyzer_cli/ (…, __main__.py, root.py, …)
│   └── tests/brokenspoke_analyzer_cli/test_root.py
├── brokenspoke-analyzer-batch/
│   ├── src/brokenspoke_analyzer_batch/ (__init__.py, main.py)
│   └── tests/brokenspoke_analyzer_batch/test_main.py
└── brokenspoke-analyzer-cache-warmer/
    ├── src/brokenspoke_analyzer_cache_warmer/ (__init__.py, main.py)
    └── tests/brokenspoke_analyzer_cache_warmer/test_main.py
```

### Layout after

```text
packages/
├── lib/
│   ├── pyproject.toml                       # name = "bna-lib"
│   ├── src/bna/                             # namespace: NO __init__.py
│   │   └── lib/                             # regular package
│   │       ├── __init__.py
│   │       ├── constant.py, datastore.py, file_utils.py, utils.py
│   │       ├── core/ … database/ … scripts/ (sql/, *.xml, pfb.style)
│   └── tests/
│       ├── test_datastore.py
│       ├── test_namespace.py                # new: the guardrail
│       └── core/test_analysis.py
├── cli/
│   ├── src/bna/cli/ (…, __main__.py, root.py, …)
│   └── tests/test_root.py
├── batch/
│   ├── src/bna/batch/ (__init__.py, main.py)
│   └── tests/test_main.py
└── cache-warmer/
    ├── src/bna/cache_warmer/ (__init__.py, main.py)
    └── tests/test_main.py
```

The directory is `cache-warmer` (hyphen, like every directory and distribution
name) while the subpackage is `cache_warmer` (underscore, a valid Python
identifier).

### Import resolution

With all members installed in editable mode, each member's `src/` directory is
on `sys.path`. Python's path finder scans every entry for `bna`; finding only
directories without `__init__.py`, it builds one namespace package whose
`__path__` lists every `src/bna/`. `bna.lib`, `bna.cli`, etc. are then ordinary
regular packages found inside that combined path.

If any entry holds `bna/__init__.py`, the path finder returns that directory as
a regular package as soon as it finds it, discarding the namespace portions, and
every other member's subpackage becomes unimportable. The guardrail exists to
catch exactly this.

In a non-editable install (the Docker image), pip unpacks the `bna-lib` and
`bna-cli` wheels into the same `site-packages/bna/` directory. Because neither
wheel ships `bna/__init__.py`, the two never write the same file.

## Components and Interfaces

### Member `pyproject.toml` files

For each of `packages/lib/pyproject.toml`, `packages/cli/pyproject.toml`,
`packages/batch/pyproject.toml` and `packages/cache-warmer/pyproject.toml`:

- `[project] name` becomes `bna-<member>`.
- Dependencies on other members and their `[tool.uv.sources]` entries use the
  new distribution names (`bna-lib`, `bna-cli`).
- `[project.scripts]` keep the script names and point at the new modules:
  `bna = "bna.cli.root:app"`, `bna-batch = "bna.batch.main:app"`,
  `bna-cache-warmer = "bna.cache_warmer.main:app"`.
- A new table tells hatchling where the package lives, since automatic detection
  looks for `src/<normalized distribution name>` and cannot find a namespace
  package:

  ```toml
  [tool.hatch.build.targets.wheel]
  packages = ["src/bna"]
  ```

- `[tool.coverage.run] omit` patterns use the new path: `*/bna/lib/…`,
  `*/bna/cli/*`, `*/bna/batch/*`, `*/bna/cache_warmer/*`. `"*/__init__.py"`
  stays.
- `[tool.hatch.version]` (`path = "../../VERSION"`) is unchanged: the directory
  depth does not change.

### Root `pyproject.toml`

| Table                                      | Change                                                                                                                                                                                             |
| :----------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[tool.uv.workspace] members`              | `packages/batch`, `packages/cache-warmer`, `packages/cli`, `packages/lib`                                                                                                                          |
| `[tool.uv.sources]`                        | keys `bna-lib`, `bna-cli`, `bna-cache-warmer`, `bna-batch`                                                                                                                                         |
| `[dependency-groups] dev`                  | the four `bna-*` names                                                                                                                                                                             |
| `[tool.isort] known_first_party`           | `["bna"]`                                                                                                                                                                                          |
| `[tool.ruff.lint.isort] known-first-party` | `["bna"]`                                                                                                                                                                                          |
| `[tool.coverage.run] omit`                 | `*/bna/batch/*`, `*/bna/cache_warmer/*`, `*/bna/cli/*`, `*/bna/lib/constant.py`, `*/bna/lib/core/compute.py`, `*/bna/lib/core/downloader.py`, `*/bna/lib/core/ingestor.py`, `*/bna/lib/database/*` |
| `[tool.pytest.ini_options] testpaths`      | `packages/<member>/tests` for each member                                                                                                                                                          |
| `[tool.ruff] src`                          | `packages/<member>/src` for each member                                                                                                                                                            |
| `[tool.ty.environment] root`               | `packages/<member>/src` for each member                                                                                                                                                            |

`[project] name = "brokenspoke-analyzer"` and `package = false` are unchanged.
The `[tool.sqlfluff]` configuration names no member path and is unchanged.

`uv.lock` is regenerated with `uv lock`, never edited by hand.

### Source code

Every `from brokenspoke_analyzer_<member>…` /
`import brokenspoke_analyzer_<member>…` in `packages/*/src` and
`packages/*/tests` becomes `from bna.<member>…` / `import bna.<member>…`. The
string-based package lookups change too:

- `packages/lib/src/bna/lib/core/ingestor.py`:
  `resources.files("bna.lib.scripts")`
- `packages/cli/src/bna/cli/compute.py`:
  `resources.files("bna.lib.scripts.sql")`
- `packages/cli/src/bna/cli/run_with.py`:
  `resources.files("bna.lib.scripts.sql")`
- `packages/cli/src/bna/cli/__main__.py`: `from bna.cli import root`, so
  `python -m bna.cli` starts the CLI.
- `packages/cli/src/bna/cli/root.py`: the `--version` callback reads
  `metadata.version("bna-cli")`. The printed text
  (`brokenspoke-analyzer version: …`) is unchanged. Click runs this callback on
  every invocation, so with the old distribution name every `bna` subcommand
  fails with `PackageNotFoundError`. Two regression tests in
  `packages/cli/tests/test_root.py` cover it: `--version`, and a subcommand
  `--help` (the root `--help` exits before the callbacks run, so the existing
  test cannot see it). (Added during implementation; see `findings.md` §1.1.)

`scripts/` and `scripts/sql/` keep their current structure; they are found
through `importlib.resources` relative to `bna.lib`, which is a regular package.

The rule that the library never imports from the CLI is unchanged: `bna.lib`
must not import `bna.cli`.

### Namespace guardrail: `packages/lib/tests/test_namespace.py`

A new test module in the library member, so it runs in `just test` and when the
library's tests run alone (`cd packages/lib && uv run pytest`). Every other
member depends on `bna-lib`, so the library is always installed wherever the
namespace exists.

It contains two tests:

1. **`test_no_member_ships_a_bna_init`**: locates the repository root from the
   test file's own path (`Path(__file__).resolve().parents[3]`), globs
   `packages/*/src/bna/__init__.py`, and asserts the result is empty. The
   assertion message lists every offending path, relative to the repository
   root. This test works whatever is installed.
2. **`test_bna_is_a_namespace_package`**: imports `bna` and asserts that it is a
   namespace package (`bna.__file__ is None`), and that the library's own
   `src/bna` directory is part of `bna.__path__`, comparing resolved paths
   (`sys.path` entries keep symlinks as given, the test's own path does not).
   This catches a regular `bna` package coming from anywhere on `sys.path`,
   including a stray installed wheel, which the file check cannot see.

The module follows the project conventions: full type hints, a pep257 module
docstring, and the per-file ignores the root `pyproject.toml` already applies to
tests.

### Tests layout

Each member's test files move up out of the
`tests/brokenspoke_analyzer_<member>/` directory, so that `tests/` mirrors the
path below `src/bna/<member>/`:

| Before                                                                                            | After                                      |
| :------------------------------------------------------------------------------------------------ | :----------------------------------------- |
| `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/test_datastore.py`              | `packages/lib/tests/test_datastore.py`     |
| `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/core/test_analysis.py`          | `packages/lib/tests/core/test_analysis.py` |
| `packages/brokenspoke-analyzer-cli/tests/brokenspoke_analyzer_cli/test_root.py`                   | `packages/cli/tests/test_root.py`          |
| `packages/brokenspoke-analyzer-batch/tests/brokenspoke_analyzer_batch/test_main.py`               | `packages/batch/tests/test_main.py`        |
| `packages/brokenspoke-analyzer-cache-warmer/tests/brokenspoke_analyzer_cache_warmer/test_main.py` | `packages/cache-warmer/tests/test_main.py` |

The root pytest configuration runs with `--import-mode=importlib`, so the two
`test_main.py` files coexist in a single root run. Each member's own pytest
configuration keeps its current `addopts`; within a single member the test file
names are unique, so the default import mode works for per-member runs.

### `justfile`

- `lib_pkg := "packages/lib"`, `cli_pkg := "packages/cli"`,
  `cache_warmer_pkg := "packages/cache-warmer"`,
  `batch_pkg := "packages/batch"`.
- `sql_dir := lib_pkg / "src/bna/lib/scripts/sql"`.
- `test` recipe:

  ```just
  uv run pytest --cov=bna.lib --cov=bna.cli --cov=bna.cache_warmer --cov=bna.batch -x $@
  ```

`src_dirs` and `test_dirs` derive from the variables above and need no change.
No new recipe is added.

### `Dockerfile`

The builder stage (`uv export … --no-emit-workspace`,
`uv build --all-packages --wheel`) names no member and is unchanged. The runtime
stage installs the renamed wheels:

```dockerfile
pkg/dist/bna_lib-*-py3-none-any.whl \
pkg/dist/bna_cli-*-py3-none-any.whl \
```

The `ENTRYPOINT [ "bna" ]`, image labels and user setup are unchanged.

### Documentation

- `docs/source/conf.py`: the `sys.path` loop iterates over the new directories
  (`("lib", "cli")`), and `package = "bna-cli"` for the
  `metadata.version(package)` lookup.
- `docs/source/lib/*.rst`: each `brokenspoke_analyzer_lib.<module>.rst` is moved
  with `git mv` to `bna.lib.<module>.rst`, its title and `automodule` target
  change to `bna.lib.<module>`, and `docs/source/lib/index.rst` lists the new
  names in its toctree. The index title becomes the distribution name `bna-lib`.
- `docs/source/cli/*.rst` and `docs/source/cli/index.rst`: the same for
  `bna.cli.<module>` and `bna-cli`.
- `docs/source/how-to/analyze-bike-infrastructure.md`: its references to
  "brokenspoke-analyzer" describe the project, not a member, and stay unchanged.
  Any member reference found during the implementation is updated.

### Contributor-facing files

- `CLAUDE.md`: commands (`--cov=bna.lib`, the sqlfluff path), "Running the CLI"
  (`bna.cli.root:app`, `packages/cli/src/bna/cli/`), and "Architecture"
  (directories, distribution names, import names, adding a new member as
  `packages/<tool>/` with `src/bna/<tool>/`). A new convention states that no
  member may ship `src/bna/__init__.py`, and why.
- `.github/CONTRIBUTING.md`: the `bna-lib` and `bna-cli` distribution names and
  the namespace rule.
- `.vscode/launch.json`: `"module": "bna.cli"`.

Both Markdown files are formatted with
`npx prettier --write --prose-wrap always <file>` after editing.

## Data Models

There is no runtime data model. The feature is defined by this name mapping:

| Member       | Directory               | Distribution       | Import name        | Wheel file                              | Console script                                   |
| :----------- | :---------------------- | :----------------- | :----------------- | :-------------------------------------- | :----------------------------------------------- |
| library      | `packages/lib`          | `bna-lib`          | `bna.lib`          | `bna_lib-<v>-py3-none-any.whl`          | —                                                |
| CLI          | `packages/cli`          | `bna-cli`          | `bna.cli`          | `bna_cli-<v>-py3-none-any.whl`          | `bna` → `bna.cli.root:app`                       |
| batch        | `packages/batch`        | `bna-batch`        | `bna.batch`        | `bna_batch-<v>-py3-none-any.whl`        | `bna-batch` → `bna.batch.main:app`               |
| cache warmer | `packages/cache-warmer` | `bna-cache-warmer` | `bna.cache_warmer` | `bna_cache_warmer-<v>-py3-none-any.whl` | `bna-cache-warmer` → `bna.cache_warmer.main:app` |

Old names, for search and replace: directory
`packages/brokenspoke-analyzer-<m>`, distribution `brokenspoke-analyzer-<m>`,
import `brokenspoke_analyzer_<m>`.

## Correctness Properties

1. **No namespace initializer**: no file matches
   `packages/*/src/bna/__init__.py`, and no built wheel contains
   `bna/__init__.py`.
2. **Disjoint wheels**: each member's wheel contains files under `bna/<member>/`
   only, so installing several wheels never overwrites a file.
3. **Namespace import**: in the workspace environment, `bna.__file__ is None`,
   and `bna.lib`, `bna.cli`, `bna.batch` and `bna.cache_warmer` all import.
4. **No old names**: outside `specs/`, the repository contains no
   `brokenspoke_analyzer_(lib|cli|batch|cache_warmer)` nor
   `brokenspoke-analyzer-(lib|cli|batch|cache-warmer)` string. The root project
   name `brokenspoke-analyzer`, the Docker image and Compose names, and the
   repository URL legitimately remain.
5. **Library independence**: no module under `packages/lib/src/bna/lib/` imports
   `bna.cli`, `bna.batch` or `bna.cache_warmer`.
6. **Unchanged command line**: the console script names, their commands, options
   and behavior are identical before and after.
7. **Same tests**: the set of collected tests equals the previous set plus the
   two guardrail tests, the two `--version` regression tests and the bundled
   script tests.

## Error Handling

- **A member ships `src/bna/__init__.py`**: `test_no_member_ships_a_bna_init`
  fails and names the file; `test_bna_is_a_namespace_package` fails as well.
  Fix: delete the file. Code that would have gone in it belongs in the member's
  own `bna/<member>/__init__.py`.
- **A regular `bna` package elsewhere on `sys.path`** (e.g. an unrelated
  installed distribution providing `bna`): only
  `test_bna_is_a_namespace_package` fails. Fix: remove that distribution from
  the environment.
- **Stale environment after pulling the rename**: the old
  `brokenspoke-analyzer-*` editable installs are still in `.venv`. `just setup`
  (`uv sync`, which removes packages not in the lock file) cleans them up.
- **Leftover directories after the moves**: `git mv` of a whole directory is a
  filesystem rename, so untracked and ignored content (`.pytest_cache/`,
  `__pycache__/`, a local OSMnx `cache/`) moves along and the old
  `packages/brokenspoke-analyzer-*` directories disappear. Only moving
  individual files out of a directory leaves it behind: the flattened
  `tests/brokenspoke_analyzer_*` folders survive holding `__pycache__/` only.
  After checking they contain only generated files, they are deleted. (Corrected
  during implementation: the first version of this design assumed the old member
  directories would survive; see `findings.md` §2.1.)
- **hatchling cannot find the package**: without
  `[tool.hatch.build.targets.wheel] packages = ["src/bna"]`, the build fails
  because no `src/bna_<member>` exists. Every member sets it.

## Integration

- **uv**: workspace sources are keyed by distribution name and resolved by path
  from the `members` list. Both change together, and `uv lock` records the new
  names and editable paths.
- **Tooling**: ruff and ty read the member `src/` roots from the root
  `pyproject.toml`; isort and ruff treat `bna` as first party; `ruff` raises no
  `INP001` for the namespace directory (verified in the prototype, because no
  Python file sits directly in `src/bna/`).
- **Docs**: Sphinx autodoc imports `bna.lib.*` and `bna.cli.*` through the
  `sys.path` entries added in `conf.py`; the namespace assembles from both.
- **CI**: the workflows under `.github/workflows/` call `just` recipes and
  `uv build --all-packages`, and name no member path, so they need no change.
  The release workflow uploads `dist/*.*`, so release assets take the new wheel
  and sdist names.
- **`integration/` and `utils/`**: they drive the `bna` command and import no
  member module, so they need no change.
- **Past specs**: `specs/0002-uv-workspace/` and every other past specification
  are left untouched.

## Testing Strategy

- **Guardrail tests** (`packages/lib/tests/test_namespace.py`): both tests pass
  on the renamed tree. To prove they work, temporarily create
  `packages/batch/src/bna/__init__.py`, confirm both fail and the first names
  the file, then delete it (and the `__pycache__/` the failing import leaves
  next to it).
- **Bundled script tests** (`packages/lib/tests/test_scripts.py`): the SQL
  script folders (`connectivity`, `features`, `stress`) resolve from
  `bna.lib.scripts.sql` and hold SQL files, and `ingestor.script_dir` holds
  `mapconfig_cycleway.xml`, `mapconfig_highway.xml` and `pfb.style`. This turns
  Requirement 3.6 into an automated check instead of a full pipeline run. (Added
  after the spec review.)
- **Existing tests**: all existing tests pass in their new locations, through
  `just test` and through each member's own `uv run pytest`. The collected test
  count from `uv run pytest --collect-only -q` is compared before and after.
- **Quality command**: `just ci` (lint including `lint-uv`, docs, tests).
- **Build checks**: `uv build --all-packages --wheel`, then list each wheel's
  contents to confirm property 1 and property 2, and that `bna_lib` contains
  `bna/lib/scripts/sql/**.sql`, the two `mapconfig_*.xml` files and `pfb.style`.
- **Command line checks**: `uv run bna --help`, `uv run bna-batch --help`,
  `uv run bna-cache-warmer --help`, `uv run python -m bna.cli --help`.
- **Docker check**: `just docker-build`, then run the image with `--help`, and
  confirm the SQL scripts resolve inside the container
  (`python -c "from importlib import resources; print(list(resources.files('bna.lib.scripts.sql').iterdir()))"`
  with the entrypoint overridden).
- **Old-name check**: a repository-wide search for the old directory,
  distribution and import names, excluding `specs/`, `.git/` and `.venv/`,
  returns nothing (property 4).
- **History check**: `git log --follow` on a moved file shows commits from
  before the rename.

## Deployment Considerations

- **Developers**: after pulling, run `just setup` to drop the old editable
  installs. IDE run configurations and shell history using
  `brokenspoke_analyzer_cli` need updating.
- **Docker**: images must be rebuilt; the image name, entrypoint and Compose
  setup are unchanged.
- **Release assets**: wheel and sdist file names on GitHub releases change to
  `bna_*`.
- **Documentation site**: API page URLs change (e.g.
  `lib/brokenspoke_analyzer_lib.core.runner.html` becomes
  `lib/bna.lib.core.runner.html`). Old URLs stop working.
- **No configuration change**: environment variables, `DATABASE_URL`, cache
  directory and S3 settings are unaffected.

## Dependencies

No new dependency. The feature relies on what the project already uses:
hatchling (build backend, `[tool.hatch.build.targets.wheel] packages`), uv
workspaces, and Python 3.13's built-in PEP 420 namespace packages.
