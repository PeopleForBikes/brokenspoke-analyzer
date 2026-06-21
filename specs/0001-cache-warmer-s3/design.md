# Design: Cache-Warmer S3

This document describes the design to add an `s3` subcommand to the
`cache-warmer` utility so it can populate an AWS S3 bucket directly from
upstream sources (no local writes). It focuses on the CLI/registry pattern,
storage backend injection, streaming data flow, failure cleanup, and concrete
code changes.

## Goals

- Reuse all download logic in `brokenspoke_analyzer/core/datastore.py`.
- Stream downloads directly into S3 using `obstore` so no local files are
  created.
- Keep operations asynchronous and sequential per artifact.
- Fail fast on any error and remove partial objects.

## High-level Architecture

- CLI: `utils/cache-warmer.py` becomes a small `typer` app with two subcommands:
  - `local` — existing behavior (populate local user cache)
  - `s3` — new behavior (stream artifacts to S3)

- Datastore: `BNADataStore` remains the source of truth for download logic. For
  `s3` runs we will inject an S3-backed `obstore` store into the
  `BNADataStore.cache` attribute so existing `fetch_to_cache` /
  `fetch_from_source` methods write directly to S3 keys.

- Storage primitives:
  - Use `brokenspoke_analyzer.core.exporter.create_s3_store(bucket_name)`
    (already present) to create an `obstore` `ObjectStore` for the bucket.
  - For cleanup and bucket-specific operations (if needed) use
    `brokenspoke_analyzer.core.exporter.get_s3_bucket(bucket_name)` which
    returns a `boto3` Bucket instance.

## Data flow

1. Invoke `cache-warmer s3 --bucket my-bucket`.
2. CLI creates an `ObjectStore` for `s3://my-bucket` via `create_s3_store`.
3. Instantiate `BNADataStore` (any CacheType is acceptable) and replace
   `bna_store.cache` with the S3 `ObjectStore`.
4. For each SourceAdapter the existing code calls
   `fetch_from_source(session, source)` which internally computes
   `path = str(source.subpath / url.name)` (for example
   `census/tl_2020_06_tabblock20.zip`).
5. `fetch_to_cache` calls
   `self.cache.put_async(path, resp.content.iter_chunked(CHUNK_SIZE))` — because
   `self.cache` is an S3 `ObjectStore`, this streams the HTTP response directly
   into the S3 object with key `census/...`, satisfying the required top-level
   prefixes.
6. On success, proceed to next artifact; on error, perform cleanup and abort.

Notes:

- The `SourceAdapter.subpath` values (e.g., `census`, `lodes`, `osm`,
  `state_speed_limits`, `city_speed_limits`) already align with the required
  top-level prefixes; no extra mapping is necessary.

## Failure handling and cleanup

- Requirement: no partial objects remain on failure.
- Strategy:
  1. Wrap each call to `fetch_to_cache` in try/except.
  2. If an exception occurs during download or streaming, attempt to delete the
     partially created key.
     - Use `boto3` via `get_s3_bucket(bucket_name)` to delete the object
       (`bucket.Object(key).delete()`), because `obstore` implementations may
       expose different internals; exporter already exposes `get_s3_bucket` for
       such operations.
  3. Log the underlying error with `loguru`/`Rich` and exit non-zero.

Implementation details:

- Where possible rely on `obstore`'s (and underlying client) default retries; do
  not implement custom retry logic.

## Concurrency and performance

- Downloads will remain asynchronous but executed sequentially per artifact (the
  existing code structure already loops sequentially). This satisfies the
  requirement and keeps the implementation simple and predictable.

## Concrete changes (files & snippets)

### 1) `utils/cache-warmer.py`

- Convert the script into a `typer` app with two subcommands:
  - `local`: reuses the existing `main()` logic unchanged (writes to local
    cache)
  - `s3`: new subcommand that accepts `--bucket` and `--mirror` and streams
    artifacts to S3

- Key `s3` implementation sketch (pseudo):

```py
import typer
from brokenspoke_analyzer.core import exporter

app = typer.Typer()

@app.command()
def s3(bucket: str, mirror: str | None = None) -> None:
    # Create S3 obstore store and boto3 bucket
    s3_store = exporter.create_s3_store(bucket)
    s3_bucket = exporter.get_s3_bucket(bucket)

    # Create BNADataStore and inject the S3 store as the cache
    bna_store = datastore.BNADataStore(
        pathlib.Path(file_utils.get_user_cache_dir()),
        datastore.CacheType.USER_CACHE,
        mirror=mirror,
    )
    bna_store.cache = s3_store

    # Run the same download loop, passing cache_only=True
    asyncio.run(_run_downloads(bna_store, cache_only=True))

```

- `_run_downloads` is extracted from the existing `main()` body so both `local`
  and `s3` subcommands can reuse it. It should allow passing a `bna_store`
  instance and an `aiohttp.ClientSession` context.

### 2) Minimal additions to `datastore.py`

- No code changes required to `datastore.py` for the first iteration. The design
  relies on runtime injection of `bna_store.cache`.

### 3) Error cleanup helper

- Add a helper (in `utils/cache-warmer.py`) to delete partial S3 objects using
  `exporter.get_s3_bucket(bucket).Object(key).delete()`.

## Testing & Verification

- Manual integration test steps:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1
uv run python utils/cache-warmer.py s3 --bucket my-test-bucket
```

- Verify keys like `census/tl_2020_06_tabblock20.zip` exist in the bucket.
- Simulate failure by temporarily revoking credentials during a run and confirm
  partial objects are removed and process exits non-zero.

## Rationale & Alternatives

- Injection vs modifying `datastore`: injection keeps change surface small and
  is reversible. It preserves the single source of download logic.
- Using `obstore` for streaming keeps code consistent with other store
  interactions in the project; using `boto3` directly for cleanup covers any
  differences in `obstore` store behavior.

## Next code tasks (what to implement next)

1. Extract `_run_downloads(bna_store, cache_only)` helper from
   `utils/cache-warmer.py`.
2. Add `typer` subcommand wiring and implement `s3` as described.
3. Add cleanup logic using `boto3` on exceptions.
4. Add unit/integration verification steps to `tasks.md`.
