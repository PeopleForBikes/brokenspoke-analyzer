# Design Document: Protected Bike Lane (PBL) Refinement

## Status

DRAFT. Implements `requirements.md` in this directory.

## Overview

PBL detection runs as a new final step in `features/bike_infra.sql`, after the
existing tag-based bike infrastructure logic and before `class_adjustments.sql`.
It works only with data already in the database (`neighborhood_ways`,
`neighborhood_osm_full_line`, `neighborhood_boundary`), keeps all intermediate
results in temporary tables, and writes its results only to the existing
`ft_bike_infra` and `tf_bike_infra` columns.

The step merges the allow-listed roads into one buffer per level (bridge, tunnel
or ground) and joins connected candidate bike paths into chains, both once per
run. It then finds where each chain lies inside the buffer for its own level,
keeps the pieces that run in the road's direction, fills short gaps between
them, and labels each candidate segment by where at least half of its length
lies. Direction comes from the one-way tags on the segment's OSM way. Four
constants in `core/compute.py` (buffer, maximum angle, maximum gap, maximum gap
distance) are passed into the SQL through the existing parameter-substitution
runner.

`features/calculate_mileage.sql` changes in two ways: a segment labeled as a PBL
is no longer also counted as `path`, and every category counts only the length
inside the city boundary.

## Architecture

### Where it runs

PBL detection is added to the _features_ stage, which runs on every analysis:

```text
one_way.sql → width_ft.sql → functional_class.sql → paths.sql
  → speed_limit.sql → lanes.sql → park.sql
  → bike_infra.sql   [existing tag rules, then NEW: PBL detection]
  → class_adjustments.sql → legs.sql → signalized / stops / rrfb / island
```

Mileage is computed later, in the _measure_ stage, by `calculate_mileage.sql`
(changed).

### Data flow inside the PBL step

```text
neighborhood_ways (allow-listed roads) ──► merge + buffer ──┐
                                                             ├─► overlap pieces ─► angle check ─► gap fill
neighborhood_osm_full_line (candidates) ─► join into chains ┘
                                                                                       │
    neighborhood_ways (candidate segments) ◄── label by half-length + direction ◄──────┘
                         (writes ft_bike_infra / tf_bike_infra = 'track')
```

### Why this placement

- It runs **after** `functional_class.sql`, so road classes and candidate `path`
  segments exist, and after the existing tag rules in `bike_infra.sql`.
- It **only adds** `track` labels to candidate segments and never changes a
  segment that already has a label from tags. In practice, candidate path
  segments have no tag-based labels today (in Philadelphia, none of the 6,550
  path segments had one), so this is a safeguard.
- It runs **before** `class_adjustments.sql`, which promotes residential and
  unclassified roads with bike infrastructure to tertiary. Detected PBLs are
  `path` segments, so they are unaffected, and promoted roads stay in the road
  allow-list either way.
- It does not touch stress, routing or `paths.sql`, so scores do not change
  (Requirement 8).

## Components and Interfaces

### C1. Settings and wiring (`core/compute.py`)

- Add four constants next to `NB_SIGCTL_SEARCH_DIST`: `NB_PBL_BUFFER_M = 25`,
  `NB_PBL_MAX_ANGLE_DEG = 15`, `NB_PBL_MAX_GAP_M = 400` and
  `NB_PBL_MAX_GAP_DIST_M = 40`. The `NB_` prefix ("neighborhood", the analysis
  area) follows the existing naming.
- `bike_infra.sql` is currently run as written (`execute_sql_file`). It must
  instead be run with `execute_sqlfile_with_substitutions`, which replaces
  placeholders in the file (`:pbl_buffer_m`, `:pbl_max_angle_deg`,
  `:pbl_max_gap_m`, `:pbl_max_gap_dist_m`) with the values of these constants
  before running it. The replacement only matches these exact names, so the many
  tag names with colons already in `bike_infra.sql` (for example
  `"cycleway:right"`) are unaffected.

### C2. PBL detection (end of `features/bike_infra.sql`)

The whole file runs in one database transaction, so the step uses temporary
tables that disappear when it finishes.

Each way's level comes from its tags in `neighborhood_osm_full_line`: `bridge`
when `bridge` is set to anything other than `no` or `boardwalk`, otherwise
`tunnel` when `tunnel` is set to anything other than `no`, otherwise `ground`.
Road segments in `neighborhood_ways` take the level of their OSM way through
`osm_id`.

The step runs these statements:

1. **Roads** (`pbl_roads`): allow-listed road segments (Requirement 2) with
   their level, indexed.
2. **Road buffer** (`pbl_road_buf`): the union of
   `ST_Buffer(geom, :pbl_buffer_m, 'endcap=flat')` over `pbl_roads`, one per
   level, split into tiles with `ST_Subdivide` and indexed. Flat ends keep the
   buffer beside each road and stop it at the road's end.
3. **Chains** (`pbl_chains`): `ST_LineMerge(ST_Union(way))` over candidate ways
   in `neighborhood_osm_full_line` (Requirement 1), split into single lines and
   indexed. Each candidate way is also kept with its chain and level
   (`pbl_cand`).
4. **Overlap pieces** (`pbl_pieces`): each chain's candidate ways intersected
   with the road buffer for the same level, merged per chain and level and split
   into continuous pieces.
5. **Parallel stretches** (`pbl_stretch`): pieces whose median angle to the
   nearest road in `pbl_roads` at the same level, sampled every 5 m along the
   piece, is at most `:pbl_max_angle_deg`.
6. **Gap fill**: for consecutive stretches on the same chain, add the part of
   the chain between them when it is at most `:pbl_max_gap_m` long and no point
   on it, sampled every 5 m, is farther than `:pbl_max_gap_dist_m` from the
   nearest road in `pbl_roads`.
7. **Labels**: `UPDATE neighborhood_ways` for candidate segments that have no
   existing `ft_bike_infra`/`tf_bike_infra` label, setting `'track'` when at
   least half of the segment lies within stretches (measured against the
   stretches buffered by 1 m, to absorb tiny geometry differences), in the
   direction given by C5.

### C3. Mileage (`features/calculate_mileage.sql`)

- Count a segment as `path` only when neither direction is labeled `track`.
- Measure every category with the length inside the city boundary,
  `ST_Length(ST_Intersection(geom, boundary))`, instead of `ST_Length(geom)`.

### C4. Lint placeholders (`pyproject.toml`)

- Add `pbl_buffer_m = 25`, `pbl_max_angle_deg = 15`, `pbl_max_gap_m = 400` and
  `pbl_max_gap_dist_m = 40` under `[tool.sqlfluff.templater.placeholder]` so
  `sqlfluff` can lint the new SQL. These are lint-only values, not runtime
  defaults.

### C5. Direction

A detected PBL is labeled in both directions only when it is mapped as two-way
for bikes. The bike direction tag is `COALESCE("oneway:bicycle", oneway)` on the
segment's OSM way:

- `no`: `ft_bike_infra` and `tf_bike_infra` are both `'track'`.
- `-1`: only `tf_bike_infra` is `'track'`.
- Anything else, including no tag: only `ft_bike_infra` is `'track'`.

Labels on `path` segments feed only the mileage and the exported data. Routing
direction comes from the `one_way` column, which is set from `one_way_car`
earlier in `bike_infra.sql`, before this step, so an untagged path stays two-way
for routing. Path stress is set to 1 in both directions by `stress_path.sql`
regardless of labels.

## Data Models

**No new permanent tables or columns.** Results are written only to the existing
`neighborhood_ways.ft_bike_infra` and `tf_bike_infra` (value `'track'`), and the
`mileage` table keeps its columns (`feature_type`, `total_mileage`).

**Temporary tables**, dropped at the end of the transaction:

| Table          | Columns                                          | Purpose                                                |
| -------------- | ------------------------------------------------ | ------------------------------------------------------ |
| `pbl_roads`    | `road_id`, `geom`, `level`                       | Allow-listed road segments with their level, indexed   |
| `pbl_road_buf` | `level`, `geom` (polygon)                        | Buffered roads per level, tiled and indexed            |
| `pbl_chains`   | `chain_id`, `geom` (line)                        | Joined candidate bike paths, indexed                   |
| `pbl_cand`     | `chain_id`, `geom`, `level`                      | Candidate ways with their chain and level, indexed     |
| `pbl_pieces`   | `piece_id`, `chain_id`, `level`, `geom`, `len_m` | Parts of chains inside the road buffer for their level |
| `pbl_stretch`  | `piece_id`, `chain_id`, `geom`, `buf`            | Parallel stretches plus filled gaps, indexed on `buf`  |

All geometries are in the same projected coordinate system as
`neighborhood_ways` (a local UTM zone chosen for each city), so lengths and
distances are in meters.

## Correctness Properties

These must hold for every city:

1. **Only candidates change.** The step changes `ft_bike_infra` and
   `tf_bike_infra` only on candidate segments (Requirement 1). Every other
   segment is untouched.
2. **Existing labels win.** A segment that already has a label from tags keeps
   it.
3. **Only one new value.** The step writes only `'track'`.
4. **Direction is consistent.** A detected PBL has both directions labeled only
   when its bike direction tag is `no`, and exactly one otherwise (`tf` for
   `-1`, `ft` for anything else). Direction comes only from the bike path's own
   tags, never from the adjacent road, and `one_way` is unchanged.
5. **Nothing else changes.** `functional_class`, stress values, `path_id` and
   `neighborhood_paths` are identical with and without the step, so scores do
   not change.
6. **No leftovers.** No new tables or columns remain after the run.
7. **No double counting.** No segment's length is counted in both `track` and
   `path`.
8. **Only inside the city.** Each segment contributes at most its length inside
   the city boundary, in every mileage category.
9. **Splitting doesn't matter.** How mappers split a path into OSM ways, or how
   the import splits ways into segments, does not change which parts of the path
   are detected, because paths are joined into chains first. The exceptions are
   roundabouts and switchback ramps (see Known Limitations in
   `requirements.md`), and segments that lie roughly half inside a stretch,
   where the half-length rule decides.
10. **Repeatable.** Running the analysis twice on the same data gives the same
    labels and mileage. `bike_infra.sql` already clears both label columns at
    the top, so a re-run starts clean.
11. **Distances are in meters,** because the data uses each city's local UTM
    projection.

## Error Handling

| Situation                                                      | What happens                                                                                                                                                          |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No candidate bike paths in the city                            | The step finds nothing and labels nothing. No error.                                                                                                                  |
| No allow-listed roads                                          | The road buffer is empty, so nothing is labeled. No error.                                                                                                            |
| A setting is not passed in                                     | The placeholder stays in the SQL, which fails with a syntax error and stops the run. This is intended: a loud failure is better than silently wrong results.          |
| Invalid geometry in OSM data (for example self-crossing lines) | Inputs to the union and intersection steps are passed through `ST_MakeValid`, so one bad shape does not stop the analysis.                                            |
| A path that forms a closed loop (for example around a park)    | Position along a loop is ambiguous, so gap fill is skipped for closed chains. Their parallel stretches are still detected.                                            |
| Any other database error                                       | The whole `bike_infra.sql` transaction rolls back and the run stops, as for any other BNA SQL step. Temporary tables disappear with it, so nothing is left half-done. |

## Integration

- **Runs on every analysis.** PBL detection is in the _features_ stage, which
  also runs in partial runs (for example `--with-parts stress` or `measure`).
- **Exported road files.** The `neighborhood_ways` shapefile and GeoJSON show
  `'track'` in `FT_BIKE_IN`/`TF_BIKE_IN` for detected PBLs. Map styles that draw
  "Off-Street Path" when only one direction is empty will draw over one-way
  PBLs; those rules should check that both directions are empty.
- **`mileage.csv` changes in three ways:** `track` goes up, `path` goes down by
  the detected physical miles, and every category drops slightly because only
  the length inside the city counts. Year-over-year mileage comparisons should
  note this change.
- **Scores do not change.** Stress, routing and connectivity do not read
  `ft_bike_infra` for path segments.
- **Earlier PBL work.** This replaces the approach on the `pbl-methodology`
  branch and the December 2025 Python inventory (`PBL-updates` branch). Numbers
  differ from that inventory, mainly because side paths now count.

## Testing Strategy

The BNA's automated tests do not run SQL against a database, so checks 2-6 are
manual scripts run on real cities.

1. **Linting and existing tests.** `just ci` passes: `sqlfluff` on the new SQL
   (using the new placeholders in `pyproject.toml`), `ruff` and `ty` on
   `compute.py`, and the existing test suite.
2. **Reference ways.** Run the BNA (partial run, `--with-parts measure`) on
   Bend, Providence, Philadelphia and Portland, and check every way in the
   validation table (Requirement 11): segments labeled out of total, and the
   direction. All must match the expected result.
3. **Match the tested results.** The implementation should give the same labels
   as the method tested on the six cities. A segment-by-segment comparison for
   at least Bend and Philadelphia should show no differences other than the
   intended ones (`ST_MakeValid` is applied, and gap fill is skipped on closed
   loops).
4. **Correctness properties.** Queries on a finished run that check:
   non-candidate segments have unchanged labels; stress values and
   `functional_class` are identical with and without the change; no segment is
   counted in both `track` and `path`; detected PBLs not tagged two-way have
   exactly one direction labeled; and no temporary tables remain.
5. **Mileage.** Compare `mileage.csv` before and after for a test city: `track`
   rises, `path` falls by the detected physical miles, and other categories
   change only by the inside-the-boundary clipping.
6. **Performance.** Time the PBL step on Philadelphia; it must finish in under
   30 seconds (Requirement 10).

## Deployment Considerations

- **No new configuration.** The four settings are constants in `compute.py`,
  with no command-line options or environment variables. To test other values,
  edit the constants and re-run.
- **No data migration.** Nothing is stored between runs; results are recomputed
  on every analysis.
- **Changed outputs** (worth a release note): detected PBLs appear as `track` in
  the road files, `mileage.csv` shows more `track` and less `path`, and all
  mileage categories count only the length inside the city boundary.
- **City Ratings timing.** City Ratings are re-run in a batch each March for the
  new release. The new detection and mileage apply from the first batch run
  after this change ships; new methodology is never applied to earlier results.
- **Changelog.** Added at release time by the maintainers, as usual.

## Dependencies

- **No new libraries or services.**
- **PostGIS functions:** `ST_Buffer`, `ST_Union`, `ST_Subdivide`,
  `ST_LineMerge`, `ST_Intersection`, `ST_LineLocatePoint`, `ST_LineSubstring`,
  `ST_Azimuth`, `ST_Segmentize` and `ST_MakeValid`, plus PostgreSQL's
  `PERCENTILE_CONT`. All are available in the PostGIS version used in
  `compose.yml` (3.6.1).
- **OSM tags:** `highway`, `bicycle`, `surface`, `oneway` and `oneway:bicycle`
  are already imported by `pfb.style`, so no import changes are needed.
- **Earlier BNA steps:** `one_way.sql` (for `one_way_car`) and
  `functional_class.sql` (road classes and candidate `path` segments) must run
  first. They already do.
