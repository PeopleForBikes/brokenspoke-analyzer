"""
Write the pipeline's results to the files the BNA publishes.

Replace `exporter.py`'s PostGIS-backed export with one that writes the
in-memory frames the pipeline already holds. The file *set*, the column names,
and the column order are unchanged -- only the source of the data and the file
names differ.

**The `neighborhood_` prefix is dropped** (requirements.md FR-EXPORT-2). It was
a holdover from a schema that only ever analyses one boundary at a time, so
`neighborhood_ways.shp` becomes `ways.shp`. This is a rename, not a behaviour
change, and the parity harness maps old names to new before comparing.
"""

import pathlib
import typing

import geopandas as gpd
import numpy as np
import pandas as pd
from loguru import logger

# Column order for each exported layer, taken from the SQL table definitions.
# Order is part of the contract (FR-EXPORT-1), so these are explicit lists
# rather than whatever order the pipeline happens to build.
WAYS_COLUMNS = (
    "road_id",
    "osm_id",
    "tag_id",
    "name",
    "intersection_from",
    "intersection_to",
    "oneway",
    "tdg_id",
    "functional_class",
    "path_id",
    "speed_limit",
    "one_way_car",
    "one_way",
    "width_ft",
    "ft_bike_infra",
    "ft_bike_infra_width",
    "tf_bike_infra",
    "tf_bike_infra_width",
    "ft_lanes",
    "tf_lanes",
    "ft_cross_lanes",
    "tf_cross_lanes",
    "twltl_cross_lanes",
    "ft_park",
    "tf_park",
    "ft_seg_stress",
    "ft_int_stress",
    "tf_seg_stress",
    "tf_int_stress",
    "xwalk",
)

# Column order for `census_blocks`: the shapefile's own fields first, then the
# score columns in the order `census_blocks.sql` adds them.
CENSUS_BLOCK_COLUMNS = (
    "gid",
    "statefp20",
    "countyfp20",
    "tractce20",
    "blockce20",
    "geoid20",
    "name20",
    "mtfcc20",
    "ur20",
    "uace20",
    "uatype20",
    "funcstat20",
    "aland20",
    "awater20",
    "intptlat20",
    "intptlon20",
    "housing20",
    "pop20",
    "road_ids",
    "pop_low_stress",
    "pop_high_stress",
    "pop_score",
    "emp_low_stress",
    "emp_high_stress",
    "emp_score",
    "schools_low_stress",
    "schools_high_stress",
    "schools_score",
    "universities_low_stress",
    "universities_high_stress",
    "universities_score",
    "colleges_low_stress",
    "colleges_high_stress",
    "colleges_score",
    "doctors_low_stress",
    "doctors_high_stress",
    "doctors_score",
    "dentists_low_stress",
    "dentists_high_stress",
    "dentists_score",
    "hospitals_low_stress",
    "hospitals_high_stress",
    "hospitals_score",
    "pharmacies_low_stress",
    "pharmacies_high_stress",
    "pharmacies_score",
    "retail_low_stress",
    "retail_high_stress",
    "retail_score",
    "supermarkets_low_stress",
    "supermarkets_high_stress",
    "supermarkets_score",
    "social_services_low_stress",
    "social_services_high_stress",
    "social_services_score",
    "parks_low_stress",
    "parks_high_stress",
    "parks_score",
    "trails_low_stress",
    "trails_high_stress",
    "trails_score",
    "community_centers_low_stress",
    "community_centers_high_stress",
    "community_centers_score",
    "transit_low_stress",
    "transit_high_stress",
    "transit_score",
    "overall_score",
    "reachable_blocks",
    "opportunity_score",
    "core_services_score",
    "recreation_score",
)

INTERSECTION_COLUMNS = (
    "int_id",
    "osm_id",
    "legs",
    "signalized",
    "stops",
    "rrfb",
    "island",
)

# The destination categories exported as their own GeoJSON layer, with the
# name each `connectivity/destinations/*.sql` table gave its `name` column.
# Retail is clustered from the outset and its table has neither an `osm_id`
# nor a name.
DESTINATION_LAYERS: dict[str, str | None] = {
    "colleges": "college_name",
    "community_centers": "center_name",
    "dentists": "dentists_name",
    "doctors": "doctors_name",
    "hospitals": "hospital_name",
    "parks": "park_name",
    "pharmacies": "pharmacy_name",
    "retail": None,
    "schools": "school_name",
    "social_services": "service_name",
    "supermarkets": "supermarket_name",
    "transit": "transit_name",
    "universities": "college_name",
}

# The population shed every destination table carries.
DESTINATION_SHED_COLUMNS = ("pop_low_stress", "pop_high_stress", "pop_score")

# Layers written as both shapefile and GeoJSON, versus GeoJSON only.
SHAPEFILE_LAYERS = ("census_blocks", "ways")

# Exports are published in EPSG:4326 regardless of the analysis CRS.
EXPORT_CRS = 4326


def _destination_layer(
    frame: gpd.GeoDataFrame,
    name_column: str | None,
) -> gpd.GeoDataFrame:
    """Shape one destination category the way its SQL table was published.

    Each `generated.neighborhood_<category>` table carried two geometries,
    `geom_pt` and `geom_poly`, and the GeoJSON export (`ogr2ogr ... select
    *`) took the first: the published geometry is the centroid, never the
    polygon. The columns follow the table definition: a serial `id`, the
    blocks, the OSM id and name where the category records them, then the
    population shed.

    Parameters
    ----------
    frame
        One category's destinations, from `scoring.extract_destinations`
        with the shed attached.
    name_column
        The table's name for the `name` column, or None for a category that
        records neither `osm_id` nor a name.

    Returns
    -------
    geopandas.GeoDataFrame
        The layer as published.
    """
    columns: dict[str, typing.Any] = {"id": np.arange(1, len(frame) + 1)}
    # `array((SELECT ...))` over no blocks is an empty array, which `ogr2ogr`
    # wrote as a null property; and a nullable string must reach the writer
    # as None, not as pandas' `<NA>` sentinel spelled out.
    columns["blockid20"] = [
        list(blocks) if len(blocks) else None for blocks in frame["blockid20"]
    ]
    if name_column is not None:
        columns["osm_id"] = frame["osm_id"].to_numpy()
        names = frame["name"].astype(object)
        columns[name_column] = names.where(names.notna(), None).to_numpy()
    for column in DESTINATION_SHED_COLUMNS:
        columns[column] = frame[column].to_numpy()
    return gpd.GeoDataFrame(
        columns,
        geometry=frame.geometry.centroid.to_numpy(),
        crs=frame.crs,
    )  # ty:ignore[no-matching-overload]


def _with_gid(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Prepend the `gid` serial column `shp2pgsql` created on import.

    Every layer loaded through `shp2pgsql` carried a `gid` primary key, and it
    survives into the exports. It has no analytical meaning, but consumers read
    these files by schema, so it is reproduced.

    Parameters
    ----------
    frame
        The layer to number.

    Returns
    -------
    geopandas.GeoDataFrame
        The layer with a leading 1-based `gid`.
    """
    numbered = frame.copy()
    numbered.insert(0, "gid", range(1, len(numbered) + 1))
    return numbered


def _lowercase_columns(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Lowercase every column name.

    PostgreSQL folds unquoted identifiers to lower case, so a shapefile loaded
    with upper-case field names came back lower-cased in the exports.

    Parameters
    ----------
    frame
        The layer to rename.

    Returns
    -------
    geopandas.GeoDataFrame
        The layer with lower-case column names.
    """
    renamed = frame.copy()
    renamed.columns = [str(c).lower() for c in renamed.columns]
    return renamed


# How `osm2pgrouting` wrote the raw `oneway` tag into `ways.oneway`. It is a
# passthrough column -- the analysis reads `one_way_car`/`one_way`, not this --
# but it is part of the published schema, so the published *spelling* has to
# match. Anything not listed here is upper-cased as-is (`REVERSIBLE` shows up
# that way in the reference exports).
ONEWAY_LABELS = {
    "yes": "YES",
    "true": "YES",
    "1": "YES",
    "no": "NO",
    "false": "NO",
    "0": "NO",
    "-1": "REVERSED",
    "reverse": "REVERSED",
    "reversible": "REVERSIBLE",
}
ONEWAY_ABSENT = "UNKNOWN"

# A junction value, and a highway class, that imply a direction on their own.
ROUNDABOUT = "roundabout"
ONEWAY_HIGHWAY = "motorway"


def _raw_tag(frame: pd.DataFrame, name: str) -> pd.Series:
    """Read a raw OSM tag column, or an all-null one where it is absent."""
    if name in frame.columns:
        return frame[name]
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _oneway_labels(
    values: pd.Series,
    junction: pd.Series | None = None,
    highway: pd.Series | None = None,
) -> pd.Series:
    """Spell the `oneway` tag the way `osm2pgrouting` spelled it.

    A roundabout, and a motorway, are one-way whether or not anyone tagged
    them so, and `osm2pgrouting` wrote `YES` for both. The implication
    **overrules the tag**: `oneway=reversible` on a motorway published as
    `YES` (though on a `motorway_link` it stayed `REVERSIBLE`), and so did
    `oneway=no` on a roundabout (findings.md §1.25). Note that this is the *published
    label* only: `one_way_car`, which the analysis actually reads, comes from
    the raw tag and stays NULL on an untagged roundabout (`one_way.sql`, and
    findings.md §1.15).

    Parameters
    ----------
    values
        The raw OSM `oneway` tag.
    junction
        The raw OSM `junction` tag, when the frame carries it.
    highway
        The raw OSM `highway` tag, when the frame carries it.

    Returns
    -------
    pandas.Series
        The published labels; `UNKNOWN` where nothing implies a direction.

    Examples
    --------
    >>> _oneway_labels(pd.Series(["yes", "-1", "no", None, "alternating"]))
    0         YES
    1    REVERSED
    2          NO
    3     UNKNOWN
    4     UNKNOWN
    dtype: object
    >>> _oneway_labels(pd.Series([None, None]), pd.Series(["roundabout", None]))
    0        YES
    1    UNKNOWN
    dtype: object
    >>> _oneway_labels(
    ...     pd.Series(["reversible", "reversible"]),
    ...     None,
    ...     pd.Series(["motorway", "motorway_link"]),
    ... )
    0           YES
    1    REVERSIBLE
    dtype: object
    >>> _oneway_labels(pd.Series(["no"]), pd.Series(["roundabout"]))
    0    YES
    dtype: object
    """
    tags = values.astype("string").str.strip().str.lower()
    known = tags.map(ONEWAY_LABELS)
    # Anything outside the enum is `UNKNOWN`, not the tag upper-cased:
    # Valencia has an `oneway=alternating` way published as `UNKNOWN`.
    labels = known

    # Both implications **overrule the tag**, not merely fill in for it: a
    # roundabout tagged `oneway=no` still published as `YES`.
    implied = pd.Series(data=False, index=labels.index)
    if junction is not None:
        implied |= (
            junction.astype("string").str.strip().str.lower() == ROUNDABOUT
        ).fillna(value=False)
    if highway is not None:
        implied |= (
            highway.astype("string").str.strip().str.lower() == ONEWAY_HIGHWAY
        ).fillna(value=False)
    labels = labels.mask(implied, "YES")
    return labels.fillna(ONEWAY_ABSENT).astype(object)


def _postgres_csv(frame: pd.DataFrame) -> pd.DataFrame:
    """Spell a CSV the way `COPY ... TO` spelled it.

    Two habits of the PostgreSQL text format are part of what downstream
    consumers parse: booleans are `t`/`f`, and an `INTEGER` column never grows
    a `.0`. pandas writes `True` and `730.0` unless told otherwise.

    Parameters
    ----------
    frame
        The frame about to be written.

    Returns
    -------
    pandas.DataFrame
        The same data, spelled for CSV.

    Examples
    --------
    >>> _postgres_csv(pd.DataFrame({"a": [True, False], "b": [1.0, 2.0]}))
       a  b
    0  t  1
    1  f  2
    """
    result = frame.copy()
    for column in result.columns:
        values = result[column]
        if pd.api.types.is_bool_dtype(values):
            result[column] = values.map({True: "t", False: "f"})
        elif pd.api.types.is_float_dtype(values) and (values.dropna() % 1 == 0).all():
            result[column] = values.astype("Int64")
    return result


def _ordered(frame: pd.DataFrame, columns: typing.Sequence[str]) -> pd.DataFrame:
    """Return the frame with the given columns, in order, filling any gaps.

    A column the pipeline does not produce is emitted as NULL rather than
    omitted: the schema is part of the export contract, and a consumer reading
    by position must not shift.

    Parameters
    ----------
    frame
        The frame to reorder.
    columns
        The required column order, excluding geometry.

    Returns
    -------
    pandas.DataFrame
        The frame with exactly those columns, plus `geometry` if present.
    """
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    keep = [*columns, "geometry"] if "geometry" in result.columns else list(columns)
    return result[keep]


def write_layer(
    frame: gpd.GeoDataFrame | pd.DataFrame,
    export_dir: pathlib.Path,
    name: str,
    *,
    shapefile: bool = False,
) -> list[pathlib.Path]:
    """Write one layer in the formats the BNA publishes.

    Parameters
    ----------
    frame
        The data to write.
    export_dir
        Destination directory.
    name
        File basename, already without the `neighborhood_` prefix.
    shapefile
        Also write an ESRI Shapefile alongside the GeoJSON.

    Returns
    -------
    list of pathlib.Path
        The files written.
    """
    written: list[pathlib.Path] = []
    if isinstance(frame, gpd.GeoDataFrame) and "geometry" in frame.columns:
        published = frame.to_crs(epsg=EXPORT_CRS) if frame.crs else frame
        geojson = export_dir / f"{name}.geojson"
        published.to_file(geojson, driver="GeoJSON")
        written.append(geojson)
        if shapefile:
            target = export_dir / f"{name}.shp"
            # Shapefiles keep the projected CRS; only GeoJSON is published in
            # EPSG:4326, matching what `pgsql2shp` produced.
            frame.to_file(target)
            written.append(target)
    else:
        csv = export_dir / f"{name}.csv"
        frame.to_csv(csv, index=False)
        written.append(csv)
    return written


def export_results(
    results: dict[str, typing.Any],
    export_dir: pathlib.Path,
) -> list[pathlib.Path]:
    """Write every published artifact for one city.

    Reproduce `exporter.TABLE_CATALOG`'s file set from in-memory frames,
    without the `neighborhood_` prefix.

    Parameters
    ----------
    results
        The pipeline output: `ways`, `census_blocks`, `intersections`,
        `boundary`, `destinations`, `connected`, `overall`, `score_inputs`,
        `mileage`, and `residential_speed_limit`.
    export_dir
        Destination directory, created if absent.

    Returns
    -------
    list of pathlib.Path
        Every file written.
    """
    export_dir.mkdir(parents=True, exist_ok=True)
    written: list[pathlib.Path] = []

    ways = results.get("ways")
    if ways is not None:
        ways = ways.assign(
            oneway=_oneway_labels(
                _raw_tag(ways, "oneway"),
                _raw_tag(ways, "junction"),
                _raw_tag(ways, "highway"),
            ),
        )
        written += write_layer(
            _ordered(ways, WAYS_COLUMNS),
            export_dir,
            "ways",
            shapefile=True,
        )

    blocks = results.get("census_blocks")
    if blocks is not None:
        written += write_layer(
            _ordered(_with_gid(blocks), CENSUS_BLOCK_COLUMNS),
            export_dir,
            "census_blocks",
            shapefile=True,
        )

    intersections = results.get("intersections")
    if intersections is not None:
        written += write_layer(
            _ordered(intersections, INTERSECTION_COLUMNS),
            export_dir,
            "ways_intersections",
        )

    boundary = results.get("boundary")
    if boundary is not None:
        written += write_layer(
            _with_gid(_lowercase_columns(boundary)),
            export_dir,
            "boundary",
        )

    for name, frame in (results.get("destinations") or {}).items():
        if name in DESTINATION_LAYERS:
            written += write_layer(
                _destination_layer(frame, DESTINATION_LAYERS[name]),
                export_dir,
                name,
            )

    for key, name in (
        ("connected", "connected_census_blocks"),
        ("overall", "overall_scores"),
        ("score_inputs", "score_inputs"),
        ("mileage", "mileage"),
        ("residential_speed_limit", "residential_speed_limit"),
    ):
        frame = results.get(key)
        if frame is not None:
            written += write_layer(_postgres_csv(frame), export_dir, name)

    logger.info(f"exported {len(written):,} files to {export_dir}")
    return written
