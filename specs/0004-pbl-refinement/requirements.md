# Requirements Document: Protected Bike Lane (PBL) Refinement

## Status

DRAFT. Open questions are listed in the last section and must be resolved before
this document is approved. The reasons behind each rule, the alternatives tested
and the test results are in `decisions.md`.

## Plain-Language Summary: How we identify protected bike lanes in OpenStreetMap

Many protected bike lanes and side paths are mapped in OpenStreetMap as their
own separate "bike path" lines, not as part of the street. Until now, the BNA
counted every one of those as an off-street trail. We now check where each bike
path actually runs, and count it as a protected lane/side path wherever it gives
people an alternative to riding on a street.

**A stretch of bike path counts when it:**

- **Runs right alongside a street,** within about 25 meters (80 feet) of the
  street's centerline, beside the street rather than past the end of it. That's
  close enough to include curb-side protected lanes and side paths set back
  behind a grass or tree strip, including along wide arterials and freeways. In
  Philadelphia, this matched mappers' own judgment for 94% of the bike paths
  they had tagged as side paths or not.
- **Follows the street,** roughly in the same direction (within about 15°). This
  keeps out paths that just cross a street, including ones that cross at a
  shallow angle or pass under a bridge.
- **Is at the same level as the street.** A path on a bridge is compared with
  roads on bridges, and a path on the ground with roads on the ground. A freeway
  passing overhead, or a road passing under a path bridge, doesn't count.
- **Is judged as a whole path.** Bike paths that mappers split into short pieces
  are joined back together first, including their street crossings. If a side
  path dips away from the street for a short distance (up to 400 meters, about a
  quarter mile) and then comes back, that dip still counts, as long as it stays
  within 40 meters (130 feet) of a road.

**What's included:**

- Protected bike lanes and side paths along any regular street, from
  neighborhood streets to major arterials.
- The parts of trails that run alongside a street. A trail can be partly
  "protected lane" (where it follows a road) and partly "trail" (where it heads
  off on its own).
- Paths shared with pedestrians.
- Paved general "paths" that are open to bikes, not only "bike paths".
- Paths along highways and freeways, including near their ramps, since they
  offer a route along the same corridor (for example the SR 520 Trail in the
  Seattle area).

**What's not included:**

- Unpaved paths, and general "paths" not marked as open to bikes. To be
  included, a path must be mapped as `highway=cycleway`, or as `highway=path`
  with `bicycle=yes` or `bicycle=designated` and a paved surface.
- Trails, or parts of trails, that don't follow a street.

**How it's counted:** a detected protected lane or side path counts its length
once, unless it is mapped as two-way for bikes (`oneway=no`), in which case it
counts twice. This avoids overcounting streets with a side path on each side.
On-street protected lanes keep the BNA's usual count, once per direction that
has one. These miles are counted as protected lanes instead of off-street paths,
never as both.

**Known gaps:** a few kinds of paths are labeled inconsistently, such as paths
circling a roundabout or park paths just under 25 meters from a wide road. They
are a small share of total mileage; see Known Limitations.

## Introduction

Protected bike lanes are often mapped in OpenStreetMap (OSM) as separate
`highway=cycleway` ways instead of as `cycleway=track` tags on the road. The BNA
classifies every `highway=cycleway` as an off-street path
(`functional_class = 'path'`), so these PBLs cannot be told apart from trails.
That means we cannot report PBL mileage, which is a deliverable for the end
of 2026.

This feature detects the parts of bike paths (`highway=cycleway`, and paved
`highway=path` ways open to bikes) that run parallel to a road, offering an
alternative to riding on the road itself, and labels them as protected lanes
(`ft_bike_infra`/`tf_bike_infra = 'track'`). They are then counted as `track` in
the mileage table instead of `path`. This includes curb-side PBLs, side paths
set back from the road, and the parts of trails that run alongside a road.

It replaces the approach drafted on the `pbl-methodology` branch, which tested
each segment separately and labeled road crossings on trails as PBLs (see
`decisions.md`).

### In scope

- Detecting the parts of candidate bike paths (Requirement 1) that run parallel
  to a road, using geometry relative to car roads.
- Setting `ft_bike_infra`/`tf_bike_infra` on detected segments, with the correct
  direction.
- Fixing mileage so a detected PBL is counted as `track` only, not also as
  `path`, and counting only the length inside the city boundary for all mileage
  categories.
- Making the detection thresholds adjustable.

### Out of scope

- Changing `functional_class`, stress scores, or trail networks
  (`neighborhood_paths`). Detected PBLs remain `functional_class = 'path'`.
  Trails will be revisited in a separate effort.
- Porting this logic to the Python pipeline (`feature/nosql`, release 5.0). That
  port will follow separately.
- Detecting PBLs among ways other than the candidates in Requirement 1 (for
  example `highway=footway`, or unpaved `highway=path`).
- Reporting PBL mileage separately from on-street `cycleway=track` mileage. Both
  are combined in the `track` total.
- Excluding cycleways by tag (name, `foot`, `segregated`, `operator`, etc.).

## Glossary

- **PBL (protected bike lane)**: for this feature, any part of a separated
  cycleway that runs parallel to a road, offering an alternative to riding on
  the road itself or a route along its corridor. This includes curb-side PBLs,
  side paths set back from the road, paths along highways and freeways, and the
  parts of trails that run alongside a road.
- **Candidate way**: one OSM way that meets Requirement 1, identified by its
  `osm_id`, with its full geometry from `neighborhood_osm_full_line`.
- **Chain**: candidate ways joined end to end where they connect (merged into
  one continuous line wherever exactly two of them meet), so that a path split
  into many short OSM ways is judged as a whole.
- **Segment**: one row of `neighborhood_ways`. The import splits each OSM way
  into segments at intersections; all segments of a way share its `osm_id`.
- **Car road**: a road segment used as the reference for detection, selected by
  the allow-list in Requirement 2.
- **Level**: whether a way is on a bridge, in a tunnel, or on the ground, from
  its OSM `bridge` and `tunnel` tags. `bridge=boardwalk` counts as ground.
- **Road buffer**: the area within `pbl_buffer_m` meters of any car road, merged
  into one shape per level. The buffer has flat ends: it covers the area beside
  each road but not past the end of it.
- **Overlap piece**: one continuous part of a chain that lies inside the road
  buffer for its own level.
- **Parallel stretch**: an overlap piece whose median angle to the nearest car
  road at the same level is at most `pbl_max_angle_deg`. A path crossing a road
  produces a piece at a steep angle; a path running alongside a road produces a
  piece at a small angle.
- **Bike direction tag**: `oneway:bicycle` if it is set, otherwise `oneway`. See
  Requirement 5.

## Requirements

### Requirement 1: Candidate selection

**User Story:** As an analyst, I want only bike paths considered for PBL
detection, so that roads, footways and unpaved trails are not affected.

#### Acceptance Criteria

1. The system SHALL consider as PBL candidates only segments whose
   `functional_class` is `'path'` and whose OSM way is either:
   - tagged `highway=cycleway`, or
   - tagged `highway=path` with `bicycle=yes` or `bicycle=designated`, and a
     `surface` of `paved`, `asphalt`, `concrete`, `concrete:plates`,
     `concrete:lanes`, `paving_stones` or `chipseal`.
2. The system SHALL NOT consider `highway=path` ways with no `surface` tag,
   since they cannot be confirmed as paved.
3. The system SHALL NOT consider segments marked as footway crossings
   (`xwalk = 1`).
4. The system SHALL NOT change `ft_bike_infra`/`tf_bike_infra` on non-candidate
   segments.

### Requirement 2: Car-road reference set

**User Story:** As an analyst, I want PBLs detected along any road that carries
motor traffic, including highways and freeways, so that every path along a road
corridor is counted.

#### Acceptance Criteria

1. The system SHALL build the road buffer from segments in `neighborhood_ways`
   whose `functional_class`, as set by `functional_class.sql`, is one of:
   `motorway`, `motorway_link`, `trunk`, `trunk_link`, `primary`,
   `primary_link`, `secondary`, `secondary_link`, `tertiary`, `tertiary_link`,
   `residential` or `unclassified`.
2. The system SHALL use this allow-list, so that any other road type (for
   example `construction`, `proposed`, `corridor` or `raceway`) is never part of
   the road buffer.
3. The system SHALL NOT include `living_street` in the road buffer, although
   `functional_class.sql` keeps it as a road.
4. WHEN a path runs alongside a highway or freeway (for example the SR 520
   Trail, way 47283428, about 14 m from SR 520 in the Seattle area), the system
   SHALL detect it like any other road.
5. WHERE a cycleway runs parallel only to roads outside the allow-list, the
   system SHALL NOT label it as a PBL.
6. The system SHALL compare each part of a candidate way only with car roads at
   the same level (see Glossary). A ground-level path SHALL NOT be detected
   because of a road passing overhead (for example East Burnside Street paths,
   ways 52233661 and 111662265, under I-205 in Portland, OR, are compared with
   East Burnside Street, not I-205), and a path bridge SHALL NOT be detected
   because of a road passing underneath.

### Requirement 3: Parallel stretches

**User Story:** As an analyst, I want the parts of a bike path that run
alongside a road detected on the path as a whole, so that road crossings are
ignored, only the parallel parts are counted, and labels do not depend on where
mappers or the import split the path.

#### Acceptance Criteria

1. The system SHALL merge the car roads into one road buffer, and SHALL join
   connected candidate ways into chains, once per run, before finding parallel
   stretches.
2. The system SHALL identify each chain's overlap pieces with the road buffer
   for the same level.
3. The system SHALL NOT apply a minimum length to overlap pieces; crossings are
   excluded by the angle check in criterion 4.
4. The system SHALL compute the angle between each overlap piece and the nearest
   car road at the same level, at points sampled along the piece, and SHALL
   treat the piece as a parallel stretch only if the median angle is at most
   `pbl_max_angle_deg`. This excludes paths that cross a road at a shallow
   angle, including where the road or path is not tagged as a bridge (for
   example way 39947864 under SW Reed Market Road in Bend, OR, and the Southwest
   Path, way 1417451441, crossing Commonwealth Avenue in Madison, WI).
5. WHEN a chain runs alongside a road for only part of its length, the system
   SHALL detect only that part (for example the part of Haul Road Trail
   297308987 in Bend, OR along Colorado Avenue).
6. WHERE a bike path is split into many short OSM ways, or into separately
   mapped crossings (`cycleway=crossing`) along the road, the system SHALL judge
   the joined chain, so that each piece takes the label of the stretch it lies
   in (for example the Delaware River Trail along Columbus Boulevard and the
   East Coast Greenway crossings along East Allegheny Avenue in Philadelphia).
7. WHEN two parallel stretches on the same chain are separated by a gap of at
   most `pbl_max_gap_m`, and no point of the gap is farther than
   `pbl_max_gap_dist_m` from a car road, the system SHALL treat the gap as part
   of the parallel stretch, so that a side path that dips away from the road for
   a short distance still counts (for example the West Bend Trail along
   Skyliners Road in Bend, OR, way 266268193, and the Marine Drive Trail in
   Portland, OR, way 5520929).
8. WHEN a gap strays farther than `pbl_max_gap_dist_m` from every car road, the
   system SHALL NOT fill it (for example way 1421068993 in Madison, WI, which
   runs behind houses, up to about 45 m from the road).
9. The system SHALL build the road buffer with flat ends, so that a path that
   continues past the end of a road, such as a connector between two dead-end
   streets, does not count as running alongside it (for example way 102021058
   between Parman Terrace and the Southwest Path in Madison, WI).

### Requirement 4: Segment labeling

**User Story:** As an analyst, I want each segment labeled by where most of it
lies, so that partial PBLs are handled and short stubs are not labeled.

#### Acceptance Criteria

1. WHEN at least half of a candidate segment's length lies within parallel
   stretches, the system SHALL label that segment as a PBL.
2. WHEN less than half of a candidate segment's length lies within parallel
   stretches, the system SHALL leave that segment as a path.
3. The half-length rule is fixed, not an adjustable parameter.
4. WHERE a candidate way lies entirely within one parallel stretch, the system
   SHALL give all of its segments the same label.

### Requirement 5: Direction

**User Story:** As an analyst, I want a detected PBL counted in both directions
only when it is mapped as two-way, so that streets with a side path on each side
are not overcounted.

#### Acceptance Criteria

1. WHEN a detected PBL's bike direction tag is `no`, the system SHALL set both
   `ft_bike_infra` and `tf_bike_infra` to `'track'`.
2. WHEN a detected PBL's bike direction tag is `-1`, the system SHALL set only
   `tf_bike_infra` to `'track'`.
3. In every other case, including when no direction tag is set, the system SHALL
   set only `ft_bike_infra` to `'track'`.
4. `oneway:bicycle` takes precedence over `oneway`, so `oneway=yes` with
   `oneway:bicycle=no` is two-way, and `oneway=no` with `oneway:bicycle=yes` is
   one-way.
5. The system SHALL NOT change the routing direction (`one_way`), which stays as
   set from the car one-way tags, so an untagged path remains rideable in both
   directions.

### Requirement 6: No exclusions by tag

**User Story:** As an analyst, I want every path that parallels a road counted,
whatever it is called or whoever uses it, so that all alternatives to riding on
the road are included.

#### Acceptance Criteria

1. The system SHALL NOT exclude a candidate from PBL detection based on its name
   (for example names containing "Trail").
2. The system SHALL NOT exclude a candidate from PBL detection based on shared
   use with pedestrians (`foot`, `pedestrian`, `segregated`).

### Requirement 7: Mileage

**User Story:** As an analyst, I want PBL mileage counted in one category only,
following the direction labels, so that the mileage table can be trusted.

#### Acceptance Criteria

1. The system SHALL count bike infrastructure mileage per labeled direction, as
   it does today for lanes and on-street tracks: a segment labeled `track` in
   both directions counts its length twice, and one labeled in one direction
   counts it once (see Requirement 5 for detected PBLs).
2. The system SHALL NOT count a detected PBL segment in the `path` mileage.
3. The system SHALL continue to count undetected candidate segments in the
   `path` mileage, once per segment.
4. The system SHALL count only the part of each segment that lies inside the
   city boundary, for every mileage category (`track`, `path`, `lane`,
   `buffered_lane`). The import keeps whole OSM ways that touch the city, so
   without this, segments mostly outside the city are counted in full (for
   example Bend cycleway 143517588, where one 1,168 m segment has only 34 m
   inside the city).
5. The system SHALL NOT report `sharrow` in the mileage table, because shared
   lane markings are not tagged consistently in OSM. Sharrow labels on roads are
   unchanged and still used for stress.

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

1. The system SHALL define `pbl_buffer_m`, `pbl_max_angle_deg`, `pbl_max_gap_m`
   and `pbl_max_gap_dist_m` once, alongside the other internal analysis
   constants, and pass them to the SQL as parameters.
2. The system SHALL NOT hard-code these values in the SQL.
3. The system SHALL NOT add command-line options for these values in this
   iteration.
4. The starting defaults SHALL be:

   | Parameter            | Default | Reason                                                                                                                                     |
   | -------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
   | `pbl_buffer_m`       | 25 m    | Covers curb-side PBLs and side paths set back on wide arterials and freeways; best agreement with Philadelphia mappers' `is_sidepath` tags |
   | `pbl_max_angle_deg`  | 15°     | Ignores paths that cross a road at a shallow angle                                                                                         |
   | `pbl_max_gap_m`      | 400 m   | Fills short gaps where a side path dips away from the road and comes back                                                                  |
   | `pbl_max_gap_dist_m` | 40 m    | Does not fill gaps where the path heads away from the road, for example behind houses                                                      |

5. The system SHALL use one value of each parameter for all roads.

### Requirement 10: Performance

**User Story:** As an operator, I want PBL detection to add little run time.

#### Acceptance Criteria

1. The system SHALL build the road buffer once per run, not once per segment or
   per way.
2. For a city the size of Philadelphia, PA, the PBL detection step SHALL
   complete in under 30 seconds.

### Requirement 11: Validation

**User Story:** As a reviewer, I want known examples checked, so that I can
trust the method before it ships.

#### Acceptance Criteria

1. The system SHALL produce the expected labels for the reference ways below,
   using the default parameters.
2. A validation query or test SHALL report, per OSM way, the number of segments
   and the number labeled `track`. This is how mixed labels are detected.

| Way                                            | Place          | Expected                                                                                       |
| ---------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------- |
| 1480451437                                     | Bend, OR       | PBL, one-way `ft` (raised, NE Olney Ave)                                                       |
| 1480451438                                     | Bend, OR       | PBL, one-way `ft` (NE Olney Ave)                                                               |
| 1474322573                                     | Bend, OR       | PBL, one-way `ft` (NE Franklin Ave)                                                            |
| 1092208840                                     | Portland, OR   | PBL, two-way (SW Naito Parkway)                                                                |
| 1354189308                                     | Providence, RI | PBL (last segment beside the RI 10 on-ramp, a known limitation)                                |
| 1497195035, 1497195036, 1497195039, 1497195040 | Bend, OR       | PBL where parallel (side paths; 1497195037 and 1497195038 were deleted from OSM)               |
| 277177723                                      | Bend, OR       | PBL where parallel (side path)                                                                 |
| 297308987                                      | Bend, OR       | PBL along Colorado Ave, path elsewhere (trail)                                                 |
| 416137820                                      | Bend, OR       | PBL along NE 9th/10th, path elsewhere (trail)                                                  |
| 532649750                                      | Bend, OR       | Path (Larkspur Trail, only crosses roads)                                                      |
| 935195280                                      | Bend, OR       | Path (Deschutes River Trail, only crosses)                                                     |
| 39947864                                       | Bend, OR       | Path (passes under SW Reed Market Rd bridge)                                                   |
| 1346549973-1346549986                          | Philadelphia   | PBL (Delaware River Trail, many short pieces)                                                  |
| 748844480, 748844482                           | Philadelphia   | PBL (East Coast Greenway crossings)                                                            |
| 132508834                                      | Philadelphia   | PBL (Schuylkill River Trail, Kelly Drive)                                                      |
| 206503757                                      | Philadelphia   | PBL (PNE Trail, paved `highway=path`)                                                          |
| 680608875                                      | Philadelphia   | PBL (Lincoln Drive Trail, `bridge=boardwalk`)                                                  |
| 1101812320                                     | Philadelphia   | Path under I-95; the segments past Richmond Street are PBL by gap fill (known limitation)      |
| 192545206                                      | Philadelphia   | Path (Grays Ferry Crescent)                                                                    |
| 52233661, 111662265                            | Portland, OR   | PBL (East Burnside Street, under I-205)                                                        |
| 130668349                                      | Providence, RI | Path (path bridge)                                                                             |
| 90091980                                       | Providence, RI | Path (India Point Park Bridge)                                                                 |
| 124607001                                      | Portland, OR   | PBL (NE 82nd Avenue, gap fill)                                                                 |
| 473843985                                      | Bend, OR       | Mostly path (Mountain View Park loop); the side along NE Conners Ave is PBL (known limitation) |
| 102021058                                      | Madison, WI    | Path (connector between two dead-end streets)                                                  |
| 1417451441                                     | Madison, WI    | Path (Southwest Path crossing Commonwealth Avenue)                                             |
| 1421068993                                     | Madison, WI    | Path behind houses (beyond 40 m); PBL only at the ends along Redan Dr and Rustic Pine Rd       |
| 308498820                                      | Madison, WI    | Path (Capital City Path)                                                                       |
| 996106676                                      | Bozeman, MT    | PBL (side path on the west side of N 19th Ave, 24-27 m away)                                   |
| 572643454                                      | Madison, WI    | PBL (West Beltline Bike Path, 21-22 m from the freeway)                                        |
| 30262881                                       | Portland, OR   | PBL where within 25 m of NE Marine Drive, path where it moves farther (Marine Drive Trail)     |

## Known Limitations

- **Roundabouts.** Cycleways circling a roundabout are made of many short OSM
  ways, and the angle to the nearest road keeps changing, so some pieces may be
  labeled PBL and others path (for example around the Newport Avenue roundabout
  in Bend, OR).
- **Untagged bridges.** Levels come from OSM `bridge` and `tunnel` tags, so a
  path on an untagged bridge beside a tagged road bridge is not detected. A
  ground-level path beside, not under, an elevated road is also not detected
  (for example part of the Vera Katz Eastbank Esplanade, way 115809984, beside
  the Marquam Bridge in Portland, OR).
- **Roads that change height without tags.** A road that climbs or drops without
  a `bridge` or `tunnel` tag, such as a ramp on an embankment, is treated as
  ground level (for example the last segment of way 1354189308 in Providence,
  RI, beside an on-ramp to the Huntington Expressway, way 1084625129).
- **Second path beside a side path.** A path running just beyond a side path,
  still within the buffer, is also labeled PBL (for example the Waterfront Park
  Trail, ways 103611804 and 119557003, beyond the SW Naito Parkway side path in
  Portland, OR).
- **Short pieces anchoring gap fill.** A short parallel piece, where a path
  briefly comes close to a road, can anchor a gap fill within 40 m (for example
  two segments of the Delaware River Trail, way 1101812320, past Richmond Street
  in Philadelphia).
- **Gap fill distance.** Some real dips stray more than 40 m from the road and
  become paths (for example parts of the Larkspur Trail, way 434843594, and the
  West Bend Trail, way 266268202, in Bend, OR).
- **Park paths near a wide road.** A park path within 25 m of a wide road can be
  labeled PBL where it runs parallel to it (for example way 142063148, 18-19 m
  from SW Reed Market Road, and part of the Mountain View Park loop, way
  473843985, in Bend, OR).
- **Switchback ramps.** A ramp that zigzags beside a road runs parallel to it,
  so it may be labeled PBL (for example the ramp to the pedestrian bridge over
  I-195 along Portugal Parkway in Providence, RI).

## Open Questions

1. **Philadelphia.** Do the reference ways and the agreement with mappers'
   `is_sidepath` tags hold up in Philadelphia with the final rules? It was last
   run before flat buffer ends, the 15° angle and the 40 m gap distance.
