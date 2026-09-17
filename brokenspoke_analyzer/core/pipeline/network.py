"""
Build the routable network and compute per-census-block reachability.

Replace `connectivity/build_network.sql`, `block_verts.sql`, and the
`reachable_roads_*` scripts, which used pgRouting's `PGR_DRIVINGDISTANCE`.

The graph is **turn-expanded**: a vertex is a *road*, positioned at its
midpoint, and an edge is a permitted *turn* from one road to another at a
shared intersection. It is not a graph of road segments joined at nodes.
Traversal cost is half of each road's length, so a path's cost is the distance
between the two roads' midpoints -- which is why a search seeded at a block's
own roads starts at zero.

Task 1's benchmark (design.md §3.3) chose `networkx` over `scipy.sparse`: the
2680 m cutoff bounds every search to a local neighbourhood, so the whole stage
runs in seconds and the engine's raw speed does not matter.
"""

import math
import typing

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from loguru import logger

from brokenspoke_analyzer.core.pipeline import errors
from brokenspoke_analyzer.core.pipeline.features import _text

# `nb_max_trip_distance`, from cli/common.py's DEFAULT_MAX_TRIP_DISTANCE. Every
# reachability search stops here.
DEFAULT_MAX_TRIP_DISTANCE = 2680

# A link is low stress only when its rating is exactly this. A NULL rating
# fails the test but still appears in the unfiltered high-stress graph.
LOW_STRESS = 1

# `greatest()` returns NULL only when every argument is NULL. Represent that
# with a sentinel that can never equal LOW_STRESS.
NULL_STRESS = -1

FULL_CIRCLE_DEGREES = 360

# `BlockRoad` from `core/pipeline/config.py`: how far around a block to look
# for its roads, and how much of a road must lie inside to count.
BLOCK_ROAD_BUFFER = 15
BLOCK_ROAD_MIN_LENGTH = 30

# Margin applied when using a polygon buffer to pre-filter candidate pairs
# before an exact distance test. A buffer inscribes the circle it stands in
# for, so without a margin it silently drops pairs near the boundary.
BUFFER_OVERCAPTURE = 1.05


def _greatest(*values: typing.Any) -> int:
    """Return the greatest non-NULL value, as PostgreSQL's `greatest()` does.

    Parameters
    ----------
    *values
        Candidate values; NaN stands in for SQL NULL.

    Returns
    -------
    int
        The largest non-NULL value, or :data:`NULL_STRESS` if all are NULL.

    Examples
    --------
    >>> _greatest(1, 3, 2)
    3
    >>> _greatest(1, float("nan"), 2)
    2
    >>> _greatest(float("nan"), float("nan"))
    -1
    """
    present = [int(v) for v in values if not pd.isna(v)]
    return max(present) if present else NULL_STRESS


def _round_half_even(value: float) -> int:
    """Round half to even, as PostgreSQL does when storing a FLOAT in an INT.

    `build_network.sql` declares the azimuths and road lengths `INTEGER` and
    fills them from `degrees(ST_Azimuth(...))` and `ST_Length(...)`, both
    FLOAT, so the cast goes through C's `rint()` (findings.md §1.1).

    Examples
    --------
    >>> _round_half_even(2.5), _round_half_even(3.5), _round_half_even(2.4)
    (2, 4, 2)
    """
    return round(value)


def _azimuth(origin: tuple[float, float], target: tuple[float, float]) -> float:
    """Return the north-based clockwise azimuth in degrees, like `ST_Azimuth`.

    Parameters
    ----------
    origin
        Origin point.
    target
        Target point.

    Returns
    -------
    float
        Azimuth in degrees, in `[0, 360)`.

    Examples
    --------
    >>> _azimuth((0.0, 0.0), (0.0, 1.0))
    0.0
    >>> _azimuth((0.0, 0.0), (1.0, 0.0))
    90.0
    """
    return (
        math.degrees(
            math.atan2(target[0] - origin[0], target[1] - origin[1]),
        )
        % FULL_CIRCLE_DEGREES
    )


def _road_records(
    ways: gpd.GeoDataFrame,
) -> tuple[
    dict[typing.Any, dict[str, typing.Any]],
    dict[typing.Any, list[typing.Any]],
    dict[typing.Any, list[typing.Any]],
]:
    """Index the roads by the intersections they may depart into and enter from.

    Collapses `build_network.sql`'s nine `INSERT` branches into three "may
    depart" cases crossed with three "may enter" cases, keyed on `one_way`.

    Parameters
    ----------
    ways
        The rated roads, in a projected CRS.

    Returns
    -------
    tuple
        Per-road geometry and stress, roads departing into each intersection,
        and roads enterable from each intersection.
    """
    roads = ways.reset_index(drop=True)
    geometry = roads.geometry
    midpoints = geometry.interpolate(0.5, normalized=True)
    lengths = geometry.length.to_numpy()
    one_way = _text(roads, "one_way")

    info: dict[typing.Any, dict[str, typing.Any]] = {}
    departs: dict[typing.Any, list[typing.Any]] = {}
    enters: dict[typing.Any, list[typing.Any]] = {}
    for position in range(len(roads)):
        int_from = roads["intersection_from"].iloc[position]
        int_to = roads["intersection_to"].iloc[position]
        if pd.isna(int_from) or pd.isna(int_to):
            continue
        line = geometry.iloc[position]
        midpoint = midpoints.iloc[position]
        start, end = line.coords[0], line.coords[-1]
        road_id = roads["road_id"].iloc[position]
        info[road_id] = {
            "int_from": int_from,
            "int_to": int_to,
            "length": float(lengths[position]),
            "mid": (midpoint.x, midpoint.y),
            "start": (start[0], start[1]),
            "end": (end[0], end[1]),
            "ft_seg": roads["ft_seg_stress"].iloc[position]
            if "ft_seg_stress" in roads.columns
            else pd.NA,
            "tf_seg": roads["tf_seg_stress"].iloc[position]
            if "tf_seg_stress" in roads.columns
            else pd.NA,
            "ft_int": roads["ft_int_stress"].iloc[position]
            if "ft_int_stress" in roads.columns
            else pd.NA,
            "tf_int": roads["tf_int_stress"].iloc[position]
            if "tf_int_stress" in roads.columns
            else pd.NA,
        }
        direction = one_way.iloc[position]
        direction = None if pd.isna(direction) else str(direction)
        if direction is None:
            depart_at, enter_at = {int_from, int_to}, {int_from, int_to}
        elif direction == "ft":
            depart_at, enter_at = {int_to}, {int_from}
        else:
            depart_at, enter_at = {int_from}, {int_to}
        for node in depart_at:
            departs.setdefault(node, []).append(road_id)
        for node in enter_at:
            enters.setdefault(node, []).append(road_id)
    return info, departs, enters


def _turn_order_key(
    source: dict[str, typing.Any],
    target: dict[str, typing.Any],
    int_id: typing.Any,
) -> tuple[tuple[int, float], int]:
    """Return the right-turn ordering key and turn angle for one turn.

    Reproduce `build_network.sql`'s `ORDER BY sin(turn) > 0 DESC, cos(turn)`.

    Parameters
    ----------
    source
        The departing road's record.
    target
        The entered road's record.
    int_id
        The shared intersection.

    Returns
    -------
    tuple
        The order key and the turn angle in degrees.
    """
    source_dir = "ft" if int_id == source["int_to"] else "tf"
    tip = source["start"] if source_dir == "tf" else source["end"]
    # Each azimuth lands in an INTEGER column before the subtraction, so it
    # is rounded on its own, not the difference.
    source_azimuth = _round_half_even(_azimuth(source["mid"], tip))

    target_dir = "ft" if int_id == target["int_to"] else "tf"
    tail = target["start"] if target_dir == "tf" else target["end"]
    target_azimuth = _round_half_even(_azimuth(tail, target["mid"]))

    angle = (
        target_azimuth - source_azimuth + FULL_CIRCLE_DEGREES
    ) % FULL_CIRCLE_DEGREES
    radians = math.radians(angle)
    positive = math.sin(radians) > 0
    tie = math.cos(radians) if positive else -math.cos(radians)
    return (0 if positive else 1, tie), angle


def build_network(ways: gpd.GeoDataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the turn-expanded network from the rated roads.

    Reproduce `build_network.sql`. Its nine `INSERT` branches collapse to
    three "may depart into this intersection" cases crossed with three "may be
    entered from it" cases, keyed on the road's `one_way`:

    - depart: two-way at either end; `ft` at its `to` end; `tf` at its `from`.
    - enter: two-way at either end; `ft` at its `from` end; `tf` at its `to`.

    Parameters
    ----------
    ways
        The rated roads, in a projected CRS.

    Returns
    -------
    tuple of pandas.DataFrame
        The vertices (one row per road) and the links (one row per turn).

    Raises
    ------
    ReachabilityError
        If the roads are not in a projected CRS, which would make every length
        a number of degrees and round every cost to zero.
    """
    if ways.crs is None or ways.crs.is_geographic:
        raise errors.ReachabilityError(
            "the road network must be in a projected CRS; "
            f"got {ways.crs}. Lengths in degrees round every link cost to 0.",
        )

    roads = ways.reset_index(drop=True)
    vertices = pd.DataFrame(
        {
            "vert_id": range(len(roads)),
            "road_id": roads["road_id"].to_numpy(),
        },
    )
    vert_of_road = dict(zip(roads["road_id"], vertices["vert_id"], strict=True))
    info, departs, enters = _road_records(roads)
    links = _build_links(info, departs, enters, vert_of_road)
    logger.info(
        f"network: {len(vertices):,} vertices, {len(links):,} links",
    )
    return vertices, links


def _link_cost(source_length: float, target_length: float) -> int:
    """Return a turn's cost: half of each road, as `build_network.sql` computes it.

    Two SQL details make this different from the obvious
    `round((a + b) / 2)`, and both lower the result:

    1. `source_road_length` and `target_road_length` are **INTEGER** columns,
       so each `ST_Length` is rounded before it is ever used.
    2. `(source_road_length + target_road_length) / 2` is therefore **integer
       division**, which truncates. The outer `round()` then does nothing.

    Computing this at full precision instead inflates every link by up to half
    a unit. That is invisible on one link and compounds along a path: it made
    reachability costs about 0.8% high, which pushed pairs sitting near the
    2680 m cutoff out of range entirely.

    Parameters
    ----------
    source_length, target_length
        Road lengths in the projected CRS's units.

    Returns
    -------
    int
        The link cost.

    Examples
    --------
    >>> _link_cost(10.4, 11.4)
    10
    >>> _link_cost(11.0, 12.0)
    11
    """
    return (_round_half_even(source_length) + _round_half_even(target_length)) // 2


def _build_links(
    info: dict[typing.Any, dict[str, typing.Any]],
    departs: dict[typing.Any, list[typing.Any]],
    enters: dict[typing.Any, list[typing.Any]],
    vert_of_road: dict[typing.Any, int],
) -> pd.DataFrame:
    """Assemble the turn links, with cost, stress, and the right-turn rule.

    Parameters
    ----------
    info
        Per-road geometry and stress, keyed by `road_id`.
    departs
        Roads that may depart into each intersection.
    enters
        Roads that may be entered from each intersection.
    vert_of_road
        `road_id` to vertex index.

    Returns
    -------
    pandas.DataFrame
        The links, with `source_vert`, `target_vert`, `link_cost`,
        `link_stress`.
    """
    sources: list[int] = []
    targets: list[int] = []
    costs: list[int] = []
    stresses: list[int] = []
    source_stresses: list[typing.Any] = []
    target_stresses: list[typing.Any] = []
    # (source road, intersection) -> [(order key, link position)], for the
    # right-turn rule below.
    turns: dict[tuple[typing.Any, typing.Any], list[tuple[tuple[int, float], int]]] = {}

    for int_id, outgoing in departs.items():
        incoming = enters.get(int_id)
        if not incoming:
            continue
        for source_road in outgoing:
            source = info[source_road]
            source_dir = "ft" if int_id == source["int_to"] else "tf"
            source_stress = source["ft_seg"] if source_dir == "ft" else source["tf_seg"]
            int_stress = source["ft_int"] if source_dir == "ft" else source["tf_int"]

            for target_road in incoming:
                if source_road == target_road:
                    continue
                target = info[target_road]
                target_dir = "ft" if int_id == target["int_to"] else "tf"
                order_key, _ = _turn_order_key(source, target, int_id)
                # Entering the target at its `to` end means travelling it `tf`
                # -- the reverse of the source convention.
                target_stress = (
                    target["tf_seg"] if target_dir == "ft" else target["ft_seg"]
                )

                position = len(sources)
                sources.append(vert_of_road[source_road])
                targets.append(vert_of_road[target_road])
                costs.append(_link_cost(source["length"], target["length"]))
                stresses.append(_greatest(source_stress, int_stress, target_stress))
                source_stresses.append(source_stress)
                target_stresses.append(target_stress)
                turns.setdefault((source_road, int_id), []).append(
                    (order_key, position),
                )

    stress_values = np.asarray(stresses, dtype=np.int64)
    # The right-turn rule: per (source road, intersection) exactly one link is
    # marked `int_crossing = FALSE`, giving it `int_stress = 1`. The SQL picks
    # it with `LIMIT 1` over an ORDER BY that does not break ties, so where two
    # turns share an order key Postgres' choice is arbitrary; `min` takes the
    # first. See tasks.md 6.3 -- the tie rate is measured, not assumed.
    for group in turns.values():
        _, winner = min(group, key=lambda item: item[0])
        stress_values[winner] = _greatest(
            source_stresses[winner],
            LOW_STRESS,
            target_stresses[winner],
        )

    return pd.DataFrame(
        {
            "source_vert": np.asarray(sources, dtype=np.int64),
            "target_vert": np.asarray(targets, dtype=np.int64),
            "link_cost": np.asarray(costs, dtype=np.int64),
            "link_stress": stress_values,
        },
    )


def count_turn_ties(ways: gpd.GeoDataFrame) -> tuple[int, int]:
    """Count how often the right-turn tie-break is ambiguous.

    tasks.md 6.3 requires this measured rather than assumed: where two turns
    from the same road at the same intersection share an order key, the SQL's
    `LIMIT 1` picks arbitrarily and exact parity is impossible in principle.

    Parameters
    ----------
    ways
        The rated roads.

    Returns
    -------
    tuple of int
        `(groups whose best key is tied, total groups)`.
    """
    info, departs, enters = _road_records(ways)
    tied = total = 0
    for int_id, outgoing in departs.items():
        incoming = enters.get(int_id)
        if not incoming:
            continue
        for source_road in outgoing:
            keys = [
                _turn_order_key(info[source_road], info[target_road], int_id)[0]
                for target_road in incoming
                if target_road != source_road
            ]
            if not keys:
                continue
            total += 1
            if keys.count(min(keys)) > 1:
                tied += 1
    return tied, total


def build_graph(links: pd.DataFrame, *, low_stress_only: bool) -> nx.DiGraph:
    """Build the searchable graph for one stress subgraph.

    Parameters
    ----------
    links
        The turn links from :func:`build_network`.
    low_stress_only
        Keep only `link_stress = 1`, per
        `reachable_roads_low_stress_calc.sql`. The high-stress query applies
        no filter at all, so a NULL-stress link survives there.

    Returns
    -------
    networkx.DiGraph
        Directed graph over vertex indices, weighted by `link_cost`.
    """
    selected = links[links["link_stress"] == LOW_STRESS] if low_stress_only else links
    graph = nx.DiGraph()
    # Parallel turns between the same pair collapse to the cheapest.
    for source, target, cost in zip(
        selected["source_vert"],
        selected["target_vert"],
        selected["link_cost"],
        strict=True,
    ):
        existing = graph.get_edge_data(int(source), int(target))
        weight = float(cost)
        if existing is None or weight < existing["weight"]:
            graph.add_edge(int(source), int(target), weight=weight)
    return graph


def block_seed_vertices(
    census_blocks: gpd.GeoDataFrame,
    vertices: pd.DataFrame,
    ways: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
) -> dict[str, np.ndarray]:
    """Map each census block to the vertices its search starts from.

    Reproduce `block_verts.sql`: the vertices of the roads listed in the
    block's `road_ids`, restricted to roads that intersect the boundary.

    Parameters
    ----------
    census_blocks
        The retained census blocks, carrying `road_ids`.
    vertices
        The network vertices.
    ways
        The roads, for the boundary restriction.
    boundary
        The city boundary, same CRS.

    Returns
    -------
    dict
        `geoid20` to seed vertex indices, for blocks with at least one seed.
    """
    boundary_geometry = boundary.geometry.union_all()
    on_boundary = set(
        ways.loc[ways.geometry.intersects(boundary_geometry), "road_id"],
    )
    vert_of_road = dict(zip(vertices["road_id"], vertices["vert_id"], strict=True))

    seeds: dict[str, np.ndarray] = {}
    for geoid, road_ids in zip(
        census_blocks["geoid20"],
        census_blocks["road_ids"],
        strict=True,
    ):
        if road_ids is None or (isinstance(road_ids, float) and pd.isna(road_ids)):
            continue
        found = {
            vert_of_road[road]
            for road in road_ids
            if road in vert_of_road and road in on_boundary
        }
        if found:
            seeds[str(geoid)] = np.asarray(sorted(found), dtype=np.int64)
    logger.debug(f"{len(seeds):,} blocks have seed vertices")
    return seeds


def reachable_roads(
    graph: nx.DiGraph,
    seeds: dict[str, np.ndarray],
    vertices: pd.DataFrame,
    max_trip_distance: int = DEFAULT_MAX_TRIP_DISTANCE,
) -> pd.DataFrame:
    """Compute which roads each census block can reach.

    Reproduce `reachable_roads_{low,high}_stress_calc.sql`. The SQL seeds each
    search from a synthetic node joined to every one of the block's vertices
    at zero cost, which is exactly multi-source Dijkstra -- not a
    single-source search from one vertex.

    Parameters
    ----------
    graph
        One stress subgraph, from :func:`build_graph`.
    seeds
        Per-block seed vertices.
    vertices
        The network vertices, to map results back to `road_id`.
    max_trip_distance
        Search cutoff, `nb_max_trip_distance`.

    Returns
    -------
    pandas.DataFrame
        Columns `source_block`, `target_road`, `total_cost`.
    """
    road_of_vert = dict(zip(vertices["vert_id"], vertices["road_id"], strict=True))
    blocks: list[str] = []
    roads: list[typing.Any] = []
    costs: list[float] = []

    present = set(graph.nodes)
    for geoid, seed in seeds.items():
        wanted = [int(vert) for vert in seed]
        usable = [vert for vert in wanted if vert in present]
        distances: dict[int, float] = (
            nx.multi_source_dijkstra_path_length(
                graph,
                set(usable),
                cutoff=max_trip_distance,
                weight="weight",
            )
            if usable
            else {}
        )
        # The synthetic source edge the SQL unions in reaches *every* seed
        # vertex at zero cost, including one the stress subgraph has no link
        # for. So a block always reaches its own roads, even where none of
        # them is low-stress -- which is what makes two blocks sharing a road
        # cost 0 apart rather than a detour (findings.md §1.14).
        for vert in wanted:
            if vert in road_of_vert:
                distances.setdefault(vert, 0.0)
        for vert, cost in distances.items():
            blocks.append(geoid)
            roads.append(road_of_vert[vert])
            costs.append(cost)

    return pd.DataFrame(
        {
            "source_block": blocks,
            "target_road": roads,
            "total_cost": costs,
        },
    )


def compute_reachability(
    ways: gpd.GeoDataFrame,
    census_blocks: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    max_trip_distance: int = DEFAULT_MAX_TRIP_DISTANCE,
) -> dict[str, typing.Any]:
    """Build the network and compute both reachability sheds.

    Kept synchronous and single-process on purpose. The SQL splits this work
    eight ways, but that reflects in-database `PGR_DRIVINGDISTANCE` cost, not
    an inherent one: task 1 measured the whole stage at about five seconds for
    the heaviest corpus city, because the distance cutoff bounds every search
    to a local neighbourhood (design.md §6).

    Parameters
    ----------
    ways
        The rated roads, in a projected CRS.
    census_blocks
        The retained census blocks.
    boundary
        The city boundary.
    max_trip_distance
        Search cutoff.

    Returns
    -------
    dict
        `vertices`, `links`, `low_stress`, and `high_stress`.
    """
    vertices, links = build_network(ways)
    seeds = block_seed_vertices(census_blocks, vertices, ways, boundary)

    sheds = {}
    for name, low_only in (("low_stress", True), ("high_stress", False)):
        graph = build_graph(links, low_stress_only=low_only)
        sheds[name] = reachable_roads(graph, seeds, vertices, max_trip_distance)
        logger.info(f"{name}: {len(sheds[name]):,} (block, road) pairs reachable")

    return {"vertices": vertices, "links": links, **sheds}


def assign_block_roads(
    census_blocks: gpd.GeoDataFrame,
    ways: gpd.GeoDataFrame,
    buffer: int = BLOCK_ROAD_BUFFER,
    min_length: int = BLOCK_ROAD_MIN_LENGTH,
) -> pd.Series:
    """Associate each census block with the roads fronting onto it.

    Reproduce `census_blocks.sql`'s `road_ids` update: buffer the block by 15 m
    and keep every road either wholly inside that buffer or overlapping it by
    more than 30 m. The length test stops a road that merely clips a corner
    from counting as the block's own.

    These roads are where a block's reachability search starts, so a block with
    no roads is unreachable and scores nothing.

    Parameters
    ----------
    census_blocks
        The retained blocks, in a projected CRS.
    ways
        The roads, same CRS.
    buffer
        Buffer distance around the block, `BlockRoad.buffer`.
    min_length
        Minimum overlap for a road that is not wholly inside,
        `BlockRoad.min_length`.

    Returns
    -------
    pandas.Series
        A list of `road_id` per block, aligned to `census_blocks`.
    """
    buffered = gpd.GeoDataFrame(
        # The buffer polygon *is* the test here, so its shape has to be the
        # shape PostGIS produced: `ST_Buffer` defaults to 8 segments per
        # quadrant, geopandas to 16 (findings.md §2.6). The finer polygon
        # reaches marginally further, which flips roads that graze the 15 m
        # edge in or out of a block -- enough to move a city score.
        {
            "geometry": census_blocks.geometry.buffer(
                buffer, resolution=POSTGIS_QUAD_SEGS
            )
        },
        crs=census_blocks.crs,
    )  # ty:ignore[no-matching-overload]
    candidates = gpd.sjoin(
        ways[["road_id", "geometry"]],
        buffered,
        how="inner",
        predicate="intersects",
    )

    assigned: dict[int, list[typing.Any]] = {
        position: [] for position in range(len(census_blocks))
    }
    block_geometries = buffered.geometry.to_numpy()
    for road_position, block_position in zip(
        candidates.index,
        candidates["index_right"],
        strict=True,
    ):
        road = ways.geometry.loc[road_position]
        block = block_geometries[block_position]
        if block.contains(road) or block.intersection(road).length > min_length:
            assigned[int(block_position)].append(ways["road_id"].loc[road_position])

    logger.debug(
        f"block roads: {sum(bool(v) for v in assigned.values()):,}"
        f"/{len(census_blocks):,} blocks have roads",
    )
    return pd.Series(
        [assigned[position] for position in range(len(census_blocks))],
        index=census_blocks.index,
    )


# `ST_Buffer`'s default segments-per-quadrant. Match it wherever the buffer
# polygon itself is the answer rather than a pre-filter.
POSTGIS_QUAD_SEGS = 8

# A low-stress route may be at most this much longer than the unrestricted one
# before the pair stops counting as low-stress connected.
LOW_STRESS_DETOUR_RATIO = 1.25


def _is_low_stress_connected(
    low_cost: float | None,
    high_cost: float | None,
    *,
    shares_road: bool,
) -> bool:
    """Decide whether a block pair counts as low-stress connected.

    Reproduce `connected_census_blocks.sql`'s `low_stress` update. Blocks that
    share a road are connected outright. Otherwise a low-stress route must
    exist and be no more than 25% longer than the unrestricted one -- a
    low-stress route that exists but detours badly is not real access.

    Parameters
    ----------
    low_cost
        Cheapest low-stress route, or None if there is none.
    high_cost
        Cheapest unrestricted route, or None.
    shares_road
        Whether the two blocks front onto a common road.

    Returns
    -------
    bool
        Whether the pair is low-stress connected.

    Examples
    --------
    >>> _is_low_stress_connected(100.0, 90.0, shares_road=False)
    True
    >>> _is_low_stress_connected(200.0, 90.0, shares_road=False)
    False
    >>> _is_low_stress_connected(None, 90.0, shares_road=True)
    True
    """
    if shares_road:
        return True
    if low_cost is None:
        return False
    # A zero or missing unrestricted cost cannot form a ratio; the SQL treats
    # that as connected rather than dividing by zero.
    if not high_cost:
        return True
    return low_cost / high_cost <= LOW_STRESS_DETOUR_RATIO


def _roads_to_blocks(road_sets: list[set]) -> dict[typing.Any, list[int]]:
    """Invert the block-to-roads mapping, so a reached road names its blocks."""
    block_of_road: dict[typing.Any, list[int]] = {}
    for index, roads in enumerate(road_sets):
        for road in roads:
            block_of_road.setdefault(road, []).append(index)
    return block_of_road


def _nearby_block_pairs(
    blocks: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    max_trip_distance: int,
) -> dict[int, set[int]]:
    """Pair each in-boundary block with the blocks within trip distance.

    Reproduce the SQL's `ST_Intersects(source, boundary) AND ST_DWithin(source,
    target, :nb_max_trip_distance)` join.
    """
    on_boundary = blocks.geometry.intersects(boundary.geometry.union_all()).to_numpy()
    # A polygon buffer *inscribes* the circle, so buffering by exactly the trip
    # distance quietly drops pairs sitting near it. Over-capture with a margin,
    # then apply the exact distance test `ST_DWithin` performs.
    candidates = gpd.sjoin(
        blocks[["geometry"]],
        gpd.GeoDataFrame(
            {
                "geometry": blocks.geometry.buffer(
                    max_trip_distance * BUFFER_OVERCAPTURE,
                ),
            },
            crs=blocks.crs,
        ),  # ty:ignore[no-matching-overload]
        how="inner",
        predicate="intersects",
    )
    geometries = blocks.geometry.to_numpy()
    allowed: dict[int, set[int]] = {}
    for raw_source, raw_target in zip(
        candidates.index,
        candidates["index_right"],
        strict=True,
    ):
        source, target = int(raw_source), int(raw_target)
        if not on_boundary[source]:
            continue
        if geometries[source].distance(geometries[target]) <= max_trip_distance:
            allowed.setdefault(source, set()).add(target)
    return allowed


def _cheapest_block_costs(
    shed: pd.DataFrame,
    index_of_geoid: dict[str, int],
    block_of_road: dict[typing.Any, list[int]],
) -> dict[tuple[int, int], float]:
    """Reduce road-level reachability to the cheapest cost per block pair."""
    best: dict[tuple[int, int], float] = {}
    for block, road, cost in zip(
        shed["source_block"],
        shed["target_road"],
        shed["total_cost"],
        strict=True,
    ):
        source = index_of_geoid.get(str(block))
        if source is None:
            continue
        for target in block_of_road.get(road, ()):
            key = (source, target)
            if key not in best or cost < best[key]:
                best[key] = cost
    return best


def connected_census_blocks(
    census_blocks: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    low_stress: pd.DataFrame,
    high_stress: pd.DataFrame,
    max_trip_distance: int = DEFAULT_MAX_TRIP_DISTANCE,
) -> pd.DataFrame:
    """Pair up census blocks that can reach each other.

    Reproduce `connected_census_blocks.sql`. A pair is kept when the source
    block can reach any of the target's roads on either network, and is marked
    *low-stress connected* when either the two blocks share a road outright or
    the low-stress route is no more than 25% longer than the unrestricted one.

    That ratio is the heart of the BNA: a low-stress route that exists but
    takes a large detour does not count as real access.

    Parameters
    ----------
    census_blocks
        The retained blocks, carrying `road_ids`.
    boundary
        The city boundary, same CRS.
    low_stress, high_stress
        Reachability from :func:`reachable_roads`.
    max_trip_distance
        Only blocks within this distance of each other are paired.

    Returns
    -------
    pandas.DataFrame
        Columns `source_blockid20`, `target_blockid20`, `low_stress`,
        `low_stress_cost`, `high_stress`, `high_stress_cost`.
    """
    blocks = census_blocks.reset_index(drop=True)
    geoids = blocks["geoid20"].astype(str).to_numpy()
    road_sets = [
        set() if road_ids is None else set(road_ids) for road_ids in blocks["road_ids"]
    ]
    block_of_road = _roads_to_blocks(road_sets)
    allowed = _nearby_block_pairs(blocks, boundary, max_trip_distance)

    index_of_geoid = {geoid: position for position, geoid in enumerate(geoids)}
    low_best = _cheapest_block_costs(low_stress, index_of_geoid, block_of_road)
    high_best = _cheapest_block_costs(high_stress, index_of_geoid, block_of_road)

    rows = []
    for source, targets in allowed.items():
        for target in targets:
            low_cost = low_best.get((source, target))
            high_cost = high_best.get((source, target))
            if low_cost is None and high_cost is None:
                continue
            connected = _is_low_stress_connected(
                low_cost,
                high_cost,
                shares_road=bool(road_sets[source] & road_sets[target]),
            )
            rows.append(
                {
                    "source_blockid20": geoids[source],
                    "target_blockid20": geoids[target],
                    "low_stress": connected,
                    "low_stress_cost": low_cost,
                    "high_stress": True,
                    "high_stress_cost": high_cost,
                },
            )

    pairs = pd.DataFrame(rows)
    logger.info(f"connected blocks: {len(pairs):,} pairs")
    return pairs
