"""
Derive the per-way attributes the stress rules read.

Replace `scripts/sql/features/*.sql`. Order matters and mirrors
`compute.features()`: `clip_osm` trims the network to the boundary buffer,
then `one_way` / `width_ft` / `functional_class` run in that sequence because
`functional_class` reads the `width_ft` this module just computed, and its two
`DELETE` statements decide which roads exist at all.

Every rule here is transcribed from the SQL, quirks included. Where the SQL
does something surprising, the surprise is reproduced and the comment says so:
the Python is judged against the SQL's output, not against what the rule looks
like it should say.
"""

import re
import typing

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from loguru import logger

# `nb_boundary_buffer`, from cli/common.py's DEFAULT_BUFFER. Roads beyond this
# distance from the boundary are dropped before any attribute is derived.
DEFAULT_BOUNDARY_BUFFER = 2680

# Highway values mapped straight through to `functional_class`.
DIRECT_FUNCTIONAL_CLASSES = (
    "living_street",
    "motorway",
    "motorway_link",
    "primary",
    "primary_link",
    "residential",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "trunk",
    "trunk_link",
    "unclassified",
)

# Bicycle tag values that count as "bikes are allowed here".
BICYCLE_ALLOWED = ("yes", "permissive", "designated")

# Minimum width, in feet, for a non-designated footway to count as a path.
MIN_FOOTWAY_PATH_WIDTH_FT = 8

# Widths at or above this, when the tag carries no unit, are treated as bogus
# rather than as metres.
MAX_UNITLESS_WIDTH_M = 20

FEET_PER_METRE = 3.28084

# Leading number in a width tag, e.g. `3`, `3.5`, `12.25`.
_WIDTH_NUMBER = re.compile(r"(\d+\.?\d?\d?)")
# Feet-and-inches notation, e.g. `12'` or `12'6"`.
_WIDTH_FEET = re.compile(r"(\d+)'")
_WIDTH_INCHES = re.compile(r'(\d+)"')


def _column(ways: pd.DataFrame, name: str) -> pd.Series:
    """Return a way column, or an all-null column when the tag is absent.

    An OSM extract only carries the tags its ways actually use, so a rule may
    reference a tag no way in this city sets. The SQL saw a NULL column there;
    reproduce that instead of raising.

    Parameters
    ----------
    ways
        The ways frame.
    name
        Tag/column name.

    Returns
    -------
    pandas.Series
        The column, or an all-null column aligned to `ways`.
    """
    if name in ways.columns:
        return ways[name]
    return pd.Series(pd.NA, index=ways.index, dtype="object")


def _text(ways: pd.DataFrame, name: str) -> pd.Series:
    """Return a way column as a nullable string, for tag comparisons."""
    return _column(ways, name).astype("string")


def _eq(values: pd.Series, expected: str) -> pd.Series:
    """Compare a nullable string column to a value, treating NULL as False.

    Plain `==` on a nullable column yields `pd.NA` where the tag is absent,
    not `False`. An `NA` then survives `~` and `&`, and pandas silently drops
    those rows when the result is used as a mask -- so an untagged way gets
    treated as though it matched. SQL's `tag = 'value'` is false for NULL, so
    this is both the safe and the faithful comparison.

    Parameters
    ----------
    values
        A nullable string column.
    expected
        The value to compare against.

    Returns
    -------
    pandas.Series
        A plain boolean mask, never containing NA.

    Examples
    --------
    >>> import pandas as pd
    >>> tags = pd.Series(["no", None, "yes"], dtype="string")
    >>> list(_eq(tags, "no"))
    [True, False, False]
    >>> list(~_eq(tags, "no"))
    [False, True, True]
    """
    return (values == expected).fillna(value=False).astype(bool)


def clip_to_boundary(
    ways: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    buffer: int = DEFAULT_BOUNDARY_BUFFER,
) -> gpd.GeoDataFrame:
    """Drop roads further than the buffer distance from the boundary.

    Reproduce `clip_osm.sql`'s `NOT ST_DWithin(ways.geom, boundary.geom,
    :nb_boundary_buffer)` delete. Distances are in the projected CRS's units,
    so `ways` and `boundary` must already be projected.

    Parameters
    ----------
    ways
        Road segments, in a projected CRS.
    boundary
        The city boundary, in the same CRS.
    buffer
        Buffer distance, in CRS units (metres).

    Returns
    -------
    geopandas.GeoDataFrame
        The roads within the buffer.
    """
    # `distance <= buffer`, not `intersects(boundary.buffer(...))`: buffering
    # approximates arcs with straight segments, so a road sitting almost
    # exactly `buffer` away can land on either side of the test depending on
    # the segmentation. `ST_DWithin` is an exact distance comparison.
    reach = boundary.geometry.union_all()
    kept = ways[ways.geometry.distance(reach) <= buffer]
    logger.debug(f"clip_osm: kept {len(kept):,}/{len(ways):,} roads")
    return kept.reset_index(drop=True)


def derive_one_way(ways: gpd.GeoDataFrame) -> pd.Series:
    """Derive `one_way_car` from the OSM `oneway` tag.

    Reproduce `one_way.sql`. Note what is absent: `oneway=-1` maps to `tf` and
    `oneway` in (`1`, `yes`) maps to `ft`, but no other value -- notably
    `reversible` or `alternating` -- sets anything, leaving the road two-way.

    Parameters
    ----------
    ways
        Road segments carrying the `oneway` tag.

    Returns
    -------
    pandas.Series
        `ft`, `tf`, or null per road.

    Examples
    --------
    >>> import geopandas as gpd, pandas as pd
    >>> ways = gpd.GeoDataFrame({"oneway": ["yes", "-1", "no", None]})
    >>> list(derive_one_way(ways))
    ['ft', 'tf', <NA>, <NA>]
    """
    oneway = _text(ways, "oneway").str.strip()
    result = pd.Series(pd.NA, index=ways.index, dtype="string")
    result[oneway.isin(["1", "yes"])] = "ft"
    result[_eq(oneway, "-1")] = "tf"
    return result


def _width_number(values: pd.Series) -> pd.Series:
    """Extract the leading number from a width tag."""
    return pd.to_numeric(values.str.extract(_WIDTH_NUMBER.pattern, expand=False))


def _leading_int(values: pd.Series) -> pd.Series:
    r"""Extract the first run of digits, as `substring(tag FROM '\d+')` does."""
    return pd.to_numeric(values.str.extract(r"(\d+)", expand=False))


def _round_half_away(values: pd.Series) -> pd.Series:
    """Round to a nullable integer, half away from zero.

    PostgreSQL rounds half away from zero when a NUMERIC value is stored in an
    `INT` column, or passed to `round()`; NumPy rounds half to even. Use this
    where the SQL expression was NUMERIC -- an integer divided by a decimal
    literal, a `SUM` over a NUMERIC column. Where it was FLOAT (`::FLOAT`,
    `ST_Length`, `degrees()`), use :func:`_round_half_even` instead
    (findings.md §1.1).

    Parameters
    ----------
    values
        Float values, possibly containing NaN.

    Returns
    -------
    pandas.Series
        Nullable `Int64` values.

    Examples
    --------
    >>> import numpy as np, pandas as pd
    >>> _round_half_away(pd.Series([8.2, 9.84, 2.5, -2.5, np.nan])).to_list()
    [8, 10, 3, -3, <NA>]
    """
    rounded = np.floor(np.abs(values) + 0.5) * np.sign(values)
    return rounded.astype("Int64")


def _round_half_even(values: pd.Series) -> pd.Series:
    """Round to a nullable integer, half to even.

    PostgreSQL casts a FLOAT to `INT` with C's `rint()`, which rounds half to
    even -- so `22.5::FLOAT` stored in an `INT` column reads back as 22, while
    `22.5::NUMERIC` reads back as 23. This is the FLOAT half; see
    :func:`_round_half_away` for the NUMERIC one.

    Parameters
    ----------
    values
        Float values, possibly containing NaN.

    Returns
    -------
    pandas.Series
        Nullable `Int64` values.

    Examples
    --------
    >>> import numpy as np, pandas as pd
    >>> _round_half_even(pd.Series([8.2, 9.84, 2.5, 3.5, -2.5, np.nan])).to_list()
    [8, 10, 2, 4, -2, <NA>]
    """
    return values.round().astype("Int64")


def derive_speed_limit(ways: gpd.GeoDataFrame) -> pd.Series:
    """Derive `speed_limit` in mph from the OSM `maxspeed` tag.

    Reproduce `speed_limit.sql`. Two passes, and the second overwrites the
    first: a bare number or `NN kmph` is read as km/h, converted, and rounded
    to the nearest 5 mph; `NN mph` is taken verbatim.

    Note the conversion divides by 1.609 and rounds the *quotient over 5*
    before multiplying back, so the result is always a multiple of 5. A value
    the SQL cannot parse at all leaves the limit NULL, which the stress rules
    then replace with a jurisdiction default.

    Parameters
    ----------
    ways
        Road segments carrying the `maxspeed` tag.

    Returns
    -------
    pandas.Series
        Speed limit in mph, or null.

    Examples
    --------
    >>> import geopandas as gpd
    >>> ways = gpd.GeoDataFrame({"maxspeed": ["30 mph", "50", "50 kmph", None]})
    >>> list(derive_speed_limit(ways))
    [30.0, 30.0, 30.0, nan]
    """
    maxspeed = _text(ways, "maxspeed")
    result = pd.Series(np.nan, index=ways.index, dtype="float64")

    # km/h: an explicit `kmph` suffix, or a bare number with no unit at all.
    kmph = maxspeed.str.endswith(" kmph", na=False) | maxspeed.str.match(
        r"^\d+(\.\d+)?$", na=False
    )
    if kmph.any():
        # round(x / 1.609 / 5) * 5 -- PostgreSQL rounds half away from zero.
        scaled = _leading_int(maxspeed[kmph]) / 1.609 / 5
        result[kmph] = np.floor(np.abs(scaled) + 0.5) * np.sign(scaled) * 5

    # mph: taken as-is, overwriting any km/h reading.
    mph = maxspeed.str.endswith(" mph", na=False)
    result[mph] = _leading_int(maxspeed[mph])
    return result


def _lane_count(
    ways: gpd.GeoDataFrame,
    turn_directional: str,
    turn_shared_oneway: tuple[str, ...],
    lanes_directional: str,
    *,
    drop_right_turn_lanes: bool,
) -> pd.Series:
    """Count lanes in one direction, following `lanes.sql`'s CASE ladder.

    The ladder is ordered and stops at the first match: an explicit
    `turn:lanes:<dir>` beats a shared `turn:lanes` on a one-way, which beats
    `lanes:<dir>`, which beats a shared `lanes` tag. A shared `lanes` on a
    two-way road is halved and rounded *up*.

    Parameters
    ----------
    ways
        Road segments carrying the lane tags.
    turn_directional
        The directional turn-lane tag, e.g. `turn:lanes:forward`.
    turn_shared_oneway
        The `oneway` values for which the undirected `turn:lanes` counts
        toward this direction.
    lanes_directional
        The directional lane-count tag, e.g. `lanes:forward`.
    drop_right_turn_lanes
        Ignore lanes marked `right` when splitting the pipe-delimited turn
        lanes. Crossing stress excludes right-only lanes; plain lane counts
        do not.

    Returns
    -------
    pandas.Series
        Lane count, or null where no tag applies.
    """
    oneway = _text(ways, "oneway")
    turn_dir = _text(ways, turn_directional)
    turn_shared = _text(ways, "turn:lanes")
    lanes_dir = _text(ways, lanes_directional)
    lanes_shared = _text(ways, "lanes")

    def split_count(values: pd.Series) -> pd.Series:
        """Count pipe-delimited turn lanes, optionally ignoring right-only."""
        parts = values.str.split("|")

        def count(entry: typing.Any) -> float:
            if not isinstance(entry, list):
                return np.nan
            if drop_right_turn_lanes:
                entry = [lane for lane in entry if lane != "right"]
            # `array_length` of an emptied array is NULL, not 0.
            return len(entry) if entry else np.nan

        return parts.map(count).astype("float64")

    shared_applies = oneway.isin(turn_shared_oneway)
    two_way = oneway.isna() | _eq(oneway, "no")

    result = pd.Series(np.nan, index=ways.index, dtype="float64")
    # Applied in reverse ladder order so earlier branches win.
    halved = np.ceil(_leading_int(lanes_shared) / 2)
    result = result.where(~(lanes_shared.notna() & two_way), halved)
    result = result.where(
        ~(lanes_shared.notna() & shared_applies), _leading_int(lanes_shared)
    )
    result = result.where(~lanes_dir.notna(), _leading_int(lanes_dir))
    result = result.where(
        ~(turn_shared.notna() & shared_applies), split_count(turn_shared)
    )
    return result.where(~turn_dir.notna(), split_count(turn_dir))


def derive_lanes(ways: gpd.GeoDataFrame) -> pd.DataFrame:
    """Derive the per-direction lane counts.

    Reproduce `lanes.sql`, which sets five columns in one statement:
    `ft_lanes`/`tf_lanes` (used for segment stress) and
    `ft_cross_lanes`/`tf_cross_lanes` (used for crossing stress, and excluding
    right-only turn lanes), plus the two-way-left-turn-lane flag.

    Note the SQL keys these off the raw OSM `oneway` tag, not the derived
    `one_way_car` column -- so a value `one_way.sql` ignores is ignored here
    too, consistently.

    Parameters
    ----------
    ways
        Road segments carrying the lane tags.

    Returns
    -------
    pandas.DataFrame
        Columns `ft_lanes`, `tf_lanes`, `ft_cross_lanes`, `tf_cross_lanes`,
        and `twltl_cross_lanes`.
    """
    forward = ("1", "yes")
    backward = ("-1",)
    frame = pd.DataFrame(index=ways.index)
    for name, turn_dir, shared, lanes_dir, drop_right in (
        ("ft_lanes", "turn:lanes:forward", forward, "lanes:forward", False),
        ("tf_lanes", "turn:lanes:backward", backward, "lanes:backward", False),
        ("ft_cross_lanes", "turn:lanes:forward", forward, "lanes:forward", True),
        ("tf_cross_lanes", "turn:lanes:backward", backward, "lanes:backward", True),
    ):
        frame[name] = _lane_count(
            ways,
            turn_dir,
            shared,
            lanes_dir,
            drop_right_turn_lanes=drop_right,
        )

    both_ways = (
        _text(ways, "lanes:both_ways").notna()
        | _text(ways, "turn:lanes:both_ways").notna()
    )
    frame["twltl_cross_lanes"] = np.where(both_ways, 1.0, np.nan)
    return frame


def derive_width_ft(ways: gpd.GeoDataFrame) -> pd.Series:
    """Derive `width_ft` from the OSM `width` tag.

    Reproduce `width_ft.sql`'s four passes, in order: explicit feet, feet and
    inches, explicit metres, then unitless values treated as metres. Only the
    last pass is conditional on nothing having matched yet, exactly as the SQL
    has it -- so a tag like `12 ft` that also parses as unitless keeps its feet
    reading, while the earlier passes freely overwrite one another.

    Parameters
    ----------
    ways
        Road segments carrying the `width` tag.

    Returns
    -------
    pandas.Series
        Width in feet, or null.

    Examples
    --------
    >>> import geopandas as gpd
    >>> ways = gpd.GeoDataFrame({"width": ["10 ft", "3 m", "2.5", None]})
    >>> derive_width_ft(ways).to_list()
    [10, 10, 8, <NA>]
    """
    width = _text(ways, "width")
    result = pd.Series(np.nan, index=ways.index, dtype="float64")

    # Feet, e.g. `10 ft`.
    feet = width.str.endswith(" ft", na=False)
    result[feet] = _width_number(width[feet])

    # Feet and inches, e.g. `12'` or `12'6"`.
    imperial = width.str.match(r".*'.*\"$", na=False) | width.str.endswith(
        "'", na=False
    )
    if imperial.any():
        whole = pd.to_numeric(
            width[imperial].str.extract(_WIDTH_FEET.pattern, expand=False),
        )
        inches = pd.to_numeric(
            width[imperial].str.extract(_WIDTH_INCHES.pattern, expand=False),
        )
        result[imperial] = whole + (inches / 12).fillna(0)

    # Metres, e.g. `3 m`.
    metres = width.str.endswith(" m", na=False)
    result[metres] = FEET_PER_METRE * _width_number(width[metres])

    # No unit: assume metres, but only where nothing matched yet, and discard
    # implausible values that are probably not metres at all.
    unitless = _width_number(width)
    fill = result.isna() & width.notna() & (unitless < MAX_UNITLESS_WIDTH_M)
    result[fill] = FEET_PER_METRE * unitless[fill]

    # `neighborhood_ways.width_ft` is declared INT, so the computed float is
    # rounded on assignment and every later reader sees the integer -- notably
    # `functional_class.sql`'s `COALESCE(width_ft, 0) >= 8` footway test, which
    # a 7.6 ft path passes once rounded. Keeping the float here would change
    # that classification. Every pass casts `::FLOAT`, so a half rounds to
    # even: `22'6"` is 22 ft, not 23.
    return _round_half_even(result)


def _access_permits_routing(ways: gpd.GeoDataFrame) -> pd.Series:
    """Return whether a road's `access` tag permits routing over it.

    Transcribed from the predicate repeated in every `functional_class.sql`
    update::

        access IS NULL
        OR (access = 'no' AND bicycle IN ('yes','permissive','designated'))
        OR access NOT IN ('no','private')

    Worth reading carefully, because the middle clause is narrower than it
    looks: `access = 'private'` is rejected outright, *even when bikes are
    explicitly designated*, since only `access = 'no'` gets the bicycle
    exemption. That asymmetry is preserved deliberately.

    Parameters
    ----------
    ways
        Road segments carrying `access` and `bicycle` tags.

    Returns
    -------
    pandas.Series
        Boolean mask of roads that may be routed over.
    """
    access = _text(ways, "access")
    bicycle = _text(ways, "bicycle")
    return (
        access.isna()
        | (_eq(access, "no") & bicycle.isin(BICYCLE_ALLOWED))
        | (~access.isin(["no", "private"]) & access.notna())
    )


def derive_functional_class(
    ways: gpd.GeoDataFrame,
    width_ft: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Derive `functional_class` and the `xwalk` flag.

    Reproduce `functional_class.sql`'s nine updates in order; later rules
    overwrite earlier ones for the same road, so the sequence is part of the
    definition.

    Parameters
    ----------
    ways
        Road segments carrying the OSM tags.
    width_ft
        Width in feet, from :func:`derive_width_ft`, which the footway rule
        reads.

    Returns
    -------
    tuple of pandas.Series
        The functional class (null where the road is not routable) and the
        crosswalk flag.
    """
    highway = _text(ways, "highway")
    bicycle = _text(ways, "bicycle")
    footway = _text(ways, "footway")
    tracktype = _text(ways, "tracktype")
    golf = _text(ways, "golf")
    golf_cart = _text(ways, "golf_cart")
    allowed = _access_permits_routing(ways)

    functional_class = pd.Series(pd.NA, index=ways.index, dtype="string")
    # `xwalk` is an INT column with no default: it stays NULL unless the
    # footway-crossing rule sets it to 1. Defaulting it to 0 would not change
    # any decision, but it would change the exported column.
    xwalk = pd.Series(pd.NA, index=ways.index, dtype="Int64")

    direct = highway.isin(DIRECT_FUNCTIONAL_CLASSES) & allowed
    functional_class[direct] = highway[direct]

    functional_class[_eq(highway, "track") & _eq(tracktype, "grade1") & allowed] = (
        "track"
    )
    functional_class[highway.isin(["cycleway", "path"]) & allowed] = "path"

    crossing = (
        _eq(highway, "footway") & footway.isin(["crossing", "traffic_island"]) & allowed
    )
    functional_class[crossing] = "path"
    xwalk[crossing] = 1

    wide_enough = _eq(bicycle, "designated") | (
        width_ft.fillna(0) >= MIN_FOOTWAY_PATH_WIDTH_FT
    )
    functional_class[
        _eq(highway, "footway") & bicycle.isin(BICYCLE_ALLOWED) & allowed & wide_enough
    ] = "path"

    functional_class[
        _eq(highway, "service") & bicycle.isin(BICYCLE_ALLOWED) & allowed
    ] = "unclassified"

    is_golf = golf.isin(["path", "cartpath"]) | golf_cart.isin(["yes", "designated"])
    functional_class[_eq(highway, "path") & is_golf & allowed] = "unclassified"

    functional_class[
        _eq(highway, "pedestrian") & bicycle.isin(BICYCLE_ALLOWED) & allowed
    ] = "living_street"

    return functional_class, xwalk


# Bike facility values that count as a real facility in `class_adjustments`.
BIKE_FACILITIES = ("track", "buffered_lane", "lane")

# Every tag `bike_infra.sql` reads.
OSM_CYCLEWAY_TAGS = (
    "cycleway",
    "cycleway:both",
    "cycleway:both:buffer",
    "cycleway:both:width",
    "cycleway:buffer",
    "cycleway:left",
    "cycleway:left:buffer",
    "cycleway:left:oneway",
    "cycleway:left:width",
    "cycleway:right",
    "cycleway:right:buffer",
    "cycleway:right:oneway",
    "cycleway:right:width",
    "cycleway:width",
    "oneway:bicycle",
)

# `cycleway:*:buffer` values that make a lane a buffered lane.
BUFFER_VALUES = ("yes", "both", "right", "left")

# Rule = (condition, resulting bike infrastructure value).
Rule = tuple["pd.Series", str]


def _first_match(rules: list[Rule], index: "pd.Index") -> pd.Series:
    """Evaluate an ordered rule list, first match winning.

    A SQL `CASE` returns the first branch whose condition holds, so the rules
    are applied in reverse and each earlier rule overwrites the later ones.

    Parameters
    ----------
    rules
        Ordered `(condition, value)` pairs, highest precedence first.
    index
        Index for the result.

    Returns
    -------
    pandas.Series
        The matched value per row, or null where no rule matched.
    """
    result = pd.Series(pd.NA, index=index, dtype="string")
    for condition, value in reversed(rules):
        result[condition] = value
    return result


def derive_bike_infra(ways: gpd.GeoDataFrame) -> tuple[pd.Series, pd.Series]:
    """Derive the per-direction bike infrastructure.

    Reproduce `bike_infra.sql`'s two 250-line `CASE` expressions. Each starts
    with a shared "both directions" prefix, then branches on `one_way_car`
    into a direction-specific ladder. The `tf` ladder mirrors `ft` with left
    and right swapped -- *almost*: see the asymmetries flagged inline, which
    are reproduced as written rather than regularised.

    Parameters
    ----------
    ways
        Road segments carrying the `cycleway:*` tags and `one_way_car`.

    Returns
    -------
    tuple of pandas.Series
        `ft_bike_infra` and `tf_bike_infra`.
    """
    tag = {name: _text(ways, name) for name in OSM_CYCLEWAY_TAGS}
    one_way_car = _text(ways, "one_way_car")

    def is_(name: str, value: str) -> pd.Series:
        """Return `tag = value`, NULL comparing false."""
        return _eq(tag[name], value)

    def buffered(name: str) -> pd.Series:
        """Return whether a buffer tag names a real buffer."""
        return tag[name].isin(BUFFER_VALUES)

    def forward(name: str) -> pd.Series:
        """Return `tag != '-1' OR tag IS NULL`, the "not reversed" test."""
        return ~_eq(tag[name], "-1")

    # Applies to both directions, before either branches on one_way_car.
    shared: list[Rule] = [
        (is_("cycleway:both", "shared_lane"), "sharrow"),
        (is_("cycleway:both", "buffered_lane"), "buffered_lane"),
        (is_("cycleway:both", "lane") & buffered("cycleway:buffer"), "buffered_lane"),
        (
            is_("cycleway:both", "lane") & buffered("cycleway:both:buffer"),
            "buffered_lane",
        ),
        (is_("cycleway:both", "lane"), "lane"),
        (is_("cycleway:both", "track"), "track"),
        (
            is_("cycleway:right", "track")
            & (is_("oneway:bicycle", "no") | is_("cycleway:right:oneway", "no")),
            "track",
        ),
        (
            is_("cycleway:left", "track")
            & (is_("oneway:bicycle", "no") | is_("cycleway:left:oneway", "no")),
            "track",
        ),
        (is_("cycleway", "track") & is_("oneway:bicycle", "no"), "track"),
    ]

    def with_flow(side: str, other: str) -> list[Rule]:
        """Rules for the direction cars travel on a one-way street.

        `side` is the kerb the facility is on for this direction (`left` for
        `ft`, `right` for `tf`); `other` is the opposite kerb.
        """
        return [
            (is_(f"cycleway:{side}", "shared_lane"), "sharrow"),
            (
                is_(f"cycleway:{side}", "lane")
                & forward(f"cycleway:{side}:oneway")
                & buffered("cycleway:buffer"),
                "buffered_lane",
            ),
            (
                is_(f"cycleway:{side}", "lane")
                & forward(f"cycleway:{side}:oneway")
                & buffered(f"cycleway:{side}:buffer"),
                "buffered_lane",
            ),
            (
                is_(f"cycleway:{side}", "lane") & forward(f"cycleway:{side}:oneway"),
                "lane",
            ),
            (
                is_(f"cycleway:{side}", "track") & forward(f"cycleway:{side}:oneway"),
                "track",
            ),
            # Carried over from the two-way ladder.
            (is_("cycleway", "shared_lane"), "sharrow"),
            (is_(f"cycleway:{other}", "shared_lane"), "sharrow"),
            (is_("cycleway", "buffered_lane"), "buffered_lane"),
            (
                is_(f"cycleway:{other}", "buffered_lane")
                # Asymmetry: the `ft` ladder also requires the other kerb's
                # `oneway` not be reversed here; the `tf` ladder does not.
                & (
                    forward(f"cycleway:{other}:oneway")
                    if side == "left"
                    else pd.Series(data=True, index=ways.index)
                ),
                "buffered_lane",
            ),
            (
                is_("cycleway", "lane")
                # Asymmetry: only the `tf` ladder gates this on the other
                # kerb's `oneway`.
                & (
                    forward(f"cycleway:{other}:oneway")
                    if side == "right"
                    else pd.Series(data=True, index=ways.index)
                )
                & buffered("cycleway:buffer"),
                "buffered_lane",
            ),
            (
                is_(f"cycleway:{other}", "lane")
                & forward(f"cycleway:{other}:oneway")
                & buffered("cycleway:buffer"),
                "buffered_lane",
            ),
            (
                is_(f"cycleway:{other}", "lane")
                & forward(f"cycleway:{other}:oneway")
                & buffered(f"cycleway:{other}:buffer"),
                "buffered_lane",
            ),
            (is_("cycleway", "lane"), "lane"),
            (
                is_(f"cycleway:{other}", "lane") & forward(f"cycleway:{other}:oneway"),
                "lane",
            ),
            (is_("cycleway", "track"), "track"),
            (
                is_(f"cycleway:{other}", "track") & forward(f"cycleway:{other}:oneway"),
                "track",
            ),
        ]

    def against_flow(*, unreachable_guard: bool) -> list[Rule]:
        """Rules for travelling against a one-way street, on contraflow infra.

        Parameters
        ----------
        unreachable_guard
            Reproduce the `one_way_car = 'tf'` guard the SQL puts on the last
            two rules. Inside the `tf_bike_infra` / `one_way_car = 'ft'`
            block that guard can never hold, so those rules are dead code --
            a copy-paste slip that is reproduced rather than repaired, since
            our SQL is the reference implementation.
        """
        guard = (
            _eq(one_way_car, "tf")
            if unreachable_guard
            else pd.Series(data=True, index=ways.index)
        )
        return [
            (
                is_("cycleway", "opposite_lane") & buffered("cycleway:buffer"),
                "buffered_lane",
            ),
            (
                is_("cycleway:right", "opposite_lane") & buffered("cycleway:buffer"),
                "buffered_lane",
            ),
            (
                is_("cycleway:right", "opposite_lane")
                & buffered("cycleway:right:buffer"),
                "buffered_lane",
            ),
            (
                is_("cycleway:left:oneway", "-1") & is_("cycleway:left", "track"),
                "track",
            ),
            (
                is_("cycleway:right:oneway", "-1") & is_("cycleway:right", "track"),
                "track",
            ),
            (
                is_("cycleway:left:oneway", "-1")
                & is_("cycleway:left", "lane")
                & is_("cycleway:left:buffer", "yes"),
                "buffered_lane",
            ),
            (
                is_("cycleway:right:oneway", "-1")
                & is_("cycleway:right", "lane")
                & is_("cycleway:right:buffer", "yes"),
                "buffered_lane",
            ),
            (
                is_("cycleway:left:oneway", "-1") & is_("cycleway:left", "lane"),
                "lane",
            ),
            (
                is_("cycleway:right:oneway", "-1") & is_("cycleway:right", "lane"),
                "lane",
            ),
            (is_("cycleway", "opposite_lane"), "lane"),
            (is_("cycleway:right", "opposite_lane"), "lane"),
            (is_("cycleway", "opposite_track"), "track"),
            (guard & is_("cycleway:left", "opposite_track"), "track"),
            (guard & is_("cycleway:right", "opposite_track"), "track"),
        ]

    def two_way(side: str) -> list[Rule]:
        """Rules for a street with no one-way restriction."""
        return [
            (is_("cycleway", "shared_lane"), "sharrow"),
            (is_(f"cycleway:{side}", "shared_lane"), "sharrow"),
            (is_("cycleway", "buffered_lane"), "buffered_lane"),
            (is_(f"cycleway:{side}", "buffered_lane"), "buffered_lane"),
            (is_("cycleway", "lane") & buffered("cycleway:buffer"), "buffered_lane"),
            (
                is_(f"cycleway:{side}", "lane") & buffered("cycleway:buffer"),
                "buffered_lane",
            ),
            (
                is_(f"cycleway:{side}", "lane") & buffered(f"cycleway:{side}:buffer"),
                "buffered_lane",
            ),
            (is_("cycleway", "lane"), "lane"),
            (is_(f"cycleway:{side}", "lane"), "lane"),
            (is_("cycleway", "track"), "track"),
            (is_(f"cycleway:{side}", "track"), "track"),
        ]

    def direction(
        flow_value: str, side: str, other: str, *, guard_is_dead: bool
    ) -> pd.Series:
        """Assemble one direction's full CASE."""
        is_forward = _eq(one_way_car, flow_value)
        is_reverse = _eq(one_way_car, "tf" if flow_value == "ft" else "ft")
        is_two_way = one_way_car.isna()

        rules: list[Rule] = list(shared)
        rules += [(is_forward & cond, value) for cond, value in with_flow(side, other)]
        rules += [
            (is_reverse & cond, value)
            for cond, value in against_flow(unreachable_guard=guard_is_dead)
        ]
        rules += [(is_two_way & cond, value) for cond, value in two_way(other)]
        return _first_match(rules, ways.index)

    # `ft`: with the flow the facility sits on the left kerb, against it on
    # the right. The `tf` direction is the mirror -- except the guard on the
    # contraflow rules, which is live for `ft` and dead for `tf`.
    ft = direction("ft", side="left", other="right", guard_is_dead=False)
    tf = direction("tf", side="right", other="left", guard_is_dead=True)
    return ft, tf


# A road at or above this speed is treated as higher-order than residential.
CLASS_ADJUSTMENT_SPEED_MPH = 30


# `parking:lane:*` values that mean cars park here, and those that mean they
# do not. `paralell` is a misspelling the SQL matches on purpose -- it occurs
# in real OSM data and dropping it would lose those roads.
PARKING_PRESENT = ("parallel", "paralell", "diagonal", "perpendicular")
PARKING_ABSENT = ("no_parking", "no_stopping")


def derive_parking(ways: gpd.GeoDataFrame) -> pd.DataFrame:
    """Derive whether each side of the road has on-street parking.

    Reproduce `park.sql`, which runs three sequential updates: a "both" pass
    setting each direction, then a "right" pass setting `ft_park` and a "left"
    pass setting `tf_park`.

    **The "both" pass has no lasting effect.** Each update assigns the `CASE`
    result unconditionally to every joined row, and a `CASE` with no matching
    branch yields NULL -- so the right pass overwrites `ft_park` with NULL on
    any road lacking a `parking:*right*` tag, discarding whatever
    `parking:lane:both` had just set. The final value of `ft_park` therefore
    depends only on the right-hand tags, and `tf_park` only on the left-hand
    ones. This is reproduced, not corrected: our SQL is the reference
    implementation (requirements.md §3).

    Parameters
    ----------
    ways
        Road segments carrying the `parking:*` tags.

    Returns
    -------
    pandas.DataFrame
        Columns `ft_park` and `tf_park`, 1 where parking is present, 0 where
        it is explicitly absent, null where nothing says.
    """

    def side(kerb: str) -> pd.Series:
        """Evaluate one side's CASE ladder."""
        lane = _text(ways, f"parking:lane:{kerb}")
        parking = _text(ways, f"parking:{kerb}")
        restriction = _text(ways, f"parking:{kerb}:restriction")
        rules: list[tuple[pd.Series, int]] = [
            (lane.isin(PARKING_PRESENT), 1),
            (lane.isin(PARKING_ABSENT), 0),
            (_eq(parking, "lane"), 1),
            (_eq(parking, "no"), 0),
            (restriction.isin(PARKING_ABSENT), 0),
        ]
        result = pd.Series(pd.NA, index=ways.index, dtype="Int64")
        for condition, value in reversed(rules):
            result[condition] = value
        return result

    return pd.DataFrame({"ft_park": side("right"), "tf_park": side("left")})


def derive_intersection_legs(
    ways: gpd.GeoDataFrame,
    intersections: pd.Index | pd.Series,
) -> pd.Series:
    """Count the roads meeting at each intersection.

    Reproduce `legs.sql`. A road is counted once per intersection it touches,
    so a road looping back to the same node counts twice there -- the SQL's
    `int_id IN (intersection_from, intersection_to)` is a membership test that
    matches such a road once, not twice, which this mirrors.

    Parameters
    ----------
    ways
        The surviving roads.
    intersections
        Intersection ids to count for.

    Returns
    -------
    pandas.Series
        Leg count per intersection id.
    """
    index = pd.Index(intersections)
    touches = pd.concat(
        [
            ways[["road_id", "intersection_from"]].rename(
                columns={"intersection_from": "int_id"},
            ),
            ways[["road_id", "intersection_to"]].rename(
                columns={"intersection_to": "int_id"},
            ),
        ],
    )
    # `IN (from, to)` matches a road once even when both ends are the node.
    counts = touches.drop_duplicates().groupby("int_id")["road_id"].size()
    return counts.reindex(index).fillna(0).astype("int64")


# `sigctl_search_dist` from `compute.py`'s NB_SIGCTL_SEARCH_DIST: how far from
# an intersection a signal, crossing, or stop sign still counts as controlling
# it, in the projected CRS's units (metres).
SIGNAL_SEARCH_DISTANCE = 25

# An intersection must have more than this many legs for a nearby crossing to
# control it. A two-leg node is a mid-block point, not a junction.
MIN_CONTROLLED_LEGS = 2

# `flashing_lights` values that mark a rectangular rapid flashing beacon.
RRFB_VALUES = ("yes", "button", "always", "sensor")

# `crossing` values that are signal-controlled, including the HAWK variants.
SIGNAL_CROSSINGS = ("traffic_signals", "hawk", "pelican", "toucan")


def build_intersections(
    ways: gpd.GeoDataFrame,
    nodes: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Build the intersection table from the surviving roads.

    An intersection is any node a surviving road starts or ends at. This also
    covers `functional_class.sql`'s "remove obsolete intersections" delete:
    building the table from the roads that remain never creates a row for a
    node nothing touches.

    Parameters
    ----------
    ways
        The surviving roads, with `intersection_from`/`intersection_to`.
    nodes
        Node geometries from `ingest.read_nodes`, in the analysis CRS.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per intersection, with `osm_id` (the OSM node id) and a point
        geometry.
    """
    used = pd.unique(
        pd.concat([ways["intersection_from"], ways["intersection_to"]]),
    )
    located = nodes[nodes["id"].isin(used)].rename(columns={"id": "osm_id"})
    intersections = located.drop_duplicates(subset="osm_id").reset_index(drop=True)
    logger.debug(f"{len(intersections):,} intersections")
    return intersections


def derive_intersection_flags(
    intersections: gpd.GeoDataFrame,
    ways: gpd.GeoDataFrame,
    points: gpd.GeoDataFrame,
    search_distance: int = SIGNAL_SEARCH_DISTANCE,
) -> pd.DataFrame:
    """Derive the traffic-control flags on each intersection.

    Reproduce `signalized.sql`, `stops.sql`, `rrfb.sql`, and `island.sql`.
    Every rule except the direct node match requires more than two legs: a
    two-leg node is a point mid-way along a road, not a junction, and a nearby
    crossing does not control it.

    Note the last rule of `signalized` and `stops` propagates the flag from an
    already-flagged intersection to its neighbours within the search distance.
    The SQL runs that update **once**, against the state at that moment, so it
    does not cascade transitively -- reproduced here as a single pass.

    Parameters
    ----------
    intersections
        The intersection table, in the analysis CRS.
    ways
        The surviving roads, for leg counts and the way-tagged signals.
    points
        Tagged OSM nodes from `ingest.read_point_features`, same CRS.
    search_distance
        How far a control point reaches, in CRS units.

    Returns
    -------
    pandas.DataFrame
        Columns `legs`, `signalized`, `stops`, `rrfb`, and `island`.
    """
    index = intersections.index
    legs = derive_intersection_legs(ways, intersections["osm_id"]).to_numpy()
    junction = legs > MIN_CONTROLLED_LEGS

    def tag(frame: gpd.GeoDataFrame, name: str) -> pd.Series:
        """Read a point tag, tolerating its absence from the extract."""
        return _text(frame, name)

    def near(mask: pd.Series) -> np.ndarray:
        """Return which intersections lie within reach of a matching point."""
        if points.empty or not mask.any():
            return np.zeros(len(intersections), dtype=bool)
        reach = points[mask.to_numpy()].geometry.union_all()
        return intersections.geometry.distance(reach).to_numpy() <= search_distance

    if points.empty:
        point_highway = pd.Series(pd.NA, index=pd.RangeIndex(0), dtype="string")
        on_node = pd.Series(data=False, index=index)
        stop_on_node = pd.Series(data=False, index=index)
    else:
        point_highway = tag(points, "highway")
        signal_ids = set(points.loc[_eq(point_highway, "traffic_signals"), "id"])
        on_node = intersections["osm_id"].isin(signal_ids)
        stop_ids = set(
            points.loc[
                _eq(point_highway, "stop") & _eq(tag(points, "stop"), "all"),
                "id",
            ],
        )
        stop_on_node = intersections["osm_id"].isin(stop_ids)

    # A way tagged `traffic_signals:direction` signals the intersection at the
    # end it points to.
    direction = _text(ways, "traffic_signals:direction")
    signalled_nodes = set(ways.loc[_eq(direction, "forward"), "intersection_to"]) | set(
        ways.loc[_eq(direction, "backward"), "intersection_from"],
    )

    is_crossing = (
        _eq(point_highway, "crossing")
        if not points.empty
        else pd.Series(data=False, index=pd.RangeIndex(0))
    )
    signalized = (
        on_node.to_numpy()
        | intersections["osm_id"].isin(signalled_nodes).to_numpy()
        | (
            junction
            & near(is_crossing & tag(points, "crossing").isin(SIGNAL_CROSSINGS))
        )
    )
    # Propagate to neighbouring junctions, once.
    if signalized.any():
        spread = intersections[signalized].geometry.union_all()
        signalized = signalized | (
            junction
            & (intersections.geometry.distance(spread).to_numpy() <= search_distance)
        )

    stops = stop_on_node.to_numpy()
    if stops.any():
        spread = intersections[stops].geometry.union_all()
        stops = stops | (
            junction
            & (intersections.geometry.distance(spread).to_numpy() <= search_distance)
        )

    rrfb = junction & near(
        is_crossing & tag(points, "flashing_lights").isin(RRFB_VALUES),
    )
    island = junction & near(
        is_crossing
        & (
            _eq(tag(points, "crossing"), "island")
            | _eq(tag(points, "crossing:island"), "yes")
        ),
    )

    return pd.DataFrame(
        {
            "legs": legs,
            "signalized": signalized,
            "stops": stops,
            "rrfb": rrfb,
            "island": island,
        },
        index=index,
    )


METRES_PER_MILE = 1609.34

# Feature types `calculate_mileage.sql` totals.
MILEAGE_FEATURE_TYPES = ("sharrow", "buffered_lane", "lane", "track", "path")


def calculate_mileage(ways: gpd.GeoDataFrame) -> pd.DataFrame:
    """Total the network mileage by bike facility type.

    Reproduce `calculate_mileage.sql`, the source of `mileage.csv`. Each road
    contributes up to three rows: its `ft_bike_infra`, its `tf_bike_infra`,
    and `path` when it is a path that is not a crosswalk.

    A road with a facility in *both* directions therefore contributes its full
    length twice -- these are directional facility miles, not centreline
    miles, and halving them would understate the network.

    Parameters
    ----------
    ways
        The roads, with bike infrastructure and `functional_class` derived,
        in a projected CRS.

    Returns
    -------
    pandas.DataFrame
        Columns `feature_type` and `total_mileage`, one row per type present.
    """
    length_miles = ways.geometry.length / METRES_PER_MILE
    # `xwalk IS NULL` -- a crosswalk is a path by class but not path mileage.
    as_path = (
        _eq(_text(ways, "functional_class"), "path")
        & _column(
            ways,
            "xwalk",
        ).isna()
    )

    contributions = [
        pd.DataFrame(
            {"feature_type": _text(ways, "ft_bike_infra"), "miles": length_miles},
        ),
        pd.DataFrame(
            {"feature_type": _text(ways, "tf_bike_infra"), "miles": length_miles},
        ),
        pd.DataFrame(
            {
                "feature_type": pd.Series(
                    "path",
                    index=ways.index,
                    dtype="string",
                ).where(as_path),
                "miles": length_miles,
            },
        ),
    ]
    stacked = pd.concat(contributions, ignore_index=True)
    eligible = stacked[stacked["feature_type"].isin(MILEAGE_FEATURE_TYPES)]
    totals = eligible.groupby("feature_type")["miles"].sum()
    return pd.DataFrame(
        {
            "feature_type": totals.index.to_numpy(),
            "total_mileage": totals.to_numpy(),
        },
    )


def cluster_paths(ways: gpd.GeoDataFrame) -> tuple[pd.Series, gpd.GeoDataFrame]:
    """Group contiguous path roads into named paths.

    Reproduce `paths.sql`: `ST_ClusterIntersecting` over every road whose
    functional class is `path`, so a trail split across many OSM ways becomes
    one path. Each cluster records its total length and the diagonal span of
    its bounding box, which the recreation access rule later tests against
    `PathConstraint.min_length` and `min_bbox`.

    Parameters
    ----------
    ways
        The roads, with `functional_class` derived, in a projected CRS.

    Returns
    -------
    tuple of (pandas.Series, geopandas.GeoDataFrame)
        The per-road `path_id` (null for non-paths), and the path table with
        `path_id`, `geometry`, `path_length`, and `bbox_length`.
    """
    is_path = _eq(_text(ways, "functional_class"), "path")
    paths = ways[is_path]
    path_id = pd.Series(pd.NA, index=ways.index, dtype="Int64")
    if paths.empty:
        empty = gpd.GeoDataFrame(
            {"path_id": [], "geometry": [], "path_length": [], "bbox_length": []},
            geometry="geometry",
            crs=ways.crs,
        )  # ty:ignore[no-matching-overload]
        return path_id, empty

    # Contiguous roads share a cluster; `ST_ClusterIntersecting` groups by
    # touching geometry, which connected components over an intersects join
    # reproduces.
    joined = gpd.sjoin(
        paths[["geometry"]],
        paths[["geometry"]],
        how="inner",
        predicate="intersects",
    )
    graph = nx.Graph()
    graph.add_nodes_from(paths.index)
    graph.add_edges_from(zip(joined.index, joined["index_right"], strict=True))

    geometries, lengths, spans = [], [], []
    for cluster, members in enumerate(nx.connected_components(graph), start=1):
        member_list = list(members)
        path_id.loc[member_list] = cluster
        geometry = paths.loc[member_list].geometry.union_all()
        geometries.append(geometry)
        lengths.append(geometry.length)
        minx, miny, maxx, maxy = geometry.bounds
        spans.append(shapely.LineString([(minx, miny), (maxx, maxy)]).length)

    table = gpd.GeoDataFrame(
        {
            "path_id": range(1, len(geometries) + 1),
            "geometry": geometries,
            "path_length": lengths,
            "bbox_length": spans,
        },
        geometry="geometry",
        crs=ways.crs,
    )  # ty:ignore[no-matching-overload]
    logger.debug(f"{len(table):,} paths from {len(paths):,} path roads")
    return path_id, table


def derive_bike_one_way(ways: gpd.GeoDataFrame) -> pd.Series:
    """Derive `one_way`, the direction constraint bikes actually face.

    Reproduce the second half of `bike_infra.sql`. This is a *different*
    column from `one_way_car`: a street that is one-way for cars is two-way
    for bikes when it carries contraflow infrastructure or is tagged
    `oneway:bicycle=no`, and the routing network is built from this column,
    not from `one_way_car`.

    The SQL keeps `one_way = one_way_car` only when neither escape applies,
    leaving it NULL -- meaning two-way -- otherwise.

    Parameters
    ----------
    ways
        Road segments with `one_way_car` and the bike infrastructure columns.

    Returns
    -------
    pandas.Series
        `ft`, `tf`, or null for two-way.
    """
    one_way_car = _text(ways, "one_way_car")
    # `COALESCE(oneway:bicycle, 'yes') = 'no'` -- an absent tag is not 'no'.
    bicycle_two_way = _eq(_text(ways, "oneway:bicycle"), "no")

    result = pd.Series(pd.NA, index=ways.index, dtype="string")
    for flow, opposite in (("ft", "tf_bike_infra"), ("tf", "ft_bike_infra")):
        contraflow_infra = _text(ways, opposite).notna()
        keeps_restriction = _eq(one_way_car, flow) & ~(
            contraflow_infra | bicycle_two_way
        )
        result[keeps_restriction] = flow
    return result


def derive_bike_infra_width(ways: gpd.GeoDataFrame) -> tuple[pd.Series, pd.Series]:
    """Derive the bike facility widths, in feet.

    Reproduce `bike_infra.sql`'s final two updates. Each is an ordered `CASE`
    over three unit groups -- explicit feet, explicit metres, then unitless
    values treated as metres -- and within each group the tags are consulted
    in a fixed order: this direction's kerb, then the *other* kerb but only on
    a one-way street, then `cycleway:both:width`, then `cycleway:width`.

    A width is only set where that direction actually has infrastructure; the
    SQL's `WHERE ft_bike_infra IS NOT NULL` guard is preserved, so a road with
    no facility keeps a NULL width rather than a parsed-but-meaningless one.

    Parameters
    ----------
    ways
        Road segments with the `cycleway:*:width` tags, `one_way_car`, and the
        derived bike infrastructure columns.

    Returns
    -------
    tuple of pandas.Series
        `ft_bike_infra_width` and `tf_bike_infra_width`.
    """
    one_way_car = _text(ways, "one_way_car")

    def width_for(side: str, other: str, flow: str, infra_column: str) -> pd.Series:
        """Build one direction's width."""
        candidates = (
            (f"cycleway:{side}:width", None),
            (f"cycleway:{other}:width", flow),
            ("cycleway:both:width", None),
            ("cycleway:width", None),
        )
        result = pd.Series(np.nan, index=ways.index, dtype="float64")
        # Applied in reverse so the earliest CASE branch wins.
        unit_groups = (("", FEET_PER_METRE), (" m", FEET_PER_METRE), (" ft", 1.0))
        for suffix, factor in unit_groups:
            for tag_name, required_flow in reversed(candidates):
                values = _text(ways, tag_name)
                applies = (
                    values.str.endswith(suffix, na=False) if suffix else values.notna()
                )
                if required_flow is not None:
                    applies = applies & _eq(one_way_car, required_flow)
                result[applies] = factor * _width_number(values[applies])
        # Only directions that actually carry a facility get a width.
        return result.where(_text(ways, infra_column).notna())

    ft = width_for("right", "left", "ft", "ft_bike_infra")
    tf = width_for("left", "right", "tf", "tf_bike_infra")
    return ft, tf


def adjust_functional_class(ways: gpd.GeoDataFrame) -> pd.Series:
    """Promote busy residential and unclassified roads to tertiary.

    Reproduce `class_adjustments.sql`: a `residential` or `unclassified` road
    becomes `tertiary` when it has bike facilities in *both* directions, more
    than one lane in either direction, or a speed limit of 30 mph or more.

    This matters far more outside the US than the rule's wording suggests. A
    typical Australian residential street is signed 50 km/h, which converts to
    31 mph and trips the speed condition, so most of Orange's residential
    network is reclassified -- 2,250 roads, versus 6 in Jackson.

    Comparisons against NULL are false, matching SQL: a road with no lane or
    speed tag is not promoted.

    Parameters
    ----------
    ways
        Road segments with `functional_class`, the lane counts, `speed_limit`,
        and the bike infrastructure columns derived.

    Returns
    -------
    pandas.Series
        The adjusted functional class.
    """
    functional_class = _text(ways, "functional_class")
    adjustable = functional_class.isin(["residential", "unclassified"])

    both_directions_have_facilities = _text(ways, "ft_bike_infra").isin(
        BIKE_FACILITIES
    ) & _text(ways, "tf_bike_infra").isin(BIKE_FACILITIES)

    def compare(name: str, threshold: int, *, inclusive: bool) -> pd.Series:
        """Compare a numeric column to a threshold, with NULL comparing false."""
        numeric = pd.to_numeric(_column(ways, name), errors="coerce")
        exceeds = numeric >= threshold if inclusive else numeric > threshold
        return exceeds.fillna(value=False).astype(bool)

    busy = (
        both_directions_have_facilities
        | compare("ft_lanes", 1, inclusive=False)
        | compare("tf_lanes", 1, inclusive=False)
        | compare("speed_limit", CLASS_ADJUSTMENT_SPEED_MPH, inclusive=True)
    )

    promoted = functional_class.copy()
    promoted[adjustable & busy] = "tertiary"
    logger.debug(f"class adjustments: promoted {int((adjustable & busy).sum()):,}")
    return promoted


def drop_orphans(ways: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop roads that connect to nothing at either end.

    Reproduce `functional_class.sql`'s orphan delete: a road goes only when
    *neither* of its endpoints is shared with another road. A road joined to a
    neighbour at just one end is kept.

    Applied once, exactly as the SQL does. It is not iterated to a fixed point,
    so a two-road chain dangling off the network survives here just as it does
    in the SQL.

    Parameters
    ----------
    ways
        Road segments with `intersection_from`/`intersection_to`.

    Returns
    -------
    geopandas.GeoDataFrame
        The roads with at least one connected end.
    """
    endpoints = pd.concat([ways["intersection_from"], ways["intersection_to"]])
    # How many roads touch each node, counting a road once per distinct end.
    touching = endpoints.groupby(endpoints).size()

    def connected(column: str) -> pd.Series:
        """Return whether another road shares this endpoint."""
        counts = ways[column].map(touching).fillna(0)
        # Subtract this road's own use of the node. A road whose two ends are
        # the same node still counts itself twice there.
        own = 1 + (ways["intersection_from"] == ways["intersection_to"]).astype(int)
        return counts - own > 0

    kept = ways[connected("intersection_to") | connected("intersection_from")]
    logger.debug(f"orphans: kept {len(kept):,}/{len(ways):,} roads")
    return kept.reset_index(drop=True)


def drop_bicycle_prohibited_paths(ways: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop paths that prohibit bicycles.

    Reproduce the statement `compute.features()` issues inline between
    `clip_osm.sql` and `one_way.sql`::

        DELETE FROM neighborhood_osm_full_line
        WHERE bicycle='no' AND highway='path'

    It deletes from the *tag* table, not from `neighborhood_ways`, so the
    effect is indirect: `functional_class.sql` joins the two on `osm_id`, the
    join finds no partner, `functional_class` stays NULL, and the road is
    removed by the "remove stuff that we don't want to route over" delete.
    Dropping the road here reaches the same end state.

    Note this rule lives in Python rather than in `scripts/sql/`, so it is
    invisible to a search of the SQL alone -- it accounted for all 88 excess
    road segments in Rehoboth Beach, whose sand beach paths carry
    `bicycle=no`.

    Parameters
    ----------
    ways
        Road segments carrying the `highway` and `bicycle` tags.

    Returns
    -------
    geopandas.GeoDataFrame
        The roads that remain.
    """
    prohibited = _eq(_text(ways, "highway"), "path") & _eq(_text(ways, "bicycle"), "no")
    kept = ways[~prohibited]
    logger.debug(
        f"bicycle-prohibited paths: dropped {int(prohibited.sum()):,} roads",
    )
    return kept.reset_index(drop=True)


def derive(
    ways: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    buffer: int = DEFAULT_BOUNDARY_BUFFER,
) -> gpd.GeoDataFrame:
    """Run the feature derivation.

    Follows `compute.features()`'s order, which is part of the definition
    because later scripts overwrite columns earlier ones set: `clip_osm.sql`,
    the inline bicycle-path delete, `one_way.sql`, `width_ft.sql`,
    `functional_class.sql` (whose two `DELETE`s decide which roads exist),
    then `speed_limit.sql` and `lanes.sql`.

    Still to come (task 4): `paths.sql`, `park.sql`, `bike_infra.sql`,
    `class_adjustments.sql`, `legs.sql`, `signalized.sql`, `stops.sql`,
    `rrfb.sql`, `island.sql`.

    Parameters
    ----------
    ways
        Road segments from `ingest`, in the projected CRS.
    boundary
        The city boundary, in the same CRS.
    buffer
        Boundary buffer distance, in CRS units.

    Returns
    -------
    geopandas.GeoDataFrame
        The routable roads, with the derived feature columns.
    """
    roads = clip_to_boundary(ways, boundary, buffer)
    roads = drop_bicycle_prohibited_paths(roads)
    roads = roads.assign(one_way_car=derive_one_way(roads))
    roads = roads.assign(width_ft=derive_width_ft(roads))
    functional_class, xwalk = derive_functional_class(roads, roads["width_ft"])
    roads = roads.assign(functional_class=functional_class, xwalk=xwalk)

    # "remove stuff that we don't want to route over"
    routable = roads[roads["functional_class"].notna()].reset_index(drop=True)
    logger.debug(
        f"functional_class: kept {len(routable):,}/{len(roads):,} roads",
    )
    final = drop_orphans(routable)

    # Attribute derivation on the surviving roads.
    final = final.assign(speed_limit=derive_speed_limit(final))
    final = final.join(derive_lanes(final))

    final = final.join(derive_parking(final))

    ft_infra, tf_infra = derive_bike_infra(final)
    final = final.assign(ft_bike_infra=ft_infra, tf_bike_infra=tf_infra)
    final = final.assign(one_way=derive_bike_one_way(final))
    ft_width, tf_width = derive_bike_infra_width(final)
    final = final.assign(ft_bike_infra_width=ft_width, tf_bike_infra_width=tf_width)

    # `class_adjustments.sql` runs last, and rewrites functional_class using
    # the lane, speed, and bike infrastructure columns above.
    final = final.assign(functional_class=adjust_functional_class(final))

    # `paths.sql` runs right after functional_class.sql in compute.features().
    path_id, _ = cluster_paths(final)
    final = final.assign(path_id=path_id)

    logger.info(f"features: {len(final):,} routable roads")
    return final


def obsolete_intersections(
    ways: gpd.GeoDataFrame,
    intersections: typing.Iterable[typing.Any],
) -> set[typing.Any]:
    """Return the intersections no surviving road touches.

    Reproduce `functional_class.sql`'s final delete.

    Parameters
    ----------
    ways
        The surviving roads.
    intersections
        Candidate intersection ids.

    Returns
    -------
    set
        The ids to drop.
    """
    used = set(ways["intersection_from"]) | set(ways["intersection_to"])
    return {i for i in intersections if i not in used}
