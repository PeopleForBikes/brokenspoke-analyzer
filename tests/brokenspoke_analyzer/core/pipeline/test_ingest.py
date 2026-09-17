"""Test the `ingest` pipeline stage.

Cover the `prepare` output contract, the road segmentation rule, and the census
block filters. Everything here runs on synthetic inputs: no database, no
network, no city fixtures.
"""

import inspect
import pathlib

import geopandas as gpd
import pandas as pd
import pytest
import shapely

from brokenspoke_analyzer.core.pipeline import (
    errors,
    ingest,
)

# A projected CRS, so lengths and areas come out in metres.
UTM13N = 32613


def line(*points: tuple[float, float]) -> shapely.LineString:
    """Build a LineString from coordinate pairs."""
    return shapely.LineString(points)


def make_edges(rows: list[dict]) -> gpd.GeoDataFrame:
    """Build a sub-edge frame shaped like `read_ways` output."""
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{UTM13N}")


def square(x: float, y: float, size: float = 10.0) -> shapely.Polygon:
    """Build an axis-aligned square polygon with its corner at (x, y)."""
    return shapely.Polygon(
        [(x, y), (x + size, y), (x + size, y + size), (x, y + size)],
    )


class TestPrepareArtifacts:
    """Test the `prepare` output contract."""

    def test_resolves_us_city_paths(self) -> None:
        """A US city resolves to the slugified per-city directory."""
        artifacts = ingest.PrepareArtifacts.resolve(
            pathlib.Path("data"), "united states", "crested butte", "colorado"
        )
        assert artifacts.slug == "crested-butte-colorado-united-states"
        assert artifacts.data_dir == pathlib.Path(
            "data/crested-butte-colorado-united-states"
        )
        assert artifacts.city_osm.name == "crested-butte-colorado-united-states.osm"
        assert artifacts.boundary.name == "crested-butte-colorado-united-states.shp"

    def test_resolves_non_us_city_paths(self) -> None:
        """A non-US city needs no region and still resolves."""
        artifacts = ingest.PrepareArtifacts.resolve(
            pathlib.Path("data"), "canada", "ancienne-lorette", "québec"
        )
        assert artifacts.slug == "ancienne-lorette-quebec-canada"

    def test_census_blocks_name_is_constant(self) -> None:
        """Census blocks are always `population.shp`, whatever the source."""
        for country, city, region in (
            ("united states", "santa rosa", "new mexico"),
            ("spain", "valencia", "valencia"),
        ):
            artifacts = ingest.PrepareArtifacts.resolve(
                pathlib.Path("data"), country, city, region
            )
            assert artifacts.census_blocks.name == "population.shp"

    def test_normalizes_usa_aliases(self) -> None:
        """`usa` and `united states` resolve to the same directory."""
        a = ingest.PrepareArtifacts.resolve(
            pathlib.Path("d"), "usa", "santa rosa", "new mexico"
        )
        b = ingest.PrepareArtifacts.resolve(
            pathlib.Path("d"), "united states", "santa rosa", "new mexico"
        )
        assert a.slug == b.slug

    def test_lodes_path(self) -> None:
        """LODES CSVs follow the `prepare` naming convention."""
        artifacts = ingest.PrepareArtifacts.resolve(
            pathlib.Path("data"), "united states", "crested butte", "colorado"
        )
        assert artifacts.lodes("co", "main", 2023).name == "co_od_main_JT00_2023.csv"

    def test_require_names_every_missing_file(self, tmp_path: pathlib.Path) -> None:
        """A missing artifact fails with a message naming it."""
        artifacts = ingest.PrepareArtifacts(data_dir=tmp_path, slug="nowhere")
        with pytest.raises(errors.IngestError, match="population.shp"):
            artifacts.require(artifacts.census_blocks)

    def test_require_passes_when_present(self, tmp_path: pathlib.Path) -> None:
        """An existing artifact raises nothing."""
        artifacts = ingest.PrepareArtifacts(data_dir=tmp_path, slug="here")
        artifacts.census_blocks.write_text("")
        artifacts.require(artifacts.census_blocks)


class TestTagCoverage:
    """Guard the OSM tag list against silent drift."""

    def test_way_tags_cover_pfb_style(self) -> None:
        """Every way tag `osm2pgsql` imported is still read here.

        A tag dropped from this list does not raise -- it silently changes a
        derived feature, and therefore a score (findings.md §2.2).

        `pfb.style` was the reference until task 11 deleted it, so the way
        tags it declared are frozen below: this file is now their only
        record. The point-table tags are excluded -- they describe a node,
        not a way attribute, and task 4.12's intersection rules read them
        from `OSM_POINT_TAGS` instead.
        """
        imported_as_way_tags = {
            "access",
            "bicycle",
            "bridge",
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
            "foot",
            "footway",
            "golf",
            "golf_cart",
            "highway",
            "junction",
            "lanes",
            "lanes:backward",
            "lanes:both_ways",
            "lanes:forward",
            "maxspeed",
            "motorcar",
            "name",
            "oneway",
            "oneway:bicycle",
            "parking",
            "parking:both",
            "parking:both:restriction",
            "parking:both:width",
            "parking:lane",
            "parking:lane:both",
            "parking:lane:both:width",
            "parking:lane:left",
            "parking:lane:left:width",
            "parking:lane:right",
            "parking:lane:right:width",
            "parking:lane:width",
            "parking:left",
            "parking:left:restriction",
            "parking:left:width",
            "parking:right",
            "parking:right:restriction",
            "parking:right:width",
            "segregated",
            "service",
            "surface",
            "tracktype",
            # The one way-only tag `signalized.sql` reads from the line
            # table. Missed on the first transcription: DC's Maine Avenue
            # lost a signal (findings.md §1.28).
            "traffic_signals:direction",
            "tunnel",
            "turn:lanes",
            "turn:lanes:backward",
            "turn:lanes:both_ways",
            "turn:lanes:forward",
            "width",
            "width:lanes",
            "width:lanes:backward",
            "width:lanes:forward",
        }
        missing = imported_as_way_tags - set(ingest.OSM_WAY_TAGS)
        assert not missing, f"way tags dropped from OSM_WAY_TAGS: {sorted(missing)}"

    def test_highway_types_match_mapconfig(self) -> None:
        """The routable highway values are `mapconfig_highway.xml`'s.

        Frozen here for the same reason: task 11 deleted the config, and this
        set decides which ways become roads at all -- and, through
        findings.md §3.11, which nodes cut them.
        """
        assert set(ingest.OSM_HIGHWAY_TYPES) == {
            "bridleway",
            "bus_guideway",
            "byway",
            "cycleway",
            "footway",
            "living_street",
            "motorway",
            "motorway_junction",
            "motorway_link",
            "path",
            "pedestrian",
            "primary",
            "primary_link",
            "residential",
            "road",
            "secondary",
            "secondary_link",
            "service",
            "services",
            "steps",
            "tertiary",
            "tertiary_link",
            "track",
            "trunk",
            "trunk_link",
            "unclassified",
        }


class TestSplitWaysAtIntersections:
    """Test the `osm2pgrouting` segmentation rule."""

    def test_splits_where_two_ways_meet(self) -> None:
        """A way is cut at an interior node another way also touches."""
        edges = make_edges(
            [
                # Way 1: A -> B -> C, with B shared.
                {"id": 1, "u": "A", "v": "B", "geometry": line((0, 0), (1, 0))},
                {"id": 1, "u": "B", "v": "C", "geometry": line((1, 0), (2, 0))},
                # Way 2: B -> D, making B an intersection.
                {"id": 2, "u": "B", "v": "D", "geometry": line((1, 0), (1, 1))},
            ],
        )
        segments = ingest.split_ways_at_intersections(edges)
        assert len(segments) == 3
        pairs = set(
            zip(
                segments["intersection_from"],
                segments["intersection_to"],
                strict=True,
            )
        )
        assert pairs == {("A", "B"), ("B", "C"), ("B", "D")}

    def test_does_not_split_at_a_private_node(self) -> None:
        """A node only one way uses stays interior to the segment."""
        edges = make_edges(
            [
                {"id": 1, "u": "A", "v": "B", "geometry": line((0, 0), (1, 0))},
                {"id": 1, "u": "B", "v": "C", "geometry": line((1, 0), (2, 0))},
            ],
        )
        segments = ingest.split_ways_at_intersections(edges)
        assert len(segments) == 1
        assert segments.iloc[0]["intersection_from"] == "A"
        assert segments.iloc[0]["intersection_to"] == "C"

    def test_splits_a_loop_at_its_own_revisited_node(self) -> None:
        """A way returning to a node it already visited is cut there.

        Leaving the loop joined yields a self-touching ring that cannot merge
        into a single LineString, which every downstream geometry step assumes.
        """
        edges = make_edges(
            [
                {"id": 1, "u": "A", "v": "B", "geometry": line((0, 0), (1, 0))},
                {"id": 1, "u": "B", "v": "C", "geometry": line((1, 0), (1, 1))},
                {"id": 1, "u": "C", "v": "B", "geometry": line((1, 1), (1, 0))},
            ],
        )
        segments = ingest.split_ways_at_intersections(edges)
        assert len(segments) == 2
        assert set(segments.geometry.geom_type) == {"LineString"}

    def test_a_closed_ring_starts_where_the_way_started(self) -> None:
        """A ring's geometry begins at the node its columns name.

        `line_merge` is free to start a closed ring at any vertex, and it does
        not pick the way's own first node -- leaving the geometry
        contradicting `intersection_from` (findings.md §2.9).
        """
        edges = make_edges(
            [
                {"id": 1, "u": "A", "v": "B", "geometry": line((0, 0), (1, 0))},
                {"id": 1, "u": "B", "v": "C", "geometry": line((1, 0), (1, 1))},
                {"id": 1, "u": "C", "v": "A", "geometry": line((1, 1), (0, 0))},
            ],
        )
        segments = ingest.split_ways_at_intersections(edges)
        ring = segments[segments["intersection_from"] == "A"].iloc[0]
        assert ring["intersection_to"] == "A"
        first = shapely.get_coordinates(ring.geometry)[0]
        assert tuple(first) == (0.0, 0.0)

    def test_segments_are_always_linestrings(self) -> None:
        """Merged multi-part segments collapse to one LineString."""
        edges = make_edges(
            [
                {"id": 1, "u": "A", "v": "B", "geometry": line((0, 0), (1, 0))},
                {"id": 1, "u": "B", "v": "C", "geometry": line((1, 0), (2, 0))},
                {"id": 1, "u": "C", "v": "D", "geometry": line((2, 0), (3, 0))},
            ],
        )
        segments = ingest.split_ways_at_intersections(edges)
        assert len(segments) == 1
        assert segments.iloc[0].geometry.geom_type == "LineString"
        # The merged geometry spans the whole way.
        assert segments.iloc[0].geometry.length == pytest.approx(3.0)

    def test_road_ids_are_unique_and_one_based(self) -> None:
        """Every segment gets its own `road_id`."""
        edges = make_edges(
            [
                {"id": 1, "u": "A", "v": "B", "geometry": line((0, 0), (1, 0))},
                {"id": 2, "u": "B", "v": "C", "geometry": line((1, 0), (2, 0))},
            ],
        )
        segments = ingest.split_ways_at_intersections(edges)
        assert sorted(segments["road_id"]) == [1, 2]

    def test_tags_survive_the_split(self) -> None:
        """A way's tags are carried onto each of its segments."""
        edges = make_edges(
            [
                {
                    "id": 1,
                    "u": "A",
                    "v": "B",
                    "highway": "residential",
                    "maxspeed": "25",
                    "geometry": line((0, 0), (1, 0)),
                },
                {
                    "id": 1,
                    "u": "B",
                    "v": "C",
                    "highway": "residential",
                    "maxspeed": "25",
                    "geometry": line((1, 0), (2, 0)),
                },
                {
                    "id": 2,
                    "u": "B",
                    "v": "D",
                    "highway": "primary",
                    "maxspeed": "45",
                    "geometry": line((1, 0), (1, 1)),
                },
            ],
        )
        segments = ingest.split_ways_at_intersections(edges)
        by_way = segments.set_index("osm_id")["highway"].to_dict()
        assert by_way[2] == "primary"
        assert set(segments[segments["osm_id"] == 1]["maxspeed"]) == {"25"}

    def test_rejects_frames_without_topology(self) -> None:
        """Edges lacking `u`/`v` fail loudly rather than silently."""
        edges = make_edges([{"id": 1, "geometry": line((0, 0), (1, 0))}])
        with pytest.raises(errors.IngestError, match="missing"):
            ingest.split_ways_at_intersections(edges)


class TestLoadCensusBlocks:
    """Test the census block filters and the population guard."""

    def write_blocks(
        self, tmp_path: pathlib.Path, frame: gpd.GeoDataFrame
    ) -> ingest.PrepareArtifacts:
        """Write a census block shapefile where `ingest` expects it."""
        artifacts = ingest.PrepareArtifacts(data_dir=tmp_path, slug="synthetic")
        frame.to_file(artifacts.census_blocks)
        return artifacts

    def boundary(self) -> gpd.GeoDataFrame:
        """Return a 100x100 m boundary at the origin."""
        return gpd.GeoDataFrame({"geometry": [square(0, 0, 100)]}, crs=f"EPSG:{UTM13N}")

    def test_keeps_blocks_inside_the_boundary(self, tmp_path: pathlib.Path) -> None:
        """A block fully inside the boundary is kept."""
        blocks = gpd.GeoDataFrame(
            {"geometry": [square(10, 10)], "pop20": [50], "aland20": [100.0]},
            crs=f"EPSG:{UTM13N}",
        )
        artifacts = self.write_blocks(tmp_path, blocks)
        kept = ingest.load_census_blocks(
            artifacts, self.boundary(), UTM13N, "united states"
        )
        assert len(kept) == 1

    def test_drops_blocks_outside_the_boundary(self, tmp_path: pathlib.Path) -> None:
        """A block that does not touch the boundary is dropped."""
        blocks = gpd.GeoDataFrame(
            {
                "geometry": [square(10, 10), square(500, 500)],
                "pop20": [50, 90],
                "aland20": [100.0, 100.0],
            },
            crs=f"EPSG:{UTM13N}",
        )
        artifacts = self.write_blocks(tmp_path, blocks)
        kept = ingest.load_census_blocks(
            artifacts, self.boundary(), UTM13N, "united states"
        )
        assert len(kept) == 1
        assert int(kept["pop20"].sum()) == 50

    def test_drops_barely_overlapping_blocks_for_us(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A US block overlapping under 50% is dropped."""
        # 80% of this block lies outside the boundary's eastern edge.
        blocks = gpd.GeoDataFrame(
            {"geometry": [square(98, 10)], "pop20": [50], "aland20": [100.0]},
            crs=f"EPSG:{UTM13N}",
        )
        artifacts = self.write_blocks(tmp_path, blocks)
        with pytest.raises(errors.InsufficientDataError):
            ingest.load_census_blocks(
                artifacts, self.boundary(), UTM13N, "united states"
            )

    def test_international_threshold_is_looser(self, tmp_path: pathlib.Path) -> None:
        """The same block survives outside the US, at the 25% threshold."""
        # 30% of this block lies inside the boundary: below 0.5, above 0.25.
        blocks = gpd.GeoDataFrame(
            {"geometry": [square(93, 10)], "pop20": [50], "aland20": [100.0]},
            crs=f"EPSG:{UTM13N}",
        )
        artifacts = self.write_blocks(tmp_path, blocks)
        kept = ingest.load_census_blocks(artifacts, self.boundary(), UTM13N, "canada")
        assert len(kept) == 1

    def test_drops_us_water_blocks(self, tmp_path: pathlib.Path) -> None:
        """A US block with no land area is dropped."""
        blocks = gpd.GeoDataFrame(
            {
                "geometry": [square(10, 10), square(30, 30)],
                "pop20": [50, 70],
                "aland20": [0.0, 100.0],
            },
            crs=f"EPSG:{UTM13N}",
        )
        artifacts = self.write_blocks(tmp_path, blocks)
        kept = ingest.load_census_blocks(
            artifacts, self.boundary(), UTM13N, "united states"
        )
        assert len(kept) == 1
        assert int(kept["pop20"].sum()) == 70

    def test_keeps_non_us_water_blocks(self, tmp_path: pathlib.Path) -> None:
        """Outside the US, zero-land blocks are not dropped."""
        blocks = gpd.GeoDataFrame(
            {
                "geometry": [square(10, 10), square(30, 30)],
                "pop20": [50, 70],
                "aland20": [0.0, 100.0],
            },
            crs=f"EPSG:{UTM13N}",
        )
        artifacts = self.write_blocks(tmp_path, blocks)
        kept = ingest.load_census_blocks(artifacts, self.boundary(), UTM13N, "canada")
        assert len(kept) == 2

    def test_zero_population_is_refused(self, tmp_path: pathlib.Path) -> None:
        """An area with no inhabitants cannot be scored."""
        blocks = gpd.GeoDataFrame(
            {"geometry": [square(10, 10)], "pop20": [0], "aland20": [100.0]},
            crs=f"EPSG:{UTM13N}",
        )
        artifacts = self.write_blocks(tmp_path, blocks)
        with pytest.raises(errors.InsufficientDataError, match="population"):
            ingest.load_census_blocks(
                artifacts, self.boundary(), UTM13N, "united states"
            )


class TestLoadJobs:
    """Test the LODES employment loader."""

    def test_missing_lodes_yields_an_empty_frame(self, tmp_path: pathlib.Path) -> None:
        """Puerto Rico has no LODES data, which is not an error."""
        artifacts = ingest.PrepareArtifacts(data_dir=tmp_path, slug="pr")
        assert ingest.load_jobs(artifacts, "pr", 2023).empty

    def test_concatenates_main_and_aux(self, tmp_path: pathlib.Path) -> None:
        """Both LODES parts are loaded and combined."""
        artifacts = ingest.PrepareArtifacts(data_dir=tmp_path, slug="co")
        for part, rows in (("main", 2), ("aux", 3)):
            frame = pd.DataFrame(
                {
                    "w_geocode": ["080000000000001"] * rows,
                    "h_geocode": ["080000000000002"] * rows,
                    "S000": range(rows),
                },
            )
            frame.to_csv(artifacts.lodes("co", part, 2023), index=False)
        jobs = ingest.load_jobs(artifacts, "CO", 2023)
        assert len(jobs) == 5
        # Geocodes must stay strings: they are zero-padded identifiers, and
        # reading them as integers would eat the leading zero.
        assert pd.api.types.is_string_dtype(jobs["w_geocode"])
        assert jobs["w_geocode"].iloc[0] == "080000000000001"


class TestReadDestinationsContract:
    """Pin the two `pyrosm` workarounds the destination read depends on.

    Both failure modes are silent -- a missing feature and a missing column,
    with no error either way -- so they are guarded structurally here and by
    the parity corpus end to end.
    """

    def test_every_key_the_rules_read_is_requested_as_a_column(self) -> None:
        """Filtering on a key does not create a column for it.

        `pyrosm` promotes only the tags it knows, so `healthcare` has to be
        asked for explicitly or every healthcare rule matches nothing
        (findings.md §2.8).
        """
        source = inspect.getsource(ingest.read_destinations)
        assert "*OSM_DESTINATION_KEYS," in source

    def test_relations_are_read_separately_and_filtered_to_areas(self) -> None:
        """Asked for relations, `pyrosm` drops their member ways.

        `osm2pgsql` only made polygons out of `multipolygon` and `boundary`
        relations, and emitted every tagged way in its own right
        (findings.md §2.7).
        """
        assert ingest.POLYGON_RELATION_TYPES == ("multipolygon", "boundary")
        source = inspect.getsource(ingest.read_destinations)
        assert "read(nodes=True, ways=True, relations=False)" in source
        assert "read(nodes=False, ways=False, relations=True)" in source

    def test_multi_part_geometries_are_exploded(self) -> None:
        """`osm2pgsql` ran without `--multi-geometry`, so parts are rows.

        A three-part nature reserve is three entries in the polygon table,
        and clusters as three destinations when its parts are far apart
        (findings.md §3.7).
        """
        source = inspect.getsource(ingest.read_destinations)
        assert "explode(index_parts=False)" in source


class TestAssembledAreaIds:
    """Test the area-assembler filter."""

    def write(self, path: pathlib.Path, ids: list[str]) -> None:
        """Write a GeoJSON sequence carrying only ids."""
        path.write_text(
            "".join(
                f'\x1e{{"type":"Feature","id":"{identifier}",'
                '"geometry":null,"properties":{}}\n'
                for identifier in ids
            ),
        )

    def test_decodes_libosmium_area_ids(self, tmp_path: pathlib.Path) -> None:
        """A way's area id is doubled, a relation's doubled plus one."""
        protobuf = tmp_path / "city.osm.pbf"
        protobuf.write_bytes(b"")
        self.write(
            protobuf.with_suffix(".areas.geojsonseq"), ["a617518142", "a8246325"]
        )
        got = ingest.assembled_area_ids(protobuf)
        assert got == {("way", 308759071), ("relation", 4123162)}

    def test_an_empty_export_yields_no_areas(self, tmp_path: pathlib.Path) -> None:
        """A city with no assembled area is not an error."""
        protobuf = tmp_path / "city.osm.pbf"
        protobuf.write_bytes(b"")
        self.write(protobuf.with_suffix(".areas.geojsonseq"), [])
        assert ingest.assembled_area_ids(protobuf) == set()


class TestSharedNodes:
    """Test the cut-node census."""

    def write(self, path: pathlib.Path, body: str) -> pathlib.Path:
        """Write a minimal OSM XML extract."""
        path.write_text(f'<?xml version="1.0"?>\n<osm version="0.6">{body}</osm>')
        return path

    def test_a_node_two_ways_touch_is_a_cut(self, tmp_path: pathlib.Path) -> None:
        """The ordinary case, and "way" means any way at all."""
        extract = self.write(
            tmp_path / "city.osm",
            """
            <way id="1"><nd ref="10"/><nd ref="11"/><nd ref="12"/></way>
            <way id="2"><nd ref="11"/><nd ref="20"/>
              <tag k="building" v="yes"/></way>
            """,
        )
        assert ingest.shared_nodes(extract) == {11}

    def test_a_tagged_node_is_a_cut_on_its_own(self, tmp_path: pathlib.Path) -> None:
        """`osm2pgrouting` reads its config for nodes too (findings.md §3.11).

        A motorway exit mid-way is a vertex even though only one way uses it.
        """
        extract = self.write(
            tmp_path / "city.osm",
            """
            <node id="11"><tag k="highway" v="motorway_junction"/></node>
            <way id="1"><nd ref="10"/><nd ref="11"/><nd ref="12"/></way>
            """,
        )
        assert ingest.shared_nodes(extract) == {11}

    def test_an_unconfigured_node_tag_is_not_a_cut(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """`highway=crossing` is not in `mapconfig_highway.xml`.

        Otherwise every pedestrian crossing would split its road.
        """
        extract = self.write(
            tmp_path / "city.osm",
            """
            <node id="11"><tag k="highway" v="crossing"/></node>
            <way id="1"><nd ref="10"/><nd ref="11"/><nd ref="12"/></way>
            """,
        )
        assert ingest.shared_nodes(extract) == set()
