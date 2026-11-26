# Implementation Plan: Shared `bna` Namespace for Workspace Members

## Overview

The plan follows the three kinds of change in `design.md`, in an order that
keeps git history clean and lets each step be verified:

1. Record a baseline, then make **pure moves** with `git mv` (directories,
   subpackages, tests, documentation pages) and nothing else, so git records
   them as 100% renames.
2. **Update references**: packaging and tool configuration first (so the
   environment can be synced), then source and test code.
3. Add the **guardrail**, run a checkpoint, then update the Dockerfile,
   documentation and contributor-facing files, and finish with a full
   verification pass.

Old names, for search and replace: directory
`packages/brokenspoke-analyzer-<m>`, distribution `brokenspoke-analyzer-<m>`,
import `brokenspoke_analyzer_<m>`. New names: `packages/<m>`, `bna-<m>`,
`bna.<m>` (with `cache-warmer` / `cache_warmer` for the cache warmer). The full
mapping is in the [Data Models](design.md#data-models) section of `design.md`.

## Tasks

- [x] 1. Record the baseline
  - Run `uv run pytest --collect-only -q` from the repository root and note the
    number of collected tests (5 when this plan was written, on 2026-11-19).
  - _Requirements: 6.4_

- [x] 2. Move the files (pure moves, no content change)
  - [x] 2.1 Rename the member directories
    - `git mv packages/brokenspoke-analyzer-lib packages/lib`
    - `git mv packages/brokenspoke-analyzer-cli packages/cli`
    - `git mv packages/brokenspoke-analyzer-batch packages/batch`
    - `git mv packages/brokenspoke-analyzer-cache-warmer packages/cache-warmer`
    - _Requirements: 1.1, 1.4_
  - [x] 2.2 Move each top-level package under `src/bna/`
    - `mkdir packages/lib/src/bna` then
      `git mv packages/lib/src/brokenspoke_analyzer_lib packages/lib/src/bna/lib`
    - Same for `packages/cli/src/bna/cli`, `packages/batch/src/bna/batch` and
      `packages/cache-warmer/src/bna/cache_warmer`.
    - Do not create any `src/bna/__init__.py`.
    - _Requirements: 3.1, 3.2, 1.4_
  - [x] 2.3 Flatten the test trees
    - `git mv packages/lib/tests/brokenspoke_analyzer_lib/test_datastore.py packages/lib/tests/test_datastore.py`
    - `git mv packages/lib/tests/brokenspoke_analyzer_lib/core packages/lib/tests/core`
    - `git mv packages/cli/tests/brokenspoke_analyzer_cli/test_root.py packages/cli/tests/test_root.py`
    - `git mv packages/batch/tests/brokenspoke_analyzer_batch/test_main.py packages/batch/tests/test_main.py`
    - For the cache warmer:

      ```sh
      git mv \
        packages/cache-warmer/tests/brokenspoke_analyzer_cache_warmer/test_main.py \
        packages/cache-warmer/tests/test_main.py
      ```

    - _Requirements: 6.1, 1.4_
  - [x] 2.4 Rename the Sphinx API pages
    - Each `docs/source/lib/brokenspoke_analyzer_lib.<module>.rst` becomes
      `docs/source/lib/bna.lib.<module>.rst` (12 files).
    - Each `docs/source/cli/brokenspoke_analyzer_cli.<module>.rst` becomes
      `docs/source/cli/bna.cli.<module>.rst` (10 files).
    - `index.rst` files are not renamed.
    - _Requirements: 7.3_
  - [x] 2.5 Check that the moves are pure
    - `git status` shows only renames (`R`), and `git diff --cached -M --stat`
      reports no content change.
    - Keep the moves on their own, so later content changes do not lower git's
      rename similarity: leave them staged and every later change unstaged, so
      the staged moves can be committed first. (The implementation does not
      commit unless asked.)
    - _Requirements: 1.4_

- [x] 3. Remove the leftover old directories
  - List what remains in the emptied `tests/brokenspoke_analyzer_*` folders
    (task 2.3 moved files out of them, so they survive with `__pycache__/`). The
    whole-directory moves of task 2.1 also carried ignored content
    (`.pytest_cache/`, the OSMnx `cache/`), so no
    `packages/brokenspoke-analyzer-*` directory should remain; check anyway.
  - Confirm it is only generated content, then delete the emptied
    `tests/brokenspoke_analyzer_*` folders (and any old directory found). Ask
    before deleting anything that is not clearly generated.
  - Check `ls packages` lists exactly `batch`, `cache-warmer`, `cli`, `lib`.
  - _Requirements: 1.1, 1.2_

- [x] 4. Update the packaging and tool configuration
  - [x] 4.1 Member `pyproject.toml` files
    - In `packages/lib/pyproject.toml`, `packages/cli/pyproject.toml`,
      `packages/batch/pyproject.toml` and
      `packages/cache-warmer/pyproject.toml`:
      - `[project] name = "bna-<member>"`.
      - Dependencies on other members and `[tool.uv.sources]` keys use `bna-lib`
        and `bna-cli`.
      - `[project.scripts]`: `bna = "bna.cli.root:app"`,
        `bna-batch = "bna.batch.main:app"`,
        `bna-cache-warmer = "bna.cache_warmer.main:app"`.
      - Add `[tool.hatch.build.targets.wheel]` with `packages = ["src/bna"]`.
      - `[tool.coverage.run] omit`: replace `brokenspoke_analyzer_<member>` with
        `bna/<member>` in every pattern; keep `"*/__init__.py"`.
      - Leave `[tool.hatch.version]` unchanged.
    - _Requirements: 2.1, 2.2, 2.4, 3.4, 5.1_
  - [x] 4.2 Root `pyproject.toml`
    - `[tool.uv.workspace] members`: `packages/batch`, `packages/cache-warmer`,
      `packages/cli`, `packages/lib`.
    - `[tool.uv.sources]` and `[dependency-groups] dev`: the four `bna-*` names.
    - `[tool.isort] known_first_party` and
      `[tool.ruff.lint.isort] known-first-party`: `["bna"]`.
    - `[tool.coverage.run] omit`: the `*/bna/…` patterns listed in `design.md`.
    - `[tool.pytest.ini_options] testpaths`, `[tool.ruff] src`,
      `[tool.ty.environment] root`: the new `packages/<member>/tests` and
      `packages/<member>/src` paths.
    - Leave `[project] name = "brokenspoke-analyzer"`, `package = false` and the
      `[tool.sqlfluff]` tables unchanged.
    - _Requirements: 1.3, 2.2, 2.3, 6.2, 7.2_
  - [x] 4.3 `justfile`
    - `lib_pkg`, `cli_pkg`, `cache_warmer_pkg`, `batch_pkg` point at
      `packages/lib`, `packages/cli`, `packages/cache-warmer`, `packages/batch`.
    - `sql_dir := lib_pkg / "src/bna/lib/scripts/sql"`.
    - `test` recipe:

      ```just
      uv run pytest --cov=bna.lib --cov=bna.cli --cov=bna.cache_warmer --cov=bna.batch -x $@
      ```

    - Leave `docker_image` and the Docker volume names unchanged.
    - _Requirements: 6.2, 5.5_
  - [x] 4.4 Regenerate the lock file and sync the environment
    - `uv lock`, then `just setup` (which also removes the old
      `brokenspoke-analyzer-*` editable installs).
    - `just lint-uv` passes.
    - _Requirements: 2.6_

- [x] 5. Update source and test code
  - [x] 5.1 Imports
    - In every `.py` file under `packages/*/src` and `packages/*/tests`, replace
      `brokenspoke_analyzer_lib` with `bna.lib`, `brokenspoke_analyzer_cli` with
      `bna.cli`, `brokenspoke_analyzer_batch` with `bna.batch` and
      `brokenspoke_analyzer_cache_warmer` with `bna.cache_warmer`, in
      `import`/`from` statements, docstrings, doctests and comments.
    - `packages/cli/src/bna/cli/__main__.py`: `from bna.cli import root`.
    - Run `uv run isort .` and `uv run ruff format` on the source and test
      directories, since the new first-party name changes the import order.
    - _Requirements: 3.1, 3.5, 5.3_
  - [x] 5.2 Package-relative resource lookups
    - `packages/lib/src/bna/lib/core/ingestor.py`:
      `resources.files("bna.lib.scripts")`.
    - `packages/cli/src/bna/cli/compute.py` and
      `packages/cli/src/bna/cli/run_with.py`:
      `resources.files("bna.lib.scripts.sql")`.
    - `packages/cli/src/bna/cli/root.py`: `metadata.version("bna-cli")` in the
      `--version` callback, and two regression tests in
      `packages/cli/tests/test_root.py` (`--version`, and `cache --help`, which
      runs the root callbacks). (Added during implementation: the old name made
      every subcommand fail; see `findings.md` §1.1.)
    - _Requirements: 3.6, 5.1, 5.2_
  - [x] 5.3 Library independence
    - Check that no module under `packages/lib/src/bna/lib/` imports `bna.cli`,
      `bna.batch` or `bna.cache_warmer`.
    - _Requirements: 3.1_

- [x] 6. Add the namespace guardrail
  - Create `packages/lib/tests/test_namespace.py` with a pep257 module docstring
    and full type hints, containing:
    - `test_no_member_ships_a_bna_init`: glob `packages/*/src/bna/__init__.py`
      from the repository root (`Path(__file__).resolve().parents[3]`) and
      assert the list is empty, with a message naming each offending path
      relative to the repository root.
    - `test_bna_is_a_namespace_package`: `import bna`, assert
      `bna.__file__ is None`, and assert the library's own `src/bna` directory
      (`Path(__file__).resolve().parents[1] / "src" / "bna"`) is in
      `bna.__path__`, comparing resolved paths.
  - _Requirements: 3.2, 4.1, 4.2, 4.3, 4.4_
  - [x] 6.1 Bundled script tests (added after the spec review)
    - Create `packages/lib/tests/test_scripts.py`: each SQL script folder
      (`connectivity`, `features`, `stress`) resolves from `bna.lib.scripts.sql`
      and holds SQL files, and `ingestor.script_dir` holds
      `mapconfig_cycleway.xml`, `mapconfig_highway.xml` and `pfb.style`.
    - Hiding one of the files makes its test fail.
    - _Requirements: 3.6_
  - [x] 6.2 Wheel content check (added after the spec review)
    - Create `utils/check_wheels.py` and a `check-wheels` recipe in `justfile`
      that builds every member's wheel into a temporary directory and runs the
      script on it; add `check-wheels` to the `ci` recipe.
    - The script fails, naming the problem, when a member has no wheel, when a
      wheel ships `bna/__init__.py`, or when a wheel's files differ from its
      member's source files.
    - Doctored wheels prove each case fails: an added `bna/__init__.py`, a
      removed `pfb.style`, an added stray file, a missing wheel.
    - Wiring the check into the GitHub workflows is left to the team.
    - _Requirements: 2.5, 3.2, 3.4, 3.6_

- [x] 7. Checkpoint: code and tests
  - `just lint-python` and `just lint-sql` pass.
  - `just test` passes with `--cov` for all four `bna.*` packages, and its
    coverage report lists the `bna/lib` modules. (`bna/cli`, `bna/batch` and
    `bna/cache_warmer` are excluded by the root `[tool.coverage.run] omit`,
    exactly as their old names were before the rename.)
  - `uv run pytest --collect-only -q` collects the baseline from task 1 plus the
    2 guardrail tests, the 2 `--version` regression tests of task 5.2 and the 6
    bundled script tests of task 6.1.
  - `cd packages/<member> && uv run pytest` passes for each of the four members,
    and the library run includes the guardrail tests.
  - `uv run python -c "import bna.lib, bna.cli, bna.batch, bna.cache_warmer"`
    succeeds.
  - Prove the guardrail: create an empty `packages/batch/src/bna/__init__.py`,
    confirm both guardrail tests fail and the first names
    `packages/batch/src/bna/__init__.py`, then delete the file and the
    `__pycache__/` the failing import left next to it, and confirm they pass
    again.
  - _Requirements: 3.3, 4.1, 4.2, 4.3, 4.4, 6.2, 6.3, 6.4, 7.1_

- [x] 8. Update the `Dockerfile`
  - Runtime stage installs `pkg/dist/bna_lib-*-py3-none-any.whl` and
    `pkg/dist/bna_cli-*-py3-none-any.whl`.
  - Leave the builder stage, `ENTRYPOINT [ "bna" ]`, labels and user setup
    unchanged.
  - _Requirements: 5.4, 5.5_

- [x] 9. Update the documentation
  - [x] 9.1 `docs/source/conf.py`
    - The `sys.path` loop iterates over `("lib", "cli")`.
    - `package = "bna-cli"`.
    - _Requirements: 7.4_
  - [x] 9.2 API pages
    - In each `docs/source/lib/bna.lib.<module>.rst` and
      `docs/source/cli/bna.cli.<module>.rst`, set the title (and its underline
      length) and the `automodule` target to the new import path.
    - `docs/source/lib/index.rst` and `docs/source/cli/index.rst`: title
      `bna-lib` / `bna-cli`, and toctree entries with the new page names.
    - _Requirements: 7.3_
  - [x] 9.3 Other pages
    - Search `docs/source/` for remaining member references and update them;
      leave project-level "brokenspoke-analyzer" mentions (such as in
      `docs/source/how-to/analyze-bike-infrastructure.md`) unchanged.
    - _Requirements: 3.5_
  - [x] 9.4 Build
    - `just docs` builds without new warnings, and the generated pages document
      the `bna.lib.*` and `bna.cli.*` modules.
    - _Requirements: 7.3, 7.4_

- [x] 10. Update the contributor-facing files
  - [x] 10.1 `CLAUDE.md`
    - Commands section: `--cov=bna.lib` example and the sqlfluff path
      `packages/lib/src/bna/lib/scripts/sql/`.
    - "Running the CLI": `bna.cli.root:app` and `packages/cli/src/bna/cli/`.
    - "Architecture": member directories, distribution names and import names;
      adding a new member means `packages/<tool>/` with `src/bna/<tool>/` and
      `[tool.hatch.build.targets.wheel] packages = ["src/bna"]`; tests mirror
      the path below `src/bna/<member>/`.
    - "Conventions": `bna.lib.constant` re-exported by `bna.cli.common`, and a
      new rule that no member may ship `src/bna/__init__.py`, with the reason
      and a pointer to `packages/lib/tests/test_namespace.py`.
    - Format with `npx prettier --write --prose-wrap always CLAUDE.md`.
    - _Requirements: 7.5_
  - [x] 10.2 `.github/CONTRIBUTING.md`
    - Refer to `bna-lib` and `bna-cli`, and state the namespace rule.
    - Format with
      `npx prettier --write --prose-wrap always .github/CONTRIBUTING.md`.
    - _Requirements: 7.5_
  - [x] 10.3 `.vscode/launch.json`
    - `"module": "bna.cli"`.
    - _Requirements: 7.6_

- [x] 11. Checkpoint: full verification
  - `just ci` passes.
  - Old names: a search for
    `brokenspoke[-_]analyzer[-_](lib|cli|batch|cache[-_]warmer)` across the
    repository, excluding `specs/`, `.git/` and `.venv/`, returns nothing.
  - Build: `uv build --all-packages --wheel -o <scratch dir>`, then list each
    wheel:
    - The files are named `bna_lib-*`, `bna_cli-*`, `bna_batch-*`,
      `bna_cache_warmer-*`.
    - No wheel contains `bna/__init__.py`, and each contains only
      `bna/<member>/…` (plus its `.dist-info`).
    - `bna_lib` contains `bna/lib/scripts/sql/**/*.sql`,
      `bna/lib/scripts/mapconfig_cycleway.xml`,
      `bna/lib/scripts/mapconfig_highway.xml` and `bna/lib/scripts/pfb.style`.
  - Command line: `uv run bna --help`, `uv run bna-batch --help`,
    `uv run bna-cache-warmer --help` and `uv run python -m bna.cli --help` show
    the same commands and options as before the rename.
  - Docker: `just docker-build`; the image runs `--help`; with the entrypoint
    overridden to `python`, `resources.files('bna.lib.scripts.sql')` lists the
    SQL directories.
  - Unchanged names: `compose.yml`, the `justfile` `docker_image` variable, the
    Docker volume name and the root project name still read
    `brokenspoke-analyzer`.
  - History:
    `git log --follow --oneline packages/lib/src/bna/lib/core/runner.py` shows
    commits from before the rename.
  - _Requirements: 1.2, 1.4, 2.1, 2.3, 2.5, 3.4, 3.5, 3.6, 5.1, 5.2, 5.3, 5.4,
    5.5, 7.1_

## Notes

- **Commit boundaries**: keep task 2 in a commit of its own. Folding the content
  changes into the same commit lowers git's rename similarity and can break
  `git log --follow` for small files such as the `__init__.py` files and the
  `.rst` pages.
- **Stale environments**: until `just setup` runs (task 4.4), the old editable
  installs still provide `brokenspoke_analyzer_*`, which can hide a missed
  import. Run the checkpoints only after syncing.
- **Offline sandboxes**: `just lint-md`, the `npx prettier` calls and
  `just docker-build` need network access. Where it is unavailable, run them on
  a machine with network access before merging and record which checks were run
  where.
- **Do not touch past specs**: `specs/0002-uv-workspace/` and the other existing
  specifications keep their old names on purpose.
- **Version**: `VERSION` is not changed by this feature.
