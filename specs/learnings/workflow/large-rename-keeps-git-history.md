---
title: Commit a large rename as moves only, so git keeps every file's history
date: 2026-11-20
updated: 2026-11-26
category: workflow
status: active
tags: [git, rename, history, git-mv, refactoring]
modules: [packages, docs/source]
spec: specs/0006-bna-namespace
related: [specs/0006-bna-namespace/findings.md]
superseded_by:
---

# Commit a large rename as moves only, so git keeps every file's history

## Context

Moving the workspace members from `packages/brokenspoke-analyzer-<member>/` to
`packages/<member>/src/bna/<member>/` and renaming the Sphinx API pages
(`specs/0006-bna-namespace/`): 144 files moved, and most of them also needed
content changes (imports, names).

## Symptom

Git stores no renames: it guesses them from content similarity (50% by default).
When moves and edits land in the same commit, small files fall under the
threshold. Here, diffing across the move and the edits at once
(`git diff -M --name-status c700cde~1 a7c57d2 -- docs/source/lib`) shows the
renamed `.rst` pages as `A`/`D` pairs instead of renames: their one changed line
(the module name) is most of the file. `git log --follow` and blame then stop at
the rename.

## What Did Not Work

- Staging everything and committing once: the 22 `.rst` pages, and other files
  short enough for the edits to dominate, lost their rename detection.

## Root Cause

Rename detection compares the deleted and added blobs of one commit. A pure move
is 100% similar; a moved file whose edits change more than half its content is,
to git, a deletion plus an unrelated new file.

## Solution

Two commits:

1. **Moves only**, done with `git mv` before any edit. `c700cde` is 144 renames,
   all `R100`: `git show --stat -M c700cde` reports
   `144 files changed, 0 insertions(+), 0 deletions(-)`.
2. **Everything else** (imports, configuration, docs) in the next commit
   (`a7c57d2`). That commit does not need to build on its own; say so in the
   first commit's message.

`git log --follow docs/source/lib/bna.lib.utils.rst` then reaches commits from
before the rename (`76a08d2`, #1175). Both commits were merged with #1292, using
"Rebase and merge": a squash merge would have folded them into one.

Practical points:

- `git mv <dir> <new>` renames the directory on disk, so untracked and ignored
  content moves too (e.g. the ignored OSMnx `cache/`, `.gitignore:30`, now in
  `packages/lib/cache`). Moving files _out_ of a directory one by one leaves the
  directory behind, holding only ignored files such as `__pycache__/`; delete it
  after checking.
- Keeping the moves staged and every edit unstaged turns the index into a
  ready-made moves-only commit. If everything gets staged together anyway, the
  split can be rebuilt without touching the working tree: save the index with
  `git write-tree`, `git read-tree HEAD`, stage only the moves with
  `git update-index --index-info` (old path removed, HEAD's blob added at the
  new path), commit, then `git read-tree <saved tree>` and commit the rest.
- Do not toggle files with `git stash -- <path>` in a partly staged rename: it
  removes a staged rename's new file from both the index and the disk
  (`specs/0006-bna-namespace/findings.md` §2.2).

## Prevention

For any change that moves many files, plan the moves-only commit first and check
it with `git diff --cached -M --stat` (expect `0 insertions(+), 0 deletions(-)`)
before committing, and `git log --follow` on a small moved file afterwards.
