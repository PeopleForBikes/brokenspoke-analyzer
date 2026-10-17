# Decisions and Testing: Protected Bike Lane (PBL) Refinement

This file records why the rules in `requirements.md` are what they are: the
decisions made, the alternatives tested and not adopted, and the test results
behind them. `requirements.md` describes only the method itself.

Test cities: Providence, RI; Philadelphia, PA; Portland, OR; Bend, OR; Bozeman,
MT; and Madison, WI. Philadelphia was left out of repeated test runs from
2026-10-15 because it takes about 1.5 hours to load.

## Decision Log

- **Definition (2026-10-06):** any part of a cycleway that runs parallel to a
  road counts as a PBL, because it offers an alternative to riding on the road.
  Side paths and the parallel parts of trails are included.
- **No tag exclusions:** cycleways are not excluded by name (such as "Trail") or
  by shared use with pedestrians.
- **Residential streets** count: a path alongside a residential street is still
  an alternative to riding on it.
- **Allow-list:** car roads are chosen by naming the types that count, reusing
  the road types and access rules of `functional_class.sql`, instead of
  excluding types. In Bend, the old exclusion approach let in `construction`,
  `proposed` (unbuilt), `corridor` (indoor) and `raceway` ways.
- **Living streets:** `living_street` is excluded from the road buffer.
  `functional_class.sql` also assigns it to `highway=pedestrian` ways that allow
  bikes, and a cycleway beside a pedestrian street is not a PBL.
- **One buffer for all roads,** rather than a buffer that varies by road class,
  to keep the method simple. Because side paths count, curb-side PBLs and side
  paths do not need separate thresholds either.
- **Chains (2026-10-08):** candidate ways are joined into chains before
  detection. Done once per run, joining is fast (about 9 seconds for all of
  Philadelphia) and it fixes gaps at crossings and in finely split trails.
- **Buffer (2026-10-08):** 20 m, based on agreement with Philadelphia's
  `is_sidepath` tags (see Test Results).
- **Gap fill (2026-10-08):** gaps of up to 400 m between parallel stretches on
  the same path count, for side paths that dip away from the road and come back.
- **Segment rule (2026-10-08):** a segment is labeled by where at least half of
  it lies. This is fixed rather than adjustable.
- **Other path types (2026-10-08):** `highway=path` ways are candidates when
  tagged `bicycle=yes` or `bicycle=designated` and paved. Unpaved or
  untagged-surface paths are not (for example the unpaved Waterline Trail in
  Bend).
- **No minimum length (2026-10-09):** the 60 m minimum stretch was removed. With
  chains and the angle check, it no longer changed agreement with mappers.
- **Mileage inside the boundary (2026-10-13):** because this change already
  edits `calculate_mileage.sql`, it also limits all mileage to the length inside
  the city boundary, in line with the policy that ratings only consider what is
  inside a city.
- **Separate reporting:** PBL mileage is not reported separately; it is part of
  the `track` total.
- **Adjusting parameters:** thresholds are constants edited in code (like the
  existing traffic-signal search distance), not command-line options.
- **Highways and freeways (2026-10-14):** `motorway`, `motorway_link`, `trunk`
  and `trunk_link` are included in the road buffer. A path along a highway
  offers a route along the same corridor (for example the SR 520 Trail, way
  47283428, in the Seattle area). This reversed an earlier decision to exclude
  them.
- **Levels (2026-10-15):** a path is compared only with roads at the same level
  (bridge, tunnel or ground). Including highways made freeways passing overhead
  the nearest road for paths beneath them, which failed the angle check (East
  Burnside Street under I-205 in Portland) or passed it wrongly (the Delaware
  River Trail under I-95 in Philadelphia). This replaced an earlier decision not
  to use `bridge` tags; the angle check still excludes crossings where bridges
  are untagged. `bridge=boardwalk` counts as ground (Lincoln Drive Trail in
  Philadelphia).
- **Roads only (2026-10-16):** detection uses only roads and paths and their
  tags. Other OSM features, such as buildings, walls or land use, are not used.
- **Flat buffer ends (2026-10-16):** the road buffer covers the area beside a
  road but not past its end. This removed connectors between dead-end streets
  and paths that continue in line with a road (for example ways 102021058 and
  308498820 in Madison) and kept every confirmed side path.
- **Angle 15° (2026-10-16):** lowered from 20°. This removed shallow crossings
  (for example the Southwest Path across Commonwealth Avenue in Madison) and the
  Mountain View Park loop in Bend, and kept every confirmed side path.
- **Gap fill distance 40 m (2026-10-16):** a gap is filled only if it stays
  within 40 m of a road. Every stretch this removed in the test cities was
  judged a path or acceptable either way, including way 1421068993 in Madison,
  which runs behind houses.

## Alternatives Tested and Not Adopted

| Idea                                                   | Why not                                                                                                                             |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- |
| Per-segment test (`pbl-methodology` branch)            | Labeled trail crossings as PBLs, split ways into mixed labels, and counted one-way PBLs twice (see Test Results)                    |
| No chaining                                            | Left gaps at crossings and in finely split trails                                                                                   |
| 60 m minimum stretch                                   | No effect on agreement once chains and the angle check were in place                                                                |
| Separate thresholds for curb-side PBLs and side paths  | Not needed, since both count                                                                                                        |
| Excluding highways                                     | Missed real side paths along freeways (SR 520 Trail, I-205 Multi-Use Path)                                                          |
| Excluding highway ramps                                | Portland lost about 3.4 mi of the I-205 Multi-Use Path, and the Providence on-ramp case stayed PBL because of the expressway itself |
| Wider buffer for freeways                              | Would fix a few side paths just over 20 m from a freeway, at the cost of a second buffer value                                      |
| Only the path closest to the road counts               | Would also remove part of the Larkspur Trail in Bend                                                                                |
| Rule against paths that double back (switchback ramps) | Extra complexity for a rare case                                                                                                    |
| Minimum stretch length for gap fill (10, 20, 30 m)     | Removed about as much real side path (NE 82nd Avenue in Portland, Bozeman side paths) as wrongly filled length                      |
| Gap no longer than the stretches on both sides         | Removed real side paths in Bozeman and did not fix the Bend park loop                                                               |
| Same street on both sides of a gap                     | Broke the I-205 Multi-Use Path, where the nearest road switches between the unnamed freeway, ramps and cross streets                |
| 40 m, or 60 m when both sides follow the same street   | Matched the judged examples but was fitted to them and harder to explain                                                            |
| Gap distance cap of 60 m                               | Kept gaps judged wrong, such as the path behind houses in Madison (45 m)                                                            |
| Angle of 20° or 10°                                    | 20° let shallow crossings through; 10° removed real side paths (West Bend Trail, Larkspur Trail)                                    |
| Buildings, walls or other non-road features            | Outside the roads-only principle                                                                                                    |

## Test Results

### Bend, OR: the `pbl-methodology` approach (2026-10-05)

- 68 OSM ways (20.4 mi) got different labels on different segments.
- Road crossings on trails were labeled as PBLs: 231 of the 262 ways labeled
  entirely `track` were shorter than 25 m.
- One-way PBLs were counted in both directions (for example NE Franklin Ave,
  `oneway=yes`).
- Parts of real PBLs near intersections were missed (for example the end of
  1480451437, up to 10.8 m from the road centerline).

### Distance from the road (2026-10-05)

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
and side paths sit 8-11 m away, with some stretches farther (up to about 16 m).
A side path's distance from the centerline is roughly half the road width, plus
the street buffer, plus half the path width: about 8.5-10 m on a two-lane
street, 12-14 m on a four-lane arterial and 15-17 m on a six-lane arterial
(typical dimensions from general bikeway design guidance).

### Philadelphia: agreement with mappers' `is_sidepath` tags (2026-10-08)

Philadelphia mappers tagged 770 of 912 cycleways with `is_sidepath=yes` (32.8
mi) or `is_sidepath=no` (42.1 mi). Using chains, a 60 m minimum stretch and a
20° angle:

| Buffer | `yes` labeled PBL | `no` left as path | Overall agreement |
| ------ | ----------------- | ----------------- | ----------------- |
| 10 m   | 42%               | 99.8%             | 74.5%             |
| 12 m   | 64%               | 99.7%             | 84.1%             |
| 15 m   | 78%               | 98.5%             | 89.4%             |
| 20 m   | 88%               | 97.5%             | 93.4%             |
| 25 m   | 91%               | 96.2%             | 94.1%             |
| 30 m   | 92%               | 95.0%             | 93.8%             |

Removing the 60 m minimum stretch left agreement unchanged (93.5%). Most
`no`-tagged paths labeled PBL at 20 m are stretches of trails that run alongside
a road (for example Lincoln Drive Trail and the Manayunk Canal Towpath); mappers
tagged the whole trail `no`, but under this feature's definition those stretches
count. These numbers predate the final rules and should be rechecked.

### Physical PBL miles as the rules changed

| City         | Highways added (2026-10-14) | Levels (2026-10-15) | Flat ends (2026-10-16) | 15°       | 40 m gap cap (final) |
| ------------ | --------------------------- | ------------------- | ---------------------- | --------- | -------------------- |
| Bozeman      | 18.3                        | 18.4                | 18.3                   | 18.2      | 18.2                 |
| Bend         | 18.5                        | 18.7                | 18.7                   | 18.1      | 17.7                 |
| Providence   | 7.9                         | 7.7                 | 7.7                    | 7.6       | 7.5                  |
| Madison      | 41.0                        | 41.5                | 40.6                   | 39.7      | 39.2                 |
| Portland     | 52.3                        | 53.3                | 52.5                   | 51.6      | 50.6                 |
| Philadelphia | 44.1                        | 43.9                | not rerun              | not rerun | not rerun            |

Gap fill added about 6.8 mi across the five cities at 15° with flat ends, before
the 40 m cap; the cap removed about 1.9 mi of it. A second path just beyond a
side path (for example the Waterfront Park Trail in Portland) was under 1% of
PBL mileage in every city.
