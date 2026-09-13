"""Test the `network` pipeline stage.

Cover the turn-expanded graph build, the reachability search, and the block
pairing. Synthetic graphs with hand-computed answers throughout.
"""

import math

import geopandas as gpd
import networkx as nx
import pandas as pd
import pytest
import shapely

from brokenspoke_analyzer.core.pipeline import (
    errors,
    network,
)

UTM13N = 32613


def roads(rows: list[dict]) -> gpd.GeoDataFrame:
    """Build a rated-roads frame with sensible defaults."""
    for index, row in enumerate(rows):
        row.setdefault("road_id", index + 1)
        row.setdefault("ft_seg_stress", 1)
        row.setdefault("tf_seg_stress", 1)
        row.setdefault("ft_int_stress", 1)
        row.setdefault("tf_int_stress", 1)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{UTM13N}")


class TestLinkCost:
    """Test the turn cost, which hides two SQL integer quirks."""

    def test_truncates_rather_than_rounds(self) -> None:
        """The SQL's integer division truncates; it does not round.

        `(10 + 11) / 2` is 10 in PostgreSQL integer arithmetic, not 10.5 or
        11. Rounding instead inflates every link and compounds along a path.
        """
        assert network._link_cost(10.0, 11.0) == 10

    def test_rounds_each_length_before_halving(self) -> None:
        """Lengths land in INTEGER columns, so each is rounded first."""
        # 10.4 -> 10 and 11.4 -> 11, then (10 + 11) // 2 == 10.
        assert network._link_cost(10.4, 11.4) == 10
        # 10.6 -> 11 and 11.6 -> 12, then (11 + 12) // 2 == 11.
        assert network._link_cost(10.6, 11.6) == 11

    def test_exact_halves(self) -> None:
        """Equal lengths give exactly half their sum."""
        assert network._link_cost(20.0, 20.0) == 20


class TestGreatest:
    """Test the NULL-skipping `greatest()`."""

    def test_skips_nulls(self) -> None:
        """A NULL argument is ignored rather than poisoning the result."""
        assert network._greatest(1, float("nan"), 3) == 3

    def test_all_null_yields_the_sentinel(self) -> None:
        """All-NULL gives a value that can never equal LOW_STRESS."""
        assert network._greatest(float("nan")) == network.NULL_STRESS
        assert network.NULL_STRESS != network.LOW_STRESS


class TestBuildNetwork:
    """Test the turn-expanded graph construction."""

    def test_requires_a_projected_crs(self) -> None:
        """A geographic CRS is refused, not silently mis-measured."""
        frame = roads(
            [
                {
                    "geometry": shapely.LineString([(0, 0), (1, 0)]),
                    "intersection_from": "a",
                    "intersection_to": "b",
                }
            ],
        ).to_crs(epsg=4326)
        with pytest.raises(errors.ReachabilityError, match="projected"):
            network.build_network(frame)

    def test_one_vertex_per_road(self) -> None:
        """Vertices are roads, not intersections."""
        frame = roads(
            [
                {
                    "geometry": shapely.LineString([(0, 0), (100, 0)]),
                    "intersection_from": "a",
                    "intersection_to": "b",
                },
                {
                    "geometry": shapely.LineString([(100, 0), (200, 0)]),
                    "intersection_from": "b",
                    "intersection_to": "c",
                },
            ],
        )
        vertices, _ = network.build_network(frame)
        assert len(vertices) == 2

    def test_two_way_roads_link_both_directions(self) -> None:
        """Two two-way roads meeting at a node can be traversed either way."""
        frame = roads(
            [
                {
                    "geometry": shapely.LineString([(0, 0), (100, 0)]),
                    "intersection_from": "a",
                    "intersection_to": "b",
                },
                {
                    "geometry": shapely.LineString([(100, 0), (200, 0)]),
                    "intersection_from": "b",
                    "intersection_to": "c",
                },
            ],
        )
        _, links = network.build_network(frame)
        assert len(links) == 2
        # Each link costs half of each 100 m road.
        assert set(links["link_cost"]) == {100}

    def test_one_way_blocks_the_reverse_turn(self) -> None:
        """A one-way road cannot be entered from its far end."""
        frame = roads(
            [
                {
                    "geometry": shapely.LineString([(0, 0), (100, 0)]),
                    "intersection_from": "a",
                    "intersection_to": "b",
                    "one_way": "ft",
                },
                {
                    "geometry": shapely.LineString([(100, 0), (200, 0)]),
                    "intersection_from": "b",
                    "intersection_to": "c",
                },
            ],
        )
        _, links = network.build_network(frame)
        # Road 1 departs at `b` into road 2, but cannot be entered at `b`.
        assert len(links) == 1
        assert links.iloc[0]["source_vert"] == 0

    def test_null_stress_link_is_excluded_from_low_stress_only(self) -> None:
        """A NULL rating fails `= 1` but survives the unfiltered graph."""
        links = pd.DataFrame(
            {
                "source_vert": [0, 1],
                "target_vert": [1, 2],
                "link_cost": [10, 10],
                "link_stress": [network.LOW_STRESS, network.NULL_STRESS],
            },
        )
        assert network.build_graph(links, low_stress_only=True).number_of_edges() == 1
        assert network.build_graph(links, low_stress_only=False).number_of_edges() == 2


class TestReachableRoads:
    """Test the reachability search."""

    def graph(self) -> nx.DiGraph:
        """A -> B -> C chain, plus a disconnected D."""
        g = nx.DiGraph()
        g.add_edge(0, 1, weight=100.0)
        g.add_edge(1, 2, weight=100.0)
        g.add_node(3)
        return g

    def vertices(self) -> pd.DataFrame:
        """Four vertices mapping to roads 10..13."""
        return pd.DataFrame({"vert_id": [0, 1, 2, 3], "road_id": [10, 11, 12, 13]})

    def test_reaches_within_the_cutoff(self) -> None:
        """Everything within the cutoff is reported, with its cost."""
        got = network.reachable_roads(
            self.graph(),
            {"block": pd.array([0]).to_numpy()},
            self.vertices(),
            max_trip_distance=250,
        )
        assert dict(zip(got["target_road"], got["total_cost"])) == {
            10: 0.0,
            11: 100.0,
            12: 200.0,
        }

    def test_cutoff_is_inclusive(self) -> None:
        """A road exactly at the cutoff distance is reachable."""
        got = network.reachable_roads(
            self.graph(),
            {"block": pd.array([0]).to_numpy()},
            self.vertices(),
            max_trip_distance=100,
        )
        assert set(got["target_road"]) == {10, 11}

    def test_disconnected_components_are_unreachable(self) -> None:
        """A vertex with no path in is never reported."""
        got = network.reachable_roads(
            self.graph(),
            {"block": pd.array([0]).to_numpy()},
            self.vertices(),
        )
        assert 13 not in set(got["target_road"])

    def test_seeds_are_reachable_even_off_the_subgraph(self) -> None:
        """A seed with no link in this stress subgraph still costs 0.

        The SQL unions its zero-cost source edges in regardless of
        `link_stress`, so a block reaches its own roads even where none of
        them is low-stress -- which is what makes two blocks sharing a road
        cost 0 apart (findings.md §1.14).
        """
        got = network.reachable_roads(
            self.graph(),
            {"block": pd.array([3]).to_numpy()},
            self.vertices(),
        )
        assert dict(zip(got["target_road"], got["total_cost"])) == {13: 0.0}

    def test_a_seed_absent_from_the_graph_entirely_still_counts(self) -> None:
        """Even a vertex the subgraph never mentions is its block's own road."""
        graph = nx.DiGraph()
        graph.add_edge(0, 1, weight=100.0)
        got = network.reachable_roads(
            graph,
            {"block": pd.array([3]).to_numpy()},
            self.vertices(),
        )
        assert dict(zip(got["target_road"], got["total_cost"])) == {13: 0.0}

    def test_multi_source_takes_the_nearest_seed(self) -> None:
        """Seeding from several roads is a single search, not one per seed.

        This mirrors the SQL's 0-cost super-source: the cost to each road is
        the distance from whichever seed is closest.
        """
        got = network.reachable_roads(
            self.graph(),
            {"block": pd.array([0, 1]).to_numpy()},
            self.vertices(),
        )
        costs = dict(zip(got["target_road"], got["total_cost"]))
        assert costs[11] == 0.0
        assert costs[12] == 100.0


class TestLowStressConnection:
    """Test the 1.25 detour ratio."""

    def test_shared_road_connects_outright(self) -> None:
        """Blocks fronting a common road are connected without any route."""
        assert network._is_low_stress_connected(None, None, shares_road=True)

    def test_detour_within_ratio(self) -> None:
        """A low-stress route up to 25% longer still counts."""
        assert network._is_low_stress_connected(125.0, 100.0, shares_road=False)
        assert not network._is_low_stress_connected(126.0, 100.0, shares_road=False)

    def test_no_low_stress_route(self) -> None:
        """Without a low-stress route the pair is not connected."""
        assert not network._is_low_stress_connected(None, 100.0, shares_road=False)

    def test_zero_unrestricted_cost(self) -> None:
        """A zero unrestricted cost cannot form a ratio; the SQL says connected."""
        assert network._is_low_stress_connected(0.0, 0.0, shares_road=False)


class TestAssignBlockRoads:
    """Test the block-to-road association."""

    def blocks(self) -> gpd.GeoDataFrame:
        """One 100 m square block."""
        return gpd.GeoDataFrame(
            {
                "geoid20": ["1"],
                "geometry": [shapely.box(0, 0, 100, 100)],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )

    def test_buffers_the_way_postgis_does(self) -> None:
        """The buffer is drawn with 8 segments per quadrant, not 16.

        The two polygons differ only near the corners, and only by
        centimetres -- but the buffer *is* the membership test here, so a road
        grazing a corner lands inside one and outside the other
        (findings.md §2.6).
        """
        blocks = self.blocks()
        corner = shapely.Point(100, 100)
        coarse = corner.buffer(network.BLOCK_ROAD_BUFFER, resolution=8)
        fine = corner.buffer(network.BLOCK_ROAD_BUFFER, resolution=16)
        # Halfway between the two polygons' inradii, at the angle where the
        # coarse one falls furthest short of the circle.
        angle = math.pi / 32
        radius = (
            network.BLOCK_ROAD_BUFFER
            * (math.cos(math.pi / 32) + math.cos(math.pi / 64))
            / 2
        )
        between = shapely.Point(
            100 + radius * math.cos(angle),
            100 + radius * math.sin(angle),
        )
        assert fine.contains(between)
        assert not coarse.contains(between)

        # A road long enough to clear the 30 m overlap test, ending in the gap.
        ways = gpd.GeoDataFrame(
            {
                "road_id": [1],
                "geometry": [shapely.LineString([(150, 150), (between.x, between.y)])],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        assert network.assign_block_roads(blocks, ways).iloc[0] == []
