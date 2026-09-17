# Tasks: SQL-to-Python Migration of the BNA Pipeline

This file contains the ordered implementation plan for replacing
`brokenspoke_analyzer/scripts/sql/**` and the PostGIS/pgRouting runtime with a
pure-Python pipeline, per `requirements.md` (WHAT) and `design.md` (HOW).

## Status

**COMPLETE** (2026-09-13). All 12 tasks done. Depends on `requirements.md`
(status: APPROVED) and `design.md` (status: APPROVED).

The pipeline runs in pure Python with no database;
`brokenspoke_analyzer/ scripts/sql/` and the PostGIS/pgRouting runtime are
deleted. The pre-ship gate is 14 of 15 corpus cities at exact parity plus one
documented deviation (requirements.md §6.1a), and it still passes after the
deletion. The stretch validation (10.3) closed on 2026-09-16 with
**Washington DC at full parity in 5 minutes against 3.2.5's 3 h 37 min**;
what it found on the way is in findings.md §1.28-1.29, §3.12 and §5a.4.

### Branch point and release

This work was built on **3.2.5** (`feature/nosql`, branched at `8a1ec91`),
which is also the version that produced every `results/**` baseline the parity
evidence rests on (findings.md §5a.2). "Parity" throughout these documents
means *parity with 3.2.5's SQL*.

It does **not** ship as 4.0.0. That release is the `uv` workspace split
(`specs/0002-uv-workspace/`, branch `issues/1143/uv-workspace`), and management
asked to keep the two breaking changes in separate releases, so this one lands
as **5.0.0** and must first be rebased onto the workspace layout.

Measured overlap between the two branches, to size that rebase: of the 96 files
this work touches that the workspace split also moves, **90 are files deleted
here** (78 SQL scripts plus the database-only CLI/core modules) and resolve as
"stay deleted"; 6 more are moved *and* modified here. Only 7 files are edited by
both branches -- `pyproject.toml`, `justfile`, `Dockerfile`, `CLAUDE.md`,
`CONTRIBUTING.md`, `utils/bna-batch.py` and `uv.lock` (regenerate that one).
The deletions are deliberately confined to a single commit, so the rename/delete
conflicts arise once rather than per commit, and
`just validate-parity --size XS --size S --size M` re-verifies the rebase
end to end in about 7.5 minutes.

**Rebase soon after 4.0.0 merges, not at release time** -- the conflict surface
grows with every week the workspace branch moves underneath this one.

### Risk acceptance

Management reviewed the risk/benefit in September 2026 and accepted it, on the
evidence that 14 of 15 corpus cities reproduce 3.2.5 exactly and that the
remaining deviation is 3 road segments traced to an `osm2pgrouting` import
artifact (findings.md §1.26, requirements.md §6.1a).

**What the change buys.** First and foremost it removes a dependency stack:
Docker, Docker Compose, PostgreSQL/PostGIS/pgRouting, `osm2pgrouting`,
`osm2pgsql`, `psql`, `pgsql2shp` and 78 SQL scripts all go, and an analysis
becomes a single `bna run` on a machine with Python and `osmium` installed.
That was the goal the spec was written for (requirements.md §1, NFR-DEP-1),
and it is unaffected by the numbers below.

**What it does not buy, as first presented.** The decision was initially
framed on an estimated 20-50x speedup. That figure was an extrapolation from
Washington DC's ~4 h SQL run against an *unmeasured* Python estimate, and the
head-to-head measurement on the corpus does not support it. `import` +
`compute` + `export` on 3.2.5 (PostGIS under Docker Desktop on macOS,
`prepare` already done) against the Python pipeline on the same machine,
2026-09-16. The first measurement prompted a profile; the second column is
after acting on it (see below):

| City | SQL (3.2.5) | Python (first) | Python (profiled) | Speedup |
| --- | --- | --- | --- | --- |
| ancienne-lorette | 15.4 s | 4.4 s | 1.3 s | 12.1x |
| rehoboth beach | 18.8 s | 3.9 s | 1.7 s | 11.0x |
| santa rosa | 24.4 s | 3.5 s | 2.8 s | 8.8x |
| provincetown | 25.0 s | 7.3 s | 4.1 s | 6.2x |
| jackson | 27.1 s | 9.6 s | 3.7 s | 7.3x |
| chambéry | 32.7 s | 41.5 s | 6.8 s | 4.8x |
| crested butte | 34.0 s | 4.6 s | 3.9 s | 8.7x |
| orange | 35.5 s | 21.0 s | 4.9 s | 7.3x |
| cañon city | 41.3 s | 11.8 s | 7.0 s | 5.9x |
| ypsilanti | 50.0 s | 30.0 s | 9.6 s | 5.2x |
| alvarado | 75.1 s | 16.7 s | 15.4 s | 4.9x |
| arcata | 77.4 s | 31.1 s | 18.8 s | 4.1x |
| st. louis park | 105.0 s | 66.1 s | 17.5 s | 6.0x |
| flagstaff | 131.4 s | 78.2 s | 21.5 s | 6.1x |
| san juan | 451.2 s | 121.7 s | 49.3 s | 9.2x |
| **corpus total** | **19.1 min** | **7.5 min** | **2.8 min** | **6.8x** |
| valencia (XL) | 283.5 s | -- | 44.2 s | 6.4x |
| **washington dc (XXL)** | **3 h 37 min** | -- | **5.2 min** | **43.8x** |

**Measured on the corpus: 6.8x overall, median 6.2x, range 4.1x-12.1x. On
Washington DC, the city the estimate was made for: 43.8x.** Two caveats pull
in opposite directions: the Python timings ran on warm caches (clipped
extract, protobuf and area index already on disk), so a cold run is somewhat
slower; and PostGIS under Docker Desktop on macOS is a slow way to run
Postgres, so on a Linux server the SQL side would look better and the ratio
smaller.

**What the profile found.** The first measurement (2.5x overall, Chambéry
*slower* than SQL at 0.8x) came from a single hot spot: a per-stage profile of
Chambéry put 92% of the run in `ingest.split_ways_at_intersections`, and all
of that in pandas row-by-row indexing (`.loc[row, col]` per node and a
`.iloc[0]` per tag per segment on a mixed-dtype frame -- 712k row lookups).
Every analysis stage together -- features, stress, network, scoring, export --
took under 10 s. Pulling each way's columns out as lists once removed it;
the parity gate is unchanged (14 PASS, Chambéry EXCEPT) and no city is now
below 4x. Ingest is the only stage that was ever slow; the ones the spec
worried about (`network.py`'s reachability, NFR-PERF-1) were never the cost.

DC is where the SQL pipeline's per-block `pgr_drivingdistance` made a run
take nearly four hours, and the Python pipeline's per-block cost is the cheap
part: the whole city runs in five minutes. The speedup grows with block count
(DC has 5,908 blocks against San Juan's 1,212), which is why the corpus
cities sit at 4-12x and DC at 44x. The original 20-50x figure was right for
the one city it was extrapolated from and wrong as a general claim; both
numbers are on record.

Against the bar the spec set -- **NFR-PERF-1, no worse than 2x slower** --
every corpus city passes with room to spare. The migration met its own
requirement; it did not meet a number that was never in the requirements, and
the record above is the correction.

## Overview

This is a big-bang rewrite (requirements.md §1): implemented as one body of
work, validated once end-to-end, not shipped stage-by-stage behind a runtime
toggle. Task ordering nonetheless follows the pipeline's own data dependencies —
`ingest → features → stress → network → scoring → export` — because each stage's
unit tests need the previous stage's output shape to exist. The routing-engine
benchmark spike (design.md §3.4) is sequenced before `network.py` since it
determines that stage's implementation, not after.

**Pre-implementation gate** (requirements.md §7.3, blocking — not a task in this
plan): every `XS`/`S`/`M` `test_size` city in `integration/ e2e-cities.csv` must
have a checked-in `results/**` baseline before task 1 starts. Do not begin
implementation until this is confirmed. Valencia, Spain (`XL`) now has a
checked-in `results/**` baseline too (generated after requirements.md's initial
approval), though it's not required for this gate — it's not part of the
automated corpus (below) regardless. Washington DC (`XXL`) is likewise not
required — it takes ~4 hours to process; its baseline and manual validation
pass, and Valencia's manual validation pass, are both a stretch goal
(requirements.md §7.4a, task 10.3 below), not a precondition for starting.

**Baseline data issue — Ypsilanti has two result directories.**
`results/united states/michigan/ypsilanti/` contains both `26.09` (16 files,
**incomplete**: every stress column NULL, no `neighborhood_overall_scores.csv`)
and `26.09.1` (32 files, complete). Every other city has exactly one complete
32-file directory. Comparing against `26.09` silently passes the feature columns
-- they are fully populated -- and only fails at stress, so the partial baseline
is easy to miss. **The parity harness (task 9.1) must select the newest complete
version directory per city rather than assuming `26.09`.** Consider deleting the
stale `26.09` directory to remove the trap.

**Validation corpus during iteration**: use only `integration/e2e-cities-XS.csv`
and `integration/e2e-cities-S.csv` cities (design.md §5) for all per-task
verification below. The automated pre-ship gate (task 9/10) uses
`integration/e2e-cities.csv` restricted to `XS`/`S`/`M` `test_size` rows.
`L`/`XL`/`XXL` cities (Valencia, Washington DC) are excluded from all automated
runs in this plan — they take hours per city with the current implementation.
Both cities' manual validation after the migration ships is a stretch goal, not
required (requirements.md §7.4a); Washington DC's `results/**` baseline is not
required by the pre-implementation gate above either, while Valencia's baseline
already exists (generated after requirements.md's initial approval), making its
manual follow-up possible but still optional.

**`prepare` stays as-is**: the `prepare` stage works well today and is not being
rewritten. `ingest.py` (task 3) is a consumer of `prepare`'s existing file
outputs (OSM extract, boundary, census blocks, jobs/speed CSVs), not a
replacement for any part of it — see task 3.0.

**Findings live in `findings.md`**, not inline here. Every non-obvious SQL
semantic, pandas trap, and pipeline-structure discovery made while transcribing
is written up there, with what it cost and which test pins it. Read it before
changing a pipeline rule -- several look like bugs unless you know they were
deliberate, and **task 11 has now deleted the SQL they describe**, so that file
is the only record.

## Tasks

- [x] 1. Benchmark spike: routing/reachability engine (design.md §3.4) — **DONE.
     Outcome: `networkx`, not `scipy`** (design.md §3.3).
  - [x] 1.1 Write a throwaway spike script (not shipped, e.g.
        `utils/spike_routing_benchmark.py`) that builds a CSR adjacency matrix
        for a small synthetic graph and for one real corpus city. _Done; ran off
        the checked-in `results/**` exports, so it needed no database and no
        `prepare` run._
  - [x] 1.2 Run reachability with both `scipy.sparse.csgraph.dijkstra`
        (`indices=[source], limit=cutoff`) and `networkx.single_source_dijkstra`
        with `cutoff`, on the same input, for the 3 cities named in design.md
        §3.4 (one XS, one S/M, and Washington DC for the perf ceiling check).
        _Done, with two deviations (design.md §3.4): **multi-source** Dijkstra
        on both sides, since the SQL seeds from a 0-cost super-source; and **San
        Juan + Valencia in place of Washington DC**, which has no baseline. San
        Juan is the heaviest reachability workload in the corpus — the stage
        scales with block count, not road count._
  - [x] 1.3 Confirm numerically identical reachable-sets between the two
        approaches (validates CSR construction, not just algorithm choice).
        _Done: identical on all 3 cities, both stress subgraphs._
  - [x] 1.4 Record wall-clock time and peak memory for both approaches on
        Washington DC specifically (NFR-PERF-1's binding constraint). _Done on
        San Juan instead. Heaviest city: scipy 1.29 s vs networkx 5.08 s for the
        whole stage; per-engine peak-memory delta ~0 MiB for both. The stage is
        not a bottleneck at corpus scale._
  - [x] 1.5 Update design.md §3.3 with the measured result: confirm
        `scipy.sparse.csgraph.dijkstra`, or record the fallback decision if it
        underperforms. Delete the spike script once §3.3 is updated. _Done: §3.3
        records the measurement and the reversed decision, §3.4 records the
        spike's carry-forward findings, §4 and §6 updated for consistency. Spike
        script deleted; `scipy` removed again from the dev dependencies._
  - _Requirements: FR-NET-1, FR-NET-2, FR-NET-3, NFR-PERF-1_

- [x] 2. Scaffold `core/pipeline/` package (design.md §7) — **DONE**
  - [x] 2.1 Create `brokenspoke_analyzer/core/pipeline/__init__.py`.
  - [x] 2.2 Create `brokenspoke_analyzer/core/pipeline/errors.py` with
        `IngestError`, `InsufficientDataError`, `ReachabilityError` (design.md
        §9). _Added a `PipelineError` base so callers can catch the whole family
        with one `except`._
  - [x] 2.3 Create `brokenspoke_analyzer/core/pipeline/config.py` and move
        `Tolerance`, `PathConstraint`, `BlockRoad`, `Score`, `Access` from
        `core/compute.py` into it unchanged (requirements.md §7 open question #2
        — these remain the single source of truth for runtime constants). _Moved
        verbatim; `compute.py` re-exports them so the SQL path keeps working
        until task 11 deletes it._
  - [x] 2.4 Create empty `tests/brokenspoke_analyzer/core/pipeline/` mirror
        directory with `test_ingest.py`, `test_features.py`, `test_stress.py`,
        `test_network.py`, `test_scoring.py` stubs. _Stubs carry a skipped
        placeholder naming the task that fills them, so pending work shows up in
        test output. Also added real `test_config.py`/`test_errors.py` covering
        the code 2.2/2.3 actually delivered — including a guard that `compute.*`
        resolves to the moved dataclasses rather than a stale copy._
  - _Requirements: NFR-TEST-1_

    **Note for task 7.1:** the `Access(...)` instances in
    `compute.py:connectivity()` (`Access("colleges", first=0.7)` and the twelve
    others) carry per-destination scoring weights that are just as authoritative
    as the `Score` weights, and are still literals inside the SQL orchestration
    function. They belong in `config.py` too; move them when task 7.1 ports
    access scoring.

- [x] 3. `ingest.py` — OSM parsing and routable graph (FR-ING-1, FR-ING-2) —
     **DONE.** Census block counts and populations match `results/**` exactly
     for Crested Butte, Santa Rosa, and Ancienne-Lorette (US and non-US paths).
     Two design corrections recorded in design.md §3.1: `pyrosm` cannot read
     `prepare`'s OSM **XML** (converted via `osmium cat` first), and neither
     `osmnx` nor `pyrosm` reproduces `osm2pgrouting`'s segmentation, so the
     splitting rule is implemented here rather than taken from a library.
  - [x] 3.0 **`prepare` is unchanged and is the input boundary for `ingest`.**
        `prepare` (`analysis.py`/`downloader.py`/ `datasource.py`) already works
        well and is explicitly out of scope for this migration (requirements.md
        §3) beyond feeding the new `ingest` step. `ingest.py` must consume the
        files `prepare` already produces on disk — the extracted city OSM PBF
        (`analysis.prepare_city_file`'s `pfb_osm_file` output, itself clipped by
        `osmium extract` from the region file using the boundary polygon), the
        boundary shapefile/GeoJSON (`retrieve_city_boundaries`), the census
        block shapefile/zip (`simulate_census_blocks` or the real Census
        download), and the jobs/speed CSVs — rather than re-downloading,
        re-extracting, or re-deriving any of that data itself. Confirm the exact
        `prepare` output paths/filenames by reading
        `analysis.py`/`downloader.py`/ `datasource.py` before writing
        `ingest.py`, and treat them as a fixed contract.
  - [x] 3.1 Read the OSM extract (PBF) produced by `prepare` (3.0) into
        GeoDataFrames of ways/nodes via `pyrosm` (design.md §3.1), preserving
        every tag currently consumed by `scripts/sql/features/*.sql` (highway
        class, cycleway/bike lane tags, lanes, maxspeed, oneway, width, surface,
        crossing/signal tags — enumerate exhaustively from the SQL, not from
        memory).
  - [x] 3.2 Build topology (node sharing, direction, source/target vertex IDs)
        via `osmnx`, replacing `osm2pgrouting`'s two-config (highway + cycleway)
        graph build in `ingestor.py:import_osm_data`.
  - [x] 3.3 Load the census blocks and jobs data already produced/fetched by
        `prepare` (3.0) into GeoDataFrames/DataFrames (replacing the `shp2pgsql`
        boundary/block import and the LODES CSV import path, which are the only
        things changing — the acquisition logic in `analysis.py` stays as-is per
        requirements.md §3).
  - [x] 3.4 Raise `InsufficientDataError` on zero population, mirroring
        `ingestor.py`'s current `ValueError` (design.md §9).
  - [x] 3.5 Unit tests: small synthetic OSM extract (2-5 ways) covering at least
        one tag from each category in 3.1; assert preserved tags and correct
        topology (source/target, direction) on a hand-verified expected graph.
  - _Requirements: FR-ING-1, FR-ING-2, NFR-TEST-1_

- [x] 4.  `features.py` — per-way attribute derivation (FR-FEAT-1) — **DONE.**

      The `ways` layer matches the baseline **exactly on all 15 `XS`/`S`/`M`
      corpus cities**: same rows, same geometry, and every one of the 30
      published columns (task 9.3, task 10.1). Chambéry's long-standing +3
      segments turned out to be an `osm2pgrouting` import artifact rather
      than anything this stage does, and is scoped out of NFR-PARITY-1
      (4.5a, findings.md §1.26).

          Two late corrections came out of the parity harness rather than this
          stage's own checks: the published `oneway` label carries
          `osm2pgrouting`'s implied one-way rules (findings.md §1.15, §1.25), and
          `line_merge` starts a closed ring wherever it likes (§2.9).

          The findings from this stage -- the any-kind segmentation rule, the
          inline `compute.py` delete, the osmconvert clip, pandas NULL
          propagation, and unrequested tags -- are written up in findings.md
          §3.1, §1.4, §3.2, §2.1 and §2.2 respectively.

          Transcribe each rule into vectorized `geopandas`/`pandas` column
          derivations, one function per attribute group (module-boundary model
          borrowed from `bikescore-bna`'s `attributes.py`, design.md §4).
          Sub-tasks follow `compute.features()`'s execution order, which is part
          of the definition: later scripts overwrite columns earlier ones set.
  - [x] 4.1 `clip_osm.sql` — drop roads beyond `nb_boundary_buffer` of the
        boundary.
  - [x] 4.2 `one_way.sql` — `one_way_car` from the `oneway` tag.
  - [x] 4.3 `width_ft.sql` — `width_ft` from the `width` tag, four passes (feet,
        feet+inches, metres, unitless-as-metres).
  - [x] 4.4 `functional_class.sql` — nine classification updates in order, then
        the NULL-class and orphan `DELETE`s that decide which roads exist at
        all.
  - [x] 4.5 Close the residual road-count gap. _Done: three separate causes
        (findings.md §1.4, §3.2, §2.1) — the inline bicycle-path delete in
        `compute.py`, the missing `osmconvert` census-block-bbox clip, and
        pandas NULL propagation in tag masks. 12 of 13 cities now exact._
  - [x] 4.5a **Chambéry residual: +3 segments of 7,212 — RESOLVED as a scoped
        parity exception** (requirements.md §6.1a, findings.md §1.26).

        A PostGIS run settled it: **no SQL deletes those segments --
            `osm2pgrouting` never imported them.** The raw
            `received.neighborhood_ways` already has 1 row for way `1038105016`
            against the OSM way's 3 edges, and the missing edges are in the table
            under the *pedestrian plaza* that traces the same kerb.

            Duplicate edges are normally kept (242 of them in that same import),
            and the behaviour is deterministic. Bisecting a local
            `osm2pgrouting` 3.0.0 against the extract found the trigger: at
            **20,000 ways in the file all 3 rows survive; at 20,001 two are
            dropped** -- with *any* way as the 20,001st, including a
            `barrier=hedge` that is never imported. It is a chunk-boundary
            artifact of the importer, keyed to a way's ordinal position in the
            file, and it moves whenever the extract changes.

            Not reproduced, deliberately: emulating it would encode an importer
            bug whose effect changes with the next data refresh. Scoped out of
            NFR-PARITY-1 for Chambéry.

  - [x] 4.6 `paths.sql` — cluster contiguous `path` roads into
        `neighborhood_paths`, set `path_id` on each road, and record
        `path_length`/`bbox_length` (the recreation-access `PathConstraint`
        reads them). Deletes nothing. _`ST_ClusterIntersecting` reproduced as
        connected components over a geopandas `intersects` self-join._
  - [x] 4.7 `speed_limit.sql` — mph verbatim, km/h converted and rounded to the
        nearest 5. _The state/city CSV defaults are **not** here: the SQL leaves
        the column NULL and the stress scripts apply the jurisdiction default,
        so that belongs to task 5._
  - [x] 4.8 `lanes.sql` — the five lane columns, via one ordered CASE ladder per
        direction.
  - [x] 4.9 `park.sql` — on-street parking per side. _Matched on first run.
        **The "both" pass has no lasting effect**: `park.sql` runs three
        sequential updates, and the later right/left passes assign their `CASE`
        result \_unconditionally_, so a road with no side tag has whatever
        `parking:lane:both` just set overwritten with NULL. `ft_park` therefore
        depends only on the right-hand tags and `tf_park` only on the left.
        Reproduced, not corrected.\_
  - [x] 4.10 `bike_infra.sql` — bike infrastructure per direction, the `one_way`
        bike-direction column, and the facility widths. _Done, the largest
        script in the migration at 639 lines. Structured as a shared "both
        kerbs" prefix plus three `one_way_car` branches per direction, evaluated
        by an ordered first-match rule list (`features._first_match`). Two
        things the transcription had to preserve:_

        - _**A dead branch.** Inside `tf_bike_infra`'s `one_way_car = 'ft'`
              block, two rules are guarded on `one_way_car = 'tf'` and can never
              fire. This is the copy-paste slip `bikescore-bna` documented
              (requirements.md §1a); per §3 it is reproduced, not repaired, and
              `test_unreachable_tf_guard_is_reproduced` pins it._
            - _**The ft/tf ladders are not quite mirrors.** `tf`'s
              `cycleway = 'lane'` rule carries an extra `cycleway:left:oneway`
              check that `ft`'s counterpart lacks, and `ft`'s
              `cycleway:{other} = 'buffered_lane'` rule carries an `oneway`
              check that `tf`'s lacks. Regularising either would change
              output._

  - [x] 4.11a `class_adjustments.sql` — promote busy residential and
        unclassified roads to tertiary. _Far more consequential outside the US
        than it reads: a 50 km/h Australian residential street converts to 31
        mph and trips the `speed_limit >= 30` branch, reclassifying 2,250 of
        Orange's roads versus 6 in Jackson._
  - [x] 4.11b `legs.sql` — leg count per intersection.
  - [x] 4.12 `signalized.sql`, `stops.sql`, `rrfb.sql`, `island.sql` —
        intersection-level flags. _Needed two new ingest readers: `read_nodes()`
        for intersection geometry and `read_point_features()` for the tagged
        nodes (`OSM_POINT_TAGS`), which are a **separate tag set** from
        `OSM_WAY_TAGS` — they describe points and land in osm2pgsql's point
        table. Intersections are built from the surviving roads' endpoints,
        which also covers `functional_class.sql`'s "remove obsolete
        intersections" delete for free. Note the signal/stop propagation rule
        runs **once**, not transitively._
  - [x] 4.13 `calculate_mileage.sql` — `mileage.csv`. _Matched exactly on every
        city tested. A road with a facility in both directions contributes its
        length **twice**: these are directional facility miles, not centreline
        miles._
  - [x] 4.14 Confirm `features/streetlight/*.sql` is not ported (dead code,
        requirements.md §7 open question #6 — out of scope). _Confirmed: no
        reference to it anywhere in `core/` or `cli/`._
  - [x] 4.15 Unit tests: one representative synthetic case per feature rule,
        matching NFR-TEST-1's explicit per-rule coverage requirement (not just
        full-pipeline coverage). _152 tests. Several pin reproduced SQL quirks
        so a later reader cannot "fix" them by accident: the dead
        `one_way_car='tf'` guard, `park.sql`'s overwritten "both" pass, the
        `paralell` misspelling, and `access=private` being rejected even for
        designated bikes._
  - [x] 4.16 Column-level validation against `results/**`, not just row counts:
        for each derived column, compare per `road_id`/`osm_id` against the
        checked-in `neighborhood_ways` export. Row counts matching does not mean
        the values do.

        _Superseded by the parity harness (task 9.1), which does this per
            column for every published layer across the whole corpus: **15 of 15
            cities match**, Chambéry included once its 3 import-artifact rows are
            excluded (4.5a). Two cautions learned here are written up as
            findings.md §4.3 (compare against the right column) and §1.1 (check
            the SQL column type, not just the expression)._

  - _Requirements: FR-FEAT-1, FR-FEAT-2, NFR-TEST-1_

- [x] 5. `stress.py` — stress classification (FR-STRESS-1) — **DONE.** Segment
     stress matches 7 of 8 cities tested and intersection stress matches 7 of 7
     (Chambéry differs only via its 4.5a rows).

     Cities verified: Crested Butte, Santa Rosa, Jackson, Orange, St. Louis
     Park, Arcata, Ypsilanti. See findings.md §1.9 for the residential
     speed-default precedence, which decides every untagged residential
     street's rating.
  - [x] 5.1 Transcribe `scripts/sql/stress/*.sql` rules into vectorized
        stress-rating derivation, covering every functional class
        (motorway/trunk, primary, secondary, tertiary, "lesser", link,
        living-street, track, path) plus intersection and one-way-reset
        adjustments. - [x] Segment stress: `stress_motorway-trunk`,
        `_segments_higher_order` (primary/secondary/tertiary, each with its own
        assumed speed and lane defaults), `_segments_lower_order` and its `_res`
        variant, `_living_street`, `_track`, `_path`, and `_one_way_reset`. Note
        the one-way reset keys off `one_way` (the _bike_ direction), not
        `one_way_car`, so a street with contraflow bike infrastructure keeps
        both directions rated. - [x] Intersection stress:
        `stress_tertiary_ints.sql` (652 lines), `stress_lesser_ints.sql` (956
        lines), plus the small `_motorway-trunk_ints`, `_primary_ints`,
        `_secondary_ints`, and `_link_ints`. _**The two big scripts share one
        rule table.** 1,608 lines of nested CASE collapse to a single
        parameterised function: they differ only in which road classes they rate
        and whether a `tertiary` crossing counts. The table was extracted by
        flattening and parsing the SQL rather than read by eye, which is the
        only safe way at that depth of nesting. Matches 7/7 cities._
  - [x] 5.2 Reproduce our SQL's behavior exactly, including any bugs it contains
        — there is no deviation-tracking mechanism in this project
        (requirements.md §3); do not "fix" anything found here.
  - [x] 5.3 Unit tests: one representative synthetic case per functional class
        in 5.1 (NFR-TEST-1).
  - _Requirements: FR-STRESS-1, NFR-TEST-1_

- [x] 6.  `network.py` — graph build & reachability (FR-NET-1/2/3) — **DONE.**
      **6 of 8 cities reproduce `neighborhood_connected_census_blocks.csv`
      exactly** — every block pair, every low-stress flag, and every cost.
      Crested Butte and Cañon City differ on 0.2-0.3% of costs (mixed sign, so
      alternate-path ties rather than a systematic error).

      **The whole gap was one SQL integer-division trap.** In
      `build_network.sql`, `source_road_length` and `target_road_length` are
      declared **INTEGER**, so each `ST_Length` is rounded on assignment and
      `(source_road_length + target_road_length) / 2` is _integer division_ --
      it truncates, and the outer `round()` does nothing. Computing
      `round((a + b) / 2)` at full precision instead inflates every link by
      up to half a unit. On one link that is invisible; along a path it
      compounded to about +0.8% (correlation 0.76 with path length), which
      pushed block pairs sitting near the 2680 m cutoff out of range
      entirely. Fixing it took cost agreement from 14% to 100% on six cities.
      This is the second time a **column type**, not an expression, carried
      the semantics -- see 4.16's note.

          **Tie measurement for 6.3 (was required before assuming parity):**
          ambiguous right-turn groups are 0/999 (Crested Butte), 0/1,123 (Santa
          Rosa) and 1/3,777 (Jackson) -- **0.03% worst case**. Exact parity is
          therefore achievable and no NFR-PARITY-1 exception is needed.

          Rewritten after task 1's spike (design.md §3.3/§3.4), which prototyped
          this stage end-to-end and settled the engine. The graph is a
          **turn-expanded (dual) graph**: vertices are roads, edges are permitted
          turns between roads meeting at an intersection. Not a road-segment
          graph — getting this wrong invalidates every cost.
  - [x] 6.1 Build the vertices, equivalent to `build_network.sql`'s
        `neighborhood_ways_net_vert`: exactly **one vertex per road**,
        positioned at `ST_LineInterpolatePoint(geom, 0.5)`. (The `vert_cost`
        column exists in the SQL but is never populated — do not port it.)
        Because there is one vertex per road, the reachability output is one row
        per `(block, reachable road)` with no de-duplication needed.
  - [x] 6.2 Build the links, equivalent to `build_network.sql`'s nine `INSERT`
        branches. Those nine collapse to **three "may depart into intersection
        `i`" cases crossed with three "may be entered from intersection `i`"
        cases** (verified equivalent to all nine during the spike): - depart:
        `one_way IS NULL` → `i in (int_from, int_to)`; `'ft'` → `i = int_to`;
        `'tf'` → `i = int_from` - enter: `one_way IS NULL` →
        `i in (int_from, int_to)`; `'ft'` → `i = int_from`; `'tf'` →
        `i = int_to`

        with `road1 != road2`. Then derive, per link:
            - `link_cost = round((source_road_length + target_road_length) / 2)`,
              **rounding half away from zero** (PostgreSQL's `round`), not
              Python/NumPy's half-to-even.
            - `source_road_dir = 'ft' if int_id == source.int_to else 'tf'`;
              `target_road_dir` likewise from the target road.
            - azimuths and `turn_angle = (target_azi - source_azi + 360) % 360`,
              with `ST_Azimuth`'s north-based clockwise convention.
            - `link_stress = greatest(source_stress, int_stress, target_stress)`
              where `source_stress` is `ft_seg_stress` when departing `ft` else
              `tf_seg_stress`, and `target_stress` is **reversed** relative to
              the source (`tf_seg_stress` when entering at the road's `to` end).

  - [x] 6.3 Implement the `int_crossing` right-turn rule: per
        `(source_road_id, int_id)` the single best-ordered link gets
        `int_crossing = FALSE`, hence `int_stress = 1`, and its `link_stress` is
        recomputed. Order by `sin(radians(turn_angle)) > 0` descending, then by
        `cos(radians(turn_angle))` ascending when `sin > 0` else `-cos(...)`
        ascending. **Parity risk (design.md §3.4, finding 3):** the SQL selects
        this link with `LIMIT 1` over an `ORDER BY` that does not break ties, so
        where two turns share an order key, Postgres' choice is arbitrary and
        unmatchable in principle. Before assuming this is negligible, **measure
        how many `(source_road, int_id)` groups actually tie** on a few corpus
        cities, and record the number here. Only if it is zero (or provably
        cannot change `link_stress`) is exact parity achievable; otherwise raise
        it as a scoped exception to NFR-PARITY-1 rather than silently diverging.
  - [x] 6.4 Implement per-census-block reachability with
        **`networkx.multi_source_dijkstra_path_length`** (task 1's measured
        choice — do **not** use `scipy`/CSR, design.md §3.3), run separately
        over the low-stress subgraph (`link_stress = 1`) and the full all-stress
        graph (no filter). - Seeds per block come from `block_verts.sql`: the
        vertices of the roads in `census_blocks.road_ids`, restricted to roads
        intersecting the boundary. The SQL's 0-cost super-source is exactly
        multi-source Dijkstra — **not** `single_source_dijkstra`. - Cutoff is
        **`nb_max_trip_distance`** (`cli/common.py`'s
        `DEFAULT_MAX_TRIP_DISTANCE = 2680`), _not_ `PathConstraint` — an earlier
        draft of this task named the wrong constant.
        `PathConstraint.min_length`/`min_bbox` govern recreation-path
        eligibility, a different rule entirely. - Reproduce the calc's block
        filter: only blocks whose geometry intersects the boundary. - A NULL
        `link_stress` fails `= 1` but survives the unfiltered high-stress query
        (design.md §3.4, finding 2) — `greatest()` returns NULL only when all
        three inputs are NULL.
  - [x] 6.5 **Do not parallelize.** Task 1 measured the whole stage at ~5 s for
        the heaviest corpus city; the SQL's 8-way `:thread_num`/`:thread_no`
        split reflects in-database `PGR_DRIVINGDISTANCE` cost, not an inherent
        one. A `ProcessPoolExecutor` would add graph-pickling or per-worker
        rebuild cost to save seconds (design.md §6). Keep it synchronous and
        single-process; revisit only on a measured regression.
  - [x] 6.6 Ensure all length/azimuth computation happens in the **projected
        output CRS** (`nb_output_srid`), never EPSG:4326. Deriving `link_cost`
        from geographic coordinates rounds every cost to 0 with no error raised
        (design.md §3.4, finding 1) — add a guard that rejects a geographic CRS
        outright.
  - [x] 6.7 Raise `ReachabilityError` on failure conditions mirroring the
        current SQL/pgRouting error paths (design.md §9).
  - [x] 6.8 Unit tests: small synthetic graphs (5-10 nodes) with hand- computed
        expected reachable sets, independent of real city data. Cover
        explicitly: a one-way pair that must not be traversable in reverse, a
        link at exactly the cutoff distance, a NULL-stress link (excluded from
        low-stress, included in high-stress), and a disconnected component.
  - _Requirements: FR-NET-1, FR-NET-2, FR-NET-3, NFR-PERF-1, NFR-TEST-1_

- [x] 7.  `scoring.py` — access, category, and overall scoring — **DONE.**

      **Every scored column now matches the baseline on 10 of the 11 XS/S
      corpus cities** -- all 13 destination categories, all 17 access scores,
      the category rollups, the per-block `overall_score` and the 23-row
      headline table. Task 9.3 has the corpus run.

          Getting there took nine separate rules, every one of them invisible in
          the phrase "extract the destinations". They are written up in
          findings.md; the short version:

          - **Destinations are clustered** (§3.3), and **transit clusters its
            points but not its polygons** (§1.24).
          - **`AND` after an unparenthesised `OR` binds to the last branch only**
            (§1.21), so a node tagged `amenity=dentist` inside a dentist polygon
            is counted twice while the same node tagged `healthcare=dentist` is
            not. Encoded per branch as `MatchBranch.guarded`.
          - **`NOT (NULL AND NULL)` is NULL** (§1.22), which is what excludes a
            bare `public_transport=station` -- and resolves the open discrepancy
            over Jackson's six ski gondolas (findings.md §5a.1), without the
            PostGIS run it was waiting on.
          - **`osm2pgsql` ran without `--multi-geometry`** (§3.7), so a
            three-part nature reserve is three destinations, not one.
          - **An invalid ring never reached PostGIS** (§3.8) -- and `pyrosm`
            repairs those silently, so the check has to run libosmium's own area
            assembler rather than look at the geometry in hand.
          - **An unclosed way is a line, and lines are not destinations** (§3.9).
          - **A destination belongs to the blocks its centroid touches too**
            (§3.10).
          - **Employment is weighted by the whole population** (§1.23), unlike
            every other member.
          - **The city's headline score is not a rollup** of the category scores
            at all (§1.19), and the rollups read *rounded* inputs (§1.18) with
            PostgreSQL's half-away-from-zero rule (§1.20).

          **Still open (not blocking):** `score_inputs.sql`'s ~110 *diagnostic*
          rows, needed for `neighborhood_score_inputs.csv` file parity
          (NFR-PARITY-2) but not for any score -- only 16 of its rows carry a
          `use_*` flag and those are done (findings.md §1.13).
  - [x] 7.1 Implement per-destination-category access scoring (FR-ACCESS-1) for
        every category in requirements.md §2.5, using the
        low-stress-vs-high-stress reachability comparison logic from
        `connectivity/access_*.sql`, consuming `network.py`'s reachability
        output and `Tolerance`/`Access` from `core/pipeline/config.py`. _Done:
        one parameterised function for all 13 destination categories plus one
        for the 17 access scripts, which are byte-identical modulo the category
        name._
  - [x] 7.2 Implement category score combination (FR-SCORE-1) using the exact
        weights from `Score` (`people=15, opportunity=20, core_services=20,
retail=15, recreation=15, transit=15`, requirements.md §7 open
        question #2) and the "drop categories with no
        reachable destinations, renormalize remaining weights" logic from
        `category_scores.sql`/`overall_scores.sql`. _Done:
        `scoring.derive_category_scores()`; the divisor counts only members the
        city actually has._
  - [x] 7.3 Implement the population-weighted overall score (FR-SCORE-2): score
        × `pop20`, normalized by total reachable population. _Done:
        `scoring.population_weighted_score()`. Note the divisor counts only
        blocks that can reach \_something_ in that category.\_
  - [x] 7.4 Produce the same summary row shape as
        `generated.neighborhood_overall_scores` (renamed
        `generated.overall_scores`, FR-EXPORT-2 — FR-SCORE-3): per-category
        scores, `population_total`, `total_miles_low_stress`,
        `total_miles_high_stress`, mileage rounded to 1 decimal place. _Done:
        all 23 rows, including the directional, boundary-clipped mileage totals
        (findings.md §1.11)._
  - [x] 7.5 Unit tests: representative synthetic cases per category (including
        the "no reachable destinations" renormalization edge case) and for the
        population-weighting formula. _Done: `TestDestinationScore`,
        `TestStepScore`, `TestCategoryScores`, `TestBlockJobs`,
        `TestClusterWithin`._
  - [ ] 7.6 `score_inputs.sql`'s remaining ~110 diagnostic rows, for
        `score_inputs.csv` file parity (NFR-PARITY-2). Deferred: they feed no
        score (findings.md §1.13), so they gate file-level parity only. The
        parity harness reports the file as absent rather than silently passing
        it.
  - _Requirements: FR-ACCESS-1, FR-SCORE-1, FR-SCORE-2, FR-SCORE-3, NFR-TEST-1_

- [x] 8.  Wire the new pipeline into the CLI and exporter — **DONE** (except the
      prose docs, deliberately deferred to task 11.5). `bna run` now runs the
      whole analysis with **no `DATABASE_URL`, no PostGIS and no Docker** --
      Crested Butte end to end in about 5 seconds, writing the calver tree.

      `core/pipeline/export.py` writes the published file set from the
      in-memory frames. **23 of 24 files are produced, and every layer the
      parity harness compares is identical to the baseline** across the XS/S
      corpus (task 9.3) -- schema, row set and values. The only missing file
      is `score_inputs.csv`, which needs `score_inputs.sql`'s ~110 diagnostic
      rows (task 7.6).

          Three PostgreSQL spellings had to be reproduced here rather than in the
          analysis: booleans as `t`/`f` and `INTEGER` columns without a trailing
          `.0` in the CSVs, and `osm2pgrouting`'s `oneway` labels
          (findings.md §1.15, §1.25).

          Two artifacts of the old import path had to be reproduced rather than
          dropped: a `gid` serial primary key `shp2pgsql` added, and lower-cased
          column names because PostgreSQL folds unquoted identifiers
          (findings.md §3.5).

          Also implemented here: `access_overall.sql`'s **per-block**
          `overall_score`, a different computation from the city's headline score
          (findings.md §3.6) *and* from the `*_category_score` columns beside it
          (§1.17). Exact on every corpus city.
  - [x] 8.1 Update `exporter.py` to consume GeoDataFrames/DataFrames in memory
        instead of querying PostGIS tables, producing byte-for-byte the same
        schema/column names/order/row contents as today but with the
        `neighborhood_` prefix dropped from file names (FR-EXPORT-1,
        FR-EXPORT-2): `neighborhood_census_blocks.*` →`census_blocks.*`,
        `neighborhood_ways.*` → `ways.*`,
        `neighborhood_ways_intersections.geojson` →
        `ways_intersections.geojson`, `neighborhood_boundary.geojson` →
        `boundary.geojson`; `mileage.csv`/`residential_speed_limit.csv` (already
        unprefixed) unchanged. _Implemented as `core/pipeline/export.py` rather
        than by editing `exporter.py`, so the new pipeline carries no database
        imports; task 11 folds in or removes `exporter.py`'s PostGIS half._
  - [x] 8.2 Replace `bna run-with compose <country> <city> <region> <fips_code>`
        with `bna run <country> <city> <region> <fips_code>` (design.md §2) — no
        Docker Compose, no `DATABASE_URL`, chaining
        `prepare → ingest → features → stress → network → scoring → export` as
        plain async orchestration (design.md §6's "overall pipeline
        orchestration" row). _Added `core/pipeline/orchestrator.py`, the shipped
        form of the harness used to validate tasks 3-7, plus a `--skip-prepare`
        flag for re-running the analysis against files already downloaded. Only
        the top level is `async`: `prepare`'s downloads and the S3 upload are
        I/O-bound, the analysis stages are CPU-bound and gain nothing from
        `await`._
  - [x] 8.3 Keep `downloader.py`/`datasource.py` async I/O paths unchanged
        (design.md §6); ensure they're awaited from the new `run.py` flow.
        _`prepare.prepare_()` is awaited unchanged. The S3/R2 upload now uploads
        the directory just written rather than re-exporting from the database,
        so the published files are exactly the ones verified locally.\_
  - [x] 8.4 Update CLI help text/docs referencing `run-with compose` or
        `DATABASE_URL` to match the new no-database flow. _CLI help done: `run`
        is now "Run a full analysis. No database required." and `run-with` is
        marked deprecated. **`README.md` and `CLAUDE.md` are deliberately left
        to task 11.5**, which removes `run-with` and the `DATABASE_URL`
        requirement outright -- rewriting them now would document a half-removed
        state._
  - _Requirements: FR-EXPORT-1, NFR-DEP-1, NFR-ASYNC-1_

- [x] 9. Checkpoint — iteration-phase parity validation — **DONE.**
     `utils/validate_parity.py` + `just validate-parity`; **all 11 XS/S cities
     at full parity on all seven dimensions** (see 9.3).
  - [x] 9.1 Implement `utils/validate_parity.py` (design.md §5): run the new
        pipeline per corpus city, compare against checked-in `results/**` per
        NFR-PARITY-1/2/3 (absolute `1e-4` on raw scores, exact match at display
        precision, row-for-row file comparison, geometry via `equals_exact` with
        tolerance), emit a structured per-city/per-dimension pass/fail report.
        _Seven dimensions: `overall_scores`, `census_blocks`, `ways`,
        `ways_intersections`, `connected_census_blocks`, `mileage`,
        `residential_speed_limit`. Three things the design did not
        anticipate:_ - _**`road_id` and `int_id` are not keys.** Both are
        database sequences, so the two pipelines number the same road
        differently and there is nothing to join on. Spatial rows pair on
        geometry instead -- OSM way id plus sorted endpoints plus length -- and
        the surrogate columns are excluded from the comparison rather than
        reported as differences._ - _**`equals_exact` is not enough on its
        own.** PostGIS typed its columns `MULTI*`, so every reference block is a
        MultiPolygon and every road a MultiLineString; `equals_exact` compares
        structure and calls that a difference, while `equals` is
        exact-arithmetic and trips on the fourteenth decimal of a reprojection.
        The harness accepts any of the three tests, including Hausdorff
        distance._ - _**Reference `t`/`f` and `True`/`False` are the same
        value.** Fixed in `export` rather than papered over in the harness --
        downstream consumers parse the PostgreSQL spelling._
  - [x] 9.2 Add `just validate-parity [city...]` recipe, defaulting to the
        `XS`/`S` corpus (`integration/e2e-cities-XS.csv`,
        `integration/e2e-cities-S.csv`) per design.md §5. _`--size` selects
        other corpora, `--json` writes the report as JSON for task 10._
  - [x] 9.3 Run `just validate-parity` against the XS/S corpus and fix any
        discrepancy in tasks 3-7 before proceeding — do not move on to task 10
        with a known parity gap in the iteration corpus.

        _**11 of 11 cities at full parity**, across all seven dimensions --
            every way, every intersection, every census block, all 1.5 M San Juan
            block pairs, and all 23 headline scores. Corpus wall clock: 4 s to
            2 min per city, about 4 minutes in total._

            _Sixteen defects surfaced here that eight cities of ad-hoc
            column-comparison had not, and **none of them was in the stage that
            looked wrong**. Two examples: Crested Butte's city score moved because
            geopandas draws a buffer with twice as many segments as PostGIS
            (findings.md §2.6), and Orange's employment columns were zero where
            the baseline had NULL because `SUM()` over no rows is NULL (§1.16).
            The full list is findings.md §1.14-§1.25, §2.6-§2.9 and §3.7-§3.10._

            _Two harness lessons worth carrying to task 10: a difference is
            usually **upstream of where it shows** (a wrong destination count
            surfaces as a wrong `overall_score` on 200 blocks), and the per-city
            wall clock is 4 s to 2 min, so a full corpus run is cheap enough to
            repeat after every fix -- which is what caught the regressions that
            a single-city check would have missed._

  - _Requirements: NFR-VALIDATION-1, NFR-PARITY-1, NFR-PARITY-2, NFR-PARITY-3_

- [x] 10. Automated pre-ship gate (`XS`/`S`/`M` corpus) — **PASSES.**

      **15 of 15 cities**: 14 at exact parity across all eight dimensions
      (the seven below plus `destinations`, added after DC -- see 10.3) and
      every published column, and Chambéry within a documented deviation
      (requirements.md §6.1a, findings.md §1.26). The corpus runs in under
      **3 minutes** end to end, so it is cheap to repeat after every change.

          `just validate-parity --size XS --size S --size M` reproduces it, and
          exits non-zero on anything outside the recorded exception.
  - [x] 10.1 Run `just validate-parity` against the automated corpus:
        `integration/e2e-cities.csv` restricted to `XS`/`S`/`M` `test_size` rows
        (NFR-VALIDATION-2). `L`/`XL`/`XXL` cities (Valencia, Washington DC) are
        excluded — they take hours per city with the current implementation,
        which is impractical for a repeatable automated gate. Both get an
        optional manual follow-up instead (10.3), not required to ship.
  - [x] 10.2 Fix any parity regression found; re-run 10.1 until the automated
        corpus passes. Do not proceed to task 11 until it does — this is a hard
        ceiling, not report-only (requirements.md §7).

        _One regression found and fixed here, in a city that had never been
            checked before: Flagstaff was missing two cuts, because a node
            carrying a `mapconfig_highway.xml` `highway` value is a routing
            vertex even where only one way uses it (findings.md §3.11). That is
            the same class of discovery as the XS/S round -- segmentation, not
            scoring -- and it landed in `ingest`, three stages upstream of the
            column that reported it._

            _Chambéry is resolved (4.5a). The PostGIS run showed no SQL deletes
            anything: `osm2pgrouting` never imported those segments, because an
            edge duplicating one from an earlier 20,000-way processing chunk is
            dropped at import. Bisecting a local `osm2pgrouting` pinned it to the
            way **count** -- 20,000 ways keeps all three rows, 20,001 drops two,
            whichever way is added. Unmatchable by any rule over the data and
            unstable across data refreshes, so it is scoped out of NFR-PARITY-1
            (requirements.md §6.1a, findings.md §1.26) rather than reproduced._

            _The harness encodes the exception by **naming the three segments**,
            so Chambéry reports `EXCEPT` rather than `FAIL` and the gate exits 0
            -- but any *other* difference there still fails, since the accepted
            set must match exactly._

  - [x] 10.3 Manual maintainer validation — **DONE, both cities, and it
        paid for itself twice** (requirements.md §7.4a; stretch goal).

        **Washington DC (XXL): PASS on every dimension** -- 100,234 ways,
        87,625 intersections, 5,908 blocks, 3,845,313 block pairs, 2,175
        destinations, all scores -- against a fresh 3.2.5 baseline the
        maintainer ran overnight (2026-09-16). Wall clock **5.2 min against
        3 h 37 min** on 3.2.5 (43.8x; NFR-PERF-1's 2x ceiling cleared by a
        wide margin). DC is where the original 20-50x estimate came from, and
        it is the one city where it was right.

        **Valencia (XL): two residuals, both recorded, neither a rule** --
        findings.md §5a.3 (one segment at a pedestrian plaza) and §5a.4 (a
        transit cluster whose centroid lies exactly on the boundary line).
        Wall clock 44 s against 283 s (6.2x).

        _What DC found, that fifteen corpus cities had not_ (findings.md
        §1.1, §1.28, §1.29, §3.12): the FLOAT-vs-NUMERIC rounding mode on
        INT columns (`22'6"` is 22 ft, not 23); `traffic_signals:direction`
        missing from the way-tag list; retail's `blockid20` testing the
        polygon alone; and -- the largest -- the **destination layers were
        never compared**. Every `access_*.sql` computes a per-destination
        population shed (`pop_low_stress`, `pop_high_stress`, `pop_score`)
        and publishes it with the centroid, and the pipeline had neither. The
        harness now has an eighth dimension, `destinations`, covering all 13
        layers, and the corpus gate is green on it: 14 PASS + Chambéry
        EXCEPT._
  - _Requirements: NFR-VALIDATION-1, NFR-VALIDATION-2, NFR-PERF-1, NFR-PARITY-1,
    NFR-PARITY-2, NFR-PARITY-3_

- [x] 11. Remove SQL/PostGIS/pgRouting entirely (requirements.md §7 open
      question #7 — hard deletion, no dual-path toggle) — **DONE.**

      **78 SQL files and the whole database layer are gone.** `bna` is down to
      three subcommands -- `cache`, `prepare`, `run` -- and the package no
      longer imports `sqlalchemy`, opens a socket, or shells out to
      `osm2pgrouting`, `osm2pgsql`, `psql` or `pgsql2shp`.

          What was kept, and why: `runner.run`/`run_osmium_extract`/
          `run_osm_convert` (the new `ingest` stage uses `osmium` and `osmconvert`),
          `exporter`'s calver/bundle/S3-R2 half (`bna run --with-export` still
          publishes), and all of `prepare`.

          Two things were preserved rather than deleted with their source:
          **`pfb.style`'s way-tag list and `mapconfig_highway.xml`'s highway
          values are now frozen in `test_ingest.py`.** Those files were the
          reference for `OSM_WAY_TAGS` and `OSM_HIGHWAY_TYPES` (findings.md §2.2,
          §3.11); with them gone the tests would have skipped silently, so the
          lists they validated are asserted directly instead.
  - [x] 11.1 Delete `brokenspoke_analyzer/scripts/sql/` in full.
  - [x] 11.2 Delete `mapconfig_highway.xml`, `mapconfig_cycleway.xml`,
        `pfb.style` (osm2pgrouting/osm2pgsql-specific).
  - [x] 11.3 Delete `brokenspoke_analyzer/core/database/` (dbcore, SQLAlchemy
        models) and any remaining `execute_sqlfile_with_substitutions` usage in
        `compute.py`/`analysis.py`. _Also deleted `core/ingestor.py` and the
        five database-only CLI apps (`importer`, `compute`, `configure`,
        `export`, `run_with`), and stripped `exporter.py`'s PostGIS export half
        and `runner.py`'s database wrappers._
  - [x] 11.4 Delete `core/compute.py`'s SQL-orchestration functions
        (`features()`, `stress()`, `connectivity()`, `measure()`, `all_()`,
        `parts()`) once `core/pipeline/` fully replaces them; keep only what
        task 2.3 didn't already move to `config.py`, or delete `compute.py`
        entirely if nothing remains. _Nothing remained: the dataclasses moved to
        `config.py` in task 2.3, so the file is gone and `test_config.py` now
        asserts it stays gone._
  - [x] 11.5 Remove `just compose-up`/`compose-down`/`docker-build` recipes and
        any `DATABASE_URL` references in `justfile`, `README.md`, `CLAUDE.md`,
        and CI config. _`compose.yml` deleted; `lint-sql` and the `sqlfluff`
        config removed; `docker-build` kept (the image is still published, it
        just no longer carries a database). README, CLAUDE.md,
        `docs/source/about.md` and `docs/source/commands.md` rewritten for the
        no-database flow, and `e2e.yaml` rewritten to run `bna run` and assert
        on the exported files instead of `psql`-querying a service container._
  - [x] 11.6 Remove `osm2pgrouting`/`osm2pgsql`/`shp2pgsql`/PostGIS/ pgRouting
        from `pyproject.toml` dependencies, Dockerfile(s), and CI service
        containers. _`sqlalchemy` and `sqlfluff` dropped (`psycopg` went with
        them -- 202 packages resolved, down from 209); the Dockerfile lost its
        `osm2pgrouting` build stage and the
        `postgis`/`postgresql-client`/`osm2pgsql`/`libpqxx` runtime packages._
  - _Requirements: NFR-DEP-1_

- [x] 12. Final checkpoint — full `just ci` pass — **DONE.**
  - [x] 12.1 Run `just ci` (lint, fmt-check, test, docs) clean with no
        PostGIS/Docker Compose dependency anywhere in the toolchain.
        _`ruff check`, `ruff format --check`, `ty`, `uv lock --check`, the
        Sphinx build and 333 tests all pass. Two caveats: `just lint-md`
        (`npx markdownlint-cli2`) could not run in this sandbox -- the markdown
        was hand-checked against `.markdownlint.yml`'s 80-column rule instead --
        and `isort --check .` trips on
        `integration/tests/core/cache/test_cli.py`, a **gitignored local file**
        that predates this work and is invisible to CI._
  - [x] 12.2 Confirm `just test` runs without `docker compose up` (user story in
        requirements.md §4). _There is no compose file left to run:
        `compose.yml` and `compose/` are deleted and the devcontainer now builds
        the `dev` stage of the Dockerfile directly._
  - [x] 12.3 Re-run task 10.1's automated `XS`/`S`/`M` `validate-parity` one
        final time post-deletion to confirm nothing in task 11's removals broke
        parity. _**Identical to the pre-deletion run**: 14 exact, Chambéry
        within its documented deviation, gate exit 0. The analysis never touched
        the SQL, so deleting it changed nothing -- which is the point of running
        it anyway._
  - _Requirements: NFR-DEP-1, NFR-TEST-1, all FR/NFR (final gate)_

## Notes & decisions

- No feature flags, no dual-path (SQL-or-Python) runtime toggle — this is a full
  cutover once task 10 passes (requirements.md §1).
- No deviation-tracking module: our SQL is the reference implementation, so
  every rule transcribed in tasks 3-7 must reproduce the SQL's behavior exactly,
  bugs included (requirements.md §3).
- Task 1's benchmark spike gates task 6 — do not start `network.py`'s real
  implementation before it completes (design.md §3.4).
- Tasks 3-7 are listed in pipeline-dependency order but their _unit_ tests
  (synthetic data, no real city fixtures) can be written and iterated on in
  parallel by different contributors, since each stage's unit tests don't
  require the previous stage's real output — only integration/parity testing
  (tasks 9-10) requires the full chain.

## Next steps (after tasks.md)

**The migration is complete.** Tasks 1-12 are done; what is left is optional or
deferred, and none of it blocks shipping:

1. **Task 10.3 — manual validation of Washington DC and Valencia**, a stretch
   goal (requirements.md §7.4a). DC also carries the NFR-PERF-1 2x ceiling
   check, which no automated corpus covers.
2. **Task 7.6 — `score_inputs.sql`'s ~110 diagnostic rows**, the one published
   file the new pipeline does not produce. It feeds no score (findings.md
   §1.13), so it gates file-level parity only.
3. **findings.md §5a.2 — the baselines are gitignored.** `results/**` is the
   frozen ground truth for `just validate-parity`, but it lives on one machine.
   Either commit it or document how to regenerate it -- and note that
   regenerating now requires checking out a pre-deletion commit, since the SQL
   that produced it is gone.
4. Keep `findings.md` alive: it is the only remaining record of why the pipeline
   behaves as it does, and CLAUDE.md now points contributors at it before they
   change a rule.
