# Requirements: SQL-to-Python Migration of the BNA Pipeline

## Status

DRAFT — under active review. Not yet approved.

## 1. Summary

Replace every SQL-driven stage of the Brokenspoke Analyzer pipeline
(`brokenspoke_analyzer/scripts/sql/**`, ~35 files / ~11k lines, plus the
`osm2pgrouting`/`osm2pgsql` ingestion step it depends on) with a pure-Python
implementation, and remove the PostGIS/pgRouting runtime dependency
(Docker Compose database) entirely.

Two drivers, roughly equal weight:

1. **Infra simplification** — `bna` should run as a plain Python package/CLI
   with no database or `docker compose` required.
2. **Maintainability/testability** — SQL scoring logic is currently hard to
   unit test, review, and step through; it should become typed, testable
   Python with clear function boundaries.

This is a full, big-bang rewrite: it is implemented as one body of work and
validated once, end-to-end, rather than shipped stage-by-stage behind a
runtime toggle.

## 1a. Reference implementation: `bikescore-bna`

[bright-fakl/bikescore-bna](https://github.com/bright-fakl/bikescore-bna) is a
third-party MIT-licensed (per its README; **no `LICENSE` file is actually
present in the repo as of this writing — must be re-verified/clarified with
the author before reusing any code**, see open question §7.8) pure-Python
port of brokenspoke-analyzer, pursuing the same goal this project has: no
database, no server, "value-for-value parity" with the SQL reference,
validated stage-by-stage against Aspen, CO. It is small (0 stars/forks, 32
commits) but structurally serious:

- **Pipeline shape**: 11 stages — `parse → census → jobs → attributes →
segment → stress → graph → connectivity → destinations → scores →
neighborhood` — closely mirroring our own stage breakdown in §2.
- **Routing/reachability**: builds CSR (compressed sparse row) adjacency
  matrices with `scipy.sparse` and reachability via `scipy.sparse.csgraph`
  Dijkstra, rather than `networkx` or `igraph`. This is a concrete, working
  answer to the routing-engine open question in §7.5.
- **OSM ingestion**: uses `osmium`/`pyosmium` directly (CLI `osmium` for
  performance, pure-Python `pyosmium` fallback, ~8× slower) rather than
  `pyrosm`/`osmnx`.
- **Tabular processing**: mixes `polars`, `pandas`, and `pyarrow` rather than
  `pandas`/`geopandas` alone.
- **Known SQL bugs**: ships a `deviations.py` documenting cases where its
  output _intentionally_ diverges from the SQL reference because the SQL
  itself is buggy (e.g. a copy-paste error leaves a `one_way_car='tf'`
  branch unreachable inside a `WHEN one_way_car='ft'` block; road topology
  is built before orphan-detection, letting some disconnected two-segment
  chains slip through as non-orphans in the SQL version). **Not applicable
  to this project**: our own SQL is the reference implementation, so there
  is no upstream ground truth we could deviate from — we must match our own
  SQL's behavior exactly, bugs included, with no deviation-tracking concept
  of our own.
- **Validation approach**: has dedicated `parity.py`/`validation.py`
  modules implying an existing stage-by-stage comparison harness — a
  candidate reference design (not necessarily a candidate dependency, see
  §7.8) for our own NFR-VALIDATION-1 harness.

This does **not** replace the need for our own requirements/design — the
project is unproven at scale (single reference city, no adoption) and its
architecture/library choices diverge from ours in several places — but it
must inform design.md, and reusable pieces (documented deviations in
particular) should be evaluated for direct incorporation rather than
re-derived from scratch. See FR-REF in §5 and open question §7.8.

## 2. In scope

The entire pipeline, from raw OSM/Census input to exported result files:

1. **Ingestion** — parsing OSM extracts and building a routable street
   network graph (currently `osm2pgrouting`/`osm2pgsql` via `runner.py` into
   PostGIS). Replaces with `pyrosm`/`osmnx`/`geopandas`, already project
   dependencies.
2. **Feature derivation** (`scripts/sql/features/*.sql`) — per-way attributes:
   bike infrastructure presence, lane counts, functional class, one-way,
   speed limit, width, signalization, RRFBs, parks/paths, mileage
   calculations, "island" detection, Streetlight-derived gates/destinations.
3. **Stress classification** (`scripts/sql/stress/*.sql`) — assigning a
   low/high traffic-stress rating to each road segment and intersection
   based on functional class, lanes, speed, and crossing type (motorway,
   primary, secondary, tertiary, link, living-street, track, path, etc.).
4. **Network build & reachability** (`connectivity/build_network.sql`,
   `block_verts.sql`,
   `reachable_roads_{low,high}_stress_{prep,calc,cleanup}.sql`) —
   building the routable graph with turn costs/angles, and computing, per
   census block, which roads are reachable within a max trip distance on
   low-stress-only vs. all-stress networks (currently `PGR_DRIVINGDISTANCE`,
   a one-to-many Dijkstra).
5. **Access/destination scoring** (`connectivity/access_*.sql`,
   `connectivity/destinations/*.sql`) — per-destination-category (schools,
   colleges, universities, doctors, dentists, hospitals, pharmacies,
   supermarkets, social services, retail, parks, trails, community centers,
   transit, jobs, population) reachability scores per census block.
6. **Category & overall scoring** (`category_scores.sql`, `score_inputs.sql`,
   `overall_scores.sql`) — combining destination scores into category scores
   (opportunity, core services, recreation, etc.) and a single 0–100 overall
   BNA score per neighborhood, with population-weighted aggregation and the
   documented category weights (people=15/20, opportunity=25,
   core_services=25/30, retail=10, recreation=10, transit=15 — see open
   question in §7 about which weight set is authoritative).
7. **Export** — `exporter.py`'s consumption of the above (CSV, GeoJSON,
   shapefile) must continue to produce the same file set and schema as today.

## 3. Out of scope

- Changes to `downloader.py`/`datasource.py` (OSM extract, Census boundary,
  and jobs data fetching) beyond what's needed to feed the new ingestion
  step — these already don't use SQL.
- Changes to the BNA scoring _methodology_ itself (weights, formulas,
  category definitions) — this is a re-implementation, not a redesign.
- New destination categories, new export formats, or new CLI commands.
- Non-US countries' Census-equivalent data sources beyond what's already
  supported (France, Australia, Canada use different demographic inputs;
  existing behavior for these is preserved as-is, not expanded).
- Fixing bugs in the existing SQL logic. Our own SQL is the reference
  implementation (not a third-party system we're porting), so there is no
  deviation-tracking concept here: every quirk/bug in `scripts/sql/**` must
  be reproduced exactly by the Python implementation, not corrected.

## 4. User stories

- **As a `bna` CLI user**, I can run `bna run <country> <city> <region>
<fips_code>` without Docker or `DATABASE_URL` and get the same result
  files I get today.
- **As a maintainer**, I can unit-test an individual scoring function (e.g.
  "compute stress rating for a motorway-trunk intersection") in isolation,
  without standing up a database or running the full pipeline.
- **As a contributor**, I can read Python with type hints and docstrings to
  understand a scoring rule, instead of parsing templated SQL.
- **As a CI pipeline**, I no longer need `just compose-up`/`docker` to run
  `just test` for pipeline logic (integration tests that exercise real city
  data may still be slower/optional, see §6).

## 5. Functional requirements

Numbering: `FR-<stage>-<n>`. Each maps to acceptance criteria in §6.

### FR-ING (Ingestion)

- FR-ING-1: Given an OSM extract (PBF) for a region, produce a routable
  graph (nodes/edges with topology equivalent to what `osm2pgrouting`
  currently produces: way geometry, direction, connectivity) without a
  database.
- FR-ING-2: Preserve all OSM tags currently read downstream by
  `features/*.sql` (highway class, cycleway/bike lane tags, lanes, maxspeed,
  oneway, width, surface, crossing/signal tags, etc.).

### FR-FEAT (Feature derivation)

- FR-FEAT-1: For each road segment, compute the same derived attributes as
  `scripts/sql/features/*.sql` (bike infra, lanes, functional class,
  one-way, speed limit, width, signalized, RRFB, stops, park/path flags,
  mileage, island membership) as pure functions/vectorized operations over
  the ingested graph.
- FR-FEAT-2: Streetlight-derived gates/destinations logic
  (`features/streetlight/*.sql`) is preserved for regions where that data
  source is used.

### FR-STRESS (Stress classification)

- FR-STRESS-1: For each road segment and intersection, compute a stress
  rating using the same rules as `scripts/sql/stress/*.sql`, covering every
  functional class currently handled (motorway/trunk, primary, secondary,
  tertiary, "lesser", link, living-street, track, path) plus intersection
  and one-way-reset adjustments.

### FR-NET (Network build & reachability)

- FR-NET-1: Build a directed, cost-weighted graph (link cost, turn
  angle/crossing cost) equivalent to `build_network.sql`.
- FR-NET-2: For each census block, compute the set of reachable road
  segments within the configured max trip distance, separately for the
  low-stress-only subgraph and the full (all-stress) subgraph, equivalent to
  `PGR_DRIVINGDISTANCE` semantics (one-to-many shortest path with a distance
  cutoff, directed).
- FR-NET-3: Reachability computation must be practical (time/memory) for the
  largest regions currently processed (see NFR-PERF).

### FR-ACCESS (Access/destination scoring)

- FR-ACCESS-1: For each destination category listed in §2.5, compute a
  per-census-block score using the same low-stress-vs-high-stress
  reachability comparison logic as `connectivity/access_*.sql`.

### FR-SCORE (Category & overall scoring)

- FR-SCORE-1: Combine destination scores into category scores using the
  exact weights and "drop categories with no reachable destinations,
  renormalize remaining weights" logic in `category_scores.sql`/
  `overall_scores.sql`.
- FR-SCORE-2: Compute the single population-weighted overall score (0–100)
  per neighborhood boundary, matching `overall_scores.sql`'s weighting
  (score × pop20, normalized by total reachable population).
- FR-SCORE-3: Produce the same summary rows as
  `generated.neighborhood_overall_scores` today (per-category scores,
  `population_total`, `total_miles_low_stress`, `total_miles_high_stress`),
  rounded the same way (1 decimal place for mileage totals).

### FR-REF (Reference implementation evaluation)

- FR-REF-1: design.md must include an explicit build-vs-reuse-vs-adapt
  assessment of `bikescore-bna` per pipeline stage (§2.1–§2.7): for each
  stage, state whether we implement independently, port/adapt its approach,
  or (contingent on licensing clarity, §7.8) reuse code directly.
- FR-REF-2 (removed): our SQL is the reference implementation; there is no
  external ground truth to diff against, so no deviation-adoption process
  applies. The Python implementation must reproduce our SQL's behavior
  exactly, including any bugs it contains — bug fixes are out of scope for
  this migration (§3).

### FR-EXPORT (Export)

- FR-EXPORT-1: `exporter.py` output (file names, formats, schemas, column
  names/order) is unchanged from today for every existing output artifact
  (`neighborhood_census_blocks.*`, `neighborhood_ways.*`,
  `neighborhood_ways_intersections.geojson`, `neighborhood_boundary.geojson`,
  `mileage.csv`, `residential_speed_limit.csv`, etc.).

## 6. Non-functional requirements & acceptance criteria

- **NFR-PARITY-1 (Numerical parity)**: For every city in the validation
  corpus (§6.1), the final overall BNA score and all category/sub-category
  scores produced by the Python pipeline must match the corresponding values
  in the checked-in `results/**/neighborhood_overall_scores`-derived output
  within `1e-4` (matching the existing `NUMERIC(16, 4)` storage precision),
  OR match at the rounded/displayed precision if a value is only ever
  surfaced rounded (e.g. mileage totals at 1 decimal place) — exact
  tolerance definition is an open question, see §7.
- **NFR-PARITY-2 (File-level parity)**: All other exported files
  (`neighborhood_census_blocks.*`, `neighborhood_ways.*`, mileage/speed
  CSVs) must be equivalent to the `results/**` versions: same rows (by
  stable key, e.g. `geoid20`/way id), same columns, numeric columns within
  the same tolerance as NFR-PARITY-1, geometry columns equivalent (same
  shape within floating-point tolerance, not necessarily identical
  WKB/coordinate ordering).
- **NFR-PARITY-3 (Ground truth)**: `results/**` files, as currently checked
  into the repository, are treated as the frozen ground truth for
  validation. They are not regenerated from a fresh SQL run before
  comparison.
- **NFR-VALIDATION-1 (Validation harness)**: A repeatable script/`just`
  recipe exists that runs the full Python pipeline for each city in the
  validation corpus and reports a pass/fail + diff report against the
  corresponding `results/**` directory.
- **NFR-VALIDATION-2 (Validation corpus)**: The full corpus (§7.3) is the
  complete `integration/e2e-cities.csv` list and is the gate for shipping
  the migration. During the iteration phase (while stages are actively
  being built out), validation runs are scoped down to just the `XS` and
  `S` `test_size` rows (`integration/e2e-cities-XS.csv` and
  `integration/e2e-cities-S.csv`) for fast feedback; the full corpus,
  including `M`/`L`/`XL`/`XXL` cities and Washington DC's NFR-PERF-1 check,
  must still pass before the migration is considered done.
- **NFR-PERF-1 (Performance)**: End-to-end run time for a given city must
  not regress beyond [threshold TBD, see §7] compared to the current
  SQL/PostGIS pipeline, measured on the same hardware.
- **NFR-TEST-1 (Testability)**: Every scoring/classification function
  (stress rules, feature derivation rules, category/overall score formulas)
  has direct unit tests with representative inputs/edge cases (not only
  covered indirectly via full-pipeline integration tests).
- **NFR-DEP-1 (No database)**: Running `bna run-with` (or the equivalent new
  entry point) requires no `DATABASE_URL`, no PostGIS, no Docker Compose.
  `just compose-up`/`compose-down` and the `docker-build` recipe are removed
  or repurposed.
- **NFR-ASYNC-1 (Asynchronous where it makes sense)**: The pipeline should
  use `async`/concurrency where it provides real benefit, consistent with
  the project's existing use of `trio`/`aiohttp`/async SQLAlchemy
  (`pyproject.toml`) elsewhere in the codebase. In particular:
  - I/O-bound work (downloading OSM extracts, Census/LODES data, uploading
    exports to S3 via `obstore`/`boto3`) should be async/concurrent, as it
    largely already is today via `downloader.py`/`datasource.py`.
  - CPU-bound work (feature derivation, stress classification, Dijkstra
    reachability, score aggregation) is _not_ a good async fit —
    `async`/`await` does not parallelize CPU-bound Python; those stages
    should instead be evaluated for vectorization (`geopandas`/`polars`/
    `numpy`/`scipy` bulk operations) and, only if that's insufficient,
    multi-process parallelism (the current SQL already parallelizes
    `reachable_roads_*_calc.sql` across threads via `:thread_num`/
    `:thread_no`, so a Python equivalent — `multiprocessing`/thread pool
    over independent census-block batches — should be evaluated).
  - design.md must state, per pipeline stage, whether it is
    async-I/O-bound, CPU-bound-vectorized, or CPU-bound-parallelized, and
    justify the choice — "make it async" is not applied uniformly for its
    own sake.
- **NFR-DOC-1**: Docstrings for all new public functions follow the
  project's pep257 + Parameters/Returns/Raises convention, with doctests
  for the happy path where practical (per `CLAUDE.md`).

## 7. Open questions (must be resolved before design.md)

Status: 8 of 9 resolved. Remaining: #5 (routing engine), which is
intentionally deferred to a design.md benchmark rather than decided here —
see rationale inline. #9 (library research) is likewise a design.md
deliverable, not a pre-design decision, and is not blocking.

1. ~~Exact numerical tolerance~~ — RESOLVED. Absolute `1e-4` on raw/internal
   scores (matching the existing `NUMERIC(16, 4)` storage precision in
   `overall_scores.sql`); values only ever surfaced rounded (e.g. mileage
   totals at 1 decimal place) must match exactly after rounding. This is
   the stricter of the two options considered — chosen because it's the
   only bar that actually proves the _logic_ matches, not just that
   rounding hides small drift.
2. ~~Authoritative category weights~~ — RESOLVED. The SQL comment blocks are
   stale/illustrative; actual weights come from `ScoreDefaultTolerance` in
   `core/compute.py:253-258` (`people=15, opportunity=20, core_services=20,
retail=15, recreation=15, transit=15`), passed as SQL variables at
   runtime. This dataclass is the single source of truth and must be ported
   as-is (or referenced directly if `compute.py` config plumbing is
   retained).
3. ~~Validation corpus~~ — RESOLVED, corrected. Use the existing
   `integration/e2e-cities.csv` fixture list in full (16 cities today), not
   an ad hoc size-based sample — superseding the size-based subset
   originally proposed here. Each row was deliberately chosen for a
   specific edge case (unicode/accented/punctuated names, disconnected
   boundary polygons, water-only census blocks, missing LODES data for
   Puerto Rico, OSM import-breaking characters, non-"true"-state
   jurisdictions, locale-specific speed defaults, etc. — see the `reason`
   column), which is exactly the kind of coverage a parity harness needs
   and is better targeted than a size-only sample. `test_size` (XS/S/M/L/
   XL/XXL) already spans the size spectrum within that set. This is the
   fixed regression set referenced by NFR-VALIDATION-2, and should stay in
   sync with `integration/e2e-cities.csv` (via `just test-e2e-prepare`)
   rather than being duplicated as a separate hardcoded list in design.md.
   During iteration, use only the `XS`/`S` subsets
   (`integration/e2e-cities-XS.csv`/`-S.csv`) for fast feedback loops; the
   full corpus remains the pre-ship gate (NFR-VALIDATION-2).

   **Pre-implementation gate — Valencia baseline**: `e2e-cities.csv` also
   lists Valencia, Spain (XL, "a non-US city with a fantastic bike
   network"), which as of this review has **no checked-in
   `results/**`directory** — every other row in the CSV does (verified: all 16 US/
Canada/France/Australia rows have a matching`results/**`path; Spain
does not appear in`results/`at all). This conflicts with
NFR-PARITY-3's "treat checked-in`results/**` as ground truth, don't
   regenerate" rule, since there's currently nothing to compare Valencia's
   Python output against.

   **Decision**: the team will generate and check in `results/spain/
valencia/` (via the current SQL pipeline) before implementation begins,
   so all 17 `e2e-cities.csv` rows have a baseline under NFR-PARITY-3 by
   the time the Python work starts — no smoke-test-only carve-out needed.
   This is a precondition for starting implementation, not a design.md
   task: **implementation must not begin until every corpus city in
   `integration/e2e-cities.csv` has a checked-in `results/**` baseline.\*\*

4. ~~Performance threshold~~ — RESOLVED. No regression beyond ~2x wall-clock
   run time on the largest corpus city (Washington DC, 16M) compared to the
   current SQL/PostGIS pipeline, measured on the same reference hardware,
   with the reachability/Dijkstra stage (FR-NET-2/NFR-PERF-1) as the
   specific stage most likely to regress and therefore the one to profile
   first. Smaller/medium cities are expected to be _faster_ once
   Docker/DB startup overhead is removed; DC is the binding constraint.
   This is a hard ceiling (gates shipping), not report-only, given the
   project's stated "cannot be done iteratively" risk profile — we want a
   concrete tripwire, not a discovered-too-late regression.
5. **Routing engine choice** — `networkx` vs `igraph`/`graph-tool` vs
   `scipy.sparse.csgraph` (the approach `bikescore-bna` uses, §1a) vs other,
   to be settled in design.md via a benchmark (see design.md plan).
   `scipy` is already a transitive dependency via `rasterio`/`geopandas` and
   the CSR-matrix approach avoids adding a new graph-library dependency at
   all — a strong candidate, but must still be benchmarked, not assumed.
6. ~~Streetlight data availability~~ — RESOLVED. `features/streetlight/*.sql`
   (`streetlight_gates.sql`, `streetlight_destinations.sql`) is never
   invoked from any Python `core/`/`cli/` code today (no references outside
   `scripts/sql/`) — it is dead code in the current pipeline. **Decision:
   out of scope for this migration.** Not ported, not validated. If
   Streetlight support is wanted in the future, it's a separate feature
   built fresh against the new Python pipeline, not a parity requirement
   here.
7. ~~Removal of `scripts/sql/**` and PostGIS-related code~~ — RESOLVED.
   Hard deletion once parity is achieved and the migration ships — no
   kept-but-unused fallback, no dual-path runtime toggle (consistent with
   the big-bang delivery decision already recorded in §1). `just
compose-up`/`compose-down`/`docker-build` recipes and the `DATABASE_URL`
   requirement are removed in the same change.
8. ~~`bikescore-bna` licensing~~ — RESOLVED. Its `pyproject.toml` declares
   `license = { text = "MIT" }` with a matching `License :: OSI Approved ::
MIT License` classifier — sufficient grounds to treat it as MIT-licensed
   even though no standalone `LICENSE` file is present in the repo (a
   packaging gap, not an ambiguous-terms one). Direct code reuse (adapted
   or verbatim, with attribution per MIT terms) is permitted under FR-REF-1;
   still confirm no-`LICENSE`-file gap doesn't cause friction if this ever
   needs legal sign-off for a redistribution question, but it does not
   block design/implementation work.
9. **Library research beyond current choices** — the team already likes
   `geopandas`/`pyrosm`/`osmnx`/`shapely`/`numpy` but wants a deliberate
   comparison rather than defaulting to them. design.md must include a
   short library-selection section per pipeline concern (OSM ingestion,
   tabular processing, routing/reachability, geometry) that at minimum
   compares our current choices against what `bikescore-bna` uses
   (`osmium`/`pyosmium`, `polars`, `scipy.sparse.csgraph`) plus any other
   credible alternative, on: correctness/parity risk, performance,
   maintenance burden (new dependency vs. already-adopted), and fit with
   NFR-ASYNC-1.

## 8. Glossary

- **BNA** — Bicycle Network Analysis, PeopleForBikes' methodology for
  scoring how well a city's street network connects people to destinations
  via low-traffic-stress routes.
- **Low/high stress** — a road segment's suitability for cycling based on
  traffic speed/volume proxies (functional class, lanes, speed limit);
  low-stress segments are considered comfortable for most riders.
- **Neighborhood** — the BNA's term for the boundary (typically a city)
  being analyzed; `neighborhood_*` tables/prefixes refer to this scope.
- **Census block** — smallest US Census Bureau geographic unit used as the
  origin point for reachability/access scoring (`geoid20` key).
- **Reachability shed** — the set of road segments/blocks reachable from a
  given origin within a max trip distance, computed separately for
  low-stress and all-stress networks.
- **Category score** — an aggregate of related destination scores (e.g.
  "opportunity" = jobs + schools + colleges + universities).
- **Overall score** — the single 0–100 population-weighted BNA score for a
  neighborhood.
