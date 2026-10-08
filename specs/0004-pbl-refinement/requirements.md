# Requirements Document: Protected Bike Lane (PBL) Refinement

## Status

DRAFT. Open questions are listed in the last section and must be resolved before
this document is approved.

## Plain-Language Summary: How we identify protected bike lanes in OpenStreetMap

Many protected bike lanes and side paths are mapped in OpenStreetMap as their
own separate "bike path" lines, not as part of the street. Until now, the BNA
counted every one of those as an off-street trail. We now check where each bike
path actually runs, and count it as a protected lane/side path wherever it gives
people an alternative to riding on a street.

**A stretch of bike path counts when it:**

- **Runs right alongside a street,** within about 15 meters (50 feet) of the
  street's centerline. That's close enough to include curb-side protected lanes
  and side paths set back behind a grass or tree strip, on streets up to about
  four lanes wide.
- **Follows the street,** roughly in the same direction (within about 20°). This
  keeps out paths that just cross a street, including ones that pass under a
  bridge at a shallow angle.
- **Stays alongside it for a while,** at least 60 meters (about 200 feet). This
  keeps out the short bits where a path meets or crosses a street.

**What's included:**

- Protected bike lanes and side paths along any regular street, from
  neighborhood streets to major arterials.
- The parts of trails that run alongside a street. A trail can be partly
  "protected lane" (where it follows a road) and partly "trail" (where it heads
  off on its own).
- Paths shared with pedestrians.

**What's not included:**

- Paths along freeways and expressways, and their ramps.
- Paths mapped as general "paths" rather than "bike paths". The path must be
  mapped as ‘highway’ = ‘cycleway’ to be included.
- Trails, or parts of trails, that don't follow a street.

**How it's counted:** protected lane mileage is counted per direction of travel,
like the BNA's other bike lanes. A two-way path counts twice, a one-way path
once. These miles are counted as protected lanes instead of off-street paths,
never as both.

**Known gaps:** very short pieces of a path (for example, where mappers split a
path at a roundabout) can be missed or picked up inconsistently. These are a
small share of total mileage.

## Introduction

Protected bike lanes are often mapped in OpenStreetMap (OSM) as separate
`highway=cycleway` ways instead of as `cycleway=track` tags on the road. The BNA
classifies every `highway=cycleway` as an off-street path
(`functional_class = 'path'`), so these PBLs cannot be told apart from trails.
That means we cannot report PBL mileage, which is a deliverable for the end
of 2026.

This feature detects the parts of `highway=cycleway` ways that run parallel to a
road, offering an alternative to riding on the road itself, and labels them as
protected lanes (`ft_bike_infra`/`tf_bike_infra = 'track'`). They are then
counted as `track` in the mileage table instead of `path`. This includes
curb-side PBLs, side paths set back from the road, and the parts of trails that
run alongside a road.

It replaces the approach drafted on the `pbl-methodology` branch, which tested
each segment separately with no parallel-ness check. A test on Bend, OR showed
that approach labels road crossings on trails as PBLs, gives different labels to
segments of the same OSM way, and counts one-way PBLs in both directions. See
the Background section.

### In scope

- Detecting the parts of `highway=cycleway` ways that run parallel to a road,
  using geometry relative to car roads.
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
- Excluding cycleways by tag (name, `foot`, `segregated`, `operator`, etc.).

## Glossary

- **PBL (protected bike lane)**: for this feature, any part of a separated
  cycleway that runs parallel to a road, offering an alternative to riding on
  the road itself. This includes curb-side PBLs, side paths set back from the
  road, and the parts of trails that run alongside a road.
- **Cycleway way**: one OSM way tagged `highway=cycleway`, identified by its
  `osm_id`, with its full geometry from `neighborhood_osm_full_line`.
- **Segment**: one row of `neighborhood_ways`. The import splits each OSM way
  into segments at intersections; all segments of a way share its `osm_id`.
- **Car road**: a road segment used as the reference for detection, selected by
  the allow-list in Requirement 2.
- **Road buffer**: the area within `pbl_buffer_m` meters of any car road, merged
  into one shape.
- **Overlap piece**: one continuous part of a cycleway way that lies inside the
  road buffer.
- **Parallel stretch**: an overlap piece at least `pbl_min_piece_m` meters long
  whose median angle to the nearest car road is at most `pbl_max_angle_deg`. A
  cycleway crossing a road produces a short piece (about 2 × `pbl_buffer_m` ÷
  sin(angle)) at a steep angle; a cycleway running alongside a road produces a
  long piece at a small angle.
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

**User Story:** As an analyst, I want PBLs detected along streets people would
otherwise ride on, so that paths next to freeways are not counted as PBLs.

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

### Requirement 3: Parallel stretches

**User Story:** As an analyst, I want the parts of a cycleway that run alongside
a road detected on the whole OSM way, so that road crossings are ignored, only
the parallel parts are counted, and labels do not depend on where the import
splits a way.

#### Acceptance Criteria

1. The system SHALL evaluate each cycleway way using its full geometry, not each
   segment independently.
2. The system SHALL identify a cycleway way's overlap pieces with the road
   buffer, and SHALL treat only overlap pieces at least `pbl_min_piece_m` long
   as parallel stretches.
3. WHEN a cycleway way crosses a road at an angle, the system SHALL NOT treat
   the crossing as a parallel stretch, provided the overlap piece is shorter
   than `pbl_min_piece_m`.
4. The system SHALL compute the angle between each overlap piece and the nearest
   car road at points sampled along the piece, and SHALL treat the piece as a
   parallel stretch only if the median angle is at most `pbl_max_angle_deg`.
   This excludes paths that cross a road at a shallow angle, such as a trail
   passing under a road bridge (way 39947864 under SW Reed Market Road in Bend,
   OR), without relying on `bridge` or `tunnel` tags.
5. WHEN a cycleway way runs alongside a road for only part of its length, the
   system SHALL detect only that part (for example way 1354189308 in Providence,
   RI, or the part of Haul Road Trail 297308987 in Bend, OR along Colorado
   Avenue).

### Requirement 4: Segment labeling

**User Story:** As an analyst, I want each segment labeled by how much of it
lies in a parallel stretch, so that partial PBLs are handled and short stubs are
not labeled.

#### Acceptance Criteria

1. WHEN at least `pbl_segment_share` of a candidate segment's length lies within
   parallel stretches, the system SHALL label that segment as a PBL.
2. WHEN less than `pbl_segment_share` of a candidate segment's length lies
   within parallel stretches, the system SHALL leave that segment as a path.
3. WHERE a cycleway way lies entirely within one parallel stretch, the system
   SHALL give all of its segments the same label.

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

### Requirement 6: No exclusions by tag

**User Story:** As an analyst, I want every path that parallels a road counted,
whatever it is called or whoever uses it, so that all alternatives to riding on
the road are included.

#### Acceptance Criteria

1. The system SHALL NOT exclude a cycleway from PBL detection based on its name
   (for example names containing "Trail").
2. The system SHALL NOT exclude a cycleway from PBL detection based on shared
   use with pedestrians (`foot`, `pedestrian`, `segregated`).

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

1. The system SHALL define `pbl_buffer_m`, `pbl_min_piece_m`,
   `pbl_segment_share` and `pbl_max_angle_deg` once, alongside the other
   internal analysis constants, and pass them to the SQL as parameters.
2. The system SHALL NOT hard-code these values in the SQL.
3. The system SHALL NOT add command-line options for these values in this
   iteration.
4. The starting defaults SHALL be:

   | Parameter           | Default | Reason                                                                                                                                                        |
   | ------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | `pbl_buffer_m`      | 15 m    | Covers a 10-12 ft sidepath with a standard street buffer (about 5 ft) along roads of up to about four lanes, measured from road centerline to path centerline |
   | `pbl_min_piece_m`   | 60 m    | Ignores short pieces where a path meets or crosses a road                                                                                                     |
   | `pbl_segment_share` | 0.5     | A segment counts when most of it lies in a parallel stretch                                                                                                   |
   | `pbl_max_angle_deg` | 20°     | Ignores paths that cross a road at a shallow angle                                                                                                            |

5. The system SHALL use one value of each parameter for all roads. Values that
   vary by road class are out of scope, to keep the method simple.

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

| Way                   | Place          | Expected                                       |
| --------------------- | -------------- | ---------------------------------------------- |
| 1480451437            | Bend, OR       | PBL, one-way `ft` (raised, NE Olney Ave)       |
| 1480451438            | Bend, OR       | PBL, one-way `ft` (NE Olney Ave)               |
| 1474322573            | Bend, OR       | PBL, one-way `ft` (NE Franklin Ave)            |
| 1092208840            | Portland, OR   | PBL, two-way (SW Naito Parkway)                |
| 1354189308            | Providence, RI | PBL along the road, path after                 |
| 1497195035-1497195040 | Bend, OR       | PBL where parallel (side paths)                |
| 277177723             | Bend, OR       | PBL where parallel (side path)                 |
| 297308987             | Bend, OR       | PBL along Colorado Ave, path elsewhere (trail) |
| 416137820             | Bend, OR       | PBL along NE 9th/10th, path elsewhere (trail)  |
| 532649750             | Bend, OR       | Path (Larkspur Trail, only crosses roads)      |
| 935195280             | Bend, OR       | Path (Deschutes River Trail, only crosses)     |
| 39947864              | Bend, OR       | Path (passes under SW Reed Market Rd bridge)   |

## Background: Bend, OR test (2026-10-05)

### Problems with the `pbl-methodology` approach

- 68 OSM ways (20.4 mi) got different labels on different segments.
- Road crossings on trails were labeled as PBLs: 231 of the 262 ways labeled
  entirely `track` were shorter than 25 m.
- One-way PBLs were counted in both directions (for example NE Franklin Ave,
  `oneway=yes`).
- Parts of real PBLs near intersections were missed (for example the end of
  1480451437, up to 10.8 m from the road centerline).

### Distance from the road

Median distance from each cycleway to the nearest road centerline:

| Way                                   | Kind      | Median distance |
| ------------------------------------- | --------- | --------------- |
| SW Naito Pkwy, Portland (1092208840)  | curb-side | 4.6 m           |
| NE Olney Ave (1480451437, 1480451438) | curb-side | 4.7-5.2 m       |
| NE Franklin Ave (1474322573)          | curb-side | 5.0 m           |
| Haul Road Trail (1499802408)          | side path | 8.2 m           |
| 277177723 (Green Lakes Loop)          | side path | 9.4 m           |
| Side-path cluster (1497195035-40)     | side path | 9.9-10.5 m      |
| Haul Road Trail (297308987)           | side path | 10.7 m          |

Curb-side PBLs drift up to about 10 m from the centerline near intersections,
and side paths sit 8-11 m away, with some stretches farther (up to about 16 m on
297308987). Because side paths count, the buffer must be wide enough to include
them.

A sidepath's distance from the road centerline is roughly half the road width,
plus the street buffer, plus half the path width. With a 5 ft (1.5 m) buffer and
a 10-12 ft path, that is about 8.5-10 m on a two-lane street, 12-14 m on a
four-lane arterial and 15-17 m on a six-lane arterial. These typical dimensions
come from general bikeway design guidance and should be checked against the
NACTO Urban Bikeway Design Guide.

### Results (2026-10-06)

| Bend, OR                          | 12 m | 15 m | 15 m + angle check |
| --------------------------------- | ---- | ---- | ------------------ |
| OSM ways with any PBL             | 58   | 66   | 64                 |
| OSM ways with mixed labels        | 24   | 22   | 21                 |
| Directional `track` miles         | 21.2 | 25.7 | 25.5               |
| Side-path cluster fully detected  | no   | yes  | yes                |
| Reed Market bridge false positive | yes  | yes  | no                 |

All runs used a 60 m minimum stretch and a 0.5 segment share, and each took 2-4
seconds. Olney Avenue and Franklin Avenue were fully detected, one-way `ft`
only, in every run.

## Known Limitations

- **Cycleways split into short OSM ways.** Each OSM way is judged separately, so
  a short piece of a PBL (under `pbl_min_piece_m`) may not be detected. Joining
  connected cycleway ways into chains first would fix this, but made the Bend
  run about eight times slower, so it is not part of this iteration.
- **Roundabouts.** Cycleways circling a roundabout are made of many short OSM
  ways (for example 1206052645-1206052656 around the Newport Avenue roundabout
  in Bend), so some pieces may be labeled PBL and others path. This appears to
  be rare.

## Open Questions

1. **Defaults.** Do the starting defaults in Requirement 9 hold up in the test
   cities: Providence, RI; Philadelphia, PA; Portland, OR; Bend, OR; Bozeman,
   MT; and Madison, WI?

## Resolved Questions

- **Definition (2026-10-06):** any part of a cycleway that runs parallel to a
  road counts as a PBL, because it offers an alternative to riding on the road.
  Side paths and the parallel parts of trails are included.
- **No tag exclusions:** cycleways are not excluded by name (such as "Trail") or
  by shared use with pedestrians.
- **Simplicity:** one buffer for all roads, rather than a buffer that varies by
  road class. A trail passing under a bridge is excluded by the angle check, not
  by `bridge` tags, because mappers often leave cycleway bridges untagged.
- **Test cities:** Providence, RI; Philadelphia, PA; Portland, OR; Bend, OR;
  Bozeman, MT; and Madison, WI.
- **Residential streets** count: a path alongside a residential street is still
  an alternative to riding on it.
- **Single threshold:** because side paths count, there is no need to separate
  curb-side PBLs from side paths. A two-threshold variant tested in Bend is
  therefore not needed.
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
