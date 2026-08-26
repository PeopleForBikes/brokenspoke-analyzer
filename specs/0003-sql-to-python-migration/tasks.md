# Tasks: SQL-to-Python Migration of the BNA Pipeline

This file contains the ordered implementation plan for replacing
`brokenspoke_analyzer/scripts/sql/**` and the PostGIS/pgRouting runtime with
a pure-Python pipeline, per `requirements.md` (WHAT) and `design.md` (HOW).

## Status

APPROVED. Depends on `requirements.md` (status: APPROVED) and `design.md`
(status: APPROVED).

## Overview

This is a big-bang rewrite (requirements.md §1): implemented as one body of
work, validated once end-to-end, not shipped stage-by-stage behind a runtime
toggle. Task ordering nonetheless follows the pipeline's own data
dependencies — `ingest → features → stress → network → scoring → export` —
because each stage's unit tests need the previous stage's output shape to
exist. The routing-engine benchmark spike (design.md §3.4) is sequenced
before `network.py` since it determines that stage's implementation, not
after.

**Pre-implementation gate** (requirements.md §7.3, blocking — not a task in
this plan): every `XS`/`S`/`M` `test_size` city in `integration/
e2e-cities.csv` must have a checked-in `results/**` baseline before task 1
starts. Do not begin implementation until this is confirmed. Valencia,
Spain (`XL`) is not required — it takes too long to run and is not part of
the automated corpus (below).

**Validation corpus during iteration**: use only `integration/e2e-cities-XS.csv`
and `integration/e2e-cities-S.csv` cities (design.md §5) for all per-task
verification below. The automated pre-ship gate (task 9/10) uses
`integration/e2e-cities.csv` restricted to `XS`/`S`/`M` `test_size` rows.
`L`/`XL`/`XXL` cities (Valencia, Washington DC) are excluded from all
automated runs in this plan — they take hours per city with the current
implementation. Washington DC is left for maintainers to validate manually
after the migration ships (its `results/**` baseline is still required by
the pre-implementation gate above, for that manual comparison); Valencia is
excluded from validation entirely for now (no baseline required, no manual
follow-up planned in this document).

**`prepare` stays as-is**: the `prepare` stage works well today and is not
being rewritten. `ingest.py` (task 3) is a consumer of `prepare`'s existing
file outputs (OSM extract, boundary, census blocks, jobs/speed CSVs), not a
replacement for any part of it — see task 3.0.

## Tasks

- [ ] 1. Benchmark spike: routing/reachability engine (design.md §3.4)
  - [ ] 1.1 Write a throwaway spike script (not shipped, e.g.
        `utils/spike_routing_benchmark.py`) that builds a CSR adjacency
        matrix for a small synthetic graph and for one real corpus city.
  - [ ] 1.2 Run reachability with both `scipy.sparse.csgraph.dijkstra`
        (`indices=[source], limit=cutoff`) and
        `networkx.single_source_dijkstra` with `cutoff`, on the same input,
        for the 3 cities named in design.md §3.4 (one XS, one S/M, and
        Washington DC for the perf ceiling check).
  - [ ] 1.3 Confirm numerically identical reachable-sets between the two
        approaches (validates CSR construction, not just algorithm choice).
  - [ ] 1.4 Record wall-clock time and peak memory for both approaches on
        Washington DC specifically (NFR-PERF-1's binding constraint).
  - [ ] 1.5 Update design.md §3.3 with the measured result: confirm
        `scipy.sparse.csgraph.dijkstra`, or record the fallback decision if
        it underperforms. Delete the spike script once §3.3 is updated.
  - _Requirements: FR-NET-1, FR-NET-2, FR-NET-3, NFR-PERF-1_

- [ ] 2. Scaffold `core/pipeline/` package (design.md §7)
  - [ ] 2.1 Create `brokenspoke_analyzer/core/pipeline/__init__.py`.
  - [ ] 2.2 Create `brokenspoke_analyzer/core/pipeline/errors.py` with
        `IngestError`, `InsufficientDataError`, `ReachabilityError`
        (design.md §9).
  - [ ] 2.3 Create `brokenspoke_analyzer/core/pipeline/config.py` and move
        `Tolerance`, `PathConstraint`, `BlockRoad`, `Score`, `Access` from
        `core/compute.py` into it unchanged (requirements.md §7 open
        question #2 — these remain the single source of truth for runtime
        constants).
  - [ ] 2.4 Create empty `tests/brokenspoke_analyzer/core/pipeline/` mirror
        directory with `test_ingest.py`, `test_features.py`,
        `test_stress.py`, `test_network.py`, `test_scoring.py` stubs.
  - _Requirements: NFR-TEST-1_

- [ ] 3. `ingest.py` — OSM parsing and routable graph (FR-ING-1, FR-ING-2)
  - [ ] 3.0 **`prepare` is unchanged and is the input boundary for
        `ingest`.** `prepare` (`analysis.py`/`downloader.py`/
        `datasource.py`) already works well and is explicitly out of scope
        for this migration (requirements.md §3) beyond feeding the new
        `ingest` step. `ingest.py` must consume the files `prepare` already
        produces on disk — the extracted city OSM PBF
        (`analysis.prepare_city_file`'s `pfb_osm_file` output, itself
        clipped by `osmium extract` from the region file using the
        boundary polygon), the boundary shapefile/GeoJSON
        (`retrieve_city_boundaries`), the census block shapefile/zip
        (`simulate_census_blocks` or the real Census download), and the
        jobs/speed CSVs — rather than re-downloading, re-extracting, or
        re-deriving any of that data itself. Confirm the exact `prepare`
        output paths/filenames by reading `analysis.py`/`downloader.py`/
        `datasource.py` before writing `ingest.py`, and treat them as a
        fixed contract.
  - [ ] 3.1 Read the OSM extract (PBF) produced by `prepare` (3.0) into
        GeoDataFrames of ways/nodes via `pyrosm` (design.md §3.1),
        preserving every tag currently consumed by
        `scripts/sql/features/*.sql` (highway class, cycleway/bike lane
        tags, lanes, maxspeed, oneway, width, surface, crossing/signal
        tags — enumerate exhaustively from the SQL, not from memory).
  - [ ] 3.2 Build topology (node sharing, direction, source/target vertex
        IDs) via `osmnx`, replacing `osm2pgrouting`'s two-config
        (highway + cycleway) graph build in `ingestor.py:import_osm_data`.
  - [ ] 3.3 Load the census blocks and jobs data already produced/fetched
        by `prepare` (3.0) into GeoDataFrames/DataFrames (replacing the
        `shp2pgsql` boundary/block import and the LODES CSV import path,
        which are the only things changing — the acquisition logic in
        `analysis.py` stays as-is per requirements.md §3).
  - [ ] 3.4 Raise `InsufficientDataError` on zero population, mirroring
        `ingestor.py`'s current `ValueError` (design.md §9).
  - [ ] 3.5 Unit tests: small synthetic OSM extract (2-5 ways) covering at
        least one tag from each category in 3.1; assert preserved tags and
        correct topology (source/target, direction) on a hand-verified
        expected graph.
  - _Requirements: FR-ING-1, FR-ING-2, NFR-TEST-1_

- [ ] 4. `features.py` — per-way attribute derivation (FR-FEAT-1)
  - [ ] 4.1 Transcribe each rule in `scripts/sql/features/*.sql` (bike
        infra, lane counts, functional class, one-way, speed limit, width,
        signalized, RRFB, stops, park/path flags, mileage, island
        detection) into vectorized `geopandas`/`pandas` column derivations,
        one function per attribute group (module-boundary model borrowed
        from `bikescore-bna`'s `attributes.py`, design.md §4).
  - [ ] 4.2 Confirm `features/streetlight/*.sql` is not ported (dead code,
        requirements.md §7 open question #6 — out of scope).
  - [ ] 4.3 Unit tests: one representative synthetic case per feature rule
        in 4.1, matching NFR-TEST-1's explicit per-rule coverage
        requirement (not just full-pipeline coverage).
  - _Requirements: FR-FEAT-1, FR-FEAT-2, NFR-TEST-1_

- [ ] 5. `stress.py` — stress classification (FR-STRESS-1)
  - [ ] 5.1 Transcribe `scripts/sql/stress/*.sql` rules into vectorized
        stress-rating derivation, covering every functional class
        (motorway/trunk, primary, secondary, tertiary, "lesser", link,
        living-street, track, path) plus intersection and one-way-reset
        adjustments.
  - [ ] 5.2 Reproduce our SQL's behavior exactly, including any bugs it
        contains — there is no deviation-tracking mechanism in this
        project (requirements.md §3); do not "fix" anything found here.
  - [ ] 5.3 Unit tests: one representative synthetic case per functional
        class in 5.1 (NFR-TEST-1).
  - _Requirements: FR-STRESS-1, NFR-TEST-1_

- [ ] 6. `network.py` — graph build & reachability (FR-NET-1/2/3)
  - [ ] 6.1 Build the directed, cost-weighted graph (link cost, turn
        angle/crossing cost) equivalent to `build_network.sql`, adapting
        `bikescore-bna`'s `segments_to_network()`/`build_graph()`/
        `_make_csr()` per design.md §4 (highest-reuse-value stage).
  - [ ] 6.2 Implement per-census-block reachability using the engine
        confirmed in task 1 (`scipy.sparse.csgraph.dijkstra` on the CSR
        matrix unless the spike overturned it), separately for the
        low-stress-only subgraph and the full (all-stress) subgraph —
        `PGR_DRIVINGDISTANCE` semantics: one-to-many, directed, distance
        cutoff from `PathConstraint`.
  - [ ] 6.3 Parallelize across independent batches of census blocks using
        `concurrent.futures.ProcessPoolExecutor` (design.md §6), matching
        the existing SQL's 8-way thread parallelism
        (`reachable_roads_*_calc.sql`'s `:thread_num`/`:thread_no`) —
        unless task 1's benchmark showed batched (not parallel)
        `dijkstra(indices=[...])` calls are already sufficient.
  - [ ] 6.4 Raise `ReachabilityError` on failure conditions mirroring the
        current SQL/pgRouting error paths (design.md §9).
  - [ ] 6.5 Unit tests: small synthetic graphs (5-10 nodes) with hand-
        computed expected reachable sets, independent of real city data.
  - _Requirements: FR-NET-1, FR-NET-2, FR-NET-3, NFR-PERF-1, NFR-TEST-1_

- [ ] 7. `scoring.py` — access, category, and overall scoring
  - [ ] 7.1 Implement per-destination-category access scoring
        (FR-ACCESS-1) for every category in requirements.md §2.5, using
        the low-stress-vs-high-stress reachability comparison logic from
        `connectivity/access_*.sql`, consuming `network.py`'s reachability
        output and `Tolerance`/`Access` from `core/pipeline/config.py`.
  - [ ] 7.2 Implement category score combination (FR-SCORE-1) using the
        exact weights from `Score` (`people=15, opportunity=20,
core_services=20, retail=15, recreation=15, transit=15`,
        requirements.md §7 open question #2) and the "drop categories with
        no reachable destinations, renormalize remaining weights" logic
        from `category_scores.sql`/`overall_scores.sql`.
  - [ ] 7.3 Implement the population-weighted overall score (FR-SCORE-2):
        score × `pop20`, normalized by total reachable population.
  - [ ] 7.4 Produce the same summary row shape as
        `generated.neighborhood_overall_scores` (renamed
        `generated.overall_scores`, FR-EXPORT-2 — FR-SCORE-3): per-category
        scores, `population_total`, `total_miles_low_stress`,
        `total_miles_high_stress`, mileage rounded to 1 decimal place.
  - [ ] 7.5 Unit tests: representative synthetic cases per category
        (including the "no reachable destinations" renormalization edge
        case) and for the population-weighting formula.
  - _Requirements: FR-ACCESS-1, FR-SCORE-1, FR-SCORE-2, FR-SCORE-3, NFR-TEST-1_

- [ ] 8. Wire the new pipeline into the CLI and exporter
  - [ ] 8.1 Update `exporter.py` to consume GeoDataFrames/DataFrames in
        memory instead of querying PostGIS tables, producing byte-for-byte
        the same schema/column names/order/row contents as today but with
        the `neighborhood_` prefix dropped from file names (FR-EXPORT-1,
        FR-EXPORT-2): `neighborhood_census_blocks.*` →`census_blocks.*`,
        `neighborhood_ways.*` → `ways.*`,
        `neighborhood_ways_intersections.geojson` →
        `ways_intersections.geojson`, `neighborhood_boundary.geojson` →
        `boundary.geojson`; `mileage.csv`/`residential_speed_limit.csv`
        (already unprefixed) unchanged.
  - [ ] 8.2 Replace `bna run-with compose <country> <city> <region>
<fips_code>` with `bna run <country> <city> <region> <fips_code>`
        (design.md §2) — no Docker Compose, no `DATABASE_URL`, chaining
        `prepare → ingest → features → stress → network → scoring →
export` as plain async orchestration (design.md §6's "overall
        pipeline orchestration" row).
  - [ ] 8.3 Keep `downloader.py`/`datasource.py` async I/O paths unchanged
        (design.md §6); ensure they're awaited from the new `run.py` flow.
  - [ ] 8.4 Update CLI help text/docs referencing `run-with compose` or
        `DATABASE_URL` to match the new no-database flow.
  - _Requirements: FR-EXPORT-1, NFR-DEP-1, NFR-ASYNC-1_

- [ ] 9. Checkpoint — iteration-phase parity validation
  - [ ] 9.1 Implement `utils/validate_parity.py` (design.md §5): run the
        new pipeline per corpus city, compare against checked-in
        `results/**` per NFR-PARITY-1/2/3 (absolute `1e-4` on raw scores,
        exact match at display precision, row-for-row file comparison,
        geometry via `equals_exact` with tolerance), emit a structured
        per-city/per-dimension pass/fail report.
  - [ ] 9.2 Add `just validate-parity [city...]` recipe, defaulting to the
        `XS`/`S` corpus (`integration/e2e-cities-XS.csv`,
        `integration/e2e-cities-S.csv`) per design.md §5.
  - [ ] 9.3 Run `just validate-parity` against the XS/S corpus and fix any
        discrepancy in tasks 3-7 before proceeding — do not move on to
        task 10 with a known parity gap in the iteration corpus.
  - _Requirements: NFR-VALIDATION-1, NFR-PARITY-1, NFR-PARITY-2, NFR-PARITY-3_

- [ ] 10. Automated pre-ship gate (`XS`/`S`/`M` corpus)
  - [ ] 10.1 Run `just validate-parity` against the automated corpus:
        `integration/e2e-cities.csv` restricted to `XS`/`S`/`M` `test_size`
        rows (NFR-VALIDATION-2). `L`/`XL`/`XXL` cities (Valencia,
        Washington DC) are excluded — they take hours per city with the
        current implementation, which is impractical for a repeatable
        automated gate. Valencia is excluded from validation entirely (no
        baseline, no manual follow-up); Washington DC gets a manual
        follow-up (10.3).
  - [ ] 10.2 Fix any parity regression found; re-run 10.1 until the
        automated corpus passes. Do not proceed to task 11 until it does —
        this is a hard ceiling, not report-only (requirements.md §7).
  - [ ] 10.3 Manual maintainer validation (not blocking, best-effort — run
        after task 11 once the codebase is stable, not as part of this
        gate): run `just validate-parity` against Washington DC and confirm
        its wall-clock run time is within the 2x ceiling of the current
        SQL/PostGIS pipeline on the same reference hardware (NFR-PERF-1);
        profile `network.py`'s reachability stage first if it regresses,
        per requirements.md §7 open question #4. File a follow-up issue for
        any regression found instead of blocking the migration on it.
        Valencia is not included — it's excluded from validation entirely
        for now (no checked-in baseline, no manual follow-up planned).
  - _Requirements: NFR-VALIDATION-1, NFR-VALIDATION-2, NFR-PERF-1, NFR-PARITY-1,
    NFR-PARITY-2, NFR-PARITY-3_

- [ ] 11. Remove SQL/PostGIS/pgRouting entirely (requirements.md §7 open
      question #7 — hard deletion, no dual-path toggle)
  - [ ] 11.1 Delete `brokenspoke_analyzer/scripts/sql/` in full.
  - [ ] 11.2 Delete `mapconfig_highway.xml`, `mapconfig_cycleway.xml`,
        `pfb.style` (osm2pgrouting/osm2pgsql-specific).
  - [ ] 11.3 Delete `brokenspoke_analyzer/core/database/` (dbcore,
        SQLAlchemy models) and any remaining `execute_sqlfile_with_substitutions`
        usage in `compute.py`/`analysis.py`.
  - [ ] 11.4 Delete `core/compute.py`'s SQL-orchestration functions
        (`features()`, `stress()`, `connectivity()`, `measure()`, `all_()`,
        `parts()`) once `core/pipeline/` fully replaces them; keep only
        what task 2.3 didn't already move to `config.py`, or delete
        `compute.py` entirely if nothing remains.
  - [ ] 11.5 Remove `just compose-up`/`compose-down`/`docker-build` recipes
        and any `DATABASE_URL` references in `justfile`, `README.md`,
        `CLAUDE.md`, and CI config.
  - [ ] 11.6 Remove `osm2pgrouting`/`osm2pgsql`/`shp2pgsql`/PostGIS/
        pgRouting from `pyproject.toml` dependencies, Dockerfile(s), and
        CI service containers.
  - _Requirements: NFR-DEP-1_

- [ ] 12. Final checkpoint — full `just ci` pass
  - [ ] 12.1 Run `just ci` (lint, fmt-check, test, docs) clean with no
        PostGIS/Docker Compose dependency anywhere in the toolchain.
  - [ ] 12.2 Confirm `just test` runs without `docker compose up` (user
        story in requirements.md §4).
  - [ ] 12.3 Re-run task 10.1's automated `XS`/`S`/`M` `validate-parity`
        one final time post-deletion to confirm nothing in task 11's
        removals broke parity.
  - _Requirements: NFR-DEP-1, NFR-TEST-1, all FR/NFR (final gate)_

## Notes & decisions

- No feature flags, no dual-path (SQL-or-Python) runtime toggle — this is a
  full cutover once task 10 passes (requirements.md §1).
- No deviation-tracking module: our SQL is the reference implementation, so
  every rule transcribed in tasks 3-7 must reproduce the SQL's behavior
  exactly, bugs included (requirements.md §3).
- Task 1's benchmark spike gates task 6 — do not start `network.py`'s real
  implementation before it completes (design.md §3.4).
- Tasks 3-7 are listed in pipeline-dependency order but their _unit_ tests
  (synthetic data, no real city fixtures) can be written and iterated on in
  parallel by different contributors, since each stage's unit tests don't
  require the previous stage's real output — only integration/parity
  testing (tasks 9-10) requires the full chain.

## Next steps (after tasks.md)

1. Confirm the pre-implementation gate (`XS`/`S`/`M` corpus baselines
   checked into `results/**`) is satisfied before starting task 1. Valencia
   is not required.
2. Execute tasks 1-12 in order, checking in after each numbered task.
3. Keep `requirements.md`/`design.md` updated if reality diverges during
   implementation (per `specs/README.md`'s contributing guidelines) rather
   than letting the specs go stale.
