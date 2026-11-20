# Findings: Shared `bna` Namespace for Workspace Members

Everything non-obvious learned while implementing this feature: behavior that
looks like a bug unless you know it is deliberate, traps in the libraries and
tools, and what worked. Each entry says what the rule is, how it was caught, and
what it cost.

Status: complete for tasks 1–11. Docker is denied in the implementation sandbox,
so a developer ran the Docker checks on their own machine on 2026-11-20:
`just docker-build` succeeded (installing the `bna_lib` and `bna_cli` wheels),
the image's `bna --help` lists the same commands and options as before, and with
the entrypoint overridden to `python`, `resources.files('bna.lib.scripts.sql')`
lists `clip_osm.sql`, `connectivity`, `features`, `prepare_tables.sql`,
`speed_tables.sql` and `stress`. Every other check ran in the sandbox.
`git log --follow` passes since the moves were committed on their own
(`9f4d632`). Keep it current as the code changes.

## 1. Behavior that does not survive a naive implementation

### 1.1 A stale distribution name broke every `bna` subcommand

`_version_callback` in `packages/cli/src/bna/cli/root.py` reads the version with
`metadata.version("<distribution name>")` inside the `--version` option
callback. Click runs option callbacks on every invocation (with `value=False`
when the flag is absent), and the lookup happens before the `if value:` check,
so after the rename to `bna-cli` every subcommand (`bna cache --help`,
`bna run-with compose …`) raised `PackageNotFoundError`. Only the root
`bna --help` still worked, because `--help` is eager and exits before other
callbacks run, and that was the only CLI behavior the test suite exercised.

The design listed the string-based _import_ lookups (`resources.files(...)`) but
not the string-based _distribution_ lookups; a search for import names does not
find `brokenspoke-analyzer-cli`. The fix is the name
(`metadata.version("bna-cli")`), plus two tests in
`packages/cli/tests/test_root.py`: `--version` output, and `cache --help`
exiting 0. With the old name restored both fail; with the fix both pass.

**Caught by**: the post-rewrite search for any remaining
`brokenspoke[-_]analyzer` string in `packages/`, then `uv run bna --version` and
`bna cache --help`.

**Cost**: would have shipped a CLI where every command fails while `just test`
stayed green (the only existing `bna` test, `test_help_lists_the_subcommands`,
calls the root `--help`).

## 2. Library and tooling traps

### 2.1 `git mv <dir>` carries ignored files; moving files out leaves the dir

`git mv packages/brokenspoke-analyzer-lib packages/lib` renames the directory on
disk, so untracked and ignored content (`.pytest_cache/`, `__pycache__/`, the
OSMnx `cache/` that `.gitignore:30` ignores) moves with it and no old directory
survives. Moving files _out_ of a directory one by one (task 2.3, flattening
`tests/brokenspoke_analyzer_<member>/`) leaves that directory on disk, holding
only `__pycache__/`.

**Caught by**: listing `packages/` after task 2; the design had predicted the
opposite (old member directories surviving) and was corrected.

**Cost**: none. The emptied folders are harmless (Python never imports from a
`__pycache__/` without the source next to it) but are clutter that reintroduces
the old names in `ls`, so they are deleted.

### 2.2 `git stash -- <path>` on a staged rename deletes the file

Stashing a single path whose index entry is the _new_ side of a staged rename
takes it out of both the working tree and the index (the rename turns into a
plain deletion), and `git stash pop --index` then refuses with "already exists
in index" because the stash's index tree holds every other staged file too.
Recovery that preserved the moves-only index:
`git checkout 'stash@{0}^2' -- <path>` (the stash's index commit, restoring the
pure-move version to index and disk), then
`git show 'stash@{0}:<path>' > <path>` (the edited working-tree version), then
`git stash drop`.

**Caught by**: an accidental `git stash` while testing a fix; the next command
failed with "No such file or directory".

**Cost**: none after recovery; the index was verified back at 143 renames, 0
insertions, 0 deletions. Use `sed`/copies, not stash, to toggle a fix in a
partially staged tree.

### 2.3 `bna.__path__` keeps `sys.path` entries as given

The portions in `bna.__path__` come from `sys.path` (the editable installs'
`.pth` files) and are not resolved, while a test's own location usually goes
through `Path(__file__).resolve()`. Comparing the two as strings fails when the
checkout is reached through a symlink, even though the namespace is fine.
`packages/lib/tests/test_namespace.py` resolves every portion before comparing.

**Caught by**: the spec review of the guardrail test.

**Cost**: none yet: no developer has used a symlinked checkout. The fixed test
passes when run through a symlink to the repository.

## 3. Method — what actually worked

### 3.1 Keep the moves staged and everything else unstaged

All 143 moves were done with `git mv` before any content edit, which
`git diff --cached -M --stat` reports as
`143 files changed, 0 insertions(+), 0 deletions(-)` (every rename at 100%
similarity). Leaving every later edit unstaged keeps the index as a ready-made
moves-only commit, without the implementation having to commit.
