# Implementation Plan: Dataset Cache

## Overview

This document outlines the implementation tasks for the dataset caching
subsystem (Feature #0000). The work is sequenced to establish core
infrastructure first (storage backend, cache manager), then build source
adapters, and finally integrate with the CLI and existing pipeline.

**Sequencing Rationale:**

1.  **Foundation First**: Storage backend and cache manager form the core
    infrastructure that everything else depends on.
2.  **Adapter Pattern**: Once the core is stable, implementing adapters becomes
    straightforward and testable in isolation.
3.  **CLI Last**: The CLI ties everything together and should be built once the
    underlying logic is verified.
4.  **Integration Final**: Connecting to the existing pipeline is the last step
    to ensure minimal disruption.

**Directory Structure Reference:**

- Specs: `specs/0000-cache/`
- Source Code: `brokenspoke_analyzer/core/cache/`
- Unit Tests: `tests/core/cache/`
- Integration Tests: `integration/tests/core/cache/`
- CLI: `brokenspoke_analyzer/cli/cache.py`

---

## Tasks

- [ ] 1. Project Setup & Infrastructure
  - [ ] 1.1 Create directory structure:
    - `specs/0000-cache/`
    - `brokenspoke_analyzer/core/cache/`
    - `brokenspoke_analyzer/core/cache/sources/`
    - `tests/core/cache/`
    - `integration/tests/core/cache/`
  - [ ] 1.2 Verify existing dependencies in `pyproject.toml`:
    - Check for `platformdirs`, `obstore`, `typer`, `loguru`, `aiohttp`,
      `tenacity`
    - Add missing packages only if not present
  - [ ] 1.3 Initialize `__init__.py` files in new directories
  - [ ] 1.4 Ensure `loguru` is available (assume pre-configured)
  - _Requirements: 1.3, 10.1, 10.3_

- [ ] 2. Storage Backend Implementation
  - [ ] 2.1 Define `StorageBackend` abstract base class with interface methods
        in `brokenspoke_analyzer/core/cache/storage.py`
  - [ ] 2.2 Implement `LocalStorageBackend` using
        `obstore.local.LocalFileSystem`
  - [ ] 2.3 Implement `put_object`, `get_object`, `exists`, `list_prefix`,
        `copy_to_local`, `delete_prefix`
  - [ ] 2.4 Write unit tests for `LocalStorageBackend` in
        `tests/core/cache/test_storage.py`
  - _Requirements: 1.3, 3.1, 10.2_

- [ ] 3. Cache Manager Core
  - [ ] 3.1 Define `CacheMode` enum (`ReadOnly`, `ReadWrite`) in
        `brokenspoke_analyzer/core/cache/enums.py`
  - [ ] 3.2 Implement `CacheManager` class in
        `brokenspoke_analyzer/core/cache/manager.py`
  - [ ] 3.3 Implement `detect_mode`, `get_or_fetch`, `clear_source`,
        `list_cache` methods
  - [ ] 3.4 Implement atomic staging logic (temp dir → move → copy to input)
  - [ ] 3.5 Handle `CacheMissError` for read-only mode
  - [ ] 3.6 Write unit tests for mode detection and basic operations in
        `tests/core/cache/test_manager.py`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.1,
    8.2, 8.3_

- [ ] 4. Source Adapter Framework
  - [ ] 4.1 Define `SourceAdapter` abstract base class in
        `brokenspoke_analyzer/core/cache/sources/base.py`
  - [ ] 4.2 Implement `SOURCE_REGISTRY` dictionary and `register_source`
        function in `brokenspoke_analyzer/core/cache/sources/registry.py`
  - [ ] 4.3 Implement `get_adapter` lookup function
  - [ ] 4.4 Write unit tests for registry pattern in
        `tests/core/cache/sources/test_registry.py`
  - _Requirements: 3.1, 3.6, 10.1, 10.2, 10.3_

- [ ] 5. Census Source Adapter
  - [ ] 5.1 Implement `CensusAdapter` class in
        `brokenspoke_analyzer/core/cache/sources/census.py`
  - [ ] 5.2 Implement `fetch` method using `aiohttp` and `tenacity`
  - [ ] 5.3 Implement `get_version_key` to extract year from filename/metadata
  - [ ] 5.4 Implement `validate` method (basic file existence/size check)
  - [ ] 5.5 Write unit tests for `CensusAdapter` in
        `tests/core/cache/sources/test_census.py` (mock HTTP responses)
  - _Requirements: 3.1, 3.2, 3.3, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 6. LODES Source Adapter
  - [ ] 6.1 Implement `LodesAdapter` class in
        `brokenspoke_analyzer/core/cache/sources/lodes.py`
  - [ ] 6.2 Implement `fetch` method using `aiohttp` and `tenacity`
  - [ ] 6.3 Implement `get_version_key` to extract year from filename/metadata
  - [ ] 6.4 Implement `validate` method (basic file existence/size check)
  - [ ] 6.5 Write unit tests for `LodesAdapter` in
        `tests/core/cache/sources/test_lodes.py` (mock HTTP responses)
  - _Requirements: 3.1, 3.2, 3.3, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 7. OSM Source Adapter
  - [ ] 7.1 Implement `OsmAdapter` class in
        `brokenspoke_analyzer/core/cache/sources/osm.py`
  - [ ] 7.2 Implement `fetch` method using `aiohttp` and `tenacity`
  - [ ] 7.3 Implement `get_version_key` returning "latest"
  - [ ] 7.4 Implement skip logic: check if `osm/latest/` exists before
        downloading
  - [ ] 7.5 Implement `validate` method (check magic bytes/header)
  - [ ] 7.6 Log warning when OSM data is skipped
  - [ ] 7.7 Write unit tests for `OsmAdapter` in
        `tests/core/cache/sources/test_osm.py` (skip behavior)
  - _Requirements: 3.1, 3.2, 3.4, 6.1, 6.2, 6.3, 6.4, 6.5, 8.4_

- [ ] 8. CLI Integration
  - [ ] 8.1 Create `brokenspoke_analyzer/cli/cache.py` with `typer.Typer()`
        subcommand group
  - [ ] 8.2 Implement `cache dir` command
  - [ ] 8.3 Implement `cache clean` command with `--source`, `--dry-run`,
        `--yes` flags
  - [ ] 8.4 Add `--cache-dir` global flag for cache path override
  - [ ] 8.5 Add `--no-cache` global flag to disable caching
  - [ ] 8.6 Use `typer` path validation for `--cache-dir` (writable check)
  - [ ] 8.7 Write integration tests for CLI commands in
        `integration/tests/cli/test_cache.py`
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.1, 9.2, 9.3,
    9.4, 9.5, 9.6_

- [ ] 9. Checkpoint - Core Functionality Verification
  - [ ] 9.1 Verify all three adapters can fetch and cache data in read-write
        mode
  - [ ] 9.2 Verify OSM skip behavior works correctly
  - [ ] 9.3 Verify cache clean commands work for all sources
  - [ ] 9.4 Verify `--no-cache` bypass works correctly
  - [ ] 9.5 Run full integration test suite
  - _Requirements: All requirements verified_

- [ ] 10. Pipeline Integration
  - [ ] 10.1 Modify existing data fetching code to use
        `CacheManager.get_or_fetch`
  - [ ] 10.2 Handle `CacheMissError` in pipeline (fail fast with clear message)
  - [ ] 10.3 Add logging throughout pipeline integration points
  - [ ] 10.4 Test with real data sources (small subset first)
  - _Requirements: 2.5, 8.1, 8.2, 8.3, 8.4_

- [ ] 11. Documentation
  - [ ] 11.1 Write module docstrings for all new modules (`manager.py`,
        `storage.py`, `sources/*.py`, `cli/cache.py`)
  - [ ] 11.2 Document process for adding new data sources in
        `brokenspoke_analyzer/core/cache/sources/README.md` (internal doc)
  - [ ] 11.3 Update main project documentation (if applicable) with cache
        feature overview
  - [ ] 11.4 Ensure all public classes and methods have comprehensive docstrings
  - _Requirements: 10.5_

- [ ] 12. Code Review & Cleanup
  - [ ] 12.1 Conduct peer code review for all modules
  - [ ] 12.2 Address review feedback
  - [ ] 12.3 Remove debug logging and temporary code
  - [ ] 12.4 Ensure consistent error messages across all modules
  - [ ] 12.5 Final linting and formatting check (ruff, black)
  - _Requirements: All requirements_

## Notes

### Implementation Guidance

1.  **Async/Await**: All download operations should use `async/await` patterns.
    The `CacheManager` should expose both sync and async interfaces if the
    existing pipeline uses synchronous code.

2.  **Error Messages**: All error messages should be user-facing and actionable.
    Example:

    ```python
    raise CacheMissError(
        f"Required data '{source}' not found in read-only cache. "
        f"Please pre-populate the cache or run with --no-cache."
    )
    ```

3.  **Logging Levels**:
    - `DEBUG`: Internal state, path resolutions
    - `INFO`: Successful operations, cache hits/misses
    - `WARNING`: OSM skip, fallback behaviors
    - `ERROR`: Failures, exceptions

4.  **Large File Handling**: For OSM (75GB), ensure streaming is used
    throughout. Do not load entire files into memory.

5.  **Temporary Files**: Always clean up temp directories on failure. Use
    `try/finally` or context managers.

### Warnings

- ⚠️ **Read-Write Mode**: Never run multiple processes in read-write mode
  simultaneously. This is a documented limitation.
- ⚠️ **OSM Size**: Test with smaller subsets before running full 75GB downloads.
- ⚠️ **Network**: Ensure retry logic (`tenacity`) is configured appropriately
  for large files (longer timeouts).

### Dependencies Checklist

| Package        | Purpose                    | Action           |
| -------------- | -------------------------- | ---------------- |
| `platformdirs` | Cache directory resolution | Check if present |
| `obstore`      | Storage abstraction        | Check if present |
| `aiohttp`      | HTTP downloads             | Check if present |
| `tenacity`     | Retry logic                | Check if present |
| `typer`        | CLI framework              | Check if present |
| `loguru`       | Logging                    | Assume present   |

### Future Enhancements (Not in Scope)

- Automatic staleness detection (check source update frequency)
- Checksum verification (SHA256) for all sources
- Cloud storage backend implementation
- Cache size limits and eviction policies
- Parallel downloads for multiple sources
