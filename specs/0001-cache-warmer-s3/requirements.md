# Requirements: Cache-Warmer S3

## Purpose

Allow the existing `cache-warmer` utility to populate an AWS S3 bucket directly
from upstream sources (no local cache writes) so downstream processes can read
pre-warmed artifacts from S3.

## EARS Requirements

### Ubiquitous Requirements

- The system SHALL add a new `cache-warmer s3` capability to populate AWS S3
  directly from upstream artifact sources.
- The system SHALL reuse download logic in
  `brokenspoke_analyzer/core/datastore.py` and SHALL NOT reimplement source
  fetch logic.
- The system SHALL use `obstore` for object storage operations and SHALL rely on
  its default retry behavior.
- The system SHALL organize uploaded objects under top-level prefixes by data
  type:
  - `census/…`
  - `lodes/…`
  - `osm/…`
  - `state-speed-limits/…`
  - `city-speed-limits/…`
- The system SHALL log progress and errors using existing Rich/loguru
  conventions.
- The system SHALL work in local development, CI, and Docker contexts using only
  standard AWS environment variables.
- The system SHALL not support `--prefix` or a dry-run/preflight report in this
  first iteration.

### Event-Driven Requirements

- WHEN `cache-warmer s3` is invoked, the system SHALL require a `--bucket`
  argument and SHALL accept `--mirror` as an optional passthrough to existing
  mirror handling in the datastore.
- WHEN `cache-warmer` is invoked with no command, the system SHALL display the
  CLI help screen and SHALL not start warming data.
- WHEN an artifact is streamed from its original source, the system SHALL write
  it directly into S3 using `obstore`-compatible uploads without writing any
  local cache files.
- WHEN an artifact is uploaded to S3, the system SHALL use the key format
  `<data-type>/<filename>` (for example, `census/fips-12345.json`).
- WHEN an upload or download error occurs for an artifact, the system SHALL
  delete any partially created S3 object for that artifact, log the cause, and
  exit non-zero.

### State-Driven Requirements

- WHILE `cache-warmer s3` is running, the system SHALL stream each artifact
  sequentially and avoid local persistence.
- WHILE `BNADataStore.cache` is routed to an S3-backed `obstore` store, the
  system SHALL let `fetch_to_cache` write directly to S3.

## Traceable Requirements

- FR-1: The `cache-warmer s3` subcommand SHALL require `--bucket` and SHALL
  accept optional `--mirror`.
- FR-2: The system SHALL stream each artifact from source directly into S3 using
  `obstore`-compatible uploads and SHALL avoid local files.
- FR-3: The system SHALL write S3 objects using the key format
  `<data-type>/<filename>`.
- FR-4: The system SHALL use AWS credentials from environment variables:
  `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and optional
  `AWS_SESSION_TOKEN`.
- FR-5: On any error, the system SHALL delete partial S3 objects, log the cause,
  and exit non-zero.
- FR-6: The system SHALL log progress and errors using existing logging
  conventions.
- NFR-1: The system SHALL minimize changes to
  `brokenspoke_analyzer/core/datastore.py` and SHALL prefer assigning an
  S3-backed `obstore` store to `BNADataStore.cache` at runtime for the `s3`
  subcommand.
- NFR-2: The system SHALL keep operations asynchronous (asyncio) and sequential
  per artifact.
- NFR-3: The system SHALL work in local dev, CI, and Docker contexts without
  special configuration other than AWS environment variables.
- NFR-4: The system SHALL not implement dry-run or preflight reporting in this
  first iteration.

## Acceptance Criteria

- AC-1: WHEN `cache-warmer s3 --bucket my-bucket` is executed, the system SHALL
  upload the same set of artifacts as local warming under the expected prefixes
  without writing any local files.
- AC-2: WHEN a network failure is simulated mid-download, the system SHALL leave
  no partial object in S3 and SHALL exit non-zero with a clear error.
- AC-3: The system SHALL log each artifact upload completion and any errors.
- AC-4: The implementation SHALL reuse datastore download helpers and confine
  changes to the reviewed runtime behavior.

## Constraints & Assumptions

- C1: The system SHALL reuse all download/fetch logic from
  `brokenspoke_analyzer/core/datastore.py`.
- C2: The system SHALL prefer `obstore` for uploads and its default retry
  policy.
- A1: The system SHALL route `BNADataStore.cache` to an S3 `obstore` store (for
  example, `from_url("s3://bucket")`) during `s3` runs so `fetch_to_cache`
  writes directly to S3.

## Out-of-Scope (first iteration)

- Support for Cloudflare R2, GCS, or other storage backends.
- `--prefix` or configurable bucket prefixing.
- Dry-run or summary reports.
