# Findings: SQL-to-Python Migration

Everything non-obvious learned while transcribing
`brokenspoke_analyzer/ scripts/sql/**` into `core/pipeline/`. Written down
because **task 11 has deleted the SQL**: this file is now the only record of why
the Python behaves as it does, and several of these rules look like bugs unless
you know they were deliberate.

Each entry says what the rule is, how it was caught, and what it cost. The
"cost" numbers are real measurements against the `results/**` baselines, not
estimates. (Those baselines are local, not committed -- see §5a.2.)

Status: complete for the migration (tasks 1-12); keep it current as the pipeline
changes.

---

## 1. SQL semantics that do not survive a naive translation

### 1.1 A column's _type_ carries meaning, not just its expression

`prepare_tables.sql` declares `width_ft`, `speed_limit`, the four lane counts,
and `xwalk` as `INT` while the scripts compute them as floats. PostgreSQL rounds
on assignment, so **every later reader sees the rounded integer**.

This is not cosmetic. `functional_class.sql` tests `COALESCE(width_ft, 0) >= 8`
on a footway — and a 7.6 ft path rounds to 8 and _qualifies_. Keeping the float
would silently reclassify those roads.

**And the rounding mode depends on the expression's type, not the column's.**
PostgreSQL rounds a NUMERIC half away from zero, but casts a FLOAT to INT with
C's `rint()`, which rounds half to even. So `22.5::NUMERIC` stores as 23 and
`22.5::FLOAT` stores as 22. The first version of this finding said "half away"
for every INT column and was wrong for the FLOAT ones; it took Washington DC to
show it — Canal Road is tagged `width=22'6"`, `width_ft.sql` computes
`substring(...)::FLOAT + ...::FLOAT / 12` = 22.5, and 3.2.5 published 22. No
corpus city had a width on an exact half.

Which is which, script by script:

| Expression                                      | Type    | Rounding  | Encoded as                   |
| ----------------------------------------------- | ------- | --------- | ---------------------------- |
| `width_ft.sql` (every pass casts `::FLOAT`)     | FLOAT   | half-even | `features._round_half_even`  |
| `build_network.sql` `degrees(ST_Azimuth(...))`  | FLOAT   | half-even | `network._round_half_even`   |
| `build_network.sql` `ST_Length(...)`            | FLOAT   | half-even | `network._round_half_even`   |
| `speed_limit.sql` `ROUND(x / 1.609 / 5) * 5`    | NUMERIC | half-away | inline in `derive_speed_limit` |
| `access_*.sql` `SUM(pop20)` (§1.27)             | NUMERIC | half-away | `features._round_half_away`  |

`1.609` is a NUMERIC literal, so the speed-limit division is NUMERIC and its
`ROUND()` is half-away; `SUM()` over a NUMERIC column is NUMERIC (the
population shapefile's `POP20` is a `N 24.15` field, which `shp2pgsql` loads as
NUMERIC). Note also that `build_network.sql` stores *each azimuth* as an
INTEGER before subtracting them, so the turn angle is a difference of two
rounded values, not a rounded difference: 10.4° and 20.6° give 21 − 10 = 11,
not round(10.2) = 10.

### 1.2 Integer division in `link_cost` — the single largest parity bug found

`build_network.sql` declares `source_road_length` and `target_road_length` as
**INTEGER**, then computes:

```sql
link_cost = round((source_road_length + target_road_length) / 2)
```

Three things happen that the expression does not show:

1. each `ST_Length` is rounded when stored in the INTEGER column;
2. `(int + int) / 2` is **integer division** — it truncates;
3. the outer `round()` is therefore a no-op.

Computing `round((a + b) / 2)` at full precision inflates every link by up to
half a unit. Invisible on one link; along a path it compounded to **+0.8%**
(correlation 0.76 with path length), which pushed block pairs sitting near the
2680 m cutoff out of range entirely.

**Cost:** block-pair cost agreement was 14%. After the fix: 100% on six of eight
cities. Encoded as `network._link_cost()`.

### 1.3 `greatest()` skips NULLs

`link_stress = greatest(source_stress, int_stress, target_stress)` returns NULL
only when _every_ argument is NULL. A NULL `link_stress` then fails the
low-stress filter `link_stress = 1` but **survives the unfiltered high-stress
query**. Valencia has such rows, so this is not hypothetical. A naive `max()`
over NaN breaks on real data. Encoded as `network._greatest()`.

### 1.4 Not every rule lives in `scripts/sql/`

`compute.features()` issues this inline, between `clip_osm.sql` and
`one_way.sql`:

```sql
DELETE FROM neighborhood_osm_full_line WHERE bicycle='no' AND highway='path'
```

It deletes from the **tag** table, so the effect is indirect:
`functional_class.sql`'s join finds no partner, the class stays NULL, and the
road is removed by the "remove stuff we don't want to route over" delete.

**Cost:** all 88 excess road segments in Rehoboth Beach (sand beach paths).
Grepping the `.sql` files alone never finds this. **Grep `compute.py` for inline
SQL before transcribing any stage.**

### 1.5 `park.sql`'s "both" pass has no lasting effect

Three sequential updates: a "both" pass sets each direction, then a "right" pass
sets `ft_park` and a "left" pass sets `tf_park`. The later passes assign their
`CASE` result **unconditionally**, and a `CASE` with no matching branch yields
NULL — so a road with no side tag has whatever `parking:lane:both` set
overwritten with NULL.

`ft_park` therefore depends only on the right-hand tags and `tf_park` only on
the left; `parking:lane:both` is dead unless a side tag also exists. Reproduced,
not corrected.

### 1.6 `bike_infra.sql` contains an unreachable branch

Inside `tf_bike_infra`'s `one_way_car = 'ft'` block, two rules are guarded on
`one_way_car = 'tf'` — which can never hold there. This is the copy-paste slip
`bikescore-bna` documented independently (requirements.md §1a). Per §3 it is
reproduced, not repaired, and `test_unreachable_tf_guard_is_reproduced` pins it
so a later reader cannot "fix" it by accident.

### 1.7 The `ft`/`tf` ladders are _almost_ mirrors

`bike_infra.sql`'s two 250-line CASEs look symmetric but are not:

- `tf`'s `cycleway = 'lane'` rule carries an extra `cycleway:left:oneway` check
  that `ft`'s counterpart lacks;
- `ft`'s `cycleway:{other} = 'buffered_lane'` rule carries an `oneway` check
  that `tf`'s lacks.

Regularising either changes output. Symmetry is a hypothesis to verify, never an
assumption.

### 1.8 `one_way` and `one_way_car` are different columns

`one_way_car` is the motor-vehicle restriction (`one_way.sql`). `one_way` is the
**bike** restriction, set later by `bike_infra.sql`: a street one-way for cars
is two-way for bikes when it has contraflow infrastructure or
`oneway:bicycle=no`.

The routing network and `stress_one_way_reset.sql` both key off `one_way`, not
`one_way_car`. The exported shapefile has _three_ similar names — `ONEWAY` (raw
OSM), `ONE_WAY_CA` (`one_way_car`), and `ONE_WAY` (bike).

### 1.9 The residential speed default never comes from the city CSV

`run_with.py:194` always passes `city_speed_limit_override`, defaulting to
`DEFAULT_CITY_SPEED_LIMIT = 30`, and the override beats the lookup in
`manage_speed_limits`. The downloaded `city_fips_speed.csv` holds real per-city
values (Jackson 25, St. Louis Park 20) that are **never used** on the `run-with`
path.

This decides the rating of every untagged residential street, and 30 mph is high
stress where 25 is low. Using the CSV values inverted Arcata's entire stress
split. Encoded in `stress.read_speed_defaults()`.

### 1.10 One rule is non-deterministic and was measured, not assumed

`build_network.sql`'s `int_crossing = FALSE` update picks one link per
`(source_road, intersection)` with `LIMIT 1` over an `ORDER BY` that does not
break ties. Where two turns share an order key, Postgres' choice is arbitrary
and exact parity is impossible in principle.

tasks.md 6.3 required measuring this before assuming parity. Measured: **0/999
(Crested Butte), 0/1,123 (Santa Rosa), 1/3,777 (Jackson) — 0.03% worst case.**
Exact parity is achievable; no NFR-PARITY-1 exception needed.

### 1.11 Mileage totals are directional _and_ clipped to the boundary

`overall_scores.sql`'s two mileage rows are not the sum of road lengths. Three
details, none visible in the phrase "total miles":

1. only the part **inside the boundary** counts --
   `ST_Length(ST_Intersection(way, boundary))`, so a road running out of town
   contributes its in-town length, not its whole length and not nothing;
2. mileage is **directional**: a road low-stress both ways counts **twice**,
   expressed as a `CASE` on `COALESCE(ft, 0) + COALESCE(tf, 0)` where 1+1 scores
   double but 1+3 scores single;
3. the low and high totals **overlap** -- a road comfortable one way and hostile
   the other contributes a mile to each.

Summing centreline length instead gave 15.8 miles against a truth of 29.4.
Encoded as `scoring.total_stress_miles()`.

### 1.12 Population and jobs use a different scoring curve from destinations

Every destination category counts _places_ and scores them through the graduated
`first`/`second`/`third` ladder. Population and employment do not: they compare
the **share** of reachable population (or jobs) that is reachable comfortably,
and map that ratio through a piecewise curve (`access_population.sql`,
`access_jobs.sql`).

The curve is deliberately front-loaded -- 3% coverage already earns 0.1, 20%
earns 0.4, 50% earns 0.8 -- because a network that connects nobody is much worse
than one that connects a little. Encoded as `scoring.step_score()`.

### 1.13 Only 16 of `score_inputs.sql`'s ~130 rows affect the score

`score_inputs.sql` is 3,883 lines and the largest script in the migration, but
it is mostly a **diagnostics table**: medians, 70th percentiles and means per
category, each with explanatory prose. `overall_scores.sql` consumes it through
`WHERE neighborhood_score_inputs.use_<x>`, and only 16 rows carry such a flag --
all of them population-weighted averages of a per-block score.

Implementing those 16 produced the entire headline score table. The other 116
rows matter only for `score_inputs.csv` file parity (NFR-PARITY-2), not for
the BNA score itself. **Check which rows are actually consumed before
transcribing a large reporting script.**

They were done last (tasks.md 7.6), once the destination sheds they read
existed (§1.29), and turned out to be four formulas repeated: every row is a
block percentile, a block ratio, a shed ratio or a shed percentile. Two of
the SQL's habits are reproduced rather than corrected: "Average score of low
stress access to <x>" divides two `INT` sums, so it is integer division and
publishes 0 in every city; and unlike `overall_scores.sql` there is no
`COALESCE`, so a city without employment data publishes an empty
`Average score of access to jobs`. The prose is carried verbatim in
`score_inputs.py`, spelling inconsistencies included ("social_services").

### 1.14 A block always reaches its own roads, even high-stress ones

`reachable_roads_low_stress_calc.sql` unions a synthetic zero-cost edge from
node `-1` to every one of the block's vertices into the graph it hands
`PGR_DRIVINGDISTANCE`. Those edges are added **regardless of link stress**, so a
seed vertex is reached at cost 0 even when the low-stress subgraph has no link
touching it at all.

Implemented as "multi-source Dijkstra over the low-stress edges", a seed vertex
missing from that subgraph is simply absent, and the block's own road is then
reached at whatever it costs to walk round to it -- or not at all.

**Cost:** two pairs of Crested Butte blocks that share a road recorded a
low-stress cost of 310 m and 66 m instead of 0. Pinned by
`test_seeds_are_reachable_even_off_the_subgraph`.

### 1.15 `oneway` the published column and `one_way_car` the analysed one

`ways.oneway` is `osm2pgrouting`'s own normalisation of the tag -- `YES`, `NO`,
`REVERSED`, `UNKNOWN`, and for anything else the tag upper-cased (`REVERSIBLE`
appears in the corpus). It also reads `junction=roundabout` as `YES` with no
`oneway` tag present at all.

`one_way_car`, which the stress model actually reads, comes from the raw OSM tag
through `neighborhood_osm_full_line` and stays NULL on that same roundabout. 247
roundabout segments in Orange sit in exactly that gap. Both behaviours had to be
reproduced, in different places: the label in `export`, the analysis value in
`features`.

### 1.16 `SUM()` over no rows is NULL, and NULL is not zero

Every `access_*.sql` is filtered `WHERE EXISTS (block intersects boundary)`, and
the population and jobs sums are correlated subqueries: a block outside the
boundary, or one with no roads and therefore no pairs, gets **NULL**, and
`pop_score` then `CASE WHEN pop_high_stress IS NULL THEN NULL`. The destination
columns are `COUNT`s in the same position and come out **0**. Two column
families, the same empty input, different answers.

Outside the US there is no LODES data, `census_block_jobs.sql` never runs, and
every employment column stays NULL for the whole city -- which is not the same
as a city where nobody works.

**Cost:** 429 of Orange's 909 blocks. Pinned by
`test_blocks_with_no_pairs_are_null` and
`test_employment_is_null_without_lodes`.

### 1.17 The per-block overall score renormalises differently again

`access_overall.sql` decides a category applies by its members' `*_high_stress`
counts, while `category_scores.sql` decides by whether the member's _score_ is
NULL -- and `access_overall.sql` keeps employment's `0.35` in the divisor
unconditionally, with no `emp_high_stress > 0` test to key it on. The two rules
agree whenever a NULL score and a zero count coincide, which is almost always,
and disagree exactly outside the US.

So the per-block `overall_score` cannot be assembled from the `*_category_score`
columns sitting next to it in the same table, even though they look like its
inputs. 157 Orange blocks were wrong that way.

### 1.18 The city rollups read _rounded_ inputs

`neighborhood_overall_scores.score_original` is `NUMERIC(16, 4)`, and the
category rollups read their member rows back out of that table with
`SELECT score_original FROM neighborhood_overall_scores`. Each member is
therefore rounded to four decimals **before** the weighted mean divides it.
Computing the rollup from the unrounded values differs in the fourth decimal,
which is exactly the precision NFR-PARITY-1 compares at.

### 1.19 The city's headline score is not a rollup at all

Every intermediate row in `neighborhood_overall_scores` is a category rollup, so
`overall_score` looks like one too. It is not: it is the population-weighted
mean of the **blocks' own** `overall_score` values. Note the two different
filters -- the sum runs over blocks with population _and_ reach, the divisor is
the population of every block with reach, inhabited or not.

Orange came out 0.161 against a published 0.2313 before this was corrected.

### 1.20 PostgreSQL rounds a tie away from zero; Python rounds it to even

`round(0.99985, 4)` is 0.9999 in PostgreSQL and 0.9998 in Python. It only bites
on an _exact_ tie, which is why the rollups have to be computed in `decimal` as
well: done in binary they land near the tie rather than on it, and the rounding
rule never gets a chance to disagree. Crested Butte's opportunity score is
exactly 0.99985.

### 1.21 An `AND` after an unparenthesised `OR` binds to the last branch only

Every destination script's point insert ends with
`AND NOT EXISTS (... a polygon already covers this point ...)`. In `parks.sql`
and `transit.sql` the `OR` list is parenthesised, so the guard applies to the
whole clause. In `dentists.sql`, `doctors.sql`, `hospitals.sql` and
`pharmacies.sql` it is **not**, and `AND` binds tighter than `OR`:

```sql
WHERE amenity = 'dentist' OR healthcare = 'dentist' AND NOT EXISTS (...)
```

reads as `amenity = 'dentist' OR (healthcare = 'dentist' AND NOT EXISTS ...)`. A
node tagged `amenity=dentist` inside a dentist polygon is therefore inserted
**twice over** -- once as the polygon, once as the point -- while the same node
tagged `healthcare=dentist` is not. Encoded per branch as `MatchBranch.guarded`.

The same precedence question decides `retail.sql`'s exclusion:
`shop NOT IN ('no', 'supermarket')` sits inside the `shop` branch's parentheses,
so a `landuse=retail` polygon with a supermarket on it stays retail.

### 1.22 `NOT (NULL AND NULL)` is NULL, and a NULL `WHERE` excludes the row

`transit.sql` accepts a stop tagged `public_transport = 'station'` plus
`NOT (railway = 'station' AND station = 'miniature')`. With neither `railway`
nor `station` present, the inner `AND` is NULL, `NOT NULL` is NULL, and the row
**does not match**. A plain `public_transport=station` with nothing else on it
is therefore not transit at all.

This resolves the open discrepancy in §5a.1: Jackson's six ski gondola stations,
and Provincetown's inclined elevator, are excluded by three-valued logic rather
than by anything in the import. In Python `not (None and None)` is `True`, so
the naive translation includes them -- worth 6 transit destinations in Jackson
and 3 in Provincetown.

`_transit_matches()` spells the condition out: the clause holds only when one of
the two tags is _known_ not to be the excluded value.

### 1.23 Employment is weighted by the whole population, not by its own

`score_inputs.sql` builds a `tmp_pop` temp table with one denominator column per
category -- `k12`, `tech`, `univ`, `doctor`, ... -- each summing `pop20` only
over blocks that can reach something in that category. There is **no `emp`
column**. The employment row divides by `tmp_pop.overall`, the whole boundary
population, exactly as the population row does.

So of the 16 scored members, two (`pop` and `emp`) use the whole population and
the other fourteen use their own. Ypsilanti's employment score was 0.1517
against a published 0.1505 with the wrong divisor.

### 1.24 Transit clusters its points but not its polygons

Every other clustered category passes its tolerance to `ST_ClusterWithin` over
the polygon set. `transit.sql` does not: its polygons are inserted one row each
(subject only to the subarea `DELETE`), and the 75 m tolerance is used twice
elsewhere -- once as the `ST_DWithin` radius that suppresses a point beside a
station building, and once to cluster the surviving _points_.

Clustering its polygons as well merged two pairs of San Juan's stations, 27
destinations against a truth of 25.

### 1.25 `osm2pgrouting` implies one-way, and the implication overrules the tag

Two cases, both visible in San Juan:

- `junction=roundabout` publishes as `YES` even where the way says `oneway=no`;
- `highway=motorway` publishes as `YES` even where the way says
  `oneway=reversible` -- while the same tag on a `motorway_link` stays
  `REVERSIBLE`, so the implication is keyed on the exact value `motorway`.

This is the published `oneway` label only; `one_way_car` still comes from the
raw tag and is unaffected (§1.15).

### 1.26 `osm2pgrouting` loses a duplicated edge across a 20,000-way boundary

The last parity gap, settled by importing Chambéry into PostGIS and
experimenting against a local `osm2pgrouting` 3.0.0.

**What the database showed.** `received.neighborhood_ways` -- the raw import,
before any SQL runs -- already has 1 row for way `1038105016` where the OSM way
has 3 edges, and 2 for way `850421039` where it has 3. No `DELETE` is involved.
The missing edges are in the table, attributed to the **pedestrian plaza** whose
outline runs along the same kerb:

| Edge                      | Emitted for                            |
| ------------------------- | -------------------------------------- |
| `1523885116 → 3257144810` | plaza `37716696`, not the primary road |
| `3257144810 → 290143766`  | plaza `37716696`, not the primary road |
| `7933888679 → 2634514696` | plaza `258021730`, not the cycleway    |

**Duplicate edges are normally kept.** That same import holds 242 edges with two
or more rows -- including a road and a plaza tracing the identical stretch, with
identical `source`/`target` vertices and identical geometry. There is no unique
constraint on the table. So "one row per edge" is not the rule.

**It is deterministic, and it is not about the data.** Two independent local
imports of the same extract are byte-identical. The pair in isolation (just the
road and the plaza) keeps all 3 rows; so does the pair plus every way that
touches the same nodes. Bisecting the file to find the trigger produced this:

| Ways in the extract | Rows for way `1038105016` |
| ------------------- | ------------------------- |
| 20,000              | 3 -- all kept             |
| 20,001              | 1 -- two edges lost       |

**Any way as the 20,001st triggers it.** The way that happened to be there is
tagged `barrier=hedge` -- `osm2pgrouting` does not even import it. Swapping it
in for another way, keeping the count at 20,000, is clean. The count alone
decides.

So `osm2pgrouting` processes ways in chunks of 20,000, and an edge duplicating
one inserted in an **earlier chunk** is dropped, while duplicates within a chunk
both survive. (A naive "chunk index of the way in file order" model explains 119
of the 146 contested edges, so the real boundary function is finer than that --
but the count experiment is unambiguous.)

**Why this is not reproduced.** The outcome depends on a way's ordinal position
in the extract relative to an internal chunk boundary -- not on the road, the
plaza, the tags, or the geometry. Reproducing it would mean emulating
`osm2pgrouting`'s chunked insert order in Python, and the result would be
**unstable anyway**: map one more hedge anywhere in Chambéry, or re-download the
extract, and the boundary moves and different edges vanish. The baseline itself
changes with the next data refresh.

This is the second unmatchable behaviour in the SQL pipeline, after §1.10's
unordered `LIMIT 1`, and the first to need an actual NFR-PARITY-1 exception
(requirements.md §6.1a). **Cost:** 3 segments of 7,211 in Chambéry (0.04%) --
one census block's scores, 53 block-pair costs, and the `path` mileage by 0.006
miles. Every other corpus city is unaffected, including the ones well past the
boundary (San Juan 137k ways, Flagstaff 43k, St. Louis Park 34k): the artifact
only bites when a _duplicated_ edge straddles a chunk boundary.

### 1.27 The shed totals are `INT` columns too, and their score reads them back

`census_blocks.pop_low_stress`, `pop_high_stress`, `emp_low_stress` and
`emp_high_stress` are declared `INT`, so each `SUM()` is rounded half away
from zero as it lands there -- and `access_population.sql`'s scoring `CASE`
is a _second_ `UPDATE` that reads those rounded columns back. The score is
computed from the rounded totals, not the exact ones.

This is §1.1 again, and it hid for the entire corpus because a US block's
`pop20` is a whole number, so the sums already were. **Valencia is the first
city where it shows**: outside the US the population is distributed from a
WorldPop raster, so block populations are fractional -- 193 of its 217 blocks
carried a fractional total, and 16 of them scored differently for it.

Worth the reminder that a rule can be exactly right on 15 cities and still be
wrong: the corpus had no city with fractional population until an `XL`
manual run added one (tasks.md 10.3).

### 1.28 `traffic_signals:direction` is a way tag the point rules read

`signalized.sql`'s second and third rules read `traffic_signals:direction` from
`neighborhood_osm_full_line` -- the *way* table -- and flag the way's
`intersection_to` (`forward`) or `intersection_from` (`backward`), with no leg
count condition. It is how a mid-block signal between two consecutive ways of
the same street gets recorded, since that node has two legs and every other
rule demands more than two.

`pfb.style` lists it as a `way` column and the first transcription of that
list into `ingest.OSM_WAY_TAGS` (§2.2) missed it, so the column never reached
`derive_intersection_flags` and the rule matched nothing. No corpus city had
the tag on a way; DC's Maine Avenue Southwest did. The frozen list in
`test_ingest.py` was transcribed from the same reading and missed it too --
a test that copies the source it checks proves only that the copy is faithful.

### 1.29 Every destination table carries a population shed, and it is published

Each `connectivity/destinations/*.sql` table has `pop_low_stress`,
`pop_high_stress` and `pop_score` columns, and the second half of every
`access_*.sql` fills them: for each destination, the population of every block
connected to *any* of the blocks the destination sits in (`SUM(MAX(pop20))
GROUP BY geoid20`, so a block reaching two of its blocks counts once), over
each network, for destinations inside the boundary. `pop_score` is
`pop_low_stress::FLOAT / pop_high_stress` on the stored INT columns (§1.27
applies: NUMERIC sum, half-away).

Two details of the *export*: the tables have two geometry columns, `geom_pt`
and `geom_poly`, and `ogr2ogr ... -sql "select * from <table>"` writes the
first, so the published GeoJSON is the **centroid**, never the polygon; and a
cluster row (every retail row, a park or transit cluster) has no `osm_id` and
no name -- the SQL inserts it with its geometry alone.

The Python pipeline computed none of this and published polygons with two
columns. It went unnoticed because the parity harness compared seven files
and the destination layers were not among them -- the same lesson as §1.27
and §1.28, from the other side: **the gate only proves what it checks**.
Encoded as `scoring.destination_population_shed`, `export._destination_layer`,
and a `destinations` dimension in `validate_parity.py` that pairs each layer's
rows on the published point.

### 1.30 The harness compared values, not schemas

Closing `score_inputs.csv` exposed that `overall_scores.csv` had been short
two columns (`id`, `human_explanation`) and spelling `0.142` where 3.2.5
wrote `0.1420` (`NUMERIC(16, 4)`), with `recreation` and `transit` in the
wrong order -- and that non-US `census_blocks` files carried fifteen TIGER
columns of NULLs that the baseline does not have, because `shp2pgsql` only
created the columns the population shapefile brought (two, outside the US).
None of it failed the gate: the harness paired rows on a key, compared the
columns both sides had, and skipped the rest.

FR-EXPORT-1 says the schema is the contract, so the harness now reports a
column either side lacks as a difference, spells `NUMERIC(16, 4)` columns
with their four decimals, and gates `score_inputs` as a dimension. With
that, `score_inputs.csv` and `overall_scores.csv` are byte-identical to
3.2.5's on every corpus city; the GeoJSON layers are equal by value (the
writers differ in coordinate precision and whitespace).

---

## 2. Python and library traps

### 2.1 pandas NULL propagation silently _drops rows_

`tag == "value"` on a nullable column yields `pd.NA` for an absent tag. The `NA`
survives `~` and `&`, and pandas then drops those rows when the result is used
as a mask — so an **untagged** way is treated as though it matched.

**Cost:** 16 untagged paths silently deleted from Crested Butte. It only
surfaced because that city had been exact and regressed.

SQL's `tag = 'value'` is false for NULL. Encoded as `features._eq()`; use it for
every tag comparison.

### 2.2 A tag you never requested looks exactly like a tag that was never set

`pyrosm` returns a fixed default column set and silently omits anything else.
`golf`/`golf_cart` arrived as NULL, so 37 golf-cart paths in St. Louis Park
classified as `path` instead of `unclassified`. No error — just a wrong score.

`ingest.read_ways()` now requests every `OSM_WAY_TAGS` entry explicitly, and
`test_way_tags_cover_pfb_style` guards the list against drift.

### 2.3 A polygon buffer _inscribes_ its circle

`geometry.buffer(d)` approximates a circle with straight segments, so
`intersects(buffer(d))` quietly drops features sitting near exactly `d` away.
`ST_DWithin` is an exact distance test.

Two places needed the exact comparison instead (the boundary clip and the
census-block pairing); a third pre-filters with a 5% margin then applies the
exact test, which is both correct and fast.

### 2.4 Real OSM polygons are not always valid

`union_all()` raises `GEOSException: TopologyException` on real destination
data. Overlays therefore use spatial joins rather than a global union — more
robust _and_ faster.

The first fix here was `make_valid()`, which was wrong: repairing an invalid
ring invents a destination that never reached PostGIS in the first place. See
§3.8 — invalid geometries are dropped instead.

### 2.5 `Element.clear()` wipes attributes

While writing a throwaway XML analysis, calling `.clear()` on `<nd>` elements
during `iterparse` erased their `ref` attributes and silently produced zero
results. Only clear the element you have finished with (`<way>`), never its
children.

### 2.6 `ST_Buffer` and `GeoSeries.buffer` do not draw the same polygon

PostGIS defaults to 8 segments per quadrant, geopandas to 16. The finer polygon
reaches marginally further, so where the buffer _is_ the test rather than a
pre-filter, borderline features fall on opposite sides of it.

**Cost:** a handful of roads moved in and out of Crested Butte's blocks, which
moved three blocks' population sheds, which moved the city score. Pass
`resolution=network.POSTGIS_QUAD_SEGS` wherever the buffer polygon is the
answer. (§2.3 is the complementary case: where an exact distance is wanted, do
not buffer at all.)

### 2.7 `pyrosm` drops a way once a relation claims it

Asked for relations, `pyrosm` treats every member way as consumed and does not
return it -- for _any_ relation type, not only multipolygons. Orange Station is
a `building=yes` way inside a `public_transport=stop_area` relation, so it
vanished, taking one of the city's two transit destinations with it.

`osm2pgsql`, which the SQL read from, only turns `multipolygon` and `boundary`
relations into polygons and emits every tagged way in its own right.
`read_destinations` now reads in two passes -- ways and nodes without relations,
then relations filtered to those two types -- and concatenates.

### 2.8 `pyrosm` silently omits a tag column it does not know

`custom_filter={"healthcare": True}` filters on the tag but does **not** create
a `healthcare` column: `pyrosm` promotes only the keys in its own default set.
Every rule reading `healthcare` then compared against a column that was not
there and matched nothing, silently. Two of Orange's seven doctors were lost
that way, and the same applies to dentists and hospitals in every city.

Pass every key the rules read in `extra_attributes`, not only in the filter.
This is §2.2 again, in a different function -- the failure mode is identical and
there is still no error.

### 2.9 `line_merge` starts a closed ring wherever it likes

Merging a way's sub-edges back into one LineString is fine until the way closes
on itself: `shapely.line_merge` then picks its own start vertex, which is not
the node the way started from. The road's geometry then contradicts its own
`intersection_from`/`intersection_to` columns. `_merge_chunk` rotates a closed
result back to the chunk's first node.

---

## 3. Pipeline structure that the SQL does not state

### 3.1 Ways are cut at nodes shared by 2+ ways _of any kind_

Not just routable ones. A road splits where a building outline or a stream
touches it. Counting only routable ways undercounts cuts — Crested Butte went
from 496 to exactly 523 roads once the full node census was used.

Implemented as `ingest.shared_nodes()`, streamed from the OSM XML with
`iterparse`.

### 3.2 The OSM extract is clipped to the census-block bbox before import

`ingestor.import_osm_data` runs `osmconvert --drop-broken-refs -b=<bbox>` where
the box is the EPSG:4326 extent of `neighborhood_census_blocks` **after**
out-of-buffer and water blocks are removed — so it is tighter than the boundary,
and much tighter for a coastal city.

Dropping broken refs changes where ways get cut, so this is not cosmetic.

**This orders the stage internally:** census blocks must be loaded and filtered
_before_ the OSM extract is read. Adding it took Alvarado, Jackson, Cañon City,
and Provincetown from +16/+11/+4/+2 segments to exact.

### 3.3 Destinations are clustered, and it dominates the counts

`ST_ClusterWithin(way, :cluster_tolerance)` merges features within the
category's `config.Tolerance` distance, so a campus mapped as several buildings
is one college rather than five.

Missing this over-counted badly: Jackson's retail was 104 against a truth of 34.
**Three categories are deliberately unclustered** — `schools`,
`social_services`, `supermarkets` are passed no tolerance. **Retail is the
exception**: it clusters shop polygons together with shop _points buffered by 10
m_, and excludes supermarkets so they are not double-counted.

### 3.4 The biggest scripts are one rule table wearing many hats

- `stress_tertiary_ints.sql` (652 lines) and `stress_lesser_ints.sql` (956)
  share a single rule table. They differ only in which road classes they rate
  and whether a `tertiary` crossing counts. Both became one parameterised
  function.
- The 17 `access_*.sql` scripts are **byte-identical modulo the category name**.
- `bike_infra.sql`'s nine link-insert branches collapse to three "may depart"
  cases crossed with three "may enter" cases.

Before transcribing a large script, check whether it is a specialisation of one
you have already done.

### 3.5 Two export columns are artifacts of the import path, not the analysis

Every exported layer carries a `gid` serial primary key -- created by
`shp2pgsql` on import, never used by any rule -- and all column names are
lower-cased, because PostgreSQL folds unquoted identifiers and the shapefiles
were loaded with upper-case field names.

Neither carries meaning, but both are part of the published schema
(FR-EXPORT-1), so they are reproduced in `export.py` rather than dropped.

### 3.6 The per-block overall score is not the city's overall score

`census_blocks.overall_score` (`access_overall.sql`) and the `overall_score` row
of `overall_scores.csv` are different computations:

- the **block** score combines that block's own category scores, renormalising
  on whether the block can reach anything in each category (`*_high_stress`);
- the **city** score averages the already-population-weighted per-category city
  scores, renormalising on whether the category scored at all.

They are close but not equal, and using one for the other is silently wrong.

### 3.7 `osm2pgsql` ran without `--multi-geometry`, so parts are rows

`runner.run_osm2pgsql` passes no `-G`, which is the default: a multipolygon
relation is written as **one row per part**, not one multi-part row. A nature
reserve mapped as three disjoint polygons is three entries in
`neighborhood_osm_full_polygon`, and where the parts are more than the cluster
tolerance apart they cluster as three destinations.

`read_destinations` explodes multi-part geometries to match. Provincetown's
parks were 16 against a truth of 19 until it did.

### 3.8 An invalid ring never reached PostGIS at all

`osm2pgsql` assembles its polygons with libosmium's area assembler, which
**refuses** a ring it cannot close cleanly. A self-intersecting closed way is
therefore simply absent from the polygon table. Repairing it with `make_valid()`
-- which is what §2.4 originally called for -- _invents_ a destination the SQL
never had: Jackson's "Jackson Hole High School" way is invalid, and repairing it
gave the city 7 schools against a truth of 6.

There are two layers to this, and both were needed:

1. **What `pyrosm` hands back invalid**, it hands back invalid: dropping those
   (rather than repairing them) covers the Jackson case.
2. **What `pyrosm` repairs behind your back** it does not: Cape Henlopen State
   Park is a multipolygon relation whose single outer way self-intersects, and
   `pyrosm` returns a perfectly valid two-part polygon for it. Nothing about the
   geometry in hand says it was ever broken.

The only reliable way to tell is to run the same assembler:
`osmium export --geometry-types=polygon` lists exactly the objects `osm2pgsql`
could have written, and `ingest.assembled_area_ids()` keeps only those. Rehoboth
Beach's parks were 12 against a truth of 11 until it did.

Note the id encoding: `osmium` reports libosmium _area_ ids, which are the
object id doubled for a way and doubled-plus-one for a relation.

### 3.9 An unclosed way is a line, and lines are not destinations

The destination scripts read the point and polygon tables only. `osm2pgsql` puts
an unclosed way in the **line** table however it is tagged, so a
`landuse=retail` way that does not close is not a retail destination. `pyrosm`
returns both closed and unclosed ways as LineStrings, so the distinction has to
be made explicitly -- a closed one becomes a polygon, an unclosed one is
dropped.

Ypsilanti had one such way; buffered as a retail "point" it stretched a cluster
into a neighbouring block and moved that block's score.

### 3.10 A destination belongs to the blocks its _centroid_ touches too

Each destination stores two geometries, `geom_poly` and `geom_pt`, and the block
assignment tests **both**:
`ST_Intersects(geom_poly, cb.geom) OR ST_Intersects(geom_pt, cb.geom)`. For a
cluster wrapped around a block -- a park either side of a street -- the centroid
lands in a block no part of the cluster touches, and that block is credited with
the destination anyway.

### 3.11 A tagged node is a vertex, even where only one way uses it

`osm2pgrouting` reads `mapconfig_highway.xml` for **nodes** as well as ways, so
a node carrying one of its `highway` values is a routing vertex and cuts the way
running through it -- no second way required. Flagstaff has a motorway exit
tagged `highway=motorway_junction` mid-way, and a path through a node tagged
`highway=steps`; both are cuts in the baseline.

This sits alongside §3.1, not instead of it: the cut set is the union of "shared
by 2+ ways of any kind" and "carries a configured `highway` value".

### 3.12 Retail is the one category whose blocks are the polygon's alone

§3.10 says a destination belongs to the block its centroid falls in as well as
the blocks its shape touches, because every `connectivity/destinations/*.sql`
sets `blockid20` with `ST_Intersects(geom_poly, cb.geom) OR
ST_Intersects(geom_pt, cb.geom)`. Every script but one: `retail.sql` tests
`geom_poly` only. There is no comment saying why; most likely the `OR` was
added to the twelve scripts that insert points as well as polygons, and retail
-- which buffers its points and clusters everything -- was never touched.

Applied uniformly it over-credits: a DC retail cluster of a corner shop and two
liquor stores has a centroid 3.8 m outside all three parts, in a block
`retail.sql` never listed. Twenty blocks gained a reachable retail destination
and the city's retail score moved from 45.58 to 45.6. Encoded as
`DestinationRule.centroid_touches_blocks`, off for `RETAIL_RULE` alone.

---

## 4. Method — what actually worked

### 4.1 Flatten and parse the SQL; do not read nested CASE by eye

At 650-950 lines of five-deep nesting, reading by eye is not reliable. Stripping
comments, collapsing whitespace, and regex-extracting the
`(condition, threshold, result)` tuples produced the rule table in minutes and
made the primary/secondary symmetry obvious.

### 4.2 Diagnose by comparing the right _granularity_

At 496 vs 523 roads, comparing totals says nothing. Comparing **per OSM way**
showed the way set was identical (145 = 145, zero differences), which isolated
the problem to segmentation alone. Later, comparing error against path length
(correlation 0.76) isolated the integer-division bug to per-link accumulation.

### 4.3 Compare against the right column

The export has `ONEWAY`, `ONE_WAY_CA`, and `ONE_WAY`. Mapping `ONE_WAY` to
`one_way_car` invented failures on two cities that were in fact exact. Verify
the mapping before trusting a diff.

### 4.4 A fix validated on one city can be a regression everywhere else

The `area=yes` hypothesis fixed Chambéry and broke all four other cities tested,
dropping them _below_ truth. Always re-run the cities that already passed.

### 4.5 Row counts matching does not mean the values match

Road counts reached 12/13 exact while `functional_class` was still wrong on four
cities. Validate per column, as a value multiset, not just per row.

---

## 5. Data quality in the baselines themselves

`results/united states/michigan/ypsilanti/` contains **two** directories:

|           | files | stress columns | `overall_scores.csv` |
| --------- | ----- | -------------- | -------------------- |
| `26.09`   | 16    | all NULL       | missing              |
| `26.09.1` | 32    | populated      | present              |

Every other city has exactly one complete 32-file directory. Comparing against
`26.09` silently passes the feature columns — they are fully populated — and
only fails at stress, so the partial baseline is easy to mistake for a code bug.

NFR-PARITY-3 treats `results/**` as frozen ground truth, so this matters: **the
parity harness (task 9.1) must select the newest complete version directory per
city** rather than assuming `26.09`. Consider deleting the stale directory to
remove the trap.

---

## 5a. Open discrepancies not yet explained

### 5a.1 Chambéry's 3 extra segments — **RESOLVED**, see §1.26

Resolved by a PostGIS run (2026-09-13). The three segments were never deleted by
any SQL: `osm2pgrouting` never imported them. The mechanism -- and why it cannot
be reproduced -- is §1.26.

### 5a.2 `results/` is gitignored — the baselines are local, not checked in

`.gitignore` excludes `results/`, so the "checked-in `results/**` baseline"
language in requirements.md §7.3 and NFR-PARITY-3 does not describe reality: the
baselines are local artifacts on one machine. They were regenerated 2026-09-11
by the **3.2.5** SQL pipeline (the branch point for this work, tasks.md
"Branch point and release"), so they did reflect the SQL as it stood, but
nothing in the repo pins them and a fresh clone has no ground truth at all.

Worth deciding before task 9: either commit the baselines (they are large), or
state explicitly that parity validation requires a local regeneration step and
document how to produce it. **Now sharper than when this was written:** the SQL
that produced them is deleted, so regenerating means checking out `8a1ec91`
(3.2.5 plus the spec) first.

### 5a.3 Valencia: one segment lost at a pedestrian plaza, mechanism unconfirmed

Valencia's manual run (tasks.md 10.3) leaves **one** difference after the two
defects it exposed were fixed (§1.15, §1.27): way `1364972005`
(`highway=residential`) keeps both its segments here, while the baseline has
only the second. Everything else in the city matches -- 45,711 of 45,712
ways, all 217 census blocks, all 4,538 block pairs.

The lost edge is shared with way `23454891`, which is **untagged** and a
member of relation `r10847213` -- `area=yes, highway=pedestrian`, a plaza.
That is the same pedestrian-plaza signature as §1.26's Chambéry case, with
one difference that matters: there the plaza was a _way_ `osm2pgrouting`
imported, and here the claimant is an untagged way it would never import. So
the §1.26 mechanism does not obviously apply, and the same-looking evidence
may have a different cause.

Settling it needs Valencia imported into PostGIS, the way Chambéry was. Until
then it is **not** in the harness's `KNOWN_DEVIATIONS`: an unverified
exception would hide a real regression, and §1.26 is only excused because its
mechanism was pinned by experiment. Cost: 1 segment of 45,712 (0.002%), two
intersection leg counts, and 0.04 miles on the high-stress total.

Valencia is an `XL` city -- outside every automated corpus, and its manual
pass is explicitly best-effort (requirements.md §7.4a).

### 5a.4 Valencia: one transit cluster sitting exactly on the boundary line

The `destinations` dimension (§1.29) shows one more Valencia difference: the
transit cluster at (-0.32531, 39.44976) has a population shed here and NULLs
in the baseline. `access_transit.sql` only fills the shed where
`ST_Intersects(geom_pt, boundary)`, and this point is a coin flip: the cluster
is two `public_transport=stop_position` nodes (`9466788241`, `9466788251`)
that are both vertices of the boundary way itself, so its centroid lies
mathematically **on** the boundary edge. PostGIS's transform of the boundary
put it a hair outside, pyproj's a hair inside. There is no rule to reproduce;
either answer is a rounding accident, and the pipeline's is the more
defensible one (the stops are in the city). Cost: one destination's
`pop_*` columns, and through them the four transit shed rows of
`score_inputs.csv` (ids 129-132, e.g. 0.7683 against 0.7660); no score
reads either.

---

## 6. Where each finding is enforced

Findings are pinned by tests so they cannot be "tidied away" later:

| Finding                        | Enforced by                                                                             |
| ------------------------------ | --------------------------------------------------------------------------------------- |
| 1.1 INT column rounding        | `test_features.py::TestRoundHalfAway`, `TestRoundHalfEven`, `TestDeriveWidthFt`; `test_network.py::TestLinkCost`, `test_turn_angle_rounds_each_azimuth_first` |
| 1.2 integer division           | `test_network.py::TestLinkCost`                                                         |
| 1.3 `greatest()` NULLs         | `test_network.py::TestGreatest`                                                         |
| 1.5 dead "both" pass           | `test_features.py::TestDeriveParking`                                                   |
| 1.6 unreachable branch         | `test_features.py::test_unreachable_tf_guard_is_reproduced`                             |
| 1.8 bike vs car one-way        | `test_stress.py::TestOneWayReset`                                                       |
| 1.9 speed override             | `test_stress.py::TestSegmentStress`                                                     |
| 1.12 step curve                | `test_scoring.py::TestStepScore`                                                        |
| 1.14 seeds cost 0 off-subgraph | `test_network.py::TestReachableRoads::test_seeds_are_reachable_even_off_the_subgraph`   |
| 1.15 `oneway` vs `one_way_car` | `test_export.py::TestOnewayLabels`                                                      |
| 1.16 `SUM()` over no rows      | `test_scoring.py::TestShedTotals`                                                       |
| 1.17 per-block renormalisation | `test_scoring.py::TestBlockOverallScore`                                                |
| 1.19 headline score            | `test_scoring.py::TestPopulationWeightedOverall`                                        |
| 1.20 rounding a tie            | `test_scoring.py::TestRoundHalfUp`                                                      |
| 1.21 `AND` after `OR`          | `test_scoring.py::TestPointGuardPrecedence`                                             |
| 1.22 `NOT (NULL AND NULL)`     | `test_scoring.py::TestTransitMatches`                                                   |
| 1.23 employment's divisor      | `test_scoring.py::TestWholePopulationMembers`                                           |
| 1.24 transit clustering        | `test_scoring.py::TestTransitClustering`                                                |
| 1.25 implied one-way           | `test_export.py::TestOnewayLabels`                                                      |
| 1.26 chunk-boundary edge loss  | _deliberately not reproduced_ — requirements.md §6.1a                                   |
| 1.28 way-tagged signals        | `test_ingest.py::test_way_tags_cover_pfb_style`, `test_features.py::TestIntersectionFlags` |
| 1.13 / 1.30 score inputs       | `test_score_inputs.py`, harness `score_inputs` dimension and `(columns)` check              |
| 1.29 destination sheds         | `test_scoring.py::TestDestinationPopulationShed`, `test_export.py::TestDestinationLayer`, harness `destinations` dimension |
| 2.1 NULL propagation           | `test_features.py::TestNullSafeComparison`                                              |
| 2.2 unrequested tags           | `test_ingest.py::test_way_tags_cover_pfb_style`                                         |
| 2.3 buffer vs distance         | `test_features.py::test_uses_true_distance_not_an_approximated_buffer`                  |
| 2.6 buffer quad segments       | `test_network.py::TestAssignBlockRoads`                                                 |
| 2.7 relations eat their ways   | `test_ingest.py::TestReadDestinationsContract`                                          |
| 2.8 unpromoted tag columns     | `test_ingest.py::TestReadDestinationsContract`                                          |
| 2.9 ring start vertex          | `test_ingest.py::test_a_closed_ring_starts_where_the_way_started`                       |
| 3.1 segmentation rule          | `test_ingest.py::TestSplitWaysAtIntersections`                                          |
| 3.3 clustering                 | `test_scoring.py::TestClusterWithin`                                                    |
| 3.5 gid and lower-casing       | `test_export.py::TestGidAndCasing`                                                      |
| 3.7 exploded multipolygons     | `test_ingest.py::test_multi_part_geometries_are_exploded`                               |
| 3.8 invalid rings dropped      | `test_scoring.py::TestDestinationGeometryKinds`, `test_ingest.py::TestAssembledAreaIds` |
| 3.9 unclosed ways are lines    | `test_scoring.py::TestDestinationGeometryKinds`                                         |
| 3.10 centroid block            | `test_scoring.py::TestBlocksTouched`                                                    |
| 3.11 tagged cut nodes          | `test_ingest.py::TestSharedNodes`                                                       |
| 3.12 retail block rule         | `test_scoring.py::TestBlocksTouched`                                                    |
| export schema contract         | `test_export.py::TestColumnOrdering`                                                    |
| jobs keyed on workplace        | `test_scoring.py::TestBlockJobs`                                                        |
| category renormalisation       | `test_scoring.py::TestCategoryScores`                                                   |
| CSV spelling                   | `test_export.py::TestPostgresCsv`                                                       |
