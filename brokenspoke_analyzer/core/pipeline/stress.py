"""
Classify traffic stress on each road segment and intersection.

Replace `scripts/sql/stress/*.sql`. A stress rating of 1 means a road most
people would ride on; 3 means they would not. Only these two values are ever
produced -- the scale has no middle.

The order in `compute.stress()` is part of the definition, because several
scripts overwrite what earlier ones set: the higher-order classes run first,
then the lower-order ones, then `living_street`/`track`/`path`, and finally
`stress_one_way_reset.sql`, which blanks the stress of whichever direction a
one-way street forbids.

Each class carries its own assumed defaults (speed, lanes, parking) which fill
in for missing tags, and those assumptions differ per class -- a tertiary road
assumes 30 mph and one lane where a primary assumes 40 and two. They are
passed from `compute.stress()`, not hardcoded in the SQL, so they live here as
a table rather than scattered through the rules.
"""

import dataclasses
import pathlib

import geopandas as gpd
import numpy as np
import pandas as pd
from loguru import logger

from brokenspoke_analyzer.core.pipeline.features import (
    _column,
    _eq,
    _text,
)

# The only two ratings the BNA assigns.
LOW_STRESS = 1
HIGH_STRESS = 3

# Speed thresholds, in mph, at which a facility stops being comfortable.
BUFFERED_LANE_MAX_SPEED = 25
LANE_MAX_SPEED = 20
SHARED_LANE_MAX_SPEED = 15
LOWER_ORDER_MAX_SPEED = 25

# Minimum comfortable width, in feet, for a conventional bike lane.
MIN_LANE_WIDTH_FT = 4

# `cli/common.py`'s DEFAULT_CITY_SPEED_LIMIT. `run_with.py` always passes this
# as an override, so it -- not the city CSV -- sets the residential default.
DEFAULT_CITY_SPEED_LIMIT = 30


@dataclasses.dataclass(frozen=True)
class ClassDefaults:
    """Assumed values for a functional class when the tags are missing.

    These come from `compute.stress()`'s bind parameters, which differ per
    class. A missing speed limit on a primary road is assumed to be 40 mph; on
    a tertiary, 30.

    Parameters
    ----------
    speed
        Assumed speed limit, mph.
    lanes
        Assumed lane count per direction.
    facility_width
        Assumed bike facility width, feet.
    """

    speed: int
    lanes: int
    facility_width: int = 5


# Higher-order classes, each also covering its `_link` variant.
HIGHER_ORDER_DEFAULTS = {
    "primary": ClassDefaults(speed=40, lanes=2),
    "secondary": ClassDefaults(speed=40, lanes=2),
    "tertiary": ClassDefaults(speed=30, lanes=1),
}

# Lower-order classes take a speed default only.
UNCLASSIFIED_DEFAULT_SPEED = 25

# Classes whose stress is a flat constant, applied after the rules above.
FLAT_STRESS = {
    "motorway": HIGH_STRESS,
    "motorway_link": HIGH_STRESS,
    "trunk": HIGH_STRESS,
    "trunk_link": HIGH_STRESS,
    "track": LOW_STRESS,
    "path": LOW_STRESS,
}


def _numeric(ways: pd.DataFrame, name: str) -> pd.Series:
    """Return a column as floats, with unparseable values becoming NaN."""
    return pd.to_numeric(_column(ways, name), errors="coerce")


def _coalesce(values: pd.Series, *fallbacks: float | None) -> pd.Series:
    """Fill missing values from the first non-null fallback, as `COALESCE`.

    Parameters
    ----------
    values
        The preferred values.
    *fallbacks
        Fallbacks in order. A `None` fallback is skipped, matching SQL, where
        `COALESCE(x, NULL, y)` falls through to `y`.

    Returns
    -------
    pandas.Series
        The coalesced values.

    Examples
    --------
    >>> import numpy as np, pandas as pd
    >>> list(_coalesce(pd.Series([1.0, np.nan]), None, 9))
    [1.0, 9.0]
    """
    result = values.astype("float64")
    for fallback in fallbacks:
        if fallback is not None:
            result = result.fillna(float(fallback))
    return result


def _segment_stress(
    ways: gpd.GeoDataFrame,
    direction: str,
    defaults: ClassDefaults,
) -> pd.Series:
    """Rate one direction of a higher-order road.

    Reproduce `stress_segments_higher_order.sql`'s `CASE`: a protected track
    is always low stress; a buffered lane survives up to 25 mph on a single
    lane; a conventional lane up to 20 mph on a single lane and only if it is
    at least 4 ft wide; anything else is low stress only at 15 mph or less on
    a single lane.

    Parameters
    ----------
    ways
        Roads of one functional class.
    direction
        `ft` or `tf`.
    defaults
        The class's assumed values.

    Returns
    -------
    pandas.Series
        Stress rating per road.
    """
    infra = _text(ways, f"{direction}_bike_infra")
    speed = _coalesce(_numeric(ways, "speed_limit"), defaults.speed)
    lanes = _coalesce(_numeric(ways, f"{direction}_lanes"), defaults.lanes)
    width = _coalesce(
        _numeric(ways, f"{direction}_bike_infra_width"),
        defaults.facility_width,
    )

    single_lane = lanes <= 1
    # Default: a shared lane, comfortable only when slow and single-lane.
    stress = pd.Series(HIGH_STRESS, index=ways.index, dtype="int64")
    stress[(speed <= SHARED_LANE_MAX_SPEED) & (lanes == 1)] = LOW_STRESS

    lane = _eq(infra, "lane")
    stress[lane] = HIGH_STRESS
    stress[
        lane & (speed <= LANE_MAX_SPEED) & single_lane & (width >= MIN_LANE_WIDTH_FT)
    ] = LOW_STRESS

    buffered = _eq(infra, "buffered_lane")
    stress[buffered] = HIGH_STRESS
    stress[buffered & (speed <= BUFFERED_LANE_MAX_SPEED) & single_lane] = LOW_STRESS

    stress[_eq(infra, "track")] = LOW_STRESS
    return stress


def _rate_lower_order(
    ways: gpd.GeoDataFrame,
    stress: pd.DataFrame,
    selected: pd.Series,
    speed_defaults: tuple[int | None, ...],
) -> None:
    """Rate a lower-order class on speed alone, in place.

    Reproduce `stress_segments_lower_order.sql` and its `_res` variant, which
    differ only in where the speed default comes from.

    Parameters
    ----------
    ways
        All roads.
    stress
        The ratings frame, modified in place.
    selected
        Which roads this class covers.
    speed_defaults
        Fallback speeds in precedence order.
    """
    if not selected.any():
        return
    speed = _coalesce(_numeric(ways[selected], "speed_limit"), *speed_defaults)
    rated = np.where(speed <= LOWER_ORDER_MAX_SPEED, LOW_STRESS, HIGH_STRESS)
    for column in ("ft_seg_stress", "tf_seg_stress"):
        stress.loc[selected, column] = pd.array(rated, dtype="Int64")


def derive_segment_stress(
    ways: gpd.GeoDataFrame,
    state_default_speed: int | None = None,
    city_default_speed: int | None = None,
) -> pd.DataFrame:
    """Rate every road segment in both directions.

    Run the per-class scripts in `compute.stress()`'s order. A road whose
    class no script covers keeps a NULL rating, exactly as in the SQL, where
    each script's `UPDATE` is scoped by `functional_class`.

    Parameters
    ----------
    ways
        The roads, with features derived.
    state_default_speed
        Residential speed default for the state, from the speed-limit CSVs.
    city_default_speed
        Residential speed default for the city, which takes precedence.

    Returns
    -------
    pandas.DataFrame
        Columns `ft_seg_stress` and `tf_seg_stress`.
    """
    functional_class = _text(ways, "functional_class")
    stress = pd.DataFrame(
        {
            "ft_seg_stress": pd.Series(pd.NA, index=ways.index, dtype="Int64"),
            "tf_seg_stress": pd.Series(pd.NA, index=ways.index, dtype="Int64"),
        },
    )

    # Higher-order classes, each covering its `_link` variant too.
    for name, defaults in HIGHER_ORDER_DEFAULTS.items():
        selected = functional_class.isin([name, f"{name}_link"])
        if not selected.any():
            continue
        subset = ways[selected]
        for direction in ("ft", "tf"):
            rated = _segment_stress(subset, direction, defaults)
            stress.loc[selected, f"{direction}_seg_stress"] = rated.astype("Int64")

    # Lower-order classes rate on speed alone. Residential lets the city
    # default outrank the state default; unclassified has a fixed assumption.
    _rate_lower_order(
        ways,
        stress,
        _eq(functional_class, "residential"),
        (city_default_speed, state_default_speed),
    )
    _rate_lower_order(
        ways,
        stress,
        _eq(functional_class, "unclassified"),
        (UNCLASSIFIED_DEFAULT_SPEED,),
    )

    # A living street is low stress unless bikes are banned outright.
    living = _eq(functional_class, "living_street")
    if living.any():
        banned = living & _eq(_text(ways, "bicycle"), "no")
        for column in ("ft_seg_stress", "tf_seg_stress"):
            stress.loc[living, column] = LOW_STRESS
            stress.loc[banned, column] = HIGH_STRESS

    for name, rating in FLAT_STRESS.items():
        selected = _eq(functional_class, name)
        if selected.any():
            stress.loc[selected, "ft_seg_stress"] = rating
            stress.loc[selected, "tf_seg_stress"] = rating

    return reset_one_way_stress(ways, stress)


def reset_one_way_stress(
    ways: gpd.GeoDataFrame,
    stress: pd.DataFrame,
) -> pd.DataFrame:
    """Blank the stress of a direction a one-way street forbids.

    Reproduce `stress_one_way_reset.sql`. Note it keys off `one_way` -- the
    *bike* direction set by `bike_infra.sql` -- not `one_way_car`, so a street
    that is one-way for cars but has contraflow bike infrastructure keeps both
    directions rated.

    Parameters
    ----------
    ways
        The roads, carrying `one_way`.
    stress
        The ratings to reset.

    Returns
    -------
    pandas.DataFrame
        The ratings, with forbidden directions set to null.
    """
    one_way = _text(ways, "one_way")
    result = stress.copy()
    result.loc[_eq(one_way, "tf"), "ft_seg_stress"] = pd.NA
    result.loc[_eq(one_way, "ft"), "tf_seg_stress"] = pd.NA
    logger.debug(
        f"one-way reset: {int(_eq(one_way, 'tf').sum()):,} ft and "
        f"{int(_eq(one_way, 'ft').sum()):,} tf ratings cleared",
    )
    return result


def read_speed_defaults(
    state_speed_limits: pathlib.Path,
    city_speed_limits: pathlib.Path,
    state_fips: str,
    city_fips: str,
    city_speed_limit_override: int | None = DEFAULT_CITY_SPEED_LIMIT,
) -> tuple[int | None, int | None]:
    """Look up the residential speed defaults for a jurisdiction.

    Reproduce `ingestor.manage_speed_limits`. `speed_limit.sql` deliberately
    leaves the column NULL where OSM has no `maxspeed`, and the residential
    stress rule falls back to these, so the default decides the rating of
    every untagged residential street -- and at 30 mph that is high stress,
    while at 25 it is low.

    **The city CSV is normally never consulted.** `run_with.py` always passes
    `city_speed_limit_override`, defaulting to 30, and the override wins over
    the lookup. The downloaded `city_fips_speed.csv` does contain real
    per-city values (Jackson 25, St. Louis Park 20), but they are overridden
    unless the caller passes `--city-speed-limit` explicitly. Pass
    `city_speed_limit_override=None` to actually use the CSV.

    Parameters
    ----------
    state_speed_limits
        The `state_fips_speed.csv` written by `prepare`.
    city_speed_limits
        The `city_fips_speed.csv` written by `prepare`.
    state_fips
        Two-digit state FIPS code.
    city_fips
        Seven-digit city FIPS code.
    city_speed_limit_override
        The CLI's `--city-speed-limit`. When set, it replaces the CSV lookup.

    Returns
    -------
    tuple
        `(state_default, city_default)`, either of which may be None when the
        jurisdiction is not listed and no override applies.
    """

    def lookup(path: pathlib.Path, column: str, code: str) -> int | None:
        """Find one jurisdiction's speed, tolerating a missing file."""
        if not path.exists():
            return None
        table = pd.read_csv(path, dtype={column: str})
        matched = table[table[column].str.strip() == code.strip()]
        if matched.empty:
            return None
        return int(matched.iloc[0]["speed"])

    state = lookup(state_speed_limits, "fips_code_state", state_fips)
    city = city_speed_limit_override or lookup(
        city_speed_limits, "fips_code_city", city_fips
    )
    logger.debug(f"residential speed defaults: state={state} city={city}")
    return state, city


# Crossing thresholds from the intersection rule table. A two-way roadway of
# more than this many lanes is hostile regardless of speed; the one-way
# threshold is the same width counted over a single direction.
WIDE_CROSSING_LANES = 4
ONE_WAY_CROSSING_LANES = 2

# Speeds, in mph, at which a crossing becomes hostile. The beacon (`rrfb`)
# variants tolerate more speed than the unaided ones.
CROSSING_SPEED_HOSTILE = 40
CROSSING_SPEED_BEACON_NARROW = 35
CROSSING_SPEED_MODERATE = 30


# Assumed speed and half-road lane count for each crossing class, from
# `compute.stress()`'s bind parameters for the intersection scripts.
CROSSING_DEFAULTS = {
    "primary": ClassDefaults(speed=40, lanes=2),
    "secondary": ClassDefaults(speed=40, lanes=2),
    "tertiary": ClassDefaults(speed=30, lanes=1),
}

# Road classes rated by `stress_tertiary_ints.sql` and which crossings it
# considers, versus the same for `stress_lesser_ints.sql`. The two scripts are
# 1,608 lines between them but share one rule table; they differ only in which
# roads they rate and whether a tertiary crossing counts.
TERTIARY_INT_CLASSES = ("tertiary",)
TERTIARY_INT_CROSSINGS = ("primary", "secondary")
LESSER_INT_CLASSES = (
    "residential",
    "unclassified",
    "living_street",
    "track",
    "path",
)
LESSER_INT_CROSSINGS = ("primary", "secondary", "tertiary")

# Classes whose intersections are assumed low stress outright, because the
# junction is either signal-controlled or grade-separated.
ALWAYS_LOW_STRESS_INTS = ("motorway", "trunk", "primary", "secondary")


def _crossing_is_hostile(
    crossings: pd.DataFrame,
    rrfb: pd.Series,
    island: pd.Series,
) -> pd.Series:
    """Decide whether a crossing road makes a junction high stress.

    The shared rule table behind `stress_tertiary_ints.sql` and
    `stress_lesser_ints.sql`. A motorway or trunk is always hostile. Otherwise
    the verdict turns on how many lanes must be crossed, how fast they move,
    and whether a beacon (`rrfb`) or a refuge `island` helps.

    Lane counting differs by direction: a two-way road counts both
    directions' lanes, while a one-way road counts whichever direction is
    tagged. That is why the thresholds are 4 and 2 respectively -- they are
    the same road width expressed two ways.

    Parameters
    ----------
    crossings
        One row per (road being rated, crossing road) pair, carrying the
        crossing's `functional_class`, `one_way`, lane counts and
        `speed_limit`.
    rrfb
        Whether the shared intersection has a flashing beacon.
    island
        Whether it has a pedestrian refuge island.

    Returns
    -------
    pandas.Series
        True where the crossing makes the junction high stress.
    """
    functional_class = _text(crossings, "functional_class")
    one_way = _text(crossings, "one_way")
    two_way = one_way.isna()
    island = island.fillna(value=False).astype(bool)

    hostile = pd.Series(data=False, index=crossings.index)
    hostile |= functional_class.isin(["motorway", "trunk"])

    for name, defaults in CROSSING_DEFAULTS.items():
        selected = _eq(functional_class, name)
        if not selected.any():
            continue
        speed = _coalesce(_numeric(crossings, "speed_limit"), defaults.speed)
        # Two-way: both directions' lanes. One-way: whichever is tagged.
        both = _coalesce(_numeric(crossings, "ft_lanes"), defaults.lanes) + _coalesce(
            _numeric(crossings, "tf_lanes"),
            defaults.lanes,
        )
        single = (
            _coalesce(
                _numeric(crossings, "ft_lanes"),
                None,
            )
            .fillna(_numeric(crossings, "tf_lanes"))
            .fillna(defaults.lanes)
        )

        wide = selected & two_way
        narrow = selected & ~two_way

        # Two-way, threshold expressed over the whole roadway.
        hostile |= wide & (both > WIDE_CROSSING_LANES)
        at_four = wide & (both == WIDE_CROSSING_LANES)
        under_four = wide & (both < WIDE_CROSSING_LANES)
        hostile |= at_four & rrfb & (speed > CROSSING_SPEED_HOSTILE)
        hostile |= (
            at_four
            & rrfb
            & (speed > CROSSING_SPEED_MODERATE)
            & (speed <= CROSSING_SPEED_HOSTILE)
            & ~island
        )
        hostile |= at_four & ~rrfb & (speed > CROSSING_SPEED_MODERATE)
        hostile |= at_four & ~rrfb & (speed == CROSSING_SPEED_MODERATE) & ~island
        hostile |= under_four & rrfb & (speed > CROSSING_SPEED_BEACON_NARROW) & ~island
        hostile |= under_four & ~rrfb & (speed > CROSSING_SPEED_MODERATE) & ~island

        # One-way, threshold expressed over the tagged direction only.
        hostile |= narrow & (single > ONE_WAY_CROSSING_LANES)
        at_two = narrow & (single == ONE_WAY_CROSSING_LANES)
        under_two = narrow & (single < ONE_WAY_CROSSING_LANES)
        hostile |= at_two & rrfb & (speed > CROSSING_SPEED_HOSTILE)
        hostile |= under_two & rrfb & (speed > CROSSING_SPEED_BEACON_NARROW)
        hostile |= at_two & ~rrfb & (speed > CROSSING_SPEED_MODERATE)
        hostile |= under_two & ~rrfb & (speed > CROSSING_SPEED_MODERATE)

    return hostile


def derive_intersection_stress(
    ways: gpd.GeoDataFrame,
    intersections: gpd.GeoDataFrame,
    intersection_flags: pd.DataFrame,
) -> pd.DataFrame:
    """Rate the stress of crossing each intersection.

    Run the intersection scripts in `compute.stress()`'s order. Higher-order
    roads and every `_link` are assumed low stress outright -- their junctions
    are controlled or grade-separated -- while tertiary and lesser roads are
    rated by the shared table in :func:`_crossing_is_hostile`.

    A junction that is signalized or all-way stopped is always low stress, and
    a crossing road sharing this road's name is ignored: the SQL's
    `COALESCE(name,'a') != COALESCE(name,'b')` treats a continuation of the
    same street as not a crossing. Note two *unnamed* roads compare as
    `'a' != 'b'`, so they do count as crossing each other.

    Parameters
    ----------
    ways
        The roads, with features and segment stress derived.
    intersections
        The intersection table, keyed by `osm_id`.
    intersection_flags
        `legs`/`signalized`/`stops`/`rrfb`/`island` per intersection.

    Returns
    -------
    pandas.DataFrame
        Columns `ft_int_stress` and `tf_int_stress`.
    """
    functional_class = _text(ways, "functional_class")
    stress = pd.DataFrame(
        {
            "ft_int_stress": pd.Series(pd.NA, index=ways.index, dtype="Int64"),
            "tf_int_stress": pd.Series(pd.NA, index=ways.index, dtype="Int64"),
        },
    )

    controlled = functional_class.isin(
        ALWAYS_LOW_STRESS_INTS
    ) | functional_class.str.endswith(
        "_link",
        na=False,
    )
    stress.loc[controlled, "ft_int_stress"] = LOW_STRESS
    stress.loc[controlled, "tf_int_stress"] = LOW_STRESS

    flags = intersection_flags.set_index(intersections["osm_id"])
    # Every road meeting each intersection, as candidate crossings.
    at_intersection = pd.concat(
        [
            ways.assign(int_id=ways["intersection_from"]),
            ways.assign(int_id=ways["intersection_to"]),
        ],
    )

    for classes, crossings in (
        (TERTIARY_INT_CLASSES, TERTIARY_INT_CROSSINGS),
        (LESSER_INT_CLASSES, LESSER_INT_CROSSINGS),
    ):
        rated = functional_class.isin(classes)
        if not rated.any():
            continue
        stress.loc[rated, "ft_int_stress"] = LOW_STRESS
        stress.loc[rated, "tf_int_stress"] = LOW_STRESS

        eligible = at_intersection[
            _text(at_intersection, "functional_class").isin(
                [*crossings, "motorway", "trunk"],
            )
        ]
        for direction, endpoint in (
            ("ft", "intersection_to"),
            ("tf", "intersection_from"),
        ):
            hostile_ints = _hostile_intersections(
                ways[rated],
                endpoint,
                eligible,
                flags,
            )
            stress.loc[rated & hostile_ints, f"{direction}_int_stress"] = HIGH_STRESS

    return stress


def _hostile_intersections(
    rated: gpd.GeoDataFrame,
    endpoint: str,
    crossings: pd.DataFrame,
    flags: pd.DataFrame,
) -> pd.Series:
    """Return which rated roads meet a high-stress junction at one endpoint.

    Parameters
    ----------
    rated
        The roads being rated.
    endpoint
        `intersection_to` for the `ft` direction, `intersection_from` for `tf`.
    crossings
        Every candidate crossing road, keyed by `int_id`.
    flags
        Intersection flags, indexed by intersection id.

    Returns
    -------
    pandas.Series
        Boolean mask over the *full* ways index.
    """
    pairs = rated[["road_id", "name", endpoint]].rename(columns={endpoint: "int_id"})
    pairs = pairs.merge(
        crossings,
        on="int_id",
        how="inner",
        suffixes=("_rated", ""),
    )
    if pairs.empty:
        return pd.Series(data=False, index=rated.index).reindex(
            rated.index,
            fill_value=False,
        )

    # A crossing that continues the same street is not a crossing. Unnamed
    # roads take the SQL's distinct sentinels, so two unnamed roads differ.
    own_name = pairs["name_rated"].astype("string").fillna("a")
    other_name = pairs["name"].astype("string").fillna("b")
    different_street = (own_name != other_name) & (
        pairs["road_id_rated"] != pairs["road_id"]
    )

    controls = flags.reindex(pairs["int_id"])
    uncontrolled = ~(
        controls["signalized"].to_numpy(dtype=bool)
        | controls["stops"].to_numpy(dtype=bool)
    )
    hostile = _crossing_is_hostile(
        pairs,
        pd.Series(controls["rrfb"].to_numpy(dtype=bool), index=pairs.index),
        pd.Series(controls["island"].to_numpy(dtype=bool), index=pairs.index),
    )

    flagged = pairs.loc[different_street & uncontrolled & hostile, "road_id_rated"]
    return rated["road_id"].isin(set(flagged))
