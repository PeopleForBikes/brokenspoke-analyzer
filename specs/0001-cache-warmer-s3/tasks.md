# Tasks: Cache-Warmer S3

This file contains the ordered implementation tasks and verification steps to
add an `s3` subcommand to the cache-warmer utility. The goal is to stream
artifacts directly into an S3 bucket using the existing `BNADataStore` download
pipeline.

## Summary

- Implement `cache-warmer s3 --bucket <name>` that streams artifacts into S3 (no
  local writes).
- Reuse `brokenspoke_analyzer/core/datastore.py` download helpers by injecting
  an `obstore` S3 store into `BNADataStore.cache` at runtime.

## Tasks

- [ ] 1 — Extract `_run_downloads(bna_store, cache_only: bool)`
  - [ ] 1.1 — Move the current download loop from `utils/cache-warmer.py:main()`
        into a reusable async helper.
  - [ ] 1.2 — Implement signature:

    ```py
    async def _run_downloads(
      bna_store: BNADataStore,
      *,
      cache_only: bool = True,
      ) -> None
    ```

  - [ ] 1.3 — Ensure the helper creates and uses an `aiohttp.ClientSession`,
        iterates the same sources in the same order, and raises on first error.

- [ ] 2 — Convert `utils/cache-warmer.py` into a `typer` app
  - [ ] 2.1 — Add `app = typer.Typer()`.
  - [ ] 2.2 — Add `local` subcommand that constructs `BNADataStore` as today and
        calls `_run_downloads`.
  - [ ] 2.3 — Configure the CLI so that `uv run python utils/cache-warmer.py`
        with no subcommand displays the help screen and does not start warming.
  - [ ] 2.4 — Keep compatibility so the original behavior is preserved when a
        subcommand is explicitly provided.

- [ ] 3 — Implement `s3` subcommand
  - [ ] 3.1 — Add CLI: `cache-warmer s3 --bucket <bucket> [--mirror <mirror>]`.
  - [ ] 3.2 — Create an S3 `obstore` store via
        `exporter.create_s3_store(bucket)`.
  - [ ] 3.3 — Instantiate `BNADataStore(..., mirror=mirror)` and set
        `bna_store.cache = s3_store`.
  - [ ] 3.4 — Call `_run_downloads(bna_store, cache_only=True)`.

- [ ] 4 — Add per-artifact failure cleanup
  - [ ] 4.1 — Wrap the call that triggers a single artifact download (the
        `fetch_to_cache` invocation) with try/except in `_run_downloads` or a
        small wrapper.
  - [ ] 4.2 — On exception, compute the S3 key used for the artifact (same
        `path` passed to `fetch_to_cache`).
  - [ ] 4.3 — Remove partial objects using `obstore` cleanup APIs if available,
        and only use `boto3` as a documented fallback if obstore cannot delete
        the partially created object reliably.
  - [ ] 4.4 — Log the error (loguru/rich) and exit/raise.

- [ ] 5 — Checkpoint: validate CLI and runtime wiring
  - [ ] 5.1 — Confirm `cache-warmer local` and `cache-warmer s3` subcommands
        exist and parse expected options.
  - [ ] 5.2 — Confirm `BNADataStore.cache` can be reassigned to an S3-backed
        `obstore` store.
  - [ ] 5.3 — Review that `boto3` is not introduced unless required for cleanup,
        and document the fallback decision.

- [ ] 6 — Tests & verification
  - [ ] 6.1 — Add a `just` task `cache-warmer-s3` to invoke the script with
        `uv`.
  - [ ] 6.2 — Add automated tests or a documentable manual verification path for
        S3 upload completion, partial-object cleanup, and non-zero exit on
        failure.

## Verification commands

Export credentials and run the s3 warmer:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1
uv run python utils/cache-warmer.py s3 --bucket my-test-bucket
```

Check bucket keys:

```bash
aws s3 ls s3://my-test-bucket/ --recursive | head -n 50
```

Simulate failure test (manual): start the process and revoke credentials or send
SIGTERM mid-download, confirm partial key removed and process exit code != 0.

## Notes & decisions

- Prefer `obstore` for streaming uploads and cleanup.
- `boto3` SHALL NOT be used unless no other viable path exists for removing
  partially created S3 objects; if `boto3` is used, document the decision and
  the missing obstore capability.
- No `--prefix` support in this iteration; top-level prefixes come from
  `SourceAdapter.subpath`.
- No dry-run option in first iteration.

## Next steps (after tasks.md)

1. Implement `_run_downloads` and the `typer` subcommands in
   `utils/cache-warmer.py`.
2. Implement cleanup logic and test manually against a test bucket.
3. Add CI/integration test hooks if desired.
