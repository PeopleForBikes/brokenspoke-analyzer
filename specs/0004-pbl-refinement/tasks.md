# Implementation Plan: Protected Bike Lane (PBL) Refinement

## Overview

Build in the order the data flows: settings first, then detection, then mileage.
Verify on Bend, which runs quickly, after each stage before running the larger
cities.

## Tasks

- [ ] 1. Settings and wiring
  - Add `NB_PBL_BUFFER_M = 20`, `NB_PBL_MAX_ANGLE_DEG = 20` and
    `NB_PBL_MAX_GAP_M = 400` to `core/compute.py`.
  - Run `bike_infra.sql` with `execute_sqlfile_with_substitutions`, passing the
    three settings.
  - Add the three lint placeholders to `pyproject.toml`.
  - _Requirements: 9; design C1, C4_

- [ ] 2. PBL detection at the end of `features/bike_infra.sql`
  - [ ] 2.1 Road buffer from allow-listed roads, with `ST_MakeValid`
    - _Requirements: 2_
  - [ ] 2.2 Candidate selection and chains
    - _Requirements: 1, 3.1, 3.6_
  - [ ] 2.3 Overlap pieces and the angle check
    - _Requirements: 3.2-3.5_
  - [ ] 2.4 Gap fill, skipping closed loops
    - _Requirements: 3.7_
  - [ ] 2.5 Label segments by the half-length rule, only where unlabeled
    - _Requirements: 4, 8_
  - [ ] 2.6 Direction from `one_way_car` and `oneway:bicycle = no`
    - _Requirements: 5; design C5_

- [ ] 3. Checkpoint - detection works on Bend
  - `sqlfluff lint` passes on `bike_infra.sql`.
  - Partial run on Bend; all Bend reference ways match the validation table.
  - Labels match the tested results for Bend, segment by segment.

- [ ] 4. Mileage in `features/calculate_mileage.sql`
  - Count `path` only when the segment is not labeled `track`.
  - Count only the length inside the city boundary, for every category.
  - _Requirements: 7; design C3_

- [ ] 5. Checkpoint - mileage on Bend
  - Compare `mileage.csv` before and after: `track` up, `path` down by the
    detected miles, other categories changed only by boundary clipping.

- [ ] 6. Validation on the test cities
  - Reference ways in Providence, Philadelphia and Portland.
  - Segment-by-segment comparison with the tested results for Philadelphia.
  - Correctness-property queries (see Correctness Properties in `design.md`).
  - PBL step timing on Philadelphia under 30 seconds.
  - _Requirements: 8, 10, 11_

- [ ] 7. Finish
  - `just ci` passes.
  - Update `design.md` and `tasks.md` if anything changed during the build.

## Notes

- The manual validation scripts live in `results/` and are not committed.
