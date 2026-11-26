---
title:
  Click option callbacks run on every command, not only when the flag is given
date: 2026-11-20
updated: 2026-11-26
category: runtime-errors
status: active
tags: [typer, click, version, callback, cli, rename]
modules:
  [packages/cli/src/bna/cli/root.py, packages/cli/tests/test_root.py, bna.cli]
spec: specs/0006-bna-namespace
related: [specs/0006-bna-namespace/findings.md]
superseded_by:
---

# Click option callbacks run on every command, not only when the flag is given

## Context

Renaming the CLI distribution from `brokenspoke-analyzer-cli` to `bna-cli`
(`specs/0006-bna-namespace/`). The root `bna` app has a `--version` option whose
callback reads the installed version by distribution name
(`packages/cli/src/bna/cli/root.py:61-66`).

## Symptom

After the rename, every subcommand failed, including `bna cache --help` and
`bna run-with compose …`:

```text
PackageNotFoundError: No package metadata was found for brokenspoke-analyzer-cli
```

`bna --help` still worked, and so did the whole test suite: the only CLI test
invoked the root `--help`.

## What Did Not Work

- Searching for the old import names (`brokenspoke_analyzer_cli`): the lookup
  uses the distribution name (`brokenspoke-analyzer-cli`), a plain string that
  an import-name search does not match.
- Relying on `bna --help` as a smoke test: Click handles the root `--help`
  before any other option callback, so it never reaches the failing code.

## Root Cause

Click calls an option's callback on every invocation that goes through that
command, with `value=None` when the flag is absent. Checked with a minimal Typer
app (root callback with a `--version` option, two subcommands):

| Arguments       | Callback called with |
| --------------- | -------------------- |
| `--help`        | not called           |
| `sub`           | `None`               |
| `sub --help`    | `None`               |
| `--version sub` | `True`               |

`_version_callback` looked the version up _before_ checking the flag
(`packages/cli/src/bna/cli/root.py:63`, then `if value:` on line 64), so every
command paid for the lookup, and failed once the distribution name was stale.

## Solution

Fix the name: `metadata.version("bna-cli")`
(`packages/cli/src/bna/cli/root.py:63`), and add two tests in
`packages/cli/tests/test_root.py`:

- `test_version_reports_the_cli_distribution_version` (line 29): `--version`
  prints the `bna-cli` version.
- `test_subcommand_help_runs_the_root_callback` (line 36): `cache --help` exits
  0, which runs the root callbacks that the root `--help` skips.

With the old name restored, both tests fail; with the fix, both pass.

## Prevention

- Do the work of an option callback only when the flag is given: check `value`
  first. The follow-up #1294 (not yet merged when this was written) adds
  `bna.cli.common.version_callback`, which does exactly that, for `bna-batch`
  and `bna-cache-warmer`. `bna`'s own callback still looks the version up
  unconditionally.
- Test a CLI through a subcommand, not only through the root `--help`, so that
  root callbacks run.
- When renaming a distribution, search for its name as a string as well
  (`metadata.version(`, `metadata.distribution(`, `entry_points`), not only for
  the import name.
