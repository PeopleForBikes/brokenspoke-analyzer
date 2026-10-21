# Implementation Plan: Protected Bike Lane (PBL) Refinement

## Overview

Build in the order the data flows: settings first, then detection, then mileage.
Verify on Bend, which runs quickly, after each stage before running the larger
cities.

## Tasks

- [x] 1. Settings and wiring
  - Add `NB_PBL_BUFFER_M = 25`, `NB_PBL_MAX_ANGLE_DEG = 15`,
    `NB_PBL_MAX_GAP_M = 400` and `NB_PBL_MAX_GAP_DIST_M = 40` to
    `core/compute.py`.
  - Run `bike_infra.sql` with `execute_sqlfile_with_substitutions`, passing the
    four settings.
  - Add the four lint placeholders to `pyproject.toml`.
  - _Requirements: 9; design C1, C4_

- [x] 2. PBL detection at the end of `features/bike_infra.sql`
  - [x] 2.1 Road levels, and a road buffer per level (flat ends) from
        allow-listed roads, with `ST_MakeValid`
    - _Requirements: 2, 3.9_
  - [x] 2.2 Candidate selection, chains, and candidate ways with their level
    - _Requirements: 1, 3.1, 3.6_
  - [x] 2.3 Overlap pieces and the angle check, at the same level
    - _Requirements: 3.2-3.5_
  - [x] 2.4 Gap fill, skipping closed loops and gaps that stray beyond the
        maximum gap distance
    - _Requirements: 3.7, 3.8_
  - [x] 2.5 Label segments by the half-length rule, only where unlabeled
    - _Requirements: 4, 8_
  - [x] 2.6 Direction from `one_way_car` and `oneway:bicycle = no`
    - _Requirements: 5; design C5_

- [x] 3. Checkpoint - detection works on Bend
  - `sqlfluff lint` passes on `bike_infra.sql`.
  - Partial run on Bend; all Bend reference ways match the validation table.
  - Labels match the tested results for Bend, segment by segment.

- [x] 4. Mileage in `features/calculate_mileage.sql`
  - Count `path` only when the segment is not labeled `track`.
  - Count only the length inside the city boundary, for every category.
  - _Requirements: 7; design C3_

- [x] 5. Checkpoint - mileage on Bend
  - Compare `mileage.csv` before and after: `track` up, `path` down by the
    detected miles, other categories changed only by boundary clipping.

- [x] 6. Validation on the test cities
  - Reference ways in Bend, Providence, Madison and Portland (Philadelphia is
    left out of repeated test runs because it takes about 1.5 hours to load).
  - Segment-by-segment comparison with the tested prototype results.
  - Correctness-property queries (see Correctness Properties in `design.md`).
  - PBL step timing on Philadelphia under 30 seconds.
  - _Requirements: 8, 10, 11_

- [x] 7. Finish
  - `just ci` passes.
  - Update `design.md` and `tasks.md` if anything changed during the build.

## Notes

- The manual validation scripts live in `results/` and are not committed.
- Philadelphia was validated with the earlier rules (20°, round buffer ends, no
  gap distance cap; PBL step 9 seconds). It has not been rerun with the final
  rules, so its reference ways and `is_sidepath` agreement should be rechecked
  before release.
