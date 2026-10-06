# Requirements Document: Protected Bike Lane (PBL) Refinement

## Status

DRAFT. Open questions are listed in the last section and must be resolved before
this document is approved.

## Introduction

Protected bike lanes are often mapped in OpenStreetMap (OSM) as separate
`highway=cycleway` ways instead of as `cycleway=track` tags on the road. The BNA
classifies every `highway=cycleway` as an off-street path
(`functional_class = 'path'`), so these PBLs cannot be told apart from trails.
That means we cannot report PBL mileage, which is a deliverable for the end
of 2026.

This feature detects `highway=cycleway` ways that run close alongside a road and
labels them as protected lanes (`ft_bike_infra`/`tf_bike_infra = 'track'`), so
that they are counted as `track` in the mileage table instead of `path`.

It replaces the approach drafted on the `pbl-methodology` branch, which tested
each segment separately against a single 10 m distance with no parallel-ness
check. A test on Bend, OR showed that approach labels road crossings on trails
as PBLs, catches side paths set back from the road, misses parts of real PBLs
near intersections, and gives different labels to segments of the same OSM way.
See the Background section.

### In scope

- Detecting PBLs among `highway=cycleway` ways, using geometry relative to car
  roads plus OSM tags.
- Setting `ft_bike_infra`/`tf_bike_infra` on detected segments, with the correct
  direction.
- Fixing mileage so a detected PBL is counted as `track` only, not also as
  `path`.
- Making the detection thresholds adjustable.

### Out of scope

- Changing `functional_class`, stress scores, or trail networks
  (`neighborhood_paths`). Detected PBLs remain `functional_class = 'path'`.
  Trails will be revisited in a separate effort.
- Porting this logic to the Python pipeline (`feature/nosql`, release 5.0). That
  port will follow separately.
- Detecting PBLs among ways other than `highway=cycleway`. In particular,
  `highway=path` ways always remain paths.
- Reporting PBL mileage separately from on-street `cycleway=track` mileage. Both
  are combined in the `track` total.

## Glossary

- **PBL (protected bike lane)**: a bikeway close alongside a road, physically
  separated from motor traffic. Whether side paths set farther back from the
  road also count is Open Question 1.
- **Cycleway way**: one OSM way tagged `highway=cycleway`, identified by its
  `osm_id`, with its full geometry from `neighborhood_osm_full_line`.
- **Segment**: one row of `neighborhood_ways`. The import splits each OSM way
  into segments at intersections; all segments of a way share its `osm_id`.
- **Car road**: a road segment used as the reference for detection, selected by
  the allow-list in Requirement 2.
- **Road buffer**: the area within `pbl_outer_buffer_m` meters of any car road,
  merged into one shape.
- **Overlap piece**: one continuous part of a cycleway way that lies inside the
  road buffer.
- **Parallel stretch**: an overlap piece at least `pbl_min_piece_m` meters long.
  A cycleway crossing a road produces a short piece (about 2 ×
  `pbl_outer_buffer_m` ÷ sin(angle)); a cycleway running alongside a road
  produces a long one.
- **Stretch distance**: the median distance from points along a parallel stretch
  to the nearest car road's centerline.
- **PBL stretch**: a parallel stretch whose stretch distance is at most
  `pbl_core_distance_m`.
- **One-way variant**: any tag combination that marks a cycleway as carrying
  bikes in one direction only. See Requirement 5.

## Requirements

### Requirement 1: Candidate selection

**User Story:** As an analyst, I want only cycleways considered for PBL
detection, so that roads, crossings and footways are not affected.

#### Acceptance Criteria

1. The system SHALL consider as PBL candidates only segments whose OSM way is
   tagged `highway=cycleway` and whose `functional_class` is `'path'`.
2. The system SHALL NOT consider segments marked as crossings (`xwalk = 1`).
3. The system SHALL NOT change `ft_bike_infra`/`tf_bike_infra` on non-candidate
   segments.

### Requirement 2: Car-road reference set

**User Story:** As an analyst, I want PBLs detected only along streets people
ride beside, so that paths next to freeways are not counted as PBLs.

#### Acceptance Criteria

1. The system SHALL build the road buffer from segments in `neighborhood_ways`
   whose `functional_class`, as set by `functional_class.sql`, is one of:
   `primary`, `primary_link`, `secondary`, `secondary_link`, `tertiary`,
   `tertiary_link`, `residential` or `unclassified`.
2. The system SHALL use this allow-list, so that any other road type (for
   example `construction`, `proposed`, `corridor` or `raceway`) is never part of
   the road buffer.
3. The system SHALL NOT include `motorway`, `motorway_link`, `trunk`,
   `trunk_link` or `living_street` in the road buffer, although
   `functional_class.sql` keeps them as roads.
4. WHERE a cycleway runs parallel only to roads outside the allow-list, the
   system SHALL NOT label it as a PBL.

### Requirement 3: PBL stretches

**User Story:** As an analyst, I want each stretch where a cycleway runs
alongside a road judged by how close it typically is, so that road crossings and
set-back side paths are ignored, real PBLs are detected even where they drift
away from the road near intersections, and labels do not depend on where the
import splits a way.

#### Acceptance Criteria

1. The system SHALL evaluate each cycleway way using its full geometry, not each
   segment independently.
2. The system SHALL identify a cycleway way's overlap pieces with the road
   buffer, and SHALL treat only overlap pieces at least `pbl_min_piece_m` long
   as parallel stretches.
3. WHEN a cycleway way crosses a road at an angle, the system SHALL NOT treat
   the crossing as a parallel stretch, provided the overlap piece is shorter
   than `pbl_min_piece_m`.
4. The system SHALL compute each parallel stretch's stretch distance from points
   sampled along it at regular intervals.
5. WHEN a parallel stretch's stretch distance is at most `pbl_core_distance_m`,
   the system SHALL treat the whole stretch as a PBL stretch, including parts
   farther from the road than `pbl_core_distance_m` (for example near
   intersections where the road widens).
6. WHEN a parallel stretch's stretch distance is greater than
   `pbl_core_distance_m`, the system SHALL NOT treat any part of it as a PBL
   stretch.
7. WHEN a cycleway way runs alongside a road for only part of its length, the
   system SHALL judge only that part (for example, the geometry of way
   1354189308 in Providence, RI, before any tag exclusions are applied).

### Requirement 4: Segment labeling

**User Story:** As an analyst, I want each segment labeled by how much of it
lies in a PBL stretch, so that partial PBLs are handled and short stubs are not
labeled.

#### Acceptance Criteria

1. WHEN at least `pbl_segment_share` of a candidate segment's length lies within
   PBL stretches, the system SHALL label that segment as a PBL.
2. WHEN less than `pbl_segment_share` of a candidate segment's length lies
   within PBL stretches, the system SHALL leave that segment as a path.
3. WHERE a cycleway way lies entirely within one PBL stretch, the system SHALL
   give all of its segments the same label.

### Requirement 5: Direction

**User Story:** As an analyst, I want one-way PBLs counted once and two-way PBLs
counted in both directions, so that PBL mileage is not overstated.

#### Acceptance Criteria

1. WHEN a detected PBL has no one-way variant, the system SHALL set both
   `ft_bike_infra` and `tf_bike_infra` to `'track'`.
2. WHEN a detected PBL has a one-way variant in the direction the way is drawn,
   the system SHALL set only `ft_bike_infra` to `'track'`.
3. WHEN a detected PBL has a one-way variant against the direction the way is
   drawn (for example `oneway=-1`), the system SHALL set only `tf_bike_infra` to
   `'track'`.
4. The system SHALL recognise every one-way variant, including at least `oneway`
   and `oneway:bicycle` with the values `yes`, `1`, `true` and `-1`. The full
   list SHALL be defined in design.md.
5. WHEN both a one-way tag and a two-way override are present (for example
   `oneway=yes` with `oneway:bicycle=no`), the system SHALL treat the PBL as
   two-way.

### Requirement 6: Exclusions by tag

**User Story:** As an analyst, I want trails that happen to run beside a road to
stay trails.

#### Acceptance Criteria

1. The system SHALL NOT label a cycleway way as a PBL when it matches an
   exclusion rule.
2. The exclusion rules are TO BE DECIDED (see Open Questions 1 and 2).

### Requirement 7: Mileage

**User Story:** As an analyst, I want PBL mileage counted per direction and in
one category only, so that it matches how other bike infrastructure is counted
and the mileage table can be trusted.

#### Acceptance Criteria

1. The system SHALL count bike infrastructure mileage per direction, as it does
   today for lanes and on-street tracks: a two-way PBL segment counts its length
   twice in `track`, and a one-way PBL segment counts it once.
2. The system SHALL NOT count a detected PBL segment in the `path` mileage.
3. The system SHALL continue to count undetected cycleway segments in the `path`
   mileage, once per segment.

### Requirement 8: No side effects on routing, scoring or outputs

**User Story:** As a maintainer, I want this change limited to labeling and
mileage, so that BNA scores do not shift unexpectedly and output files keep the
same schema.

#### Acceptance Criteria

1. The system SHALL keep `functional_class = 'path'` on detected PBL segments.
2. The system SHALL NOT change stress values for any segment.
3. The system SHALL NOT change `neighborhood_paths` or `path_id`.
4. The system SHALL NOT add columns or attributes to any exported table or
   output file. Detection results SHALL appear only as values in the existing
   `ft_bike_infra` and `tf_bike_infra` columns, and intermediate results SHALL
   be kept in temporary tables or queries.

### Requirement 9: Adjustable parameters

**User Story:** As an analyst, I want to tune the detection thresholds by
changing one value in one place, so that I can test values across cities without
editing the SQL logic.

#### Acceptance Criteria

1. The system SHALL define `pbl_outer_buffer_m`, `pbl_min_piece_m`,
   `pbl_core_distance_m` and `pbl_segment_share` once, alongside the other
   internal analysis constants, and pass them to the SQL as parameters.
2. The system SHALL NOT hard-code these values in the SQL.
3. The system SHALL NOT add command-line options for these values in this
   iteration.
4. The defaults SHALL be decided before approval (see Open Question 3). The Bend
   prototype used 12 m, 60 m, 7 m and 0.5.

### Requirement 10: Performance

**User Story:** As an operator, I want PBL detection to add little run time.

#### Acceptance Criteria

1. The system SHALL build the road buffer once per run, not once per segment or
   per way.
2. For a city the size of Bend, OR, the PBL detection step SHALL complete in
   under 10 seconds.

### Requirement 11: Validation

**User Story:** As a reviewer, I want known examples checked, so that I can
trust the method before it ships.

#### Acceptance Criteria

1. The system SHALL produce the expected labels for the reference ways below,
   using the default parameters.
2. A validation query or test SHALL report, per OSM way, the number of segments
   and the number labeled `track`. This is how mixed labels are detected.

| Way                   | Place          | Expected                                   |
| --------------------- | -------------- | ------------------------------------------ |
| 1480451437            | Bend, OR       | PBL, one-way `ft` (raised, NE Olney Ave)   |
| 1480451438            | Bend, OR       | PBL, one-way `ft` (NE Olney Ave)           |
| 1474322573            | Bend, OR       | PBL, one-way `ft` (NE Franklin Ave)        |
| 1092208840            | Portland, OR   | PBL, two-way (SW Naito Parkway)            |
| 1354189308            | Providence, RI | PBL along the road, path after \*          |
| 532649750             | Bend, OR       | Path (Larkspur Trail)                      |
| 935195280             | Bend, OR       | Path (Deschutes River Trail)               |
| 277177723             | Bend, OR       | Path (side path along Green Lakes Loop) \* |
| 297308987             | Bend, OR       | Path (Haul Road Trail) \*                  |
| 1499802408            | Bend, OR       | Path (Haul Road Trail) \*                  |
| 416137820             | Bend, OR       | Path (Coyner Trail) †                      |
| 1497195035-1497195040 | Bend, OR       | Side paths: to be decided \*               |

\* Depends on Open Question 1. † Depends on Open Question 2.

## Background: Bend, OR test (2026-10-05)

### Distance from the road separates PBLs from side paths

Median distance from each cycleway to the nearest road centerline:

| Way                                   | Judged as | Median distance |
| ------------------------------------- | --------- | --------------- |
| SW Naito Pkwy, Portland (1092208840)  | PBL       | 4.6 m           |
| NE Olney Ave (1480451437, 1480451438) | PBL       | 4.7-5.2 m       |
| NE Franklin Ave (1474322573)          | PBL       | 5.0 m           |
| Haul Road Trail (1499802408)          | path      | 8.2 m           |
| 277177723 (Green Lakes Loop)          | path      | 9.4 m           |
| Side-path cluster (1497195035-40)     | either    | 9.9-10.5 m      |
| Haul Road Trail (297308987)           | path      | 10.7 m          |

Real PBLs drift farther from the centerline near intersections: parts of Olney
sit 7-10 m away. A single distance therefore either misses parts of real PBLs
(about 7 m) or catches side paths (10-12 m). This is why Requirement 3 uses two
thresholds: a looser buffer to find the stretches, and a tighter typical
distance to decide whether each stretch is a PBL.

### Results

| Measure                                    | `pbl-methodology`  | Prototype |
| ------------------------------------------ | ------------------ | --------- |
| OSM ways with mixed segment labels         | 68                 | 7         |
| OSM ways labeled entirely `track`          | 262 (mostly stubs) | 14        |
| Reference PBLs fully labeled, correct dir. | 0 of 3             | 3 of 3    |
| Reference paths and side paths left alone  | 1 of 10            | 9 of 10   |
| Directional `track` miles from cycleways   | 13.0               | 5.0       |
| Run time                                   | n/a                | ~2 s      |

The prototype used 12 m, 60 m, 7 m and 0.5. Remaining false positives are ways
named as trails (Coyner Trail, Discovery Trail, Cascade Highlands Connector),
mostly along residential streets; see Open Question 2.

## Known Limitations

- **Cycleways split into short OSM ways.** Each OSM way is judged separately, so
  a short piece of a PBL (under `pbl_min_piece_m`) may not be detected. Joining
  connected cycleway ways into chains first would fix this, but made the Bend
  run about eight times slower, so it is not part of this iteration.
- **Roundabouts.** Cycleways circling a roundabout are made of many short OSM
  ways (for example 1206052645-1206052656 around the Newport Avenue roundabout
  in Bend), so some pieces may be labeled PBL and others path. This appears to
  be rare, and the correct label for roundabout cycleways is undecided.

## Open Questions

1. **Side paths and shared-use paths.** Should side paths set back from the road
   count as PBLs? With the prototype defaults they do not (they sit 8-11 m from
   the road centerline). A colleague considers Providence way 1354189308 a PBL.
   Separately, should cycleways tagged `foot=designated` or
   `pedestrian=designated` with `segregated=no` be excluded? Note that one piece
   of NE Franklin Ave (1474322575), a confirmed PBL, is tagged `foot=yes` and
   `segregated=no`. Owner: Grace and colleague.
2. **Trail signals.** The remaining false positives are named as trails and
   mostly run along residential streets. Options: drop `residential` from the
   road allow-list (all confirmed PBLs are on secondary or tertiary roads),
   treat names containing "Trail" as trails, lower `pbl_core_distance_m`
   slightly, or use an `operator` that is a parks department (this tag is not
   imported today).
3. **Defaults.** What are the default values for the four parameters? They
   should be checked on at least one more city besides Bend, ideally one with
   many PBLs (for example Portland).

## Resolved Questions

- **Two thresholds:** a single distance cannot separate real PBLs from side
  paths (see Background), so stretches are found with a looser buffer and judged
  by their typical distance.
- **No chaining:** cycleway ways are not joined into chains before detection, to
  keep the run fast and the logic simple (see Known Limitations).
- **Trunk roads:** `trunk` and `trunk_link` are excluded from the road buffer,
  like motorways, because a PBL along them would be unusual.
- **Allow-list:** car roads are chosen by naming the types that count, reusing
  the road types and access rules of `functional_class.sql`, instead of
  excluding types. In Bend, the old exclusion approach let in `construction`,
  `proposed` (unbuilt), `corridor` (indoor) and `raceway` ways.
- **Adjusting parameters:** thresholds are constants edited in code (like the
  existing traffic-signal search distance), not command-line options.
- **Living streets:** `living_street` is excluded from the road buffer.
  `functional_class.sql` also assigns it to `highway=pedestrian` ways that allow
  bikes, and a cycleway beside a pedestrian street is not a PBL.
- **Other path types:** `highway=path` ways are never PBL candidates.
- **Separate reporting:** PBL mileage is not reported separately; it is part of
  the `track` total.
