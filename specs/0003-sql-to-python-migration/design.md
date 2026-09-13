# Design: SQL-to-Python Migration of the BNA Pipeline

## Status

APPROVED. Depends on `requirements.md` (status: APPROVED). The one item left
open at approval time — final routing-engine confirmation — is resolved via the
mandatory pre-implementation benchmark spike (§3.4), not a runtime guess.

## 0. Findings

Implementation findings -- SQL semantics that do not survive a naive
translation, pandas traps, and pipeline structure the SQL does not state -- are
collected in `findings.md` rather than scattered through this document.

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
executed through `execute_sqlfile_with_substitutions()` (`compute.py:22-37`),
which does naive `:param` string substitution — not parameterized queries.
`compute.py`'s dataclasses (`Tolerance`, `PathConstraint`, `BlockRoad`, `Score`,
`Access`) are already the authoritative source of runtime constants (per
requirements.md §7.2); they carry over unchanged in shape, just consumed by
Python instead of injected into SQL text.

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

No PostGIS, no pgRouting, no Docker Compose, no `DATABASE_URL`. Each stage is a
pure function:
`GeoDataFrame(s)/DataFrame(s) in → GeoDataFrame(s)/ DataFrame(s) out`,
independently unit-testable without any I/O.

## 3. Library selection

Per requirements.md open question #9 (deferred to design.md) and FR-REF-1.
Candidates evaluated: our current stack (`geopandas`/`pyrosm`/`osmnx`/
`shapely`/`numpy`, all already project dependencies) vs. `bikescore-bna`'s stack
(`osmium`/`pyosmium`, `polars`, `scipy.sparse.csgraph`) vs. other credible
alternatives.

### 3.1 OSM ingestion: `pyrosm`/`osmnx` (keep) vs. `osmium`/`pyosmium`

|                             | `pyrosm` (current)                                                                                                                                  | `osmium`/`pyosmium` (`bikescore-bna`)                                                               |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Already a dependency        | Yes                                                                                                                                                 | No (new)                                                                                            |
| Performance                 | Fast (Rust-backed reader), designed for exactly this use case                                                                                       | CLI `osmium` is fastest available; pure-Python `pyosmium` ~8x slower per `bikescore-bna`'s own docs |
| Tag access                  | Full tag dict per way/node                                                                                                                          | Full tag dict via handler callbacks                                                                 |
| Graph/topology construction | `osmnx` builds a routable `networkx` graph directly on top, saving us from re-deriving topology (node sharing, direction) by hand                   | `bikescore-bna` builds topology itself in `stages/graph.py` — more code we'd own                    |
| Risk                        | Low — proven in this codebase already (ingestor.py's `import_osm_data` path already reads OSM tags for feature derivation indirectly via osm2pgsql) | New dependency, new code path, no track record in this project                                      |

**Recommendation: keep `pyrosm` for reading the OSM extract into GeoDataFrames
of ways/nodes, and `osmnx` for turning that into a routable graph structure with
topology (source/target vertex IDs, direction).** This avoids re-implementing
topology construction (`build_network.sql`'s job) from scratch, which is one of
the highest-risk, most bug-prone parts of the original SQL (turn angles,
intersection cost, one-way handling). Do **not** adopt `osmium`/`pyosmium` — it
would mean owning topology construction ourselves for no demonstrated benefit
over `osmnx`, which already does it and is already a dependency.

#### Corrections from implementing task 3

Two parts of the above did not survive contact with the real inputs.

1. **`pyrosm` cannot read what `prepare` produces.** `prepare` writes
   `<slug>.osm` as OSM **XML** (`osmium extract` picks the format from the
   extension); `pyrosm` accepts protobuf only and rejects the file outright.
   **Resolution:** `ingest.as_protobuf()` shells out to `osmium cat` to convert
   XML → `.osm.pbf` before reading. The conversion is cheap (0.07 s and 2.3 MB →
   113 KB for Crested Butte) and `osmium` is already required by `prepare`, so
   this keeps `prepare` untouched as requirements.md §3 demands. A cleaner
   long-term fix — having `prepare` emit `.osm.pbf` directly — is a one-line
   change explicitly permitted by §3's "beyond what's needed to feed the new
   ingestion step", and is worth doing if `prepare` is ever reopened.
2. **Neither `osmnx` nor `pyrosm` reproduces `osm2pgrouting`'s segmentation**,
   so topology is _not_ had for free. Measured on Crested Butte:
   `osmnx.graph_from_xml(simplify=True)` yields 952 directed edges,
   `pyrosm.get_network(nodes=True)` yields 1,577 sub-edges (it cuts at every
   node), and `osm2pgrouting`'s rule — cut a way only at nodes shared with
   another routable way — yields 742. The BNA's costs are defined against the
   last of these, so `ingest.split_ways_at_intersections()` implements it
   directly. `osmnx` is therefore **not** used for topology; `pyrosm` supplies
   ways, tags, and the node chain, and the segmentation rule is ours.

   One addition the SQL implies but does not state: a node a way visits
   **twice** (a loop closing on itself) is also a cut point. Without that, the
   segment is a self-touching ring that cannot merge into a single LineString,
   and every downstream geometry step (start/end point, midpoint, azimuth, turn
   angle) assumes one continuous LineString per road.

**Validation.** With the census-block filters from
`ingestor.import_neighborhood` reproduced, block counts and populations match
the checked-in `results/**` exactly for Crested Butte (106 blocks / 1,639),
Santa Rosa (142 / 2,850), and Ancienne-Lorette (76 / 7,600) — covering the US
and non-US paths, which use different overlap thresholds and differ on water
blocks. With task 4's road-defining feature rules added, **road counts match
`results/**` exactly for 12 of 13 cities tested**; Chambéry is +3 of 7,212.

#### The ingest stage has a second, non-obvious input dependency

`ingest` is not purely "read what `prepare` wrote". Before `osm2pgrouting` sees
the extract, `ingestor.import_osm_data` clips it with
`osmconvert --drop-broken-refs -b=<bbox>`, where the box is the **EPSG:4326
extent of the census blocks that survived filtering** — after the out-of-buffer
and water-block deletes, so it is tighter than the boundary, and much tighter
for a coastal city. Dropping broken refs removes way nodes outside the box,
which changes where ways are cut and therefore how many road segments exist.

This orders the stage internally: **census blocks must be loaded and filtered
before the OSM extract is read**, because the clip depends on their extent.
Adding it took Alvarado, Jackson, Cañon City, and Provincetown from +16, +11,
+4, and +2 segments to exact. `ingest.clip_to_census_blocks()` reuses the
project's existing `runner.run_osm_convert`, i.e. the same tool the SQL pipeline
used, which is the safest choice for parity.

### 3.2 Tabular/geometry processing: `geopandas`/`pandas` (keep) vs. `polars`

`bikescore-bna` mixes `polars`+`pandas`+`pyarrow`. `polars` is faster than
`pandas` for large non-geometric tabular joins/aggregations (destination
scoring, category/overall score aggregation), but:

- `geopandas` (required for all geometry operations — clipping, buffering,
  intersection, `ST_Length`-equivalents) is built on `pandas`, not `polars`;
  mixing both means two DataFrame libraries in the codebase and conversion
  overhead at the boundary.
- The project's existing dev dependencies (`pandas-stubs`) and `ty`/mypy typing
  setup are pandas-oriented.

**Recommendation: `pandas`/`geopandas` only, not `polars`, unless the benchmark
spike (§3.4) shows a specific non-geometric aggregation stage (most likely
`scoring.py`'s category/overall score combination, which is pure tabular) is a
measured bottleneck on the largest corpus city (Washington DC). If so, `polars`
may be adopted narrowly for that one stage only — not project-wide — converting
to/from `pandas` at the boundary.** This keeps the dependency surface minimal
per NFR §7.9's "maintenance burden" criterion, while leaving the door open where
there's a real, measured reason.

### 3.3 Routing/reachability: `networkx` vs `igraph` vs `scipy.sparse.csgraph`

This is the highest-risk, most consequential choice (FR-NET-1/2, the direct
replacement for `PGR_DRIVINGDISTANCE`). Requirements.md §7.5 explicitly deferred
this to a design.md benchmark rather than a desk decision.

|                                                                                                                           | `networkx`                                                                   | `igraph`/`graph-tool`                                                                       | `scipy.sparse.csgraph`                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Already a dependency                                                                                                      | No, but pairs naturally with `osmnx` (§3.1), which returns `networkx` graphs | No — new C-backed dependency                                                                | Yes — transitive via `rasterio`/`geopandas`/`scipy`'s own presence as a `numpy` ecosystem staple; **currently not a direct dependency but trivially added, and philosophically "already in the family"**                        |
| Performance                                                                                                               | Pure-Python Dijkstra; historically the slow option at city/region scale      | Fastest (C-backed), but requires converting `osmnx`'s `networkx` graph to `igraph`'s format | Fast (C-backed via `scipy.sparse.csgraph.dijkstra`), and works directly off a CSR adjacency matrix, which we're already building conceptually to represent `build_network.sql`'s link table                                     |
| One-to-many with cutoff (our actual query shape — one census block source, many road targets, within `max_trip_distance`) | Supported (`single_source_dijkstra` with `cutoff`) but slowest of the three  | Supported, fast                                                                             | `scipy.sparse.csgraph.dijkstra(csr, indices=[source], limit=cutoff)` — directly matches `PGR_DRIVINGDISTANCE`'s semantics (one-to-many, directed, distance cutoff)                                                              |
| Precedent                                                                                                                 | None in this project or in `bikescore-bna`                                   | None                                                                                        | **`bikescore-bna` uses exactly this approach** (`stages/graph.py`: CSR matrices via `scipy.sparse`, `GraphBundle` dataclass, dual `G_high`/`G_low` graphs) — a working, validated-against-Aspen precedent for our exact problem |
| Dependency cost                                                                                                           | Zero (would be added but is extremely common/lightweight)                    | New, heavier (C extension, platform wheels)                                                 | Zero-ish (`scipy` is already ubiquitous in this ecosystem; formalizing it as a direct dependency is trivial)                                                                                                                    |

#### Measured result (spike executed — supersedes the table above)

The §3.4 spike was run. **Two cells of the table above were factually wrong, and
the benchmark overturned its recommendation.** Corrections:

- **`scipy` is _not_ an existing dependency.** It is an optional extra of
  `geopandas` (`extra == "all"`) and `osmnx` (`extra == "entropy"/"neighbors"`)
  only; it was not installed in the project venv. Adding it is a real new direct
  dependency.
- **`networkx` _is_ an existing dependency.** `osmnx>=2.1.1` requires
  `networkx>=2.5` unconditionally, so it is already installed and already in the
  dependency tree the design keeps for topology construction (§3.1).

The "already a dependency / dependency cost" criterion therefore favours
`networkx`, not `scipy` — the reverse of what the table asserted.

Benchmark, run from the checked-in `results/**` exports (no database), with
`nb_max_trip_distance = 2680`, over every census block in each city:

| City            | Blocks | Verts  | Links   | scipy (low + high) | networkx (low + high) |
| --------------- | ------ | ------ | ------- | ------------------ | --------------------- |
| Santa Rosa (XS) | 138    | 648    | 2,128   | 0.012 s            | 0.040 s               |
| San Juan (S)    | 3,536  | 19,315 | 56,962  | **1.285 s**        | **5.082 s**           |
| Valencia (XL)   | 193    | 45,712 | 106,083 | 0.253 s            | 1.129 s               |

- **Reachable sets are identical** between the two engines on all three cities,
  for both stress subgraphs (tasks.md 1.3). This validates the CSR construction,
  not merely the algorithm choice.
- **Peak memory is a non-issue for both.** Measured one engine per process with
  results streamed rather than retained, the peak-RSS delta attributable to
  either engine was ~0 MiB; process peak (218–315 MiB) is dominated by the
  loaded `GeoDataFrame`s, identically for both.
- **`scipy` is ~4x faster on the high-stress graph but ~3x _slower_ on the
  low-stress graph.** `dijkstra(..., min_only=True)` sweeps the full node array
  regardless of how little is reachable, whereas `networkx` explores only the
  reachable component — and low-stress subgraphs are sparse and highly
  fragmented (San Juan: 1,708 low-stress edges spanning 19,315 vertices).
  `scipy` wins in aggregate only because the high-stress leg dominates.
- **The stage is not a bottleneck at corpus scale, for either engine.** The 2680
  m cutoff bounds each search to a local neighbourhood, so per-block cost stays
  at 1.7–4.6 ms essentially independently of total graph size. The whole
  reachability stage is seconds, in a pipeline that runs for minutes.
  requirements.md §7.4's premise that reachability is "the stage most likely to
  regress" is not supported by measurement.

**Decision: `networkx`, not `scipy`.** The absolute saving from `scipy` is ~3.8
s on the heaviest corpus city (San Juan) — far inside NFR-PERF-1's 2x ceiling
either way — and it costs a new direct dependency, a CSR index-mapping layer,
and a conversion step away from the `networkx` graphs `osmnx` already hands us
for topology (§3.1). Per requirements.md §7.9's explicit "new dependency vs.
already-adopted" maintenance criterion, that trade goes to `networkx`.

`scipy` remains a proven drop-in should a future workload need it: the spike
established the two engines return identical results, so switching is a
low-risk, localised change rather than a rewrite. Revisit if a city ever
materially exceeds San Juan's block count _and_ the stage measures as a real
share of pipeline wall-clock.

**Consequences for the implementation plan** (tasks.md task 6): the CSR
construction in 6.1, the `scipy`-specific reachability call in 6.2, and the
`ProcessPoolExecutor` parallelism in 6.3 are no longer warranted as written. The
SQL parallelises this step 8-way because in-database `PGR_DRIVINGDISTANCE` was
slow, not because the algorithm demands it; a 5-second stage does not need a
process pool. See §6.

### 3.4 Mandatory pre-implementation benchmark spike — DONE

**Status: executed; results recorded in §3.3.** The spike ran as
`utils/spike_routing_benchmark.py` and was deleted afterwards per tasks.md 1.5.
Two deviations from the plan below, both forced by facts on the ground:

- **Washington DC was replaced by San Juan and Valencia.** DC has no checked-in
  `results/**` baseline and is exempt from the pre-implementation gate
  (requirements.md §7.3/§7.4a), so it could not be measured. Of the cities that
  do have baselines, **San Juan is the heaviest reachability workload — not
  Valencia**: the stage scales with census-block count, and non-US cities get
  far fewer simulated blocks (San Juan 3,536 blocks / 19,315 roads vs. Valencia
  193 blocks / 45,712 roads, roughly 10x the total Dijkstra work despite half
  the road count). Use **block count**, not road count or `test_size`, to pick
  the perf-binding city for this stage.
- **Multi-source, not single-source, Dijkstra.** The SQL seeds each search from
  a synthetic 0-cost super-source wired to every vertex of the block's roads.
  The faithful analogues are `scipy.sparse.csgraph.dijkstra(..., min_only=True)`
  and `networkx.multi_source_dijkstra_path_length`, not the
  `single_source_dijkstra` this plan named.

The spike also established that it needs **no database and no `prepare` run**:
`results/**`'s `neighborhood_ways` export carries every column
`build_network.sql` consumes (`road_id`, `intersection_from`/`_to`, `one_way`,
and the four stress columns), and `neighborhood_census_blocks` carries the
`road_ids` array that `block_verts.sql` seeds from. The same trick lets task 6's
unit/integration work run offline against real city topology.

#### Findings that carry into task 6

Discovered while reproducing `build_network.sql` in Python; all three are parity
risks, not spike artefacts:

1. **CRS matters and fails silently.** The GeoJSON exports are EPSG:4326
   (degrees); the shapefiles carry the projected `nb_output_srid` the SQL
   computes lengths and azimuths in. Deriving `link_cost` from the GeoJSON
   geometry without reprojecting rounds every cost to 0 — with no error.
2. **`greatest()` skips NULLs.**
   `link_stress = greatest(source_stress, int_stress, target_stress)` yields
   NULL only when all three are NULL; a NULL `link_stress` then fails the
   low-stress `link_stress = 1` filter but survives the unfiltered high-stress
   query. Valencia has such rows, so a naive `max()` over NaN breaks on real
   data.
3. **The right-turn rule is non-deterministic in the SQL.**
   `build_network. sql`'s `int_crossing = FALSE` update picks one link per
   `(source_road_id, int_id)` via `LIMIT 1` over an `ORDER BY` that does not
   break ties, so where two turns share an order key, which one gets
   `int_stress = 1` is arbitrary in Postgres. Since NFR-PARITY-1 requires
   matching our SQL exactly, this is an inherently unmatchable case: quantify
   how many links tie in practice before assuming it is negligible.

---

The original plan, retained for reference. Before `network.py` (§2) is
implemented for real, run a throwaway spike that:

1. Builds a CSR graph for 3 corpus cities spanning the size range (e.g.
   Ancienne-Lorette [XS], Santa Rosa [M], Washington DC [XXL], per the corpus in
   requirements.md §7.3).
2. Computes low-stress and high-stress reachability for every census block in
   each city using (a) `scipy.sparse.csgraph.dijkstra` and (b)
   `networkx.single_source_dijkstra` with cutoff, for the same input.
3. Compares wall-clock time and peak memory for both approaches on DC
   specifically (the NFR-PERF-1 binding constraint).
4. Confirms numerically identical reachable-sets between the two approaches on
   all 3 cities (they should be, since Dijkstra is Dijkstra) — this validates
   the CSR construction itself, not just the algorithm choice.

Record results in this file (§3.3) or a short spike report linked from here
before writing `tasks.md`'s network-stage tasks. If `scipy.sparse.csgraph`
underperforms unexpectedly, fall back to the `networkx`/`igraph` comparison
using the same harness.

### 3.5 Other libraries — no change

`shapely`, `numpy`, `pygris`, `us`, `python-slugify`, `boto3`/`obstore`
(export), `aiohttp`/`tenacity` (downloads) all carry over unchanged — none of
`bikescore-bna`'s choices (`pydantic`, `pyyaml`, `hypothesis`) displace an
existing, working choice in this codebase strongly enough to justify a switch;
`pydantic` in particular would duplicate what `dataclasses` already does for
`compute.py`'s config objects (§1) without a clear win.

## 4. Reference implementation mapping (FR-REF-1)

Per-stage build/reuse/adapt assessment against `bikescore-bna` (MIT-licensed per
requirements.md §7.8, reuse permitted with attribution):

| Our stage                                               | `bikescore-bna` stage(s)                 | Decision                                             | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------------- | ---------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ingest.py`                                             | `parse`, `census`, `jobs`                | **Build independently**                              | Their approach uses `osmium` (rejected, §3.1); our `pyrosm`/`osmnx`/`pygris` path is already proven in this codebase for boundary/census/jobs acquisition (`analysis.py`, `downloader.py`) — only the OSM-to-graph-topology piece is genuinely new, and that leans on `osmnx`, not their code.                                                                                                                                                                                                                                                                                                 |
| `features.py`                                           | `attributes`                             | **Adapt approach, not code**                         | Their `attributes.py`/`intersection_attributes.py` module boundaries are a reasonable model to mirror (one module per attribute-group), but the actual per-tag derivation rules must be transcribed from _our_ SQL (`scripts/sql/features/*.sql`), not theirs, since correctness is judged against our SQL's exact behavior (NFR-PARITY), not theirs.                                                                                                                                                                                                                                          |
| `stress.py`                                             | `stress`                                 | **Adapt approach**                                   | Same rationale as `features.py`: module boundaries are a reasonable model, but the actual rules are transcribed from _our_ SQL. Our SQL is the reference implementation (requirements.md §3) — no deviation-tracking or diffing against `bikescore-bna`'s `deviations.py`; any bug in our SQL is reproduced exactly, not fixed.                                                                                                                                                                                                                                                                |
| `network.py`                                            | `graph`                                  | **Structural inspiration only** (revised post-spike) | Originally "reuse approach directly, adapt code" on the assumption we would build CSR matrices as `bikescore-bna` does. The §3.3 benchmark selected `networkx` over `scipy.sparse`, so `_make_csr()` and the CSR half of `GraphBundle` no longer apply. Their `segments_to_network()` remains worth reading for how they turn segments into a turn-expanded graph, but our topology must come from _our_ `build_network.sql` (turn angles, the right-turn `int_crossing` rule, `link_stress = greatest(...)`), which has no counterpart there. Attribute per MIT terms if any code is adapted. |
| `connectivity.py`/`destinations` scoring → `scoring.py` | `connectivity`, `destinations`, `scores` | **Build independently, structural inspiration only** | Score formulas/weights must match our SQL exactly (`category_scores.sql`, `overall_scores.sql`, `compute.py`'s `Score`/`Access`/`Tolerance` dataclasses) — these are project-specific business rules, not generic algorithms, so there's little to "reuse" beyond module organization.                                                                                                                                                                                                                                                                                                         |
| `neighborhood`/export                                   | `neighborhood`, `export`                 | **Build independently**                              | Our `exporter.py` interface/output contract (FR-EXPORT-1) is fixed by our own current file formats; not a reuse candidate.                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| N/A                                                     | `parity.py`, `validation.py`             | **Adapt directly (see §5)**                          | Process/tooling modules, not business logic — highest reuse value of anything in the reference repo. `deviations.py` is **not** adopted: our SQL is the reference implementation, so there is no external ground truth to track divergence against (requirements.md §3).                                                                                                                                                                                                                                                                                                                       |

## 5. Validation harness (NFR-VALIDATION-1)

New `just` recipe: `just validate-parity [city...]`. Default corpus depends on
phase (requirements.md §6/§7.3):

- **Iteration phase** (while stages are being actively built): `XS`/`S`
  `test_size` cities only, from `integration/e2e-cities-XS.csv` and
  `integration/e2e-cities-S.csv`, for fast feedback.
- **Pre-ship gate**: the automated corpus, `integration/e2e-cities.csv`
  restricted to `XS`/`S`/`M` `test_size` rows (NFR-VALIDATION-2). `L`/`XL`/
  `XXL` cities (Valencia, Washington DC) are excluded — with the current
  implementation they take hours per city, which is impractical for a repeatable
  automated gate. Both are instead validated manually by maintainers, as a
  stretch goal (requirements.md §7.4a), after the migration (e.g.
  `just validate-parity washington`, `just validate-parity valencia`), including
  the NFR-PERF-1 check for Washington DC. Neither manual pass is required to
  ship.

Runs `utils/validate_parity.py` (or a `brokenspoke_analyzer` test-only module):

1. For each corpus city, run the new Python pipeline end-to-end, producing the
   same output tree shape as `results/<country>/<region>/<city>/ <version>/`.
2. Load the corresponding checked-in `results/**` files (frozen ground truth per
   NFR-PARITY-3) and the freshly generated output.
3. Compare, per FR/NFR §5-6 (mapping each legacy `neighborhood_`-prefixed
   reference name to its unprefixed new-pipeline name, requirements.md
   FR-EXPORT-2 — the prefix drop is a rename, not a value it validates):
   - `neighborhood_overall_scores`/`overall_scores`-derived values: absolute
     diff ≤ `1e-4` (raw) or exact match at display precision. No skip/ exception
     list — our SQL is the reference implementation (requirements.md §3), so
     every row/column must match.
   - Row-for-row comparison of `neighborhood_census_blocks.*`/
     `census_blocks.*`, `neighborhood_ways.*`/`ways.*`, `mileage.csv`,
     `residential_speed_limit.csv` by stable key (`geoid20`/way id); numeric
     columns within tolerance; geometry columns compared via
     `shapely.geometry.base.BaseGeometry. equals_exact` with a small tolerance
     (not WKB byte-equality, matching NFR-PARITY-2's explicit allowance for
     representation differences).
4. Emit a structured pass/fail report per city + per comparison dimension (not
   just an aggregate pass/fail), so a single-city or single-column regression is
   diagnosable without re-running the whole corpus.
5. Report wall-clock time per city run. Washington DC is not part of any
   automated corpus (`XS`/`S`/`M` pre-ship gate or `XS`/`S` iteration corpus);
   the NFR-PERF-1 2x ceiling against it is checked manually by maintainers, not
   by this harness.

This harness is itself modeled on `bikescore-bna`'s `parity.py`/ `validation.py`
(architectural reuse per §4's last row), adapted to our `results/**` layout and
our tolerance rules.

## 6. Async design (NFR-ASYNC-1)

| Stage                                                                         | I/O-bound or CPU-bound?                                                                            | Concurrency approach                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `downloader.py`/`datasource.py` (OSM extract, Census, LODES downloads)        | I/O-bound                                                                                          | Already `aiohttp`/`trio`-based (unchanged) — keep as-is                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `ingest.py` (OSM parse via `pyrosm`, boundary/graph construction via `osmnx`) | CPU-bound (parsing/topology construction is compute, not I/O)                                      | Synchronous; no `async` benefit. If profiling shows it's a bottleneck on large cities, evaluate `multiprocessing` for independent sub-regions, not `async`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `features.py`, `stress.py`                                                    | CPU-bound, vectorizable                                                                            | Synchronous, vectorized `geopandas`/`pandas`/`numpy` operations (column-wise, no per-row Python loops) — no `async`, no multiprocessing needed at this granularity                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `network.py` (graph build + per-block Dijkstra)                               | CPU-bound                                                                                          | **Synchronous, single-process** (revised post-spike). Synchronous `networkx.multi_source_dijkstra_path_length` calls per census block. The existing SQL parallelizes this step 8-way (`:thread_num`/`:thread_no` in `reachable_roads_*_calc.sql`, `compute.py:331-337`), but that reflects in-database `PGR_DRIVINGDISTANCE` cost, not an inherent one: the §3.3 benchmark measured the entire stage at ~5 s for the heaviest corpus city, because the 2680 m cutoff bounds each search to a local neighbourhood. **Do not add a `ProcessPoolExecutor`** — it would add real complexity (pickling the graph to every worker, or rebuilding it per worker) to save seconds. Revisit only if a city ever measures this stage as a material share of pipeline wall-clock |
| `scoring.py` (access/category/overall scores)                                 | CPU-bound, vectorizable                                                                            | Synchronous, vectorized `pandas` operations — no `async`, no multiprocessing (this is the smallest-data stage, operating on per-block aggregates, not per-way/per-block-pair data)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `exporter.py` (write local files + optional S3 upload)                        | Mixed: local file writes are I/O but typically fast/small; S3 upload is I/O-bound over the network | Keep S3 upload async (already `obstore`/`boto3`-based per current code); local file writes stay synchronous — no benefit to making small local writes async                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| Overall pipeline orchestration (`run.py`/`run_with.py`)                       | Orchestration                                                                                      | Stays `async def` at the top level (already is, via `asyncio.run`/`trio`) so I/O-bound sub-steps (downloads, S3 export) can be awaited without blocking; CPU-bound stages are called synchronously from within that async orchestration (they block the event loop briefly, which is fine — there's nothing else to run concurrently with them in this CLI's single-run-at-a-time model)                                                                                                                                                                                                                                                                                                                                                                              |

This directly answers requirements.md's NFR-ASYNC-1 requirement to state, per
stage, whether it's async-I/O-bound, CPU-bound-vectorized, or
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
                                  # (XS/S/M rows only are the automated gate;
                                  # L/XL/XXL rows stay for manual validation)
```

`justfile` changes: remove `compose-up`/`compose-down`/`docker-build` recipes (§
requirements.md NFR-DEP-1); add `validate-parity` (§5).

## 8. Data model sketch

Illustrative, not exhaustive — full column-level schemas are a `tasks.md`- level
deliverable once each stage's SQL is transcribed.

- **Ways** (`GeoDataFrame`): one row per road segment, replacing
  `neighborhood_ways` (exported as `ways.*`, the `neighborhood_` prefix dropped
  per requirements.md FR-EXPORT-2). Columns: `way_id`, `geometry` (LineString),
  OSM tags subset (`highway`, `cycleway`, `lanes`, `maxspeed`, `oneway`,
  `width`, ...), derived feature columns (`functional_class`, `bike_infra`,
  `ft_seg_stress`, `tf_seg_stress`, ...).
- **Network vertices/links** (`pandas.DataFrame`, feeding `network.py`'s CSR
  build): `vert_id`, `road_id`, `geometry` (Point) for vertices; `link_id`,
  `source_vert`, `target_vert`, `link_cost`, `link_stress` for links — direct
  analogues of `neighborhood_ways_net_vert`/ `neighborhood_ways_net_link`
  (internal working tables, not exported — FR-EXPORT-2's rename applies to
  exported artifacts, not internal pipeline state, so these have no new-pipeline
  equivalent name to define).
- **Census blocks** (`GeoDataFrame`): `geoid20`, `geometry` (Polygon), `pop20`,
  plus per-destination-category score columns added by `scoring.py` (`*_score`,
  `*_high_stress`, ...) — analogue of `neighborhood_census_blocks` (exported as
  `census_blocks.*`, prefix dropped per FR-EXPORT-2).
- **Destinations** (`GeoDataFrame` per category): `geometry` (Point),
  category-specific attributes, clustered per `Tolerance` dataclass values.
- **Reachability result** (`network.py` output, feeding `scoring.py`): sparse
  mapping `{block_geoid: {reachable_road_ids}}`, separately for low-stress and
  high-stress graphs — analogue of
  `neighborhood_reachable_roads_{low,high}_stress`.
- **Scores** (`pandas.DataFrame`): analogue of
  `generated.neighborhood_overall_scores` (renamed `generated.overall_scores`
  per FR-EXPORT-2) — `score_id`, `score_original`, `score_normalized`,
  `human_explanation`.

## 9. Error handling

- Stage functions raise typed exceptions (a small `core/pipeline/errors.py`
  hierarchy: `IngestError`, `InsufficientDataError` (e.g. zero population,
  mirroring `ingestor.py`'s current `ValueError` on `population == 0`),
  `ReachabilityError`) rather than propagating raw `KeyError`/library exceptions
  — improves on the current SQL pipeline's undifferentiated `sqlalchemy`
  exceptions, but is not a parity requirement (internal quality improvement
  only, per requirements.md's testability driver).
- No silent fallback for missing/malformed OSM tags — mirror current SQL's
  `COALESCE(..., 0)`/`NULL`-handling behavior exactly (NFR-PARITY), don't
  "improve" default-value logic as a side effect of the rewrite. There is no
  deviation-tracking mechanism to file such a change under — our SQL is the
  reference implementation, so any intentional divergence is out of scope for
  this migration (requirements.md §3).

## 10. Testing strategy (NFR-TEST-1)

- Unit tests per stage module
  (`tests/brokenspoke_analyzer/core/pipeline/ test_*.py`) using small synthetic
  GeoDataFrames (2-5 rows) covering: one representative case per functional
  class in `stress.py` (motorway/trunk, primary, secondary, tertiary,
  residential/lower-order, living-street, track, path, link) and per feature
  rule in `features.py` — this is the concrete deliverable behind NFR-TEST-1's
  "not only covered indirectly via full-pipeline integration tests."
- `network.py` unit tests use small synthetic graphs (5-10 nodes) with hand-
  computed expected reachable sets, independent of any real city data.
- Full-pipeline integration/parity tests are the `just validate-parity` harness
  (§5) against the corpus (requirements.md §7.3) — these are slow and not part
  of `just test`'s default fast loop; wired as a separate `just` recipe/CI job,
  consistent with the user story in requirements.md §4 about not needing Docker
  for `just test`.
