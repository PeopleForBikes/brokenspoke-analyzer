# Deviations: uv Workspace Restructuring

Tracks: PeopleForBikes/brokenspoke-analyzer#1143

## Purpose

This document records every place where the implementation departs from
`requirements.md`, `design.md` or `tasks.md`, and why. It is the delta between
the specification as authored and the repository as built.

Deviations fall into three kinds:

- **Stale fact** — the spec described the repository as it was believed to be,
  and reality differed.
- **Spec conflict** — two spec documents disagreed and one reading had to win.
- **Gap** — the spec did not cover something the restructuring forced a decision
  on.

## Summary

| #   | Kind          | Area          | Deviation                                                          |
| :-- | :------------ | :------------ | :----------------------------------------------------------------- |
| 1   | Stale fact    | Versioning    | Shared version is `3.2.4`, not `3.1.1`                             |
| 2   | Spec conflict | Versioning    | Root declares `dynamic = ["version"]`, not a static literal        |
| 3   | Gap           | Architecture  | The library imported from the CLI; `common.py` had to be split     |
| 4   | Gap           | Architecture  | Typer `Annotated` aliases in `core/compute.py` became plain types  |
| 5   | Stale fact    | Architecture  | `pyrosm/` does not exist; its config exclusions were dropped       |
| 6   | Spec conflict | Architecture  | The lib sub-layout follows `design.md`'s diagram (partial flatten) |
| 7   | Gap           | Packaging     | Concrete dependency split, including three unresolved cases        |
| 8   | Stale fact    | Tests         | The duplicated `tests/core/` tree did not exist                    |
| 9   | Gap           | Tests         | pytest/coverage config lives at the root _and_ per member          |
| 10  | Gap           | Tooling       | ruff now lints tests, and needs explicit first-party configuration |
| 11  | Gap           | Tooling       | `main.py` came back as `__main__.py`                               |
| 12  | Gap           | Tooling       | `.gitignore`'s `lib/` pattern hid `docs/source/lib/`               |
| 13  | Gap           | Docker        | `uv export` needs `--all-packages --no-emit-workspace`             |
| 14  | Stale fact    | CI            | The external reusable workflows need no workaround                 |
| 15  | Gap           | Documentation | Sphinx needed `suppress_warnings` and one docstring fix            |
| 16  | Gap           | Packaging     | Member sdists do not contain `VERSION`                             |

## Details

### 1. The shared version is `3.2.4`, not `3.1.1`

`design.md` ("Shared version source") and `tasks.md` (task 1) both name `3.1.1`
as the current version. The repository was at `3.2.4` when the work started, so
the root `VERSION` file was seeded with `3.2.4`.

No impact beyond the literal.

### 2. The root declares `dynamic = ["version"]`

`design.md`'s workspace root snippet keeps a static `version = "3.1.1"` "for
tools reading root metadata", while Requirement 4.2 states that the root and
both members "SHALL each declare `dynamic = ["version"]`".

Requirement 4.2 won: the root carries `dynamic = ["version"]` with
`[tool.hatch.version] path = "VERSION"`. Keeping a static literal at the root
would have re-introduced exactly the second version location that Requirement
4.1 forbids.

### 3. The library imported from the CLI

**Not covered by any spec document.** Three modules that `requirements.md` 2.1
assigns to the library imported `brokenspoke_analyzer.cli.common`:

- `core/compute.py`
- `core/ingestor.py`
- `core/datastore.py`

That is a `lib` → `cli` cycle, which breaks Correctness Property 4 ("no cyclic
or accidental cross-member imports from lib into cli") and would have forced
`brokenspoke-analyzer-lib` to depend on `typer`, breaking Requirement 2.4.

`common.py` was therefore split. The four values both sides need moved to
`brokenspoke_analyzer_lib.constant`:

- `DEFAULT_BUFFER`
- `DEFAULT_CITY_FIPS_CODE`
- `DEFAULT_COMPUTE_PARTS`
- `DEFAULT_MAX_TRIP_DISTANCE`

`brokenspoke_analyzer_cli.common` re-exports them under their existing names, so
no CLI call site changed. The remaining CLI-only defaults and every Typer
`Annotated` alias stayed in the CLI.

### 4. Typer annotations in `core/compute.py` became plain types

Consequence of deviation 3. `compute.all_` and `compute.parts` annotated their
parameters with the CLI's Typer aliases (`common.DatabaseURL`, `common.Buffer`,
`common.MaxTripDistance`, `common.ComputeParts`). These are plain library
functions, never registered as Typer commands — the actual commands are declared
in `brokenspoke_analyzer_cli.compute` with their own annotations — so the Typer
metadata was inert. They are now `str`, `int`, `int` and
`list[constant.ComputePart] | None`.

Verified as behaviour-preserving: the help text of all 15 `bna` command and
subcommand screens is byte-identical before and after, once cwd-derived default
paths are normalised.

### 5. `pyrosm/` does not exist

`design.md`'s architecture diagram lists a `pyrosm/` package under the library,
and `tasks.md` 2.2 repeats it. No such directory is tracked in the repository —
`pyrosm` is only consumed as a third-party dependency.

Accordingly, the `pyrosm` entries were dropped from `[tool.ruff] extend-exclude`
and `[tool.ty.src] exclude`, and from the coverage `omit` list, rather than
being rewritten to a `packages/...` path.

### 6. The library sub-layout follows the design diagram

`requirements.md` 2.1 reads as though everything lands directly under
`brokenspoke_analyzer_lib/`, while `design.md`'s diagram keeps a `core/`
subpackage alongside top-level modules. `tasks.md` 2.2 offers both and asks to
"confirm final sub-layout matches `design.md`'s Architecture diagram".

The diagram won. Final layout:

```text
brokenspoke_analyzer_lib/
├── constant.py         # was core/constant.py
├── datastore.py        # was core/datastore.py
├── file_utils.py       # was core/file_utils.py
├── utils.py            # was core/utils.py
├── database/           # was core/database/
├── scripts/            # was brokenspoke_analyzer/scripts/
└── core/               # pipeline modules only
    ├── analysis.py
    ├── compute.py
    ├── datasource.py
    ├── downloader.py
    ├── exporter.py
    ├── ingestor.py
    └── runner.py
```

### 7. Dependency split

`design.md` left three cases open. Resolved by inspecting actual imports:

| Dependency                       | Placement | Reason                                              |
| :------------------------------- | :-------- | :-------------------------------------------------- |
| `rich`                           | cli       | Imported only by CLI modules (`rich.console`, etc.) |
| `pycountry`                      | cli       | Imported only by `brokenspoke_analyzer_cli`         |
| `typer`                          | cli       | As specified                                        |
| `aiohttp`, `geopandas`, `loguru` | both      | Imported directly by both members                   |
| `us`                             | lib       | Imported by `core/analysis.py`                      |

`python-dotenv` and `tenacity` were declared but not imported anywhere in either
member; they have since been removed from `brokenspoke-analyzer-lib`'s
dependencies.

`pygris` appears in `CLAUDE.md`'s prose but was neither a declared dependency
nor an import; it was a stale entry in the local virtualenv and is gone after
the re-sync.

### 8. The duplicated test tree did not exist

`design.md` ("Test layout") and `tasks.md` 2.3 describe consolidating two
overlapping trees, `tests/brokenspoke_analyzer/core/` and `tests/core/cache/`.
Only the first contained tracked sources; `tests/core/` held nothing but stale
`__pycache__` artefacts from a removed feature branch. There was no duplication
to resolve.

What actually moved:

| Before                                             | After                                                                                    |
| :------------------------------------------------- | :--------------------------------------------------------------------------------------- |
| `tests/brokenspoke_analyzer/core/test_analysis.py` | `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/core/test_analysis.py` |
| `tests/test_cache_warmer.py`                       | `packages/brokenspoke-analyzer-lib/tests/brokenspoke_analyzer_lib/test_datastore.py`     |
| `tests/test_brokenspoke_analyzer.py`               | deleted                                                                                  |
| `tests/__init__.py`                                | deleted                                                                                  |

`test_cache_warmer.py` was renamed because it exercises
`brokenspoke_analyzer_lib.datastore`, not the `utils/cache-warmer.py` script;
its old name no longer mapped to anything, and Requirement 6.2 requires the test
tree to mirror `src/`.

`test_brokenspoke_analyzer.py` contained only `assert True`. Requirement 3.5
requires the CLI to have its own test suite, so it was replaced by
`packages/brokenspoke-analyzer-cli/tests/brokenspoke_analyzer_cli/test_root.py`,
which asserts that `bna --help` exits cleanly and advertises every pipeline
stage.

### 9. pytest and coverage configuration is duplicated

`design.md` places `[tool.pytest.ini_options]` in each member's
`pyproject.toml`, which satisfies Requirement 6.3 (standalone runs). It does not
satisfy Requirement 6.4, which wants one root `just test` with combined
coverage: pytest resolves a single `configfile`, so the root needs its own
section with `testpaths` pointing at both members.

Both now exist. The markers list and `addopts` are duplicated across the three
files — a known maintenance cost, accepted because no single-config alternative
satisfies 6.3 and 6.4 together.

### 10. ruff configuration

Two changes beyond a path rewrite:

- **First-party detection.** With the packages under `packages/*/src`, neither
  isort nor ruff auto-detects them, and the two tools disagreed about import
  grouping (16 `I001` errors). Both are now told explicitly: `known_first_party`
  for isort, `[tool.ruff] src` plus `[tool.ruff.lint.isort] known-first-party`
  for ruff.
- **Test trees are now linted.** Requirement 7.4 asks that linting cover both
  members' source _and test_ trees; previously ruff only saw `src` and `utils`.
  Turning it on surfaced 36 pre-existing findings, so a
  `[tool.ruff.lint.per-file-ignores]` block for `**/tests/**` was added covering
  the conventional test exemptions (`S101`, `D101`–`D107`, `ANN201`, `PLR2004`,
  `PYI034`, `T201`). One genuine finding (`TC003`) was fixed instead.

### 11. `main.py` came back as `__main__.py`

`tasks.md` 3.2 says to remove `brokenspoke_analyzer/main.py`. It was, but the
tracked `.vscode/launch.json` used it as its debug `program`, and
`.github/CONTRIBUTING.md` documents that debugging flow — Requirement 7.6
requires the VS Code workflow to keep working unchanged.

The equivalent entry point is now
`packages/brokenspoke-analyzer-cli/src/brokenspoke_analyzer_cli/__main__.py`,
and `launch.json` uses `"module": "brokenspoke_analyzer_cli"` instead of a file
path. This also restores `python -m brokenspoke_analyzer_cli`.

### 12. `.gitignore` hid the new documentation directory

Not anticipated anywhere. `.gitignore` carried an unanchored `lib/` pattern
(intended for setuptools build output at the root), which silently ignored the
new `docs/source/lib/` directory required by Requirement 5.2.

`lib/` and `lib64/` are now anchored as `/lib/` and `/lib64/`. `build/` was
deliberately left unanchored, because `docs/build/` relies on it.

### 13. Docker needs `uv export --all-packages`

`design.md`'s Dockerfile section covers `uv build` but assumes the `uv export`
step "still works". It does not: against a virtual root, a plain `uv export`
resolves the root project's own dependencies, which are empty, and produces a
requirements file with zero packages.

The builder stage now runs:

```sh
uv export --all-packages --no-emit-workspace ...
```

`--all-packages` takes the union of both members' runtime dependencies (63
packages) and `--no-emit-workspace` keeps the members themselves out of the
requirements file, since they are installed from the wheels built alongside.

The main stage installs both wheels in a single `pip install` invocation so the
`brokenspoke-analyzer-cli` → `brokenspoke-analyzer-lib` dependency resolves
locally. `.dockerignore` also gained `packages/*/tests`, which the existing
root-anchored `tests` entry no longer matched.

### 14. The external reusable workflows need no workaround

`design.md`'s Error Handling section anticipates that `PeopleForBikes/.github`'s
`ci-python-uv.yml` and `release-python-uv.yml` may break against a virtual root,
and `tasks.md` 8 budgets for a temporary local workaround.

Both workflows were read. Neither invokes `uv build` or `uv publish`; they only
call `uv sync`, `uv lock --check` and `just` recipes (`lint-md`, `lint-python`,
`docs`, `test`). They work unchanged. **No workaround was added, and the
separately tracked shared-workflow issue is not a blocker for this feature.**

The only CI change was in this repository's own `release.yaml`, whose
`release-dist` job ran a bare `uv build --sdist --wheel`. That does fail at a
virtual root, and is now `uv build --all-packages --sdist --wheel`.

### 15. Sphinx needed two additional changes

`docs/` is built with `-W` (warnings as errors). Adding the `automodule` pages
required by Requirement 5.2 made autodoc import the packages for the first time,
surfacing four warnings that no page had previously triggered:

- One malformed bullet list in `core/datasource.py`'s
  `OSMAdapter.map_region_name` docstring — fixed at the source.
- Three from `obstore`'s Rust-backed re-exports, whose annotations reference
  types that are not importable at build time. Not actionable from this
  repository, so `suppress_warnings` in `conf.py` now lists
  `sphinx_autodoc_typehints.forward_reference` and
  `sphinx_autodoc_typehints.guarded_import`, keeping `-W` in force for
  everything else.

`conf.py` also reads `metadata.version("brokenspoke-analyzer-cli")`, per
`design.md`. The user-visible `bna --version` string still reads
`brokenspoke-analyzer version: <x.y.z>`, so no CLI output changed.

### 16. Member sdists do not contain `VERSION`

`[tool.hatch.version] path = "../../VERSION"` resolves correctly for wheels and
for sdist _metadata_ — both members' `PKG-INFO` report the right version — but
hatchling cannot include a file living outside the project root in an sdist.
Rebuilding a wheel from a published sdist would therefore fail.

Publishing to PyPI is explicitly out of scope (`requirements.md`, Out of Scope),
and `release.yaml` only attaches artefacts to a GitHub release, so this is inert
today. It must be resolved before any member is published independently — most
likely by switching `[tool.hatch.version]` to a `hatch-vcs` git-tag source,
which `requirements.md` 4.1 already allows.

## Verification status

Everything in `tasks.md` was completed. All items requiring verification outside
the implementation sandbox — **Task 8.1** (CI green on the PR) and **Task 10**
(the full manual verification pass, including the dev container round-trip and
an `integration/` spot-check) — have since been confirmed by the user outside
the sandbox.

`just lint-sql` and `just lint-md` could not be invoked through `just` in the
implementation sandbox (sqlfluff walks parent directories to `/`; npm could not
write to `~/.npm`). Both were later confirmed outside the sandbox.

**Task 6.1** (Docker builds and runs) was verified outside the implementation
sandbox via `just docker-build-devcontainer` (the `dev` target) followed by
`just docker-prepare-all`, which was retargeted from `:latest` to `:dev` so it
unambiguously exercises the image built from this branch rather than whatever
`:latest` happens to resolve to locally (a real ambiguity the original recipe
had). `dev` shares the `builder`/`main` stages with the plain `docker-build`
target, so this exercises the same `uv export --all-packages`/two-wheel-install
path described in deviation 13. Plain `just docker-build` (`:latest`) itself was
not separately re-run.
