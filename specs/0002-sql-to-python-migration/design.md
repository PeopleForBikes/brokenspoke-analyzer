# Design: SQL-to-Python Migration of the BNA Pipeline

## Status

DRAFT — depends on `requirements.md` (status: requirements locked, 8/9 open
questions resolved). This document resolves the remaining deferred items
(routing engine, library selection) via a documented recommendation +
mandatory pre-implementation benchmark spike, not a runtime guess.

## 1. Current architecture (baseline)

```txt
bna run-with compose <country> <city> <region> <fips>
        │
        ├─ configure (Docker Compose: PostGIS + pgRouting)
        │
        ├─ prepare   (analysis.py, downloader.py, datasource.py)
        │     osmnx/pygris/pyrosm → boundary shapefile, census blocks
        │     shapefile, OSM extract, jobs CSVs, speed CSVs
        │
        ├─ import    (ingestor.py)
        │     shp2pgsql  → boundary, census block tables
        │     osm2pgrouting (x2: highway + cycleway configs) → routable graph
        │     osm2pgsql   → full tag-rich OSM tables (points/lines/polygons)
        │     CSV import  → LODES jobs, state/city speed limits
        │
        ├─ compute   (compute.py → executes scripts/sql/**)
        │     features()      scripts/sql/features/*.sql
        │     stress()        scripts/sql/stress/*.sql
        │     connectivity()  scripts/sql/connectivity/*.sql (incl. pgRouting
        │                      PGR_DRIVINGDISTANCE reachability)
        │     measure()       scripts/sql/features/calculate_mileage.sql
        │
        └─ export    (exporter.py)
              PostGIS tables → CSV / GeoJSON / Shapefile, optionally to S3
```

Every stage after `import` operates on PostGIS tables via raw SQL strings
executed through `execute_sqlfile_with_substitutions()`
(`compute.py:22-37`), which does naive `:param` string substitution — not
parameterized queries. `compute.py`'s dataclasses (`Tolerance`,
`PathConstraint`, `BlockRoad`, `Score`, `Access`) are already the
authoritative source of runtime constants (per requirements.md §7.2); they
carry over unchanged in shape, just consumed by Python instead of injected
into SQL text.

## 2. Target architecture

```txt
bna run <country> <city> <region> <fips>      # no "compose"/"with" split needed
        │
        ├─ prepare    (unchanged: analysis.py, downloader.py, datasource.py)
        │
        ├─ ingest     (NEW: core/pipeline/ingest.py)
        │     Consumes prepare's existing file outputs (OSM extract,
        │     boundary, census blocks, jobs/speed CSVs) as-is — prepare
        │     itself is unchanged.
        │     OSM extract → GeoDataFrame(s) of ways + nodes with routing
        │     topology, tags preserved (replaces shp2pgsql + osm2pgrouting +
        │     osm2pgsql)
        │
        ├─ features   (NEW: core/pipeline/features.py)
        │     vectorized GeoDataFrame column derivation
        │     (replaces scripts/sql/features/*.sql)
        │
        ├─ stress     (NEW: core/pipeline/stress.py)
        │     vectorized stress classification
        │     (replaces scripts/sql/stress/*.sql)
        │
        ├─ network    (NEW: core/pipeline/network.py)
        │     CSR graph build + per-block reachability (low/high stress)
        │     (replaces build_network.sql, block_verts.sql,
        │      reachable_roads_*.sql / PGR_DRIVINGDISTANCE)
        │
        ├─ scoring    (NEW: core/pipeline/scoring.py)
        │     access/destination scores → category scores → overall score
        │     (replaces access_*.sql, category_scores.sql, score_inputs.sql,
        │      overall_scores.sql)
        │
        └─ export     (unchanged interface, new data source: GeoDataFrames/
                        DataFrames in memory instead of PostGIS tables)
```

No PostGIS, no pgRouting, no Docker Compose, no `DATABASE_URL`. Each stage
is a pure function: `GeoDataFrame(s)/DataFrame(s) in → GeoDataFrame(s)/
DataFrame(s) out`, independently unit-testable without any I/O.

## 3. Library selection

Per requirements.md open question #9 (deferred to design.md) and FR-REF-1.
Candidates evaluated: our current stack (`geopandas`/`pyrosm`/`osmnx`/
`shapely`/`numpy`, all already project dependencies) vs. `bikescore-bna`'s
stack (`osmium`/`pyosmium`, `polars`, `scipy.sparse.csgraph`) vs. other
credible alternatives.

### 3.1 OSM ingestion: `pyrosm`/`osmnx` (keep) vs. `osmium`/`pyosmium`

|                             | `pyrosm` (current)                                                                                                                                  | `osmium`/`pyosmium` (`bikescore-bna`)                                                               |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Already a dependency        | Yes                                                                                                                                                 | No (new)                                                                                            |
| Performance                 | Fast (Rust-backed reader), designed for exactly this use case                                                                                       | CLI `osmium` is fastest available; pure-Python `pyosmium` ~8x slower per `bikescore-bna`'s own docs |
| Tag access                  | Full tag dict per way/node                                                                                                                          | Full tag dict via handler callbacks                                                                 |
| Graph/topology construction | `osmnx` builds a routable `networkx` graph directly on top, saving us from re-deriving topology (node sharing, direction) by hand                   | `bikescore-bna` builds topology itself in `stages/graph.py` — more code we'd own                    |
| Risk                        | Low — proven in this codebase already (ingestor.py's `import_osm_data` path already reads OSM tags for feature derivation indirectly via osm2pgsql) | New dependency, new code path, no track record in this project                                      |

**Recommendation: keep `pyrosm` for reading the OSM extract into
GeoDataFrames of ways/nodes, and `osmnx` for turning that into a routable
graph structure with topology (source/target vertex IDs, direction).** This
avoids re-implementing topology construction (`build_network.sql`'s job)
from scratch, which is one of the highest-risk, most bug-prone parts of the
original SQL (turn angles, intersection cost, one-way handling). Do **not**
adopt `osmium`/`pyosmium` — it would mean owning topology construction
ourselves for no demonstrated benefit over `osmnx`, which already does it
and is already a dependency.

### 3.2 Tabular/geometry processing: `geopandas`/`pandas` (keep) vs. `polars`

`bikescore-bna` mixes `polars`+`pandas`+`pyarrow`. `polars` is faster than
`pandas` for large non-geometric tabular joins/aggregations (destination
scoring, category/overall score aggregation), but:

- `geopandas` (required for all geometry operations — clipping, buffering,
  intersection, `ST_Length`-equivalents) is built on `pandas`, not `polars`;
  mixing both means two DataFrame libraries in the codebase and conversion
  overhead at the boundary.
- The project's existing dev dependencies (`pandas-stubs`) and `ty`/mypy
  typing setup are pandas-oriented.

**Recommendation: `pandas`/`geopandas` only, not `polars`, unless the
benchmark spike (§3.4) shows a specific non-geometric aggregation stage
(most likely `scoring.py`'s category/overall score combination, which is
pure tabular) is a measured bottleneck on the largest corpus city
(Washington DC). If so, `polars` may be adopted narrowly for that one stage
only — not project-wide — converting to/from `pandas` at the boundary.**
This keeps the dependency surface minimal per NFR §7.9's "maintenance
burden" criterion, while leaving the door open where there's a real,
measured reason.

### 3.3 Routing/reachability: `networkx` vs `igraph` vs `scipy.sparse.csgraph`

This is the highest-risk, most consequential choice (FR-NET-1/2, the direct
replacement for `PGR_DRIVINGDISTANCE`). Requirements.md §7.5 explicitly
deferred this to a design.md benchmark rather than a desk decision.

|                                                                                                                           | `networkx`                                                                   | `igraph`/`graph-tool`                                                                       | `scipy.sparse.csgraph`                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Already a dependency                                                                                                      | No, but pairs naturally with `osmnx` (§3.1), which returns `networkx` graphs | No — new C-backed dependency                                                                | Yes — transitive via `rasterio`/`geopandas`/`scipy`'s own presence as a `numpy` ecosystem staple; **currently not a direct dependency but trivially added, and philosophically "already in the family"**                        |
| Performance                                                                                                               | Pure-Python Dijkstra; historically the slow option at city/region scale      | Fastest (C-backed), but requires converting `osmnx`'s `networkx` graph to `igraph`'s format | Fast (C-backed via `scipy.sparse.csgraph.dijkstra`), and works directly off a CSR adjacency matrix, which we're already building conceptually to represent `build_network.sql`'s link table                                     |
| One-to-many with cutoff (our actual query shape — one census block source, many road targets, within `max_trip_distance`) | Supported (`single_source_dijkstra` with `cutoff`) but slowest of the three  | Supported, fast                                                                             | `scipy.sparse.csgraph.dijkstra(csr, indices=[source], limit=cutoff)` — directly matches `PGR_DRIVINGDISTANCE`'s semantics (one-to-many, directed, distance cutoff)                                                              |
| Precedent                                                                                                                 | None in this project or in `bikescore-bna`                                   | None                                                                                        | **`bikescore-bna` uses exactly this approach** (`stages/graph.py`: CSR matrices via `scipy.sparse`, `GraphBundle` dataclass, dual `G_high`/`G_low` graphs) — a working, validated-against-Aspen precedent for our exact problem |
| Dependency cost                                                                                                           | Zero (would be added but is extremely common/lightweight)                    | New, heavier (C extension, platform wheels)                                                 | Zero-ish (`scipy` is already ubiquitous in this ecosystem; formalizing it as a direct dependency is trivial)                                                                                                                    |

**Recommendation: `scipy.sparse.csgraph.dijkstra` on a CSR adjacency
matrix, following `bikescore-bna`'s precedent.** It matches
`PGR_DRIVINGDISTANCE`'s one-to-many-with-cutoff query shape most directly,
has a working reference implementation validated against real BNA output,
and avoids adding a new non-`numpy`-ecosystem dependency. `networkx` remains
useful upstream (via `osmnx`) for initial graph _construction_/topology, but
the reachability _queries themselves_ should run on a CSR matrix, not by
calling `networkx`'s Dijkstra directly per block (which would not scale to
Washington DC's block count within the NFR-PERF-1 2x ceiling).

**This recommendation is not final without the benchmark spike in §3.4** —
it is the design's best-evidence default, to be confirmed or overturned by
measurement before other stages (scoring, which depends on reachability
output shape) are built against it.

### 3.4 Mandatory pre-implementation benchmark spike

Before `network.py` (§2) is implemented for real, run a throwaway spike
that:

1. Builds a CSR graph for 3 corpus cities spanning the size range (e.g.
   Ancienne-Lorette [XS], Santa Rosa [M], Washington DC [XXL], per the
   corpus in requirements.md §7.3).
2. Computes low-stress and high-stress reachability for every census block
   in each city using (a) `scipy.sparse.csgraph.dijkstra` and (b)
   `networkx.single_source_dijkstra` with cutoff, for the same input.
3. Compares wall-clock time and peak memory for both approaches on DC
   specifically (the NFR-PERF-1 binding constraint).
4. Confirms numerically identical reachable-sets between the two approaches
   on all 3 cities (they should be, since Dijkstra is Dijkstra) — this
   validates the CSR construction itself, not just the algorithm choice.

Record results in this file (§3.3) or a short spike report linked from here
before writing `tasks.md`'s network-stage tasks. If `scipy.sparse.csgraph`
underperforms unexpectedly, fall back to the `networkx`/`igraph` comparison
using the same harness.

### 3.5 Other libraries — no change

`shapely`, `numpy`, `pygris`, `us`, `python-slugify`, `boto3`/`obstore`
(export), `aiohttp`/`tenacity` (downloads) all carry over unchanged — none
of `bikescore-bna`'s choices (`pydantic`, `pyyaml`, `hypothesis`) displace
an existing, working choice in this codebase strongly enough to justify a
switch; `pydantic` in particular would duplicate what `dataclasses` already
does for `compute.py`'s config objects (§1) without a clear win.

## 4. Reference implementation mapping (FR-REF-1)

Per-stage build/reuse/adapt assessment against `bikescore-bna`
(MIT-licensed per requirements.md §7.8, reuse permitted with attribution):

| Our stage                                               | `bikescore-bna` stage(s)                 | Decision                                             | Rationale                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------------- | ---------------------------------------- | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ingest.py`                                             | `parse`, `census`, `jobs`                | **Build independently**                              | Their approach uses `osmium` (rejected, §3.1); our `pyrosm`/`osmnx`/`pygris` path is already proven in this codebase for boundary/census/jobs acquisition (`analysis.py`, `downloader.py`) — only the OSM-to-graph-topology piece is genuinely new, and that leans on `osmnx`, not their code.                                                                                          |
| `features.py`                                           | `attributes`                             | **Adapt approach, not code**                         | Their `attributes.py`/`intersection_attributes.py` module boundaries are a reasonable model to mirror (one module per attribute-group), but the actual per-tag derivation rules must be transcribed from _our_ SQL (`scripts/sql/features/*.sql`), not theirs, since correctness is judged against our SQL's exact behavior (NFR-PARITY), not theirs.                                   |
| `stress.py`                                             | `stress`                                 | **Adapt approach**                                   | Same rationale as `features.py`: module boundaries are a reasonable model, but the actual rules are transcribed from _our_ SQL. Our SQL is the reference implementation (requirements.md §3) — no deviation-tracking or diffing against `bikescore-bna`'s `deviations.py`; any bug in our SQL is reproduced exactly, not fixed.                                                         |
| `network.py`                                            | `graph`                                  | **Reuse approach directly, adapt code**              | This is the one stage where `bikescore-bna`'s code is directly relevant and worth reading line-by-line (not just architecturally): `segments_to_network()`, `build_graph()`, `_make_csr()`, and the `GraphBundle` dataclass shape are a strong starting point for our own CSR construction (§3.3/3.4), pending the benchmark. Attribute per MIT terms if code is adapted substantially. |
| `connectivity.py`/`destinations` scoring → `scoring.py` | `connectivity`, `destinations`, `scores` | **Build independently, structural inspiration only** | Score formulas/weights must match our SQL exactly (`category_scores.sql`, `overall_scores.sql`, `compute.py`'s `Score`/`Access`/`Tolerance` dataclasses) — these are project-specific business rules, not generic algorithms, so there's little to "reuse" beyond module organization.                                                                                                  |
| `neighborhood`/export                                   | `neighborhood`, `export`                 | **Build independently**                              | Our `exporter.py` interface/output contract (FR-EXPORT-1) is fixed by our own current file formats; not a reuse candidate.                                                                                                                                                                                                                                                              |
| N/A                                                     | `parity.py`, `validation.py`             | **Adapt directly (see §5)**                          | Process/tooling modules, not business logic — highest reuse value of anything in the reference repo. `deviations.py` is **not** adopted: our SQL is the reference implementation, so there is no external ground truth to track divergence against (requirements.md §3).                                                                                                                |

## 5. Validation harness (NFR-VALIDATION-1)

New `just` recipe: `just validate-parity [city...]`. Default corpus depends
on phase (requirements.md §6/§7.3):

- **Iteration phase** (while stages are being actively built): `XS`/`S`
  `test_size` cities only, from `integration/e2e-cities-XS.csv` and
  `integration/e2e-cities-S.csv`, for fast feedback.
- **Pre-ship gate**: full corpus from `integration/e2e-cities.csv`
  (NFR-VALIDATION-2), including Washington DC for the NFR-PERF-1 check.

Runs `utils/validate_parity.py` (or a `brokenspoke_analyzer` test-only
module):

1. For each corpus city, run the new Python pipeline end-to-end, producing
   the same output tree shape as `results/<country>/<region>/<city>/
<version>/`.
2. Load the corresponding checked-in `results/**` files (frozen ground
   truth per NFR-PARITY-3) and the freshly generated output.
3. Compare, per FR/NFR §5-6:
   - `neighborhood_overall_scores`-derived values: absolute diff ≤ `1e-4`
     (raw) or exact match at display precision. No skip/exception list —
     our SQL is the reference implementation (requirements.md §3), so
     every row/column must match.
   - Row-for-row comparison of `neighborhood_census_blocks.*`,
     `neighborhood_ways.*`, `mileage.csv`, `residential_speed_limit.csv` by
     stable key (`geoid20`/way id); numeric columns within tolerance;
     geometry columns compared via `shapely.geometry.base.BaseGeometry.
equals_exact` with a small tolerance (not WKB byte-equality, matching
     NFR-PARITY-2's explicit allowance for representation differences).
4. Emit a structured pass/fail report per city + per comparison dimension
   (not just an aggregate pass/fail), so a single-city or single-column
   regression is diagnosable without re-running the whole corpus.
5. Report wall-clock time per city, specifically flagging Washington DC
   against the NFR-PERF-1 2x ceiling (pre-ship gate run only — DC is
   `XXL`, not part of the XS/S iteration corpus).

This harness is itself modeled on `bikescore-bna`'s `parity.py`/
`validation.py` (architectural reuse per §4's last row), adapted to our
`results/**` layout and our tolerance rules.

## 6. Async design (NFR-ASYNC-1)

| Stage                                                                         | I/O-bound or CPU-bound?                                                                            | Concurrency approach                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `downloader.py`/`datasource.py` (OSM extract, Census, LODES downloads)        | I/O-bound                                                                                          | Already `aiohttp`/`trio`-based (unchanged) — keep as-is                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `ingest.py` (OSM parse via `pyrosm`, boundary/graph construction via `osmnx`) | CPU-bound (parsing/topology construction is compute, not I/O)                                      | Synchronous; no `async` benefit. If profiling shows it's a bottleneck on large cities, evaluate `multiprocessing` for independent sub-regions, not `async`                                                                                                                                                                                                                                                                                                                                                                                                        |
| `features.py`, `stress.py`                                                    | CPU-bound, vectorizable                                                                            | Synchronous, vectorized `geopandas`/`pandas`/`numpy` operations (column-wise, no per-row Python loops) — no `async`, no multiprocessing needed at this granularity                                                                                                                                                                                                                                                                                                                                                                                                |
| `network.py` (CSR build + per-block Dijkstra)                                 | CPU-bound                                                                                          | Synchronous `scipy.sparse.csgraph.dijkstra` calls; the existing SQL already parallelizes this step 8-way (`:thread_num`/`:thread_no` in `reachable_roads_*_calc.sql`, `compute.py:331-337`), so the Python equivalent should use a process pool (`concurrent.futures.ProcessPoolExecutor`, not `async`, since this is CPU-bound) over independent batches of census blocks. `scipy.sparse.csgraph.dijkstra` also natively supports multiple `indices` in one call, which may make batched-not-parallel calls sufficient — resolve during the §3.4 benchmark spike |
| `scoring.py` (access/category/overall scores)                                 | CPU-bound, vectorizable                                                                            | Synchronous, vectorized `pandas` operations — no `async`, no multiprocessing (this is the smallest-data stage, operating on per-block aggregates, not per-way/per-block-pair data)                                                                                                                                                                                                                                                                                                                                                                                |
| `exporter.py` (write local files + optional S3 upload)                        | Mixed: local file writes are I/O but typically fast/small; S3 upload is I/O-bound over the network | Keep S3 upload async (already `obstore`/`boto3`-based per current code); local file writes stay synchronous — no benefit to making small local writes async                                                                                                                                                                                                                                                                                                                                                                                                       |
| Overall pipeline orchestration (`run.py`/`run_with.py`)                       | Orchestration                                                                                      | Stays `async def` at the top level (already is, via `asyncio.run`/`trio`) so I/O-bound sub-steps (downloads, S3 export) can be awaited without blocking; CPU-bound stages are called synchronously from within that async orchestration (they block the event loop briefly, which is fine — there's nothing else to run concurrently with them in this CLI's single-run-at-a-time model)                                                                                                                                                                          |

This directly answers requirements.md's NFR-ASYNC-1 requirement to state,
per stage, whether it's async-I/O-bound, CPU-bound-vectorized, or
CPU-bound-parallelized, and to avoid applying `async` where it doesn't fit.

## 7. Module/directory structure

```txt
brokenspoke_analyzer/
  core/
    pipeline/                  # NEW
      __init__.py
      ingest.py                # FR-ING
      features.py               # FR-FEAT
      stress.py                 # FR-STRESS
      network.py                 # FR-NET (CSR graph + reachability)
      scoring.py                 # FR-ACCESS + FR-SCORE
    # analysis.py, downloader.py, datasource.py, exporter.py, utils.py,
    # constant.py, compute.py: retained; compute.py's dataclasses
    # (Tolerance/PathConstraint/BlockRoad/Score/Access) move into
    # core/pipeline/scoring.py or a shared core/pipeline/config.py,
    # SQL-execution functions in compute.py/analysis.py's SQL helpers
    # (execute_sqlfile_with_substitutions, dbcore usage) are deleted.
    database/                    # REMOVED (dbcore, SQLAlchemy models) —
                                  # per requirements.md §7.7, hard deletion
  scripts/
    sql/                        # REMOVED entirely (§7.7) once parity
                                  # validated and the migration ships
    mapconfig_highway.xml        # REMOVED (osm2pgrouting-specific)
    mapconfig_cycleway.xml       # REMOVED
    pfb.style                    # REMOVED (osm2pgsql-specific)
utils/
  validate_parity.py             # NEW, §5
tests/
  brokenspoke_analyzer/core/pipeline/   # NEW, mirrors core/pipeline/
    test_ingest.py
    test_features.py
    test_stress.py
    test_network.py
    test_scoring.py
integration/
  e2e-cities.csv                 # unchanged, now doubles as the
                                  # NFR-VALIDATION-2 parity corpus source
```

`justfile` changes: remove `compose-up`/`compose-down`/`docker-build`
recipes (§ requirements.md NFR-DEP-1); add `validate-parity` (§5).

## 8. Data model sketch

Illustrative, not exhaustive — full column-level schemas are a `tasks.md`-
level deliverable once each stage's SQL is transcribed.

- **Ways** (`GeoDataFrame`): one row per road segment, replacing
  `neighborhood_ways`. Columns: `way_id`, `geometry` (LineString),
  OSM tags subset (`highway`, `cycleway`, `lanes`, `maxspeed`, `oneway`,
  `width`, ...), derived feature columns (`functional_class`, `bike_infra`,
  `ft_seg_stress`, `tf_seg_stress`, ...).
- **Network vertices/links** (`pandas.DataFrame`, feeding `network.py`'s
  CSR build): `vert_id`, `road_id`, `geometry` (Point) for vertices;
  `link_id`, `source_vert`, `target_vert`, `link_cost`, `link_stress` for
  links — direct analogues of `neighborhood_ways_net_vert`/
  `neighborhood_ways_net_link`.
- **Census blocks** (`GeoDataFrame`): `geoid20`, `geometry` (Polygon),
  `pop20`, plus per-destination-category score columns added by
  `scoring.py` (`*_score`, `*_high_stress`, ...) — analogue of
  `neighborhood_census_blocks`.
- **Destinations** (`GeoDataFrame` per category): `geometry` (Point),
  category-specific attributes, clustered per `Tolerance` dataclass values.
- **Reachability result** (`network.py` output, feeding `scoring.py`):
  sparse mapping `{block_geoid: {reachable_road_ids}}`, separately for
  low-stress and high-stress graphs — analogue of
  `neighborhood_reachable_roads_{low,high}_stress`.
- **Scores** (`pandas.DataFrame`): analogue of
  `generated.neighborhood_overall_scores` — `score_id`, `score_original`,
  `score_normalized`, `human_explanation`.

## 9. Error handling

- Stage functions raise typed exceptions (a small `core/pipeline/errors.py`
  hierarchy: `IngestError`, `InsufficientDataError` (e.g. zero population,
  mirroring `ingestor.py`'s current `ValueError` on `population == 0`),
  `ReachabilityError`) rather than propagating raw `KeyError`/library
  exceptions — improves on the current SQL pipeline's undifferentiated
  `sqlalchemy` exceptions, but is not a parity requirement (internal
  quality improvement only, per requirements.md's testability driver).
- No silent fallback for missing/malformed OSM tags — mirror current SQL's
  `COALESCE(..., 0)`/`NULL`-handling behavior exactly (NFR-PARITY), don't
  "improve" default-value logic as a side effect of the rewrite. There is no
  deviation-tracking mechanism to file such a change under — our SQL is the
  reference implementation, so any intentional divergence is out of scope
  for this migration (requirements.md §3).

## 10. Testing strategy (NFR-TEST-1)

- Unit tests per stage module (`tests/brokenspoke_analyzer/core/pipeline/
test_*.py`) using small synthetic GeoDataFrames (2-5 rows) covering: one
  representative case per functional class in `stress.py`
  (motorway/trunk, primary, secondary, tertiary, residential/lower-order,
  living-street, track, path, link) and per feature rule in `features.py`
  — this is the concrete deliverable behind NFR-TEST-1's "not only covered
  indirectly via full-pipeline integration tests."
- `network.py` unit tests use small synthetic graphs (5-10 nodes) with hand-
  computed expected reachable sets, independent of any real city data.
- Full-pipeline integration/parity tests are the `just validate-parity`
  harness (§5) against the corpus (requirements.md §7.3) — these are slow
  and not part of `just test`'s default fast loop; wired as a separate
  `just` recipe/CI job, consistent with the user story in requirements.md
  §4 about not needing Docker for `just test`.
