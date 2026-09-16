"""
Ingest the files produced by `prepare` into in-memory frames.

Replace the `shp2pgsql` + `osm2pgrouting` + `osm2pgsql` import step. `prepare`
itself is unchanged and is the input boundary for this stage: everything here
reads what `prepare` already wrote to disk, and nothing here re-downloads,
re-extracts, or re-derives that data.

The road topology is deliberately built here rather than taken from a library's
default: `osmnx` and `pyrosm` each segment a way differently from
`osm2pgrouting`, and the BNA's costs are defined against `osm2pgrouting`'s
segmentation. See `split_ways_at_intersections`.
"""

import collections
import dataclasses
import json
import pathlib
import typing
from xml.etree import ElementTree as ET

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from loguru import logger

from brokenspoke_analyzer.core import (
    analysis,
    runner,
    utils,
)
from brokenspoke_analyzer.core.pipeline import errors

# Minimum share of a census block that must fall inside the boundary for the
# block to be kept, from `ingestor.py`. Non-US boundaries are looser because
# their simulated blocks are a synthetic grid that rarely aligns with the
# boundary.
US_MIN_OVERLAP_RATIO = 0.5
INTERNATIONAL_MIN_OVERLAP_RATIO = 0.25

# Highway values `osm2pgrouting` imports, from `scripts/mapconfig_highway.xml`.
# A way whose `highway` tag is outside this set never enters the network.
OSM_HIGHWAY_TYPES = frozenset(
    {
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
    },
)

# Way tags the downstream feature derivation reads, from `scripts/pfb.style`
# (the `osm2pgsql` column list). Kept exhaustive on purpose: a tag dropped here
# silently changes a score rather than raising.
OSM_WAY_TAGS = (
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
    "tunnel",
    "turn:lanes",
    "turn:lanes:backward",
    "turn:lanes:both_ways",
    "turn:lanes:forward",
    "width",
    "width:lanes",
    "width:lanes:backward",
    "width:lanes:forward",
)


# `highway` values on OSM *nodes* that the intersection rules look for.
OSM_POINT_HIGHWAY_VALUES = ("traffic_signals", "crossing", "stop")

# Node tags those rules read. Distinct from OSM_WAY_TAGS: these describe a
# point, and `pfb.style` imports them into the osm2pgsql *point* table.
OSM_POINT_TAGS = (
    "button_operated",
    "crossing",
    "crossing:island",
    "crossing_ref",
    "flashing_lights",
    "highway",
    "stop",
    "traffic_sign",
    "traffic_signals",
)


# Tags that can mark a destination. `pyrosm` needs the keys up front, and a key
# absent from the extract simply yields no column -- `features._column` treats
# that as all-NULL, which is what the SQL saw too.
OSM_DESTINATION_KEYS = (
    "amenity",
    "building",
    "healthcare",
    "landuse",
    "leisure",
    "public_transport",
    "railway",
    "shop",
)

# Extra attributes read alongside them.
OSM_DESTINATION_TAGS = ("name", "station", "operator")

# The relation tag naming what kind of relation it is, and the two kinds
# `osm2pgsql` turned into polygons. Every other kind (a route, a stop area) is
# not a feature in its own right.
RELATION_TYPE_TAG = "type"
POLYGON_RELATION_TYPES = ("multipolygon", "boundary")


def assembled_area_ids(protobuf: pathlib.Path) -> set[tuple[str, int]]:
    """List the objects `osmium` can actually build an area from.

    `osm2pgsql` assembles its polygons with libosmium's area assembler, and
    the assembler **refuses** a ring it cannot close cleanly -- a
    self-intersecting outer way, an incomplete multipolygon. Those objects
    never reached `neighborhood_osm_full_polygon`, so they are not
    destinations, however they are tagged (findings.md §3.8).

    `pyrosm` hides this: it repairs a self-intersecting ring into a valid
    multipolygon and hands it over as though nothing were wrong. Running the
    same assembler `osm2pgsql` used, and keeping only what it accepts, is the
    only way to tell the two apart.

    Parameters
    ----------
    protobuf
        An OSM protobuf extract, from :func:`as_protobuf`.

    Returns
    -------
    set of tuple
        `("way" | "relation", id)` for every assembled area.
    """
    areas = protobuf.with_suffix(".areas.geojsonseq")
    if not areas.exists():
        logger.debug(f"assembling areas from {protobuf.name}...")
        runner.run(
            [
                "osmium",
                "export",
                str(protobuf.resolve(strict=True)),
                "--geometry-types=polygon",
                # Ids come back as libosmium area ids: a way's is doubled, a
                # relation's is doubled plus one.
                "--add-unique-id=type_id",
                "-f",
                "geojsonseq",
                "-o",
                str(areas.resolve()),
            ],
        )

    found: set[tuple[str, int]] = set()
    with areas.open() as handle:
        for line in handle:
            # RFC 8142 sequences prefix each record with a record separator.
            record = line.strip().lstrip("\x1e")
            if not record:
                continue
            identifier = int(json.loads(record)["id"][1:])
            if identifier % 2:
                found.add(("relation", (identifier - 1) // 2))
            else:
                found.add(("way", identifier // 2))
    logger.debug(f"{len(found):,} assembled areas")
    return found


def read_destinations(protobuf: pathlib.Path) -> gpd.GeoDataFrame:
    """Read every tagged feature a destination rule might match.

    The analogue of `neighborhood_osm_full_point` and
    `neighborhood_osm_full_polygon` together. The destination scripts consult
    both: a school mapped as a building footprint and one mapped as a single
    node are the same destination, and the polygon takes precedence.

    Parameters
    ----------
    protobuf
        An OSM protobuf extract, from :func:`as_protobuf`.

    Returns
    -------
    geopandas.GeoDataFrame
        Points and polygons with their tags, or an empty frame when the
        extract has none.
    """
    from pyrosm import OSM  # noqa: PLC0415

    osm = OSM(str(protobuf.resolve(strict=True)))

    def read(*, nodes: bool, ways: bool, relations: bool) -> gpd.GeoDataFrame | None:
        return osm.get_data_by_custom_criteria(
            custom_filter=dict.fromkeys(OSM_DESTINATION_KEYS, True),
            filter_type="keep",
            keep_nodes=nodes,
            keep_ways=ways,
            keep_relations=relations,
            # `pyrosm` promotes only the tags it knows to columns, and
            # `healthcare` is not one of them -- ask for every key the rules
            # read, or they match against a column that is not there
            # (findings.md §2.8).
            extra_attributes=[
                *OSM_DESTINATION_TAGS,
                RELATION_TYPE_TAG,
                *OSM_DESTINATION_KEYS,
            ],
        )

    # Read in two passes. Asked for relations, `pyrosm` treats every member way
    # as consumed and drops it -- so a station building inside a
    # `public_transport=stop_area` relation disappears, taking its destination
    # with it. `osm2pgsql`, which the SQL read from, only ever turned
    # `multipolygon` and `boundary` relations into polygons and emitted every
    # tagged way in its own right (findings.md §2.7).
    parts = [read(nodes=True, ways=True, relations=False)]
    relations = read(nodes=False, ways=False, relations=True)
    if relations is not None and not relations.empty:
        areas = relations[RELATION_TYPE_TAG].isin(POLYGON_RELATION_TYPES)
        parts.append(relations[areas])

    usable = [part for part in parts if part is not None and not part.empty]
    found = (
        gpd.GeoDataFrame(pd.concat(usable, ignore_index=True), crs=usable[0].crs)  # ty:ignore[no-matching-overload]
        if usable
        else None
    )
    if found is None or found.empty:
        logger.debug("no destination features in the extract")
        return gpd.GeoDataFrame(
            {"id": [], "geometry": []},
            geometry="geometry",
            crs="EPSG:4326",
        )  # ty:ignore[no-matching-overload]
    # Drop what the area assembler could not build: `pyrosm` repaired those
    # rings, `osm2pgsql` did not have them at all.
    is_area = found.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    if is_area.any():
        assembled = assembled_area_ids(protobuf)
        keys = list(
            zip(found["osm_type"], found["id"].astype("int64"), strict=True),
        )
        buildable = pd.Series(
            [key in assembled for key in keys],
            index=found.index,
        )
        found = found[~is_area | buildable]

    # `osm2pgsql` ran without `--multi-geometry`, so it wrote one row per
    # *part*: a nature reserve mapped as a three-part multipolygon is three
    # rows in `neighborhood_osm_full_polygon`, and clusters as three
    # destinations when the parts are far apart (findings.md §3.7).
    found = gpd.GeoDataFrame(
        found.explode(index_parts=False).reset_index(drop=True),
        crs=found.crs,
    )  # ty:ignore[no-matching-overload]
    logger.debug(f"read {len(found):,} destination candidates")
    return found


@dataclasses.dataclass(frozen=True)
class PrepareArtifacts:
    """Locate the files `prepare` writes for one city.

    Treat this as a fixed contract: `prepare` is out of scope for the
    SQL-to-Python migration, so these names and locations are given, not
    chosen. Every path is relative to `prepare`'s per-city working directory,
    `<data_dir>/<slug>`.

    Parameters
    ----------
    data_dir
        The per-city working directory, `<data_dir>/<slug>`.
    slug
        The slugified `city, region, country` query.
    """

    data_dir: pathlib.Path
    slug: str

    @classmethod
    def resolve(
        cls,
        data_dir: pathlib.Path,
        country: str,
        city: str,
        region: str | None = None,
    ) -> "PrepareArtifacts":
        """Derive the artifact locations the way `prepare` derives them.

        Parameters
        ----------
        data_dir
            The root data directory, the same value `prepare` was given.
        country
            Country name.
        city
            City name.
        region
            Region/state name, if any.

        Returns
        -------
        PrepareArtifacts
            The resolved artifact set.

        Examples
        --------
        >>> import pathlib
        >>> a = PrepareArtifacts.resolve(
        ...     pathlib.Path("data"), "united states", "santa rosa", "new mexico"
        ... )
        >>> a.slug
        'santa-rosa-new-mexico-united-states'
        >>> a.city_osm.name
        'santa-rosa-new-mexico-united-states.osm'
        >>> a.census_blocks.name
        'population.shp'
        """
        country = utils.normalize_country_name(country)
        _, _, slug = analysis.osmnx_query(country, city, region)
        return cls(data_dir=data_dir / slug, slug=slug)

    @property
    def boundary(self) -> pathlib.Path:
        """Return the city boundary shapefile, the source of the output SRID."""
        return self.data_dir / f"{self.slug}.shp"

    @property
    def boundary_geojson(self) -> pathlib.Path:
        """Return the city boundary as GeoJSON, in EPSG:4326."""
        return self.data_dir / f"{self.slug}.geojson"

    @property
    def city_osm(self) -> pathlib.Path:
        """Return the city OSM extract, as OSM XML.

        `prepare` writes XML, not protobuf, because `osmium extract` infers the
        format from this extension. `pyrosm` reads protobuf only, so
        :func:`as_protobuf` converts it first.
        """
        return self.data_dir / f"{self.slug}.osm"

    @property
    def census_blocks(self) -> pathlib.Path:
        """Return the census blocks shapefile.

        Always `population.shp`, whether it came from the US Census, WorldPop,
        or the synthetic-grid fallback for non-US cities.
        """
        return self.data_dir / "population.shp"

    @property
    def state_speed_limits(self) -> pathlib.Path:
        """Return the US state speed limit CSV."""
        return self.data_dir / "state_fips_speed.csv"

    @property
    def city_speed_limits(self) -> pathlib.Path:
        """Return the city speed limit CSV."""
        return self.data_dir / "city_fips_speed.csv"

    def lodes(self, state_abbrev: str, part: str, year: int) -> pathlib.Path:
        """Return one LODES employment CSV.

        Parameters
        ----------
        state_abbrev
            Two-letter state abbreviation, lowercased by `prepare`.
        part
            LODES part, `main` or `aux`.
        year
            LODES year.

        Returns
        -------
        pathlib.Path
            Path to the CSV.
        """
        return self.data_dir / f"{state_abbrev}_od_{part}_JT00_{year}.csv"

    def require(self, *paths: pathlib.Path) -> None:
        """Fail with one message naming every missing artifact.

        Parameters
        ----------
        *paths
            Artifacts that must exist.

        Raises
        ------
        IngestError
            If any path is missing.
        """
        missing = [str(p) for p in paths if not p.exists()]
        if missing:
            raise errors.IngestError(
                "`prepare` outputs are missing; run `bna prepare` first: "
                + ", ".join(missing),
            )


def output_srid(artifacts: PrepareArtifacts) -> int:
    """Derive the projected CRS the analysis runs in.

    Match `utils.get_srid`: estimate the UTM zone from the boundary. Every
    length, azimuth, and cost downstream is computed in this CRS -- doing that
    work in EPSG:4326 silently produces degrees, which round to zero.

    Parameters
    ----------
    artifacts
        The resolved `prepare` outputs.

    Returns
    -------
    int
        The EPSG code of the projected CRS.
    """
    artifacts.require(artifacts.boundary)
    return utils.get_srid(artifacts.boundary)


def as_protobuf(
    osm_xml: pathlib.Path,
    destination: pathlib.Path | None = None,
) -> pathlib.Path:
    """Convert an OSM XML extract to protobuf, for `pyrosm`.

    `prepare` writes `<slug>.osm` as XML, which `pyrosm` refuses. Conversion is
    cheap (well under a second even for a large city) and shrinks the file by
    roughly 20x, so it is done here rather than by changing `prepare`, which is
    out of scope for this migration.

    Parameters
    ----------
    osm_xml
        The OSM XML extract written by `prepare`.
    destination
        Where to write the protobuf. Defaults to the input path with an
        `.osm.pbf` suffix.

    Returns
    -------
    pathlib.Path
        The protobuf file, reused as-is if it already exists.
    """
    destination = destination or osm_xml.with_suffix(".osm.pbf")
    if destination.exists():
        logger.debug(f"reusing existing protobuf extract: {destination}")
        return destination
    logger.info(f"converting {osm_xml.name} to protobuf...")
    runner.run(
        [
            "osmium",
            "cat",
            str(osm_xml.resolve(strict=True)),
            "-o",
            str(destination.resolve()),
        ],
    )
    return destination


def read_ways(protobuf: pathlib.Path) -> gpd.GeoDataFrame:
    """Read the routable ways out of an OSM protobuf extract.

    Parameters
    ----------
    protobuf
        An OSM protobuf extract, from :func:`as_protobuf`.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per OSM way, carrying the node sequence (`u`/`v` per sub-edge)
        and every tag in :data:`OSM_WAY_TAGS` that the extract defines.

    Raises
    ------
    IngestError
        If the extract yields no routable ways.
    """
    from pyrosm import OSM  # noqa: PLC0415

    osm = OSM(str(protobuf.resolve(strict=True)))
    # Ask for every tag explicitly. `pyrosm` returns a fixed default set and
    # silently omits anything else, and an omitted tag does not raise -- it
    # just changes a derived feature. `golf`/`golf_cart` reaching
    # `functional_class.sql` as NULL misclassified 37 golf-cart paths in
    # St. Louis Park before this was made exhaustive.
    nodes, edges = osm.get_network(
        network_type="all",
        nodes=True,
        extra_attributes=list(OSM_WAY_TAGS),
    )
    if edges is None or edges.empty:
        raise errors.IngestError(f"no routable ways found in {protobuf}")
    logger.debug(f"read {len(edges):,} sub-edges and {len(nodes):,} nodes")
    return edges


def _merge_chunk(geometries: list[shapely.geometry.base.BaseGeometry]) -> typing.Any:
    """Join consecutive sub-edges into a single LineString.

    `union_all` is not enough: unioning two connected LineStrings yields a
    MultiLineString, and everything downstream (start/end point, midpoint,
    azimuth, turn angle) assumes one continuous LineString per road.

    Parameters
    ----------
    geometries
        Sub-edge geometries, in travel order.

    Returns
    -------
    shapely.geometry.base.BaseGeometry
        A LineString when the pieces connect, otherwise the merged
        MultiLineString the input actually describes.
    """
    if len(geometries) == 1:
        return geometries[0]
    merged = shapely.line_merge(shapely.MultiLineString(geometries))
    if not isinstance(merged, shapely.LineString):
        return merged
    # `line_merge` is free to start a closed ring wherever it likes, and it
    # does not pick the node the way itself started from. Rotate it back:
    # `intersection_from`/`intersection_to` name that node, and a road whose
    # geometry starts somewhere else contradicts its own columns
    # (findings.md §2.9).
    coordinates = shapely.get_coordinates(merged)
    start = shapely.get_coordinates(geometries[0])[0]
    if not (coordinates[0] == coordinates[-1]).all():
        return merged
    offsets = np.flatnonzero((coordinates[:-1] == start).all(axis=1))
    if not offsets.size or offsets[0] == 0:
        return merged
    offset = int(offsets[0])
    rotated = np.concatenate(
        [coordinates[offset:-1], coordinates[: offset + 1]],
    )
    return shapely.LineString(rotated)


def read_point_features(protobuf: pathlib.Path) -> gpd.GeoDataFrame:
    """Read the tagged OSM nodes the intersection rules consult.

    The analogue of `neighborhood_osm_full_point`. The intersection scripts
    (`signalized.sql`, `stops.sql`, `rrfb.sql`, `island.sql`) look for traffic
    signals, stop signs, and pedestrian crossings -- both exactly on an
    intersection node and within a search radius of one.

    Parameters
    ----------
    protobuf
        An OSM protobuf extract, from :func:`as_protobuf`.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per matching node, with `id`, `geometry`, and the tags in
        :data:`OSM_POINT_TAGS` that the extract defines. Empty when the
        extract has no such nodes.
    """
    from pyrosm import OSM  # noqa: PLC0415

    osm = OSM(str(protobuf.resolve(strict=True)))
    points = osm.get_data_by_custom_criteria(
        custom_filter={"highway": list(OSM_POINT_HIGHWAY_VALUES)},
        filter_type="keep",
        keep_nodes=True,
        keep_ways=False,
        keep_relations=False,
        extra_attributes=list(OSM_POINT_TAGS),
    )
    if points is None or points.empty:
        logger.debug("no tagged point features in the extract")
        return gpd.GeoDataFrame(
            {"id": [], "geometry": []},
            geometry="geometry",
            crs="EPSG:4326",
        )  # ty:ignore[no-matching-overload]
    logger.debug(f"read {len(points):,} tagged point features")
    return points


def shared_nodes(osm_xml: pathlib.Path) -> set[int]:
    """Find the nodes `osm2pgrouting` cuts ways at.

    Two kinds qualify:

    1. **A node two or more ways touch** -- and "way" here means *any* way in
       the extract, not only the routable ones: a road is split where a
       building outline, a barrier, or a stream shares one of its nodes just
       as much as where another road does. Restricting the count to routable
       ways undercounts the cuts and merges roads the SQL keeps separate.
    2. **A node carrying a `highway` value from `mapconfig_highway.xml`**,
       even where only one way uses it. `osm2pgrouting` reads that config for
       nodes as well as ways, so a motorway exit tagged
       `highway=motorway_junction` mid-way is a vertex and cuts the road there
       (findings.md §3.11).

    Streamed with `iterparse` so a large extract costs little memory: only the
    node references are retained, and each element is discarded once counted.

    Parameters
    ----------
    osm_xml
        The OSM XML extract written by `prepare`.
    Returns
    -------
    set of int
        Node ids to cut at.
    """
    seen: set[int] = set()
    shared: set[int] = set()
    tagged: set[int] = set()
    # The extract is a local file this pipeline's own `prepare` step
    # produced with osmium, not untrusted input.
    for _, element in ET.iterparse(osm_xml, events=("end",)):  # noqa: S314
        if element.tag == "node":
            highway = next(
                (
                    tag.get("v")
                    for tag in element.iterfind("tag")
                    if tag.get("k") == "highway"
                ),
                None,
            )
            if highway in OSM_HIGHWAY_TYPES:
                identifier = element.get("id")
                if identifier is not None:
                    tagged.add(int(identifier))
            element.clear()
            continue
        if element.tag != "way":
            continue
        for reference in {nd.get("ref") for nd in element.iterfind("nd")}:
            if reference is None:
                continue
            node = int(reference)
            if node in seen:
                shared.add(node)
            else:
                seen.add(node)
        element.clear()
    logger.debug(
        f"{len(shared):,} nodes shared by 2+ ways, "
        f"{len(tagged - shared):,} more tagged as a highway node",
    )
    return shared | tagged


def read_nodes(protobuf: pathlib.Path) -> gpd.GeoDataFrame:
    """Read the network node geometries, for locating intersections.

    Parameters
    ----------
    protobuf
        An OSM protobuf extract, from :func:`as_protobuf`.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per node with `id` and `geometry`.
    """
    from pyrosm import OSM  # noqa: PLC0415

    osm = OSM(str(protobuf.resolve(strict=True)))
    nodes, _ = osm.get_network(network_type="all", nodes=True)
    if nodes is None or nodes.empty:
        raise errors.IngestError(f"no network nodes found in {protobuf}")
    return nodes[["id", "geometry"]]


def split_ways_at_intersections(
    edges: gpd.GeoDataFrame,
    cut_nodes: set[int] | None = None,
) -> gpd.GeoDataFrame:
    """Split OSM ways into road segments the way `osm2pgrouting` does.

    A way is cut at every interior node it shares with another way; nodes used
    by only one way stay interior to the segment. This is what defines a "road"
    for the rest of the pipeline, and it matches neither `pyrosm`'s
    segmentation (which cuts at every node) nor `osmnx`'s simplified graph, so
    it is derived here rather than taken from either.

    Parameters
    ----------
    edges
        Sub-edges from :func:`read_ways`, carrying `id` (the OSM way id) plus
        `u`/`v` node ids.
    cut_nodes
        Nodes to cut at, from :func:`shared_nodes`. When omitted, the cut set
        is derived from the routable ways in `edges` alone, which undercounts
        real intersections -- pass the full set for anything but a synthetic
        test.

    Returns
    -------
    geopandas.GeoDataFrame
        One row per road segment, with `intersection_from`/`intersection_to`
        node ids and the way's tags carried through.
    """
    required = {"id", "u", "v"}
    if not required.issubset(edges.columns):
        raise errors.IngestError(
            f"edges are missing {sorted(required - set(edges.columns))}; "
            "they must come from `read_ways`",
        )

    if cut_nodes is not None:
        shared: set[typing.Any] = cut_nodes
    else:
        # Fallback: a node is an intersection when two or more of the ways
        # present here touch it.
        ways_per_node = (
            pd.concat(
                [
                    edges[["u", "id"]].rename(columns={"u": "node"}),
                    edges[["v", "id"]].rename(columns={"v": "node"}),
                ],
            )
            .drop_duplicates()
            .groupby("node")["id"]
            .size()
        )
        shared = set(ways_per_node.index[ways_per_node > 1])
    logger.debug(f"{len(shared):,} intersection nodes")

    segments = []
    tag_columns = [tag for tag in OSM_WAY_TAGS if tag in edges.columns]
    for way_id, group in edges.groupby("id", sort=False):
        # Pull the columns out once per way: indexing a mixed-dtype frame row
        # by row is what dominated the whole pipeline's run time.
        sources = group["u"].tolist()
        targets = group["v"].tolist()
        geometries = group.geometry.tolist()
        # Every sub-edge of a way carries the way's tags, so read them once.
        first = group.iloc[0]
        tags = {tag: first[tag] for tag in tag_columns}
        # A node the way itself visits twice (a loop closing on itself) is an
        # intersection just as much as one shared with another way, and must be
        # cut at: leaving it joined produces a self-touching ring that cannot be
        # merged into a single LineString.
        visits = collections.Counter([sources[0], *targets])
        revisited = {node for node, count in visits.items() if count > 1}
        run_start = 0
        last = len(targets) - 1
        for position, node in enumerate(targets):
            if position == last or node in shared or node in revisited:
                segments.append(
                    {
                        "osm_id": way_id,
                        "intersection_from": sources[run_start],
                        "intersection_to": node,
                        "geometry": _merge_chunk(geometries[run_start : position + 1]),
                        **tags,
                    },
                )
                run_start = position + 1

    frame = gpd.GeoDataFrame(
        segments,
        geometry="geometry",
        crs=edges.crs,
    )  # ty:ignore[no-matching-overload]
    frame.insert(0, "road_id", range(1, len(frame) + 1))
    logger.info(f"split {edges['id'].nunique():,} ways into {len(frame):,} segments")
    return frame


def load_boundary(
    artifacts: PrepareArtifacts,
    srid: int,
) -> gpd.GeoDataFrame:
    """Load the city boundary, projected into the analysis CRS.

    Parameters
    ----------
    artifacts
        The resolved `prepare` outputs.
    srid
        The projected CRS to reproject into, from :func:`output_srid`.

    Returns
    -------
    geopandas.GeoDataFrame
        The boundary polygon(s).
    """
    artifacts.require(artifacts.boundary)
    return gpd.read_file(artifacts.boundary).to_crs(epsg=srid)


def load_census_blocks(
    artifacts: PrepareArtifacts,
    boundary: gpd.GeoDataFrame,
    srid: int,
    country: str,
) -> gpd.GeoDataFrame:
    """Load the census blocks and apply the same filters the SQL import did.

    Reproduce `ingestor.import_neighborhood`: drop blocks that fall outside the
    boundary or overlap it too little, drop US water blocks, then refuse to
    continue if nobody lives in what is left.

    Parameters
    ----------
    artifacts
        The resolved `prepare` outputs.
    boundary
        The city boundary, already in `srid`.
    srid
        The projected CRS to work in.
    country
        Country name, deciding the overlap threshold and water-block handling.

    Returns
    -------
    geopandas.GeoDataFrame
        The retained census blocks.

    Raises
    ------
    InsufficientDataError
        If the retained blocks hold no population.
    """
    artifacts.require(artifacts.census_blocks)
    blocks = gpd.read_file(artifacts.census_blocks).to_crs(epsg=srid)
    blocks.columns = [c.lower() for c in blocks.columns]

    is_usa = utils.is_usa(country)
    min_overlap = US_MIN_OVERLAP_RATIO if is_usa else INTERNATIONAL_MIN_OVERLAP_RATIO

    boundary_geom = boundary.geometry.union_all()
    overlap = blocks.geometry.intersection(boundary_geom).area / blocks.geometry.area
    kept = blocks[blocks.geometry.intersects(boundary_geom) & (overlap >= min_overlap)]
    logger.debug(
        f"kept {len(kept):,}/{len(blocks):,} blocks (overlap >= {min_overlap})",
    )

    if is_usa and "aland20" in kept.columns:
        kept = kept[kept["aland20"] != 0]
        logger.debug(f"{len(kept):,} blocks remain after dropping water blocks")

    population = int(kept["pop20"].sum()) if "pop20" in kept.columns else 0
    if population == 0:
        raise errors.InsufficientDataError(
            "the population cannot be equal to zero; "
            f"no inhabitants found in {len(kept):,} census blocks",
        )
    logger.info(f"{len(kept):,} census blocks, population {population:,}")
    return kept.reset_index(drop=True)


def clip_to_census_blocks(
    osm_xml: pathlib.Path,
    census_blocks: gpd.GeoDataFrame,
) -> pathlib.Path:
    """Clip the OSM extract to the bounding box of the retained census blocks.

    Reproduce the `osmconvert` step `ingestor.import_osm_data` runs before
    handing the extract to `osm2pgrouting`. The box comes from
    `retrieve_boundary_box`, which takes the EPSG:4326 extent of
    `neighborhood_census_blocks` *after* the out-of-buffer and water blocks
    have been removed -- so it is tighter than the boundary, and tighter still
    for a coastal city whose water blocks are gone.

    This is not cosmetic. `--drop-broken-refs` discards way nodes that fall
    outside the box, which changes where ways get cut and therefore how many
    road segments exist. Skipping it leaves a handful of excess segments in
    most cities (Alvarado +16, Jackson +11, Cañon City +4, Provincetown +2);
    applying it made all four match their `results/**` baseline exactly.

    Parameters
    ----------
    osm_xml
        The OSM XML extract written by `prepare`.
    census_blocks
        The retained census blocks, from :func:`load_census_blocks`.

    Returns
    -------
    pathlib.Path
        The clipped extract, reused as-is if it already exists.
    """
    clipped = osm_xml.with_suffix(".clipped.osm")
    if clipped.exists():
        logger.debug(f"reusing existing clipped extract: {clipped}")
        return clipped
    minx, miny, maxx, maxy = census_blocks.to_crs(epsg=4326).total_bounds
    logger.info(f"clipping {osm_xml.name} to the census block extent...")
    return runner.run_osm_convert(osm_xml, (minx, miny, maxx, maxy))


def load_jobs(
    artifacts: PrepareArtifacts,
    state_abbrev: str,
    lodes_year: int,
) -> pd.DataFrame:
    """Load the LODES employment data for a US state.

    Parameters
    ----------
    artifacts
        The resolved `prepare` outputs.
    state_abbrev
        Two-letter state abbreviation.
    lodes_year
        LODES year, as resolved by `prepare`.

    Returns
    -------
    pandas.DataFrame
        The concatenated `main` and `aux` origin-destination records. Empty
        when the state has no LODES data, which is the case for Puerto Rico.
    """
    frames: list[pd.DataFrame] = []
    for part in ("main", "aux"):
        csv = artifacts.lodes(state_abbrev.lower(), part, lodes_year)
        if not csv.exists():
            logger.warning(f"no LODES {part} data at {csv}")
            continue
        frames.append(pd.read_csv(csv, dtype={"w_geocode": str, "h_geocode": str}))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def ingest(
    data_dir: pathlib.Path,
    country: str,
    city: str,
    region: str | None = None,
) -> dict[str, typing.Any]:
    """Ingest every `prepare` output for one city.

    Parameters
    ----------
    data_dir
        The root data directory `prepare` was given.
    country
        Country name.
    city
        City name.
    region
        Region/state name, if any.

    Returns
    -------
    dict
        The ingested frames plus the analysis CRS, keyed `srid`, `boundary`,
        `census_blocks`, and `ways`.
    """
    artifacts = PrepareArtifacts.resolve(data_dir, country, city, region)
    srid = output_srid(artifacts)
    logger.info(f"ingesting {artifacts.slug} in EPSG:{srid}")

    boundary = load_boundary(artifacts, srid)
    census_blocks = load_census_blocks(artifacts, boundary, srid, country)

    artifacts.require(artifacts.city_osm)
    # The clip depends on the census blocks, so it has to follow them.
    clipped = clip_to_census_blocks(artifacts.city_osm, census_blocks)
    protobuf = as_protobuf(clipped)
    edges = read_ways(protobuf)
    cut_nodes = shared_nodes(clipped)
    ways = split_ways_at_intersections(edges, cut_nodes).to_crs(epsg=srid)
    nodes = read_nodes(protobuf).to_crs(epsg=srid)
    points = read_point_features(protobuf)
    if not points.empty:
        points = points.to_crs(epsg=srid)
    destinations = read_destinations(protobuf)
    if not destinations.empty:
        destinations = destinations.to_crs(epsg=srid)

    return {
        "srid": srid,
        "boundary": boundary,
        "census_blocks": census_blocks,
        "ways": ways,
        "nodes": nodes,
        "points": points,
        "destinations": destinations,
    }
