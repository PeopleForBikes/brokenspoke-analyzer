# Requirements Document: Shared `bna` Namespace for Workspace Members

## Introduction

The uv workspace introduced by `specs/0002-uv-workspace/` names every member
after the workspace itself, so the project name appears three times in each
source path: `packages/brokenspoke-analyzer-lib/src/brokenspoke_analyzer_lib/`.
Directories, distribution names and import names all carry the
`brokenspoke-analyzer` prefix, which makes paths long, noisy in tracebacks,
editor tabs and diffs, and gives every member at least two hyphens in its name.

This feature shortens the member directories to `packages/<member>/` and moves
every member under a single shared [PEP 420](https://peps.python.org/pep-0420/)
namespace package named `bna`, matching the name of the command line tool. The
library becomes `bna.lib`, the CLI `bna.cli`, and so on, so the path above
becomes `packages/lib/src/bna/lib/`. Distribution names follow the same scheme
(`bna-lib`, `bna-cli`, …). Because a single misplaced `bna/__init__.py` in any
member would silently break the shared namespace for all the others, the feature
also adds an automated guardrail against it.

The workspace layout has never been part of a release, and the packages are not
published on PyPI, so the rename is a clean break with no compatibility aliases.
It targets the v4.0.0 release.

**In scope:**

- Renaming the four member directories, distribution names and import names.
- Flattening each member's test tree to mirror the path below
  `src/bna/<member>/`.
- Updating every reference in the repository: workspace and tool configuration,
  `justfile`, `Dockerfile`, Sphinx documentation (including the API page file
  names), `.vscode/launch.json`, `CLAUDE.md` and `.github/CONTRIBUTING.md`.
- A test-based guardrail protecting the shared namespace.

**Out of scope:**

- Bumping `VERSION` to 4.0.0 (a release step, not part of this feature).
- Compatibility aliases for the old `brokenspoke_analyzer_*` import names or
  `brokenspoke-analyzer-*` distribution names.
- Renaming the console scripts (`bna`, `bna-batch`, `bna-cache-warmer`), the
  root project (`brokenspoke-analyzer`), the Docker image, the Docker Compose
  project or volumes, the GitHub repository, or the cache directory.
- Publishing packages to PyPI.
- Rewriting past specifications (including `specs/0002-uv-workspace/`); they
  stay as the historical record of the layout they introduced.
- Any behavioral change to the analysis pipeline.

## Glossary

- **Member**: one of the four uv workspace projects under `packages/` (lib, cli,
  batch, cache-warmer).
- **Member_Directory**: the folder holding a member, e.g. `packages/lib/`.
- **Distribution_Name**: the `name` in a member's `pyproject.toml`, used by uv
  sources, `uv run --package`, dependency declarations and wheel file names.
- **Import_Name**: the dotted Python path used to import a member's code, e.g.
  `bna.lib`.
- **Namespace_Package**: a PEP 420 package without an `__init__.py`, whose
  contents are merged from several directories on `sys.path`. Here: `bna`.
- **Regular_Package**: a package with an `__init__.py`. If any member ships
  `src/bna/__init__.py`, `bna` becomes a regular package and the other members'
  subpackages can no longer be imported.
- **Namespace_Guardrail**: the automated test that fails when the shared `bna`
  namespace is broken.
- **Quality_Command**: `just ci` (lint, docs, test).

## Requirements

### Requirement 1: Short Member Directories

**User Story:** As a developer, I want each member to live in a short directory,
so that paths no longer repeat the workspace name.

#### Acceptance Criteria

1. The system SHALL hold the members in `packages/lib/`, `packages/cli/`,
   `packages/batch/` and `packages/cache-warmer/`.
2. The system SHALL contain no directory matching
   `packages/brokenspoke-analyzer-*`.
3. The system SHALL declare exactly these four directories as workspace members
   in the root `pyproject.toml`.
4. WHEN a file is moved to its new member directory, the system SHALL keep its
   git history traceable through `git log --follow`.

### Requirement 2: Short Distribution Names

**User Story:** As a developer, I want distribution names that match the
directories and import paths, so that I can tell which package is which without
a lookup table.

#### Acceptance Criteria

1. The system SHALL name the members' distributions `bna-lib`, `bna-cli`,
   `bna-batch` and `bna-cache-warmer`.
2. The system SHALL declare every dependency between members, and every uv
   workspace source, using the new distribution names.
3. The system SHALL keep the root virtual project named `brokenspoke-analyzer`.
4. The system SHALL keep all members on the single shared version read from the
   root `VERSION` file.
5. WHEN the members are built, the system SHALL produce wheel files named after
   the new distribution names (e.g. `bna_lib-<version>-py3-none-any.whl`).
6. The system SHALL keep `uv.lock` consistent with the renamed members, so that
   `uv lock --check` succeeds.

### Requirement 3: Shared `bna` Namespace

**User Story:** As a developer, I want every member importable under one short
`bna` prefix, so that imports are short and still clearly belong to this
project.

#### Acceptance Criteria

1. The system SHALL expose the members as `bna.lib`, `bna.cli`, `bna.batch` and
   `bna.cache_warmer`.
2. The system SHALL make `bna` a namespace package: no member SHALL ship a
   `src/bna/__init__.py`.
3. WHILE all members are installed in the same environment, the system SHALL
   allow every member's subpackage to be imported from that environment.
4. The system SHALL build each member's wheel with only its own subpackage
   (`bna/<member>/…`) and no `bna/__init__.py`.
5. The system SHALL contain no reference to the import names
   `brokenspoke_analyzer_lib`, `brokenspoke_analyzer_cli`,
   `brokenspoke_analyzer_batch` or `brokenspoke_analyzer_cache_warmer`, nor to
   the distribution names `brokenspoke-analyzer-lib`,
   `brokenspoke-analyzer-cli`, `brokenspoke-analyzer-batch` or
   `brokenspoke-analyzer-cache-warmer`, outside `specs/`.
6. WHEN the analysis loads its bundled SQL scripts and import configuration
   files, the system SHALL find them under the `bna.lib` package.

### Requirement 4: Namespace Guardrail

**User Story:** As a maintainer, I want the test suite to fail when the shared
namespace is broken, so that a stray `__init__.py` is caught in CI instead of
surfacing as a confusing import error.

#### Acceptance Criteria

1. IF any file matches `packages/*/src/bna/__init__.py`, THEN the
   Namespace_Guardrail SHALL fail and name every offending file.
2. IF `bna` imports as a regular package, THEN the Namespace_Guardrail SHALL
   fail.
3. WHEN `just test` runs, the system SHALL run the Namespace_Guardrail.
4. WHEN the library member's tests run on their own, the system SHALL run the
   Namespace_Guardrail.

### Requirement 5: Unchanged User-Facing Behavior

**User Story:** As a user of the `bna` tools, I want the rename to be invisible
from the command line, so that my scripts and pipelines keep working.

#### Acceptance Criteria

1. The system SHALL keep installing the console scripts `bna`, `bna-batch` and
   `bna-cache-warmer`, with the same commands and options as before.
2. WHEN a user runs `uv run bna <command>` from the repository root, the system
   SHALL behave as it did before the rename.
3. WHEN a user runs `python -m bna.cli`, the system SHALL start the `bna` CLI.
4. WHEN the Docker image is built with `just docker-build`, the system SHALL
   produce an image whose `bna` entrypoint runs, with the bundled SQL scripts
   and import configuration files available.
5. The system SHALL keep environment variables, the cache directory location,
   the Docker image name and the Docker Compose project name unchanged.

### Requirement 6: Flattened Test Layout

**User Story:** As a developer, I want each member's tests to mirror only the
path below its subpackage, so that test paths do not reintroduce the repetition
this feature removes.

#### Acceptance Criteria

1. The system SHALL place each member's tests under `packages/<member>/tests/`,
   mirroring the path below `src/bna/<member>/` (e.g.
   `packages/lib/tests/core/test_analysis.py` for
   `packages/lib/src/bna/lib/core/analysis.py`).
2. WHEN `just test` runs, the system SHALL collect every test of every member
   and report combined coverage for `bna.lib`, `bna.cli`, `bna.batch` and
   `bna.cache_warmer`.
3. WHEN a member's tests are run from its own directory
   (`cd packages/<member> && uv run pytest`), the system SHALL collect and run
   that member's tests.
4. The system SHALL keep the same set of tests, so the number of collected tests
   does not decrease, apart from the tests the Namespace_Guardrail adds.

### Requirement 7: Tooling and Documentation

**User Story:** As a contributor, I want the tooling and docs to describe the
new layout, so that I can work in the repository without stumbling on stale
paths.

#### Acceptance Criteria

1. WHEN the Quality_Command runs, the system SHALL pass with no new lint, type,
   SQL lint or test failures.
2. The system SHALL treat `bna` as the first-party package for both isort and
   ruff import sorting.
3. The system SHALL name the Sphinx API pages after the new import paths (e.g.
   `docs/source/lib/bna.lib.core.runner.rst`), and each page SHALL document the
   matching module.
4. WHEN `just docs` builds the documentation, the system SHALL read the release
   version from the renamed CLI distribution.
5. The system SHALL describe the new directories, distribution names, import
   names and the "no `src/bna/__init__.py`" rule in `CLAUDE.md` and
   `.github/CONTRIBUTING.md`.
6. The system SHALL point the `.vscode/launch.json` debug configuration at
   `bna.cli`.
