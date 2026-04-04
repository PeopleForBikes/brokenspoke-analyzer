# Requirements Document: Dataset Cache

## Introduction

The brokenspoke-analyzer requires a caching mechanism to store datasets fetched
from multiple external sources. Currently, each analysis run fetches raw data
from US Census blocks, LODES employment data, and OpenStreetMap (OSM) via HTTPS,
which is inefficient for repeated analyses and creates unnecessary load on
external services.

This feature implements a file-based cache that stores downloaded datasets
locally, reducing redundant network requests and enabling faster analysis
iterations. The cache must support two operational modes: read-only for parallel
cloud pipeline execution (up to 1000 concurrent workers) and read-write for
sequential local utility usage.

The scope includes:

- Download and storage of three data sources: US Census blocks, LODES employment
  data, and OSM data
- Cache directory management with platform-standard locations and custom path
  support
- CLI commands for cache inspection and cleanup
- Manual cache invalidation via CLI flags
- Download resilience with cleanup on failure
- Ability to bypass cache entirely when needed

Out of scope:

- Automatic staleness detection (future enhancement)
- Distributed cache coordination
- Database ingestion logic (handled downstream in existing pipeline)

## Glossary

- **Bypass Mode**: A mode activated by the `--no-cache` global flag in which the
  `CacheManager` is skipped entirely and data is downloaded directly to the
  run's input directory.
- **Cache Bypass**: Direct download to input directory without storing in cache
- **Cache Hit**: A condition where all expected files for a given source/version
  combination are present and pass integrity checks in the cache directory.
- **Cache Miss**: A condition where one or more expected files are absent or
  fail integrity checks, triggering a download.
- **Cache**: Local file-based storage for downloaded datasets. Resolved at
  runtime via `platformdirs.user_cache_dir"brokenspoke-analyzer")` unless
  overridden by the `--cache-dir` CLI flag.
- **Dataset Version**: Temporal identifier for cached data (year for
  census/lodes, creation date for OSM)
- **Input Directory**: The per-run working directory where the
  brokenspoke-analyzer expects its input files to be located before execution
  begins.
- **Invalidation**: Removal of cached data to force fresh downloads
- **OSM Non-Overwrite Policy**: A hard rule that existing OSM data is never
  automatically overwritten. If `osm/latest/` contains data, the download is
  skipped and a warning is logged regardless of cache mode.
- **Read-Only Mode**: An operating mode automatically engaged when `os.access`
  reports the cache directory is not writable (e.g., a pre-populated read-only
  mount in a CI/cloud pipeline). Downloads are prohibited; a cache miss causes
  immediate failure.
- **Read-Write Mode**: Cache state where downloads and updates are permitted
  (sequential usage). This is the default operating mode when the cache
  directory is writable, as determined by `os.access(cache_dir, os.W_OK)`.
  Downloads are permitted and results are persisted.
- **Source Adapter**: A pluggable component, subclassing `SourceAdapter`,
  responsible for downloading and validating one data source (Census, LODES, or
  OSM).
- **Source Key**: A short, stable identifier for a data source used as the
  top-level subdirectory name (e.g., `census`, `lodes`, `osm`).
- **Source**: One of the data providers (census, lodes, osm, or future sources)
- **Storage Backend**: The abstraction layer (wrapping `obstore`) that isolates
  all filesystem I/O, enabling future migration to cloud storage.
- **Version Slug**: A string appended to the source key to form the versioned
  cache path (e.g., `2023` in `census/2023/`). OSM uses the fixed slug `latest`.

## Requirements

### Requirement 1: Cache Storage

**User Story:** As a developer, I want datasets to be stored locally after
download, so that subsequent analyses don't require redundant network requests.

#### Acceptance Criteria

1. The system SHALL store downloaded files in a directory structure organized by
   source and version.
2. The system SHALL create the cache directory if it does not exist when in
   read-write mode.
3. The system SHALL use the `platformdirs` library to auto-detect
   platform-standard cache locations:
   - Linux: `$XDG_CACHE_HOME/brokenspoke-analyzer` or
     `~/.cache/brokenspoke-analyzer`
   - macOS: `~/Library/Caches/brokenspoke-analyzer`
   - Windows: `%LOCALAPPDATA%\brokenspoke-analyzer\cache`
4. The system SHALL allow overriding the cache location via CLI argument
   `--cache-dir`.

### Requirement 2: Operational Modes

**User Story:** As a cloud pipeline operator, I want the cache to automatically
detect whether it should be read-only or read-write, so that parallel workers
cannot corrupt shared data.

#### Acceptance Criteria

1. The system SHALL determine cache mode by testing directory writability using
   `os.access(path, os.W_OK)`.
2. The system SHALL operate in read-only mode if the cache directory is not
   writable.
3. The system SHALL operate in read-write mode if the cache directory is
   writable.
4. The system SHALL fail with a clear error message if writability detection
   returns inconsistent results between checks.
5. The system SHALL raise an error if any write operation is attempted while in
   read-only mode.

### Requirement 3: Data Source Management

**User Story:** As an analyst, I want to cache data from multiple sources
independently, so that I can invalidate or update individual datasets without
affecting others.

#### Acceptance Criteria

1. The system SHALL support three distinct data sources: `census`, `lodes`, and
   `osm`.
2. The system SHALL organize cached files under
   `<cache-dir>/<source>/<version>/`.
3. The system SHALL use year-based versioning for census and lodes datasets.
4. The system SHALL use file creation date for OSM dataset versioning.
5. The system SHALL validate that all required files for a source/version exist
   before marking it as complete.
6. The system SHALL be designed to support additional data sources without
   modifying core cache logic (extensibility).

### Requirement 4: Cache Inspection

**User Story:** As a user, I want to query the cache location and contents, so
that I can verify what data is available.

#### Acceptance Criteria

1. The system SHALL provide a `cache dir` command that outputs the effective
   cache directory path.
2. The system SHALL report the custom cache path if `--cache-dir` was specified.
3. The system SHALL report the default platform path if no override was
   specified.

### Requirement 5: Cache Cleanup

**User Story:** As a user, I want to remove cached data selectively or entirely,
so that I can free disk space or force fresh downloads.

#### Acceptance Criteria

1. The system SHALL provide a `cache clean` command that removes all cached
   data.
2. The system SHALL provide a `cache clean <source>` command that removes only
   the specified source's data.
3. The system SHALL prompt for confirmation before deletion (unless `--yes` flag
   is provided).
4. The system SHALL report the total size and number of files deleted after
   completion.
5. The system SHALL provide a `--dry-run` flag that shows what would be deleted
   without performing deletion.
6. The system SHALL fail gracefully if the cache directory does not exist during
   cleanup.

### Requirement 6: Download Resilience

**User Story:** As a user, I want downloads to handle failures gracefully, so
that partial downloads don't corrupt the cache.

#### Acceptance Criteria

1. The system SHALL use the existing `aiohttp` library for HTTPS downloads.
2. The system SHALL use the existing `tenacity` library for retry management.
3. The system SHALL write downloads to a temporary file first, then move to
   final location on success.
4. The system SHALL remove any partial/temporary files if download fails.
5. The system SHALL raise an error if download fails after all retry attempts.
6. The system SHALL NOT resume partial downloads (cleanup and retry on failure).
7. WHEN fetched data is compressed (`.zip`, `.gz`, etc.), the system SHALL
   uncompressed it before copying it into the input dir, and the cache must only
   contain the uncompressed data.

### Requirement 7: Manual Invalidation

**User Story:** As a user, I want to force cache invalidation for specific
sources, so that I can fetch updated data without manual cache deletion.

#### Acceptance Criteria

1. The system SHALL accept a `--invalidate <source>` CLI flag to mark a source
   as stale.
2. The system SHALL delete the specified source's cached data before proceeding
   with analysis.
3. The system SHALL support multiple `--invalidate` flags for multiple sources.
4. The system SHALL treat `--invalidate all` as equivalent to `cache clean`.

### Requirement 8: Concurrency Safety

**User Story:** As a cloud operator, I want the cache to remain safe under high
concurrency, so that 1000 simultaneous workers don't corrupt data.

#### Acceptance Criteria

1. The operator SHALL use the appropriate flag `--cache-read-only` to trigger
   this mode.
2. The system SHALL NOT attempt any file writes in read-only mode.
3. The system SHALL log a warning if read-only mode is detected during
   operations that expect write access.
4. The system SHALL document that read-write mode is strictly for sequential
   usage only.

### Requirement 9: Cache Bypass

**User Story:** As a user, I want to disable caching entirely when needed, so
that I can download directly to the input directory without storing intermediate
files.

#### Acceptance Criteria

1. The system SHALL accept a `--no-cache` CLI flag to disable caching.
2. When `--no-cache` is specified, the system SHALL download data directly to
   the input data directory.
3. When `--no-cache` is specified, the system SHALL NOT store any files in the
   cache directory.
4. When `--no-cache` is specified, the system SHALL NOT attempt to read from the
   cache.
5. The `--no-cache` flag SHALL take precedence over all other cache-related
   flags.
6. The system SHALL log a warning when cache bypass is active to inform users of
   increased network usage.

### Requirement 10: Extensibility

**User Story:** As a developer, I want to add new data sources easily, so that
the cache system remains maintainable as requirements evolve.

#### Acceptance Criteria

1. The system SHALL define a source registration interface for adding new data
   sources.
2. The system SHALL isolate source-specific logic (URLs, versioning, file
   formats) from core cache logic.
3. The system SHALL support configuration-driven source definitions (e.g.,
   YAML/JSON config or Python registry).
4. The system SHALL validate that new sources conform to the expected cache
   structure before integration.
5. The system SHALL document the process for adding new data sources in the
   codebase.

### Requirement 11: Custom Cache Directory Override

**User Story:** As a CI/CD operator, I want to specify a custom cache directory
via a CLI flag so that I can point the brokenspoke-analyzer at a pre-populated,
shared cache volume.

#### Acceptance Criteria

1. The global flag `--cache-dir <path>` shall override the default
   `platformdirs` path for the duration of the command invocation.
2. When `--cache-dir` is provided, the system shall validate that the path
   exists or can be created; if neither is possible it shall exit with a
   non-zero status and a human-readable error message.
3. The resolved custom path shall be logged at `INFO` level.

### Requirement 11: OSM Non-Overwrite Policy

**User Story:** As an operator, I want OSM data to never be silently overwritten
by an automatic re-download so that I retain control over which OSM snapshot the
pipeline uses.

#### Acceptance Criteria

1. OSM data shall always be stored under `<cache_dir>/osm/latest/` regardless of
   when it was downloaded.
2. When `osm/latest/` contains one or more files, the system shall skip the
   download, log a `WARNING`-level message via `loguru` stating that existing
   OSM data was found and will be reused, and proceed with the cached data.
3. The system shall never delete, overwrite, or truncate any file under
   `osm/latest/` during a normal pipeline run.
4. The only supported mechanism to refresh OSM data is the
   `brokenspoke cache clean osm` CLI command (see Requirement 5).

### Requirement 12: Cache Hit / Miss Data Flow

**User Story:** As a developer, I want a well-defined, auditable data flow for
cache operations so that I can debug caching issues by reading log output.

#### Acceptance Criteria

1. On every `CacheManager.get()` call the system shall log at `DEBUG` level: the
   source key, version slug, and resolved cache path being checked.
2. On a cache hit the system shall log at `INFO` level:
   `"Cache hit: {source}/{version}"`.
3. On a cache miss in Read-Write mode the system shall log at `INFO` level:
   `"Cache miss: downloading {source}/{version}"`.
4. After a successful download and validation the system shall log at `INFO`
   level: `"Cached: {source}/{version} -> {final_path}"`.
5. After copying from cache to the Input Directory the system shall log at
   `DEBUG` level: `"Copied {source}/{version} to {input_dir}"`.

### Requirement 13: Source Adapter Extensibility

**User Story:** As a contributor, I want to add support for a new data source by
implementing a single class so that the caching system is easy to extend without
modifying core logic.

#### Acceptance Criteria

1. The system shall expose a `SourceAdapter` abstract base class in
   `brokenspoke_analyzer/core/cache/adapters.py` with the abstract methods
   `source_key`, `version_slug`, `expected_files`, `download`, and `validate`.
2. The system shall maintain a module-level registry (a
   `dict[str, type[SourceAdapter]]`) in
   `brokenspoke_analyzer/core/cache/registry.py` populated via a `@register`
   decorator.
3. Applying `@register` to a `SourceAdapter` subclass shall automatically add it
   to the registry; no other file shall need modification to make the adapter
   available to the `CacheManager`.
4. The `CacheManager` shall resolve adapters exclusively through the registry by
   source key string, raising `UnknownSourceError` for unrecognized keys.
5. All three built-in adapters (Census, LODES, OSM) shall be implemented using
   this pattern and registered in `brokenspoke_analyzer/core/cache/adapters.py`.

### Requirement 14: Download Integrity Validation

**User Story:** As a pipeline operator, I want downloaded files to be validated
before being added to the cache so that corrupted or incomplete downloads do not
poison the cache.

#### Acceptance Criteria

1. Each `SourceAdapter` shall implement a `validate(path: Path) -> None` method
   that raises `ValidationError` if the downloaded data is invalid.
2. Files shall only be moved from the Temp Cache to the Final Cache after
   `validate` returns without raising.
3. If `validate` raises, the temporary files shall be deleted and
   `CacheManager.get` shall re-raise `ValidationError` to the caller with the
   source/version context appended.
4. A minimum file-size check (configurable per adapter, defaulting to 1 byte)
   shall be included in every adapter's `validate` implementation.
