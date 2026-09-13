"""
Score how well the low-stress network reaches the places people go.

Replace `connectivity/destinations/*.sql`, `connectivity/access_*.sql`,
`category_scores.sql`, and `overall_scores.sql`.

The shape of the computation is the same for every destination category, which
is why 13 destination scripts and 17 access scripts collapse to two
parameterised functions here. For each census block the pipeline counts how
many destinations it can reach on the *unrestricted* network and how many on
the *low-stress* network, and scores the ratio between them. A place you can
only reach by riding a hostile road does not count as reachable.

Category scores average the destination scores that belong to them, the overall
score is their weighted combination, and every weight comes from
`core/pipeline/config.py`.
"""

import dataclasses
import decimal
import math
import typing

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from loguru import logger

from brokenspoke_analyzer.core.pipeline import config
from brokenspoke_analyzer.core.pipeline.features import (
    _column,
    _eq,
    _text,
)
from brokenspoke_analyzer.core.pipeline.network import (
    BUFFER_OVERCAPTURE,
    POSTGIS_QUAD_SEGS,
)
from brokenspoke_analyzer.core.pipeline.stress import (
    HIGH_STRESS,
    LOW_STRESS,
)


@dataclasses.dataclass(frozen=True)
class MatchBranch:
    """One `OR` branch of a destination script's `WHERE` clause.

    Parameters
    ----------
    key
        The OSM tag to test.
    accepted
        Accepted values. Empty means "any non-null value", the SQL's
        `shop IS NOT NULL`.
    excluded
        Values that disqualify the feature *through this branch only*. Retail
        excludes supermarkets from its `shop` branch but not from its
        `landuse=retail` one.
    guarded
        Whether the point insert's `NOT EXISTS (... inside a polygon ...)`
        applies to this branch. In most scripts the clause is unparenthesised,
        so `AND` binds to the last `OR` branch alone and a point matching an
        earlier branch is inserted even when a polygon already covers it
        (findings.md §1.21).
    """

    key: str
    accepted: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    guarded: bool = True


@dataclasses.dataclass(frozen=True)
class DestinationRule:
    """How to recognise one category of destination in OSM data.

    Parameters
    ----------
    name
        The category name, matching its `Access` entry and score column.
    matches
        The `OR` branches identifying the destination.
    predicate
        A hand-written mask, for the one category whose `WHERE` clause does
        not decompose into independent branches.
    tolerance
        `ST_ClusterWithin` distance, from `config.Tolerance`. Features within
        this distance merge into one destination -- a campus mapped as several
        buildings is one college. Zero means no clustering.
    point_buffer
        Buffer applied to matching *points* before clustering, so they can
        merge with nearby polygons. Only retail uses this.
    point_exclusion_distance
        How near a polygon a point has to be to count as the same
        destination. Zero is the usual `ST_Intersects`; transit uses
        `ST_DWithin` at the cluster tolerance instead.
    cluster_points
        Whether matching points are clustered among themselves. Only transit
        does this.
    cluster_polygons
        Whether `tolerance` also merges polygons. Transit is the one category
        where it does not: `transit.sql` clusters its *points* at the
        tolerance while keeping every polygon a destination of its own,
        subject only to the subarea delete (findings.md §1.24).
    """

    name: str
    matches: tuple[MatchBranch, ...] = ()
    predicate: typing.Callable[[gpd.GeoDataFrame], pd.Series] | None = None
    tolerance: int = 0
    point_buffer: int = 0
    point_exclusion_distance: int = 0
    cluster_points: bool = False
    cluster_polygons: bool = True


def _transit_matches(features: gpd.GeoDataFrame) -> pd.Series:
    """Recognise a transit stop the way `transit.sql` does.

    The third clause is the interesting one:

    ```sql
    public_transport = 'station'
    AND NOT (railway = 'station' AND station = 'miniature')
    ```

    With `railway` and `station` both absent, `NOT (NULL AND NULL)` is NULL,
    not TRUE, so the row does **not** match. A plain `public_transport=station`
    with nothing else on it is therefore excluded -- which is why Jackson's
    six ski gondola stations and Provincetown's inclined elevator are not
    transit in the published results (findings.md §1.22).
    """
    amenity = _text(features, "amenity")
    railway = _text(features, "railway")
    station = _text(features, "station")
    transport = _text(features, "public_transport")

    is_rail_station = _eq(railway, "station")
    not_miniature = station.isna() | ~_eq(station, "miniature")
    # `NOT (A AND B)` is TRUE only when one side is *known* false.
    known_not_miniature = (railway.notna() & ~is_rail_station) | (
        station.notna() & ~_eq(station, "miniature")
    )

    return (
        amenity.isin(TRANSIT_AMENITIES)
        | (is_rail_station & not_miniature)
        | (_eq(transport, "station") & known_not_miniature)
    )


TRANSIT_AMENITIES = ("bus_station", "ferry_terminal")

# Transcribed from `connectivity/destinations/*.sql`. Several categories accept
# both a British and an American spelling, or both an `amenity` and a
# `healthcare` tagging; those are the SQL's own alternatives, not tidying.
DESTINATION_RULES = (
    DestinationRule(
        "colleges",
        (MatchBranch("amenity", ("college",)),),
        tolerance=100,
    ),
    DestinationRule(
        "community_centers",
        (MatchBranch("amenity", ("community_centre", "community_center")),),
        tolerance=50,
    ),
    # In these four the point insert's guard binds to the last branch alone.
    DestinationRule(
        "dentists",
        (
            MatchBranch("amenity", ("dentist",), guarded=False),
            MatchBranch("healthcare", ("dentist",)),
        ),
        tolerance=50,
    ),
    DestinationRule(
        "doctors",
        (
            MatchBranch("amenity", ("clinic", "doctors"), guarded=False),
            MatchBranch("healthcare", ("doctor", "doctors", "clinic")),
        ),
        tolerance=50,
    ),
    DestinationRule(
        "hospitals",
        (
            MatchBranch("amenity", ("hospitals", "hospital"), guarded=False),
            MatchBranch("healthcare", ("hospital",)),
        ),
        tolerance=50,
    ),
    # Parks parenthesises its `OR` list, so the guard applies throughout.
    DestinationRule(
        "parks",
        (
            MatchBranch("amenity", ("park",)),
            MatchBranch("leisure", ("park", "nature_reserve", "playground")),
        ),
        tolerance=50,
    ),
    DestinationRule(
        "pharmacies",
        (
            MatchBranch("amenity", ("pharmacy",), guarded=False),
            MatchBranch("shop", ("chemist",)),
        ),
        tolerance=50,
    ),
    DestinationRule(
        "transit",
        predicate=_transit_matches,
        tolerance=75,
        point_exclusion_distance=75,
        cluster_points=True,
        cluster_polygons=False,
    ),
    DestinationRule(
        "universities",
        (MatchBranch("amenity", ("university",)),),
        tolerance=150,
    ),
    # These three are *not* clustered: the SQL passes them no tolerance, so two
    # adjacent schools stay two schools.
    DestinationRule("schools", (MatchBranch("amenity", ("school", "kindergarten")),)),
    DestinationRule("social_services", (MatchBranch("amenity", ("social_facility",)),)),
    DestinationRule("supermarkets", (MatchBranch("shop", ("supermarket",)),)),
)

# Retail is the odd one out. It clusters shop polygons together with shop
# *points buffered by 10 m*, so a parade of separately-mapped shops becomes one
# retail area rather than a dozen destinations. Supermarkets are excluded from
# the `shop` branch -- but not from the other two -- so they are not counted in
# two categories.
RETAIL_RULE = DestinationRule(
    "retail",
    (
        MatchBranch("landuse", ("retail",)),
        MatchBranch("building", ("retail",)),
        MatchBranch("shop", (), excluded=("no", "supermarket")),
    ),
    tolerance=50,
    point_buffer=10,
)


def _branch_mask(features: gpd.GeoDataFrame, branch: MatchBranch) -> pd.Series:
    """Return which features satisfy one `OR` branch."""
    column = _text(features, branch.key)
    matched = column.isin(branch.accepted) if branch.accepted else column.notna()
    if branch.excluded:
        matched &= ~column.isin(branch.excluded)
    return matched.fillna(value=False).astype(bool)


def _matches_rule(features: gpd.GeoDataFrame, rule: DestinationRule) -> pd.Series:
    """Return which features satisfy a destination rule.

    Parameters
    ----------
    features
        Candidate OSM features with their tags.
    rule
        The rule to apply.

    Returns
    -------
    pandas.Series
        Boolean mask over `features`.
    """
    if rule.predicate is not None:
        return rule.predicate(features).fillna(value=False).astype(bool)
    matched = pd.Series(data=False, index=features.index)
    for branch in rule.matches:
        matched |= _branch_mask(features, branch)
    return matched


def cluster_within(
    geometries: gpd.GeoSeries,
    tolerance: int,
) -> list[list[int]]:
    """Group geometries lying within `tolerance` of each other.

    Reproduce `ST_ClusterWithin`. A campus mapped as several adjacent
    buildings is one college, not five, so the destination counts -- and
    therefore the scores -- depend on this grouping.

    Parameters
    ----------
    geometries
        Geometries to cluster, in a projected CRS.
    tolerance
        Maximum separation for two geometries to share a cluster. Zero leaves
        every geometry on its own.

    Returns
    -------
    list of list of int
        Positional indices, one list per cluster.
    """
    count = len(geometries)
    if tolerance <= 0 or count == 0:
        return [[position] for position in range(count)]

    frame = gpd.GeoDataFrame({"geometry": geometries.to_numpy()}, crs=geometries.crs)  # ty:ignore[no-matching-overload]
    # Buffer one side and intersect, then confirm with an exact distance test:
    # a polygon buffer inscribes its circle and would drop borderline pairs.
    reach = gpd.GeoDataFrame(
        {"geometry": frame.geometry.buffer(tolerance * BUFFER_OVERCAPTURE)},
        crs=frame.crs,
    )  # ty:ignore[no-matching-overload]
    pairs = gpd.sjoin(frame, reach, how="inner", predicate="intersects")

    graph = nx.Graph()
    graph.add_nodes_from(range(count))
    values = frame.geometry.to_numpy()
    for raw_left, raw_right in zip(pairs.index, pairs["index_right"], strict=True):
        left, right = int(raw_left), int(raw_right)
        if left < right and values[left].distance(values[right]) <= tolerance:
            graph.add_edge(left, right)
    return [sorted(component) for component in nx.connected_components(graph)]


def _covered_points(
    points: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    distance: int,
) -> set[int]:
    """Find the points a kept polygon already accounts for.

    `distance` is 0 for the usual `ST_Intersects`; transit uses `ST_DWithin`
    at its cluster tolerance instead, so a stop node beside its station
    building is the same stop.
    """
    if polygons.empty or points.empty:
        return set()
    if distance:
        # Over-capture with a margin, then apply the exact distance test:
        # a polygon buffer inscribes its circle (findings.md §2.3).
        reach = polygons.assign(
            geometry=polygons.geometry.buffer(distance * BUFFER_OVERCAPTURE),
        )
        candidates = gpd.sjoin(
            points[["geometry"]],
            reach[["geometry"]],
            how="inner",
            predicate="intersects",
        )
        shapes = polygons.geometry.to_numpy()
        return {
            int(point)
            for point, polygon in zip(
                candidates.index,
                candidates["index_right"],
                strict=True,
            )
            if points.geometry.iloc[int(point)].distance(shapes[int(polygon)])
            <= distance
        }
    covered = gpd.sjoin(
        points[["geometry"]],
        polygons[["geometry"]],
        how="inner",
        predicate="intersects",
    )
    return {int(position) for position in covered.index}


def _surviving_points(
    points: gpd.GeoDataFrame,
    polygons: gpd.GeoDataFrame,
    rule: DestinationRule,
) -> gpd.GeoDataFrame:
    """Drop the points a polygon already covers, branch by branch.

    A point inside a kept polygon is usually the same destination mapped
    twice -- but only the branches the SQL actually guards are dropped
    (findings.md §1.21).
    """
    if points.empty:
        return points
    covered = _covered_points(points, polygons, rule.point_exclusion_distance)
    if not covered:
        return points

    is_covered = pd.Series(
        [position in covered for position in range(len(points))],
        index=points.index,
    )
    if rule.predicate is not None or not rule.matches:
        keep = ~is_covered
    else:
        keep = pd.Series(data=False, index=points.index)
        for branch in rule.matches:
            matched = _branch_mask(points, branch)
            keep |= matched & ~is_covered if branch.guarded else matched
    return points[keep].reset_index(drop=True)


def _cluster_points(points: gpd.GeoDataFrame, tolerance: int) -> gpd.GeoDataFrame:
    """Merge nearby points into one destination at their centroid.

    `transit.sql` is the only script that clusters its points, with
    `ST_Centroid(ST_CollectionExtract(unnest(ST_ClusterWithin(...)), 1))`.
    """
    if points.empty or len(points) == 1:
        return points
    clusters = cluster_within(points.geometry, tolerance)
    shapes = points.geometry.to_numpy()
    return gpd.GeoDataFrame(
        {
            "id": [points["id"].to_numpy()[members[0]] for members in clusters]
            if "id" in points.columns
            else np.arange(len(clusters)),
            "geometry": [
                shapely.MultiPoint([shapes[member] for member in members]).centroid
                for members in clusters
            ],
        },
        geometry="geometry",
        crs=points.crs,
    )  # ty:ignore[no-matching-overload]


def _as_points_and_polygons(features: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep only what `osm2pgsql` would have written as a point or a polygon.

    The destination scripts read `neighborhood_osm_full_point` and
    `_polygon` and nothing else. An **unclosed** way went to the line table
    instead, so it is not a destination however it is tagged -- while a
    closed way with an area tag became a polygon (findings.md §3.9).
    `pyrosm` returns both as LineStrings, so the distinction has to be made
    here.
    """
    is_line = features.geometry.geom_type.isin(["LineString", "LinearRing"])
    if not is_line.any():
        return features[~features.geometry.geom_type.str.endswith("LineString")]
    closed = is_line & features.geometry.apply(
        lambda shape: bool(getattr(shape, "is_closed", False)),
    )
    repaired = features.copy()
    repaired.loc[closed, "geometry"] = features.loc[closed, "geometry"].apply(
        shapely.Polygon,
    )
    keep = ~features.geometry.geom_type.isin(
        ["LineString", "LinearRing", "MultiLineString"]
    )
    return repaired[keep | closed].reset_index(drop=True)


def extract_destinations(
    features: gpd.GeoDataFrame,
    census_blocks: gpd.GeoDataFrame,
    rule: DestinationRule,
) -> gpd.GeoDataFrame:
    """Find one category's destinations and the blocks they sit in.

    Reproduce the shared shape of `connectivity/destinations/*.sql`:

    1. take matching polygons, using their centroid as the point;
    2. drop a polygon wholly inside another of the same category, because a
       school's sports field tagged `amenity=school` is not a second school;
    3. add matching points, skipping any that fall inside a polygon already
       taken -- the same destination mapped twice;
    4. record every census block the destination touches.

    Parameters
    ----------
    features
        Candidate OSM features, in the analysis CRS.
    census_blocks
        The retained census blocks, same CRS.
    rule
        The category to extract.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per destination, with `blockid20` listing its blocks.
    """
    if features.empty:
        return gpd.GeoDataFrame(
            {"osm_id": [], "blockid20": [], "geometry": []},
            geometry="geometry",
            crs=census_blocks.crs,
        )  # ty:ignore[no-matching-overload]

    matched = features[_matches_rule(features, rule)].reset_index(drop=True)
    # A self-intersecting ring never reached PostGIS at all: `osm2pgsql`
    # refuses to write a polygon it cannot build, so the feature is simply
    # absent from `neighborhood_osm_full_polygon` (findings.md §3.8). Dropping
    # it here matches that, and keeps the invalid ring out of the overlays,
    # where GEOS would raise on it.
    matched = matched[matched.geometry.is_valid].reset_index(drop=True)
    matched = _as_points_and_polygons(matched)
    is_area = matched.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    polygons = matched[is_area].reset_index(drop=True)
    points = matched[~is_area].reset_index(drop=True)

    if rule.point_buffer:
        # Retail merges shop points into the polygon clustering by buffering
        # them first, so a row of separately-mapped shops becomes one area.
        buffered = points.assign(
            geometry=points.geometry.buffer(
                rule.point_buffer,
                resolution=POSTGIS_QUAD_SEGS,
            ),
        )
        polygons = pd.concat([polygons, buffered]).reset_index(drop=True)
        points = points.iloc[0:0]

    if rule.tolerance and rule.cluster_polygons:
        clusters = cluster_within(polygons.geometry, rule.tolerance)
        polygons = gpd.GeoDataFrame(
            {
                "geometry": [
                    polygons.geometry.iloc[members].union_all() for members in clusters
                ],
            },
            crs=polygons.crs,
        )  # ty:ignore[no-matching-overload]
    elif len(polygons) > 1:
        # Unclustered categories still drop a polygon wholly inside another:
        # a school's playing field tagged `amenity=school` is not a second
        # school.
        nested = gpd.sjoin(
            polygons[["geometry"]],
            polygons[["geometry"]],
            how="inner",
            predicate="within",
        )
        contained = {
            int(inner)
            for inner, outer in zip(
                nested.index,
                nested["index_right"],
                strict=True,
            )
            if int(inner) != int(outer)
        }
        polygons = polygons.drop(index=list(contained)).reset_index(drop=True)

    points = _surviving_points(points, polygons, rule)

    if rule.cluster_points:
        points = _cluster_points(points, rule.tolerance)

    destinations = pd.concat([polygons, points])
    if destinations.empty:
        return gpd.GeoDataFrame(
            {"osm_id": [], "blockid20": [], "geometry": []},
            geometry="geometry",
            crs=census_blocks.crs,
        )  # ty:ignore[no-matching-overload]

    blocks = _blocks_touched(destinations, census_blocks)
    result = gpd.GeoDataFrame(
        {
            "osm_id": destinations["id"].to_numpy()
            if "id" in destinations.columns
            else np.arange(len(destinations)),
            "blockid20": blocks,
            "geometry": destinations.geometry.to_numpy(),
        },
        geometry="geometry",
        crs=census_blocks.crs,
    )  # ty:ignore[no-matching-overload]
    logger.debug(f"{rule.name}: {len(result):,} destinations")
    return result


def _blocks_touched(
    destinations: gpd.GeoDataFrame,
    census_blocks: gpd.GeoDataFrame,
) -> list[list[str]]:
    """List the census blocks each destination belongs to.

    The SQL tests **both** geometries it stores:
    `ST_Intersects(geom_poly, cb.geom) OR ST_Intersects(geom_pt, cb.geom)`,
    where `geom_pt` is the polygon's centroid. A cluster wrapped around a
    block -- a park either side of a street -- has a centroid that lands in a
    block none of its parts touch, and that block counts too
    (findings.md §3.10).
    """
    shapes = destinations[["geometry"]].reset_index(drop=True)
    centroids = shapes.set_geometry(shapes.geometry.centroid)
    grouped: dict[int, set[str]] = {}
    for frame in (shapes, centroids):
        joined = gpd.sjoin(
            frame,
            census_blocks[["geoid20", "geometry"]],
            how="left",
            predicate="intersects",
        )
        for position, geoid in zip(joined.index, joined["geoid20"], strict=True):
            if pd.isna(geoid):
                continue
            grouped.setdefault(int(position), set()).add(str(geoid))
    return [
        sorted(grouped.get(position, set())) for position in range(len(destinations))
    ]


def count_reachable(
    census_blocks: gpd.GeoDataFrame,
    destinations: gpd.GeoDataFrame,
    connected: pd.DataFrame,
) -> pd.DataFrame:
    """Count the destinations each block reaches, by network.

    Reproduce the first half of every `access_*.sql`: for each block, how many
    destinations sit in a block it is connected to, counted once over the
    unrestricted network and once over the low-stress one.

    Parameters
    ----------
    census_blocks
        The retained blocks.
    destinations
        One category's destinations, with `blockid20`.
    connected
        Block pairs from `network.connected_census_blocks`.

    Returns
    -------
    pandas.DataFrame
        Columns `low_stress` and `high_stress`, indexed like `census_blocks`.
    """
    counts = pd.DataFrame(
        {
            "low_stress": pd.Series(0, index=census_blocks.index, dtype="int64"),
            "high_stress": pd.Series(0, index=census_blocks.index, dtype="int64"),
        },
    )
    if destinations.empty or connected.empty:
        return counts

    # Which destinations sit in each block.
    in_block: dict[str, set[int]] = {}
    for position, blockids in enumerate(destinations["blockid20"]):
        for geoid in blockids:
            in_block.setdefault(geoid, set()).add(position)

    position_of_geoid = {
        str(geoid): position for position, geoid in enumerate(census_blocks["geoid20"])
    }
    high: dict[int, set[int]] = {}
    low: dict[int, set[int]] = {}
    for source, target, is_low in zip(
        connected["source_blockid20"],
        connected["target_blockid20"],
        connected["low_stress"],
        strict=True,
    ):
        position = position_of_geoid.get(str(source))
        if position is None:
            continue
        reached = in_block.get(str(target))
        if not reached:
            continue
        high.setdefault(position, set()).update(reached)
        if is_low:
            low.setdefault(position, set()).update(reached)

    high_column = np.zeros(len(census_blocks), dtype="int64")
    low_column = np.zeros(len(census_blocks), dtype="int64")
    for position, found in high.items():
        high_column[position] = len(found)
    for position, found in low.items():
        low_column[position] = len(found)
    counts["high_stress"] = high_column
    counts["low_stress"] = low_column
    return counts


def destination_score(
    low_stress: pd.Series,
    high_stress: pd.Series,
    access: config.Access,
) -> pd.Series:
    """Score a block's access to one destination category.

    Reproduce the `CASE` shared by every `access_*.sql`. The shape depends on
    how many destinations the category rewards individually:

    - With no `first` weight the score is the plain ratio of low-stress to
      total reachable destinations.
    - With weights, the first, second, and third reachable destinations earn
      fixed amounts, and anything beyond them shares the remainder
      proportionally. Reaching one supermarket is most of the value; the
      fourth adds little.

    A block that can reach nothing at all scores NULL, not zero -- it is
    unscored rather than scored badly, and the category is dropped from its
    overall score.

    Parameters
    ----------
    low_stress, high_stress
        Reachable destination counts per block.
    access
        The category's weights, from `config.Access`.

    Returns
    -------
    pandas.Series
        Score per block, or null where nothing is reachable.
    """
    low = low_stress.astype("float64")
    high = high_stress.astype("float64")
    score = pd.Series(np.nan, index=low.index, dtype="float64")

    reachable = high > 0
    score[reachable & (low == 0)] = 0.0
    score[reachable & (low == high)] = float(access.max_score)

    graduated = reachable & (low != high) & (low > 0)
    if not access.first:
        score[graduated] = low[graduated] / high[graduated]
        return score

    remaining = float(access.max_score) - access.first
    if not access.second:
        score[graduated] = access.first + (remaining * (low[graduated] - 1)) / (
            high[graduated] - 1
        )
        return score

    remaining -= access.second
    if not access.third:
        score[graduated & (low == 1)] = access.first
        score[graduated & (low == SECOND_TIER)] = access.first + access.second
        beyond = graduated & (low > SECOND_TIER)
        score[beyond] = (
            access.first
            + access.second
            + (remaining * (low[beyond] - SECOND_TIER)) / (high[beyond] - SECOND_TIER)
        )
        return score

    remaining -= access.third
    score[graduated & (low == 1)] = access.first
    score[graduated & (low == SECOND_TIER)] = access.first + access.second
    score[graduated & (low == THIRD_TIER)] = access.first + access.second + access.third
    beyond = graduated & (low > THIRD_TIER)
    score[beyond] = (
        access.first
        + access.second
        + access.third
        + (remaining * (low[beyond] - THIRD_TIER)) / (high[beyond] - THIRD_TIER)
    )
    return score


# How many destinations earn an individually-weighted share before the rest
# split the remainder proportionally.
METRES_PER_MILE = 1609.34

SECOND_TIER = 2
THIRD_TIER = 3


# The `Access` weights `compute.py:connectivity()` passes to each
# `access_*.sql`. They belong with the other runtime constants rather than as
# literals inside a SQL-orchestration function (tasks.md note for 7.1).
ACCESS_WEIGHTS = (
    config.Access("colleges", first=0.7),
    config.Access("community_centers", first=0.4, second=0.2, third=0.1),
    config.Access("doctors", first=0.4, second=0.2, third=0.1),
    config.Access("dentists", first=0.4, second=0.2, third=0.1),
    config.Access("hospitals", first=0.7),
    config.Access("pharmacies", first=0.4, second=0.2, third=0.1),
    config.Access("parks", first=0.3, second=0.2, third=0.2),
    config.Access("retail", first=0.4, second=0.2, third=0.1),
    config.Access("schools", first=0.3, second=0.2, third=0.2),
    config.Access("social_services", first=0.7),
    config.Access("supermarkets", first=0.6, second=0.2),
    config.Access("transit", first=0.6),
    config.Access("universities", first=0.7),
)


def access_weights() -> dict[str, config.Access]:
    """Return the per-category access weights, keyed by category name."""
    return {access.name: access for access in ACCESS_WEIGHTS}


# `category_scores.sql`: each category is a weighted average of its members,
# renormalised over whichever members the city actually has. A city with no
# university is not penalised for it -- the weight is removed from the divisor
# rather than the score being treated as zero.
CATEGORY_WEIGHTS = {
    "opportunity": {
        "emp": 0.35,
        "schools": 0.35,
        "colleges": 0.1,
        "universities": 0.2,
    },
    "core_services": {
        "doctors": 0.2,
        "dentists": 0.1,
        "hospitals": 0.2,
        "pharmacies": 0.1,
        "supermarkets": 0.25,
        "social_services": 0.15,
    },
    "recreation": {
        "parks": 0.4,
        "trails": 0.35,
        "community_centers": 0.25,
    },
}

# The 16 rows `overall_scores.sql` pulls from `score_inputs.sql` via its
# `use_*` flags, mapped to the census-block column they average. Of the ~130
# rows `score_inputs.sql` produces, only these carry a flag; the rest are
# diagnostics for `neighborhood_score_inputs.csv`.
OVERALL_SCORE_ROWS = (
    ("people", "pop"),
    ("opportunity_employment", "emp"),
    ("opportunity_k12_education", "schools"),
    ("opportunity_technical_vocational_college", "colleges"),
    ("opportunity_higher_education", "universities"),
    ("core_services_doctors", "doctors"),
    ("core_services_dentists", "dentists"),
    ("core_services_hospitals", "hospitals"),
    ("core_services_pharmacies", "pharmacies"),
    ("core_services_grocery", "supermarkets"),
    ("core_services_social_services", "social_services"),
    ("retail", "retail"),
    ("recreation_parks", "parks"),
    ("recreation_trails", "trails"),
    ("recreation_community_centers", "community_centers"),
    ("transit", "transit"),
)

# Members weighted by the *whole* boundary population rather than by the
# population that can reach one. `score_inputs.sql` builds a `tmp_pop` column
# per category to divide by -- but there is no `emp` column in it, so
# employment divides by `tmp_pop.overall`, exactly as population does
# (findings.md §1.21).
WHOLE_POPULATION_MEMBERS = frozenset({"pop", "emp"})

# `NUMERIC(16, 4)` on `neighborhood_overall_scores`, and the reason
# NFR-PARITY-1's tolerance is 1e-4.
SCORE_DECIMALS = 4

# Mileage totals are only ever surfaced to one decimal place.
MILEAGE_DECIMALS = 1


def derive_category_scores(census_blocks: gpd.GeoDataFrame) -> pd.DataFrame:
    """Combine destination scores into the three category scores.

    Reproduce `category_scores.sql`. Each category is a weighted mean of its
    member scores, with **the divisor built from only the members that are not
    NULL**. A block that can reach no university at all drops that weight from
    the divisor instead of scoring zero for it, so a city without universities
    is not penalised.

    A block with no scored member at all gets NULL, not zero -- the SQL's
    `NULLIF(..., 0)` guards the division.

    Parameters
    ----------
    census_blocks
        Blocks carrying the per-destination `*_score` columns.

    Returns
    -------
    pandas.DataFrame
        Columns `opportunity_score`, `core_services_score`,
        `recreation_score`.
    """
    scores = pd.DataFrame(index=census_blocks.index)
    for category, members in CATEGORY_WEIGHTS.items():
        numerator = pd.Series(0.0, index=census_blocks.index)
        divisor = pd.Series(0.0, index=census_blocks.index)
        for member, weight in members.items():
            value = pd.to_numeric(
                _column(census_blocks, f"{member}_score"),
                errors="coerce",
            )
            present = value.notna()
            numerator += value.fillna(0) * weight
            divisor += present.astype(float) * weight
        scores[f"{category}_score"] = numerator / divisor.replace(0.0, np.nan)
    return scores


def population_weighted_score(
    census_blocks: gpd.GeoDataFrame,
    score_column: str,
    reachable_column: str | None = None,
) -> float:
    """Average one score across the city, weighted by population.

    Reproduce the 16 flagged `score_inputs.sql` rows:
    `SUM(pop20 * score / total_pop)`, where `total_pop` counts only the blocks
    that can reach *anything* in that category. Excluding unreachable blocks
    from the divisor is what stops a category being diluted by blocks it never
    applied to.

    Parameters
    ----------
    census_blocks
        Blocks intersecting the boundary, with `pop20`.
    score_column
        The per-block score to average.
    reachable_column
        The matching `*_high_stress` count deciding which blocks count toward
        the denominator. When omitted the whole population is the denominator,
        as the `people` score does.

    Returns
    -------
    float
        The weighted score, or 0.0 when no population qualifies.
    """
    population = pd.to_numeric(
        _column(census_blocks, "pop20"),
        errors="coerce",
    ).fillna(0)
    score = pd.to_numeric(
        _column(census_blocks, score_column),
        errors="coerce",
    ).fillna(0)

    if reachable_column is None:
        total = float(population.sum())
    else:
        reachable = pd.to_numeric(
            _column(census_blocks, reachable_column),
            errors="coerce",
        ).fillna(0)
        total = float(population[reachable != 0].sum())

    if total == 0:
        return 0.0
    return float((population * score / total).sum())


def _round_half_up(value: float, decimals: int) -> float:
    """Round the way PostgreSQL rounds a `NUMERIC`, not the way Python does.

    Python rounds a tie to the even digit, PostgreSQL rounds it away from
    zero. The rule only bites on an exact tie, which is why the category
    rollups above are computed in decimal: done in binary they miss the tie
    and the rounding rule never gets a chance to disagree (findings.md
    §1.20).

    Parameters
    ----------
    value
        The value to round.
    decimals
        How many decimal places to keep.

    Returns
    -------
    float
        The rounded value; NaN passes through.

    Examples
    --------
    >>> _round_half_up(2.675, 2), round(2.675, 2)
    (2.68, 2.67)
    """
    if value is None or math.isnan(value):
        return math.nan
    quantum = decimal.Decimal(1).scaleb(-decimals)
    rounded = decimal.Decimal(str(value)).quantize(
        quantum, rounding=decimal.ROUND_HALF_UP
    )
    return float(rounded)


def _any_reachable(census_blocks: gpd.GeoDataFrame, member: str) -> bool:
    """Whether any block in the city reaches one of these destinations."""
    counts = pd.to_numeric(
        _column(census_blocks, f"{member}_high_stress"),
        errors="coerce",
    )
    return bool((counts.fillna(0) > 0).any())


def _population_weighted_overall(census_blocks: gpd.GeoDataFrame) -> float:
    """Average the blocks' own overall scores, weighted by population.

    Reproduce `overall_scores.sql`'s final `INSERT`. Note the two different
    filters: the sum runs over blocks with population *and* reach, while the
    divisor is the population of every block with reach, inhabited or not.

    Returns
    -------
    float
        The city score, on a 0-1 scale.
    """
    population = pd.to_numeric(
        _column(census_blocks, "pop20"),
        errors="coerce",
    ).fillna(0)
    reachable = pd.to_numeric(
        _column(census_blocks, "reachable_blocks"),
        errors="coerce",
    ).fillna(0)
    score = pd.to_numeric(
        _column(census_blocks, "overall_score"),
        errors="coerce",
    )

    divisor = float(population[reachable > 0].sum())
    if not divisor:
        return 0.0
    counted = (population > 0) & (reachable > 0)
    return float((score[counted].fillna(0) / 100 * population[counted]).sum() / divisor)


def derive_overall_scores(
    census_blocks: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    ways: gpd.GeoDataFrame,
    weights: config.Score | None = None,
) -> pd.DataFrame:
    """Build the city's headline score table.

    Reproduce `overall_scores.sql`: the 16 population-weighted destination
    scores, the three category rollups, the single overall score, and the
    population and mileage totals.

    The overall score combines the categories using `config.Score`'s weights,
    renormalised over the categories the city actually has -- the same
    "drop it from the divisor" rule the category scores use one level down.

    Parameters
    ----------
    census_blocks
        The retained blocks with every score column derived.
    boundary
        The city boundary; only blocks intersecting it are scored.
    ways
        The rated roads, for the mileage totals.
    weights
        Category weights. Defaults to `config.Score`.

    Returns
    -------
    pandas.DataFrame
        Columns `score_id`, `score_original`, `score_normalized`.
    """
    weights = weights or config.Score()
    scored = census_blocks[
        census_blocks.geometry.intersects(boundary.geometry.union_all())
    ]

    rows: list[tuple[str, float]] = []
    values: dict[str, float] = {}
    for score_id, member in OVERALL_SCORE_ROWS:
        reachable = (
            None if member in WHOLE_POPULATION_MEMBERS else f"{member}_high_stress"
        )
        # `score_original` is `NUMERIC(16, 4)`, so each member row is rounded
        # as it is inserted and the rollups below read the *rounded* value
        # (findings.md §1.18).
        value = _round_half_up(
            population_weighted_score(scored, f"{member}_score", reachable),
            SCORE_DECIMALS,
        )
        values[member] = value
        rows.append((score_id, value))

    # Category rollups, renormalised over the members the city has. "Has" is
    # `EXISTS (block with <member>_high_stress > 0)`, not "scored above zero":
    # a city whose every block scores 0.0 for pharmacies still keeps the
    # pharmacy weight in the divisor, and is penalised for it.
    # In decimal, because the members it reads are `NUMERIC(16, 4)` and the
    # division lands on an exact tie often enough that binary rounding shows.
    category_values: dict[str, float] = {}
    for category, members in CATEGORY_WEIGHTS.items():
        numerator = sum(
            decimal.Decimal(str(values.get(member, 0.0))) * decimal.Decimal(str(weight))
            for member, weight in members.items()
        )
        divisor = sum(
            decimal.Decimal(str(weight))
            for member, weight in members.items()
            if _any_reachable(census_blocks, member)
        )
        category_values[category] = float(numerator / divisor) if divisor else math.nan
    rows.insert(5, ("opportunity", category_values["opportunity"]))
    rows.insert(12, ("core_services", category_values["core_services"]))
    rows.insert(18, ("recreation", category_values["recreation"]))

    # The city's headline score is not a rollup of the category scores at all:
    # it is the population-weighted mean of the *blocks'* own overall scores.
    # Only blocks that reach something count, and the divisor counts them even
    # where nobody lives (findings.md §1.19).
    rows.append(("overall_score", _population_weighted_overall(census_blocks)))

    population_total = float(
        pd.to_numeric(_column(scored, "pop20"), errors="coerce").fillna(0).sum(),
    )
    low, high = total_stress_miles(ways, boundary)
    rows.append(("population_total", population_total))
    rows.append(("total_miles_low_stress", low))
    rows.append(("total_miles_high_stress", high))

    table = pd.DataFrame(rows, columns=["score_id", "score_original"])
    table["score_original"] = [
        _round_half_up(value, SCORE_DECIMALS) for value in table["score_original"]
    ]
    # Scores are surfaced on a 0-100 scale; the totals are not rescaled, and
    # mileage is only ever shown to one decimal place.
    normalized = table["score_original"] * 100
    is_mileage = table["score_id"].str.startswith("total_miles")
    normalized[is_mileage] = table.loc[is_mileage, "score_original"].round(
        MILEAGE_DECIMALS,
    )
    normalized[table["score_id"] == "population_total"] = np.nan
    table["score_normalized"] = [
        _round_half_up(value, SCORE_DECIMALS) for value in normalized
    ]
    return table


def total_stress_miles(
    ways: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
) -> tuple[float, float]:
    """Total the network's low- and high-stress mileage.

    Reproduce the two mileage rows in `overall_scores.sql`. Three details that
    the phrase "total miles" does not suggest:

    1. **Only the part inside the boundary counts.** The SQL measures
       `ST_Length(ST_Intersection(way, boundary))`, so a road running out of
       town contributes only its in-town length -- not its whole length, and
       not nothing.
    2. **Mileage is directional.** A road low-stress in both directions counts
       **twice**; one comfortable direction counts once. The SQL expresses
       this as a `CASE` on `COALESCE(ft, 0) + COALESCE(tf, 0)`: 1+1 = 2 scores
       double, while 1+3 = 4 or a lone 1 score single.
    3. The two totals overlap. A road that is low stress one way and high
       stress the other contributes a mile to *each* total.

    Parameters
    ----------
    ways
        The rated roads, in a projected CRS.
    boundary
        The city boundary, same CRS.

    Returns
    -------
    tuple of float
        `(low_stress_miles, high_stress_miles)`.
    """
    inside = ways.geometry.intersection(boundary.geometry.union_all())
    miles = inside.length / METRES_PER_MILE
    ft = pd.to_numeric(_column(ways, "ft_seg_stress"), errors="coerce").fillna(0)
    tf = pd.to_numeric(_column(ways, "tf_seg_stress"), errors="coerce").fillna(0)
    combined = ft + tf

    def total(rating: int, doubled: int) -> float:
        """Sum the directional miles at one stress rating."""
        eligible = (ft == rating) | (tf == rating)
        multiplier = pd.Series(0.0, index=ways.index)
        # Both directions at this rating.
        multiplier[combined == doubled] = 2.0
        # One direction at this rating, the other rated differently or unrated.
        multiplier[combined == LOW_STRESS + HIGH_STRESS] = 1.0
        multiplier[combined == rating] = 1.0
        return float((miles * multiplier)[eligible].sum())

    return (
        total(LOW_STRESS, LOW_STRESS * 2),
        total(HIGH_STRESS, HIGH_STRESS * 2),
    )


@dataclasses.dataclass(frozen=True)
class StepScore:
    """The piecewise curve used for population and jobs access.

    Population and employment are scored differently from the destination
    categories: instead of counting places, they compare *how much* of the
    reachable population or jobs is reachable comfortably, and map that ratio
    through a curve that rewards early gains steeply.

    Reaching just 3% of the area's population low-stress already earns 0.1,
    and 50% earns 0.8 -- the curve is deliberately front-loaded, because a
    network that connects nobody is far worse than one that connects half.

    Parameters
    ----------
    step1, step2, step3
        Ratio breakpoints.
    score1, score2, score3
        Scores at those breakpoints, interpolated linearly between.
    max_score
        Score at a ratio of 1.
    """

    step1: float = 0.03
    score1: float = 0.1
    step2: float = 0.2
    score2: float = 0.4
    step3: float = 0.5
    score3: float = 0.8
    max_score: float = 1.0


def step_score(
    low_stress: pd.Series,
    high_stress: pd.Series,
    curve: StepScore | None = None,
) -> pd.Series:
    """Score a low-stress share against the piecewise curve.

    Reproduce the `CASE` shared by `access_population.sql` and
    `access_jobs.sql`.

    Parameters
    ----------
    low_stress, high_stress
        Population or jobs reachable low-stress and overall.
    curve
        The breakpoints. Defaults to the values `compute.py` passes.

    Returns
    -------
    pandas.Series
        Score per block, or null where nothing is reachable.
    """
    curve = curve or StepScore()
    low = pd.to_numeric(low_stress, errors="coerce").astype("float64")
    high = pd.to_numeric(high_stress, errors="coerce").astype("float64")

    score = pd.Series(np.nan, index=low.index, dtype="float64")
    reachable = high.notna() & (high > 0)
    ratio = (low / high).where(reachable)

    score[reachable & (low == 0)] = 0.0
    score[reachable & (low == high)] = curve.max_score

    graduated = reachable & (low > 0) & (low != high)
    # Below the first breakpoint the curve rises linearly from the origin.
    below = graduated & (ratio <= curve.step1)
    score[below] = curve.score1 * (ratio[below] / curve.step1)

    for lower, upper, lower_score, upper_score in (
        (curve.step1, curve.step2, curve.score1, curve.score2),
        (curve.step2, curve.step3, curve.score2, curve.score3),
        (curve.step3, 1.0, curve.score3, curve.max_score),
    ):
        band = graduated & (ratio > lower) & (ratio <= upper)
        score[band] = lower_score + (upper_score - lower_score) * (
            (ratio[band] - lower) / (upper - lower)
        )
    return score


def shed_totals(
    census_blocks: gpd.GeoDataFrame,
    connected: pd.DataFrame,
    value_column: str,
) -> pd.DataFrame:
    """Sum a per-block quantity across each block's reachable shed.

    Reproduce `access_population.sql` and `access_jobs.sql`'s first half: for
    each block, total the population (or jobs) of every block it can reach,
    once over the low-stress network and once over the unrestricted one.

    Parameters
    ----------
    census_blocks
        The retained blocks.
    connected
        Block pairs from `network.connected_census_blocks`.
    value_column
        The per-block quantity to total, `pop20` or `jobs`.

    Returns
    -------
    pandas.DataFrame
        Columns `low_stress` and `high_stress`.
    """
    values = (
        pd.to_numeric(_column(census_blocks, value_column), errors="coerce")
        .fillna(0)
        .to_numpy()
    )
    position_of_geoid = {
        str(geoid): position for position, geoid in enumerate(census_blocks["geoid20"])
    }

    low = np.zeros(len(census_blocks), dtype="float64")
    high = np.zeros(len(census_blocks), dtype="float64")
    reached: set[int] = set()
    for source, target, is_low in zip(
        connected["source_blockid20"],
        connected["target_blockid20"],
        connected["low_stress"],
        strict=True,
    ):
        origin = position_of_geoid.get(str(source))
        destination = position_of_geoid.get(str(target))
        if origin is None or destination is None:
            continue
        reached.add(origin)
        high[origin] += values[destination]
        if is_low:
            low[origin] += values[destination]

    # `SUM()` over no rows is NULL, not 0, and a block that is not a source in
    # the pair table -- it sits outside the boundary, or has no roads -- has no
    # rows. The difference carries: a NULL total scores NULL, a zero total
    # scores zero (findings.md §1.16).
    missing = np.array(
        [position not in reached for position in range(len(census_blocks))],
    )
    low[missing] = np.nan
    high[missing] = np.nan

    return pd.DataFrame(
        {"low_stress": low, "high_stress": high},
        index=census_blocks.index,
    )


def block_jobs(census_blocks: gpd.GeoDataFrame, jobs: pd.DataFrame) -> pd.Series:
    """Total the jobs located in each census block.

    Reproduce `census_block_jobs.sql`: sum LODES `S000` over both the `main`
    and `aux` parts, keyed on the block where the job *is* (`w_geocode`), not
    where the worker lives. A block with no LODES rows has zero jobs, not
    NULL.

    Parameters
    ----------
    census_blocks
        The retained blocks.
    jobs
        LODES records from `ingest.load_jobs`.

    Returns
    -------
    pandas.Series
        Job count per block.
    """
    if jobs.empty or "w_geocode" not in jobs.columns:
        return pd.Series(0, index=census_blocks.index, dtype="int64")
    totals = jobs.groupby(jobs["w_geocode"].astype(str))["S000"].sum()
    mapped = census_blocks["geoid20"].astype(str).map(totals)
    return mapped.fillna(0).astype("int64")


# `access_trails.sql`'s weights, which differ from every other category.
TRAILS_ACCESS = config.Access("trails", first=0.7, second=0.2)


def count_reachable_trails(
    census_blocks: gpd.GeoDataFrame,
    ways: gpd.GeoDataFrame,
    paths: gpd.GeoDataFrame,
    low_stress: pd.DataFrame,
    high_stress: pd.DataFrame,
    constraint: config.PathConstraint | None = None,
) -> pd.DataFrame:
    """Count the recreational trails each block can reach.

    Reproduce `access_trails.sql`. Trails are unlike every other category in
    two ways:

    1. A trail is a *path cluster* from `paths.sql`, not an OSM feature, and it
       only counts as recreational if it is both long enough
       (`PathConstraint.min_length`) and spread out enough
       (`min_bbox`). The bounding-box test excludes a long path that merely
       loops in a small area -- a park's internal footpath network is not a
       trail to ride out on.
    2. Reachability is measured at the **road** level, not block-to-block: a
       block reaches a trail if it can reach any road belonging to it.

    Parameters
    ----------
    census_blocks
        The retained blocks.
    ways
        The roads, carrying the `path_id` assigned by `features.cluster_paths`.
    paths
        The path table, with `path_length` and `bbox_length`.
    low_stress, high_stress
        Road-level reachability from `network.reachable_roads`.
    constraint
        Length and span thresholds. Defaults to `config.PathConstraint`.

    Returns
    -------
    pandas.DataFrame
        Columns `low_stress` and `high_stress`, indexed like `census_blocks`.
    """
    constraint = constraint or config.PathConstraint()
    counts = pd.DataFrame(
        {
            "low_stress": pd.Series(0, index=census_blocks.index, dtype="int64"),
            "high_stress": pd.Series(0, index=census_blocks.index, dtype="int64"),
        },
    )
    if paths.empty:
        return counts

    qualifying = paths[
        (paths["path_length"] > constraint.min_length)
        & (paths["bbox_length"] > constraint.min_bbox)
    ]
    if qualifying.empty:
        return counts

    # Which trail each road belongs to, for the trails that qualify.
    wanted = set(qualifying["path_id"])
    path_of_road = {
        road: int(path)
        for road, path in zip(ways["road_id"], _column(ways, "path_id"), strict=True)
        if not pd.isna(path) and int(path) in wanted
    }
    if not path_of_road:
        return counts

    position_of_geoid = {
        str(geoid): position for position, geoid in enumerate(census_blocks["geoid20"])
    }

    def tally(shed: pd.DataFrame) -> np.ndarray:
        """Count distinct qualifying trails reached per block."""
        reached: dict[int, set[int]] = {}
        for block, road in zip(shed["source_block"], shed["target_road"], strict=True):
            trail = path_of_road.get(road)
            if trail is None:
                continue
            position = position_of_geoid.get(str(block))
            if position is None:
                continue
            reached.setdefault(position, set()).add(trail)
        totals = np.zeros(len(census_blocks), dtype="int64")
        for position, trails in reached.items():
            totals[position] = len(trails)
        return totals

    counts["low_stress"] = tally(low_stress)
    counts["high_stress"] = tally(high_stress)
    return counts


# Members whose weight sits in `access_overall.sql`'s divisor whether or not
# the block reaches one. Employment is the only one: there is no
# `emp_high_stress > 0` test to key it on, just the bare `0.35`.
UNCONDITIONAL_OVERALL_MEMBERS = frozenset({"emp"})

# Which `*_high_stress` counts decide whether a category applies to a block,
# for `access_overall.sql`'s per-block renormalisation.
OVERALL_CATEGORY_MEMBERS = {
    "people": (),
    "opportunity": ("schools", "colleges", "universities"),
    "core_services": (
        "doctors",
        "dentists",
        "hospitals",
        "pharmacies",
        "supermarkets",
        "social_services",
    ),
    "retail": ("retail",),
    "recreation": ("parks", "trails", "community_centers"),
    "transit": ("transit",),
}


def derive_block_overall_score(
    census_blocks: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    weights: config.Score | None = None,
) -> pd.Series:
    """Score each census block out of 100.

    Reproduce `access_overall.sql`, the **per-block** score exported on
    `census_blocks`. It is not the same computation as the city's headline
    `overall_score`, which averages the per-category city scores: this one
    combines each block's own category scores.

    The renormalisation also differs from `category_scores.sql`'s. Here a
    category counts only when the block can reach *something* in it -- keyed
    on the `*_high_stress` counts, not on the score being non-NULL -- so a
    block that can reach no shop at all drops `retail` from its divisor
    instead of scoring zero for it.

    Parameters
    ----------
    census_blocks
        Blocks with every destination score and reachability count derived.
    boundary
        The city boundary; blocks outside it are not scored.
    weights
        Category weights. Defaults to `config.Score`.

    Returns
    -------
    pandas.Series
        Score per block, out of `weights.total`, or null outside the boundary.
    """
    weights = weights or config.Score()
    weight_of = {
        "people": weights.people,
        "opportunity": weights.opportunity,
        "core_services": weights.core_services,
        "retail": weights.retail,
        "recreation": weights.recreation,
        "transit": weights.transit,
    }

    def subscore(category: str) -> pd.Series:
        """Weight a category's members the way `access_overall.sql` does.

        Not the same renormalisation as `category_scores.sql`: a member counts
        here when the block can *reach* one, keyed on its `*_high_stress`
        count, and employment's 0.35 is in the divisor unconditionally -- even
        outside the US, where there is no LODES data and `emp_score` is NULL
        (findings.md §1.17). The two rules disagree exactly when a member's
        score is NULL but its count is not, so the per-block `overall_score`
        cannot be built from the `*_category_score` columns.
        """
        numerator = pd.Series(0.0, index=census_blocks.index)
        divisor = pd.Series(0.0, index=census_blocks.index)
        for member, weight in CATEGORY_WEIGHTS[category].items():
            numerator += weight * pd.to_numeric(
                _column(census_blocks, f"{member}_score"),
                errors="coerce",
            ).fillna(0)
            counts = (
                pd.Series(data=True, index=census_blocks.index)
                if member in UNCONDITIONAL_OVERALL_MEMBERS
                else pd.to_numeric(
                    _column(census_blocks, f"{member}_high_stress"),
                    errors="coerce",
                ).fillna(0)
                > 0
            )
            divisor += weight * counts.astype(float)
        return numerator / divisor.replace(0.0, np.nan)

    def reachable(members: tuple[str, ...]) -> pd.Series:
        """Whether the block reaches anything in the category."""
        if not members:
            return pd.Series(data=True, index=census_blocks.index)
        total = pd.Series(0.0, index=census_blocks.index)
        for member in members:
            total += pd.to_numeric(
                _column(census_blocks, f"{member}_high_stress"),
                errors="coerce",
            ).fillna(0)
        return total > 0

    numerator = pd.Series(0.0, index=census_blocks.index)
    divisor = pd.Series(0.0, index=census_blocks.index)
    for category, members in OVERALL_CATEGORY_MEMBERS.items():
        weight = weight_of[category]
        applies = reachable(members)
        if category == "people":
            value = pd.to_numeric(
                _column(census_blocks, "pop_score"),
                errors="coerce",
            ).fillna(0)
        elif category in CATEGORY_WEIGHTS:
            value = subscore(category).fillna(0)
        else:
            value = pd.to_numeric(
                _column(census_blocks, f"{category}_score"),
                errors="coerce",
            ).fillna(0)
        numerator += weight * value.where(applies, 0.0)
        divisor += weight * applies.astype(float)

    score = weights.total * numerator / divisor.replace(0.0, np.nan)
    inside = census_blocks.geometry.intersects(boundary.geometry.union_all())
    return score.where(inside)
