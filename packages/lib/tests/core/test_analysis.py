"""Test the analysis module."""

lazy import pathlib

import geopandas as gpd
import shapely
from osmnx import (
    geocoder,
    settings,
)

from bna.lib.core import (
    analysis,
)


def test_osmnx_query_multipolygon():
    """Ensure the osmnx query returns a multypoligon."""
    settings.log_console = True
    structured_query, q, _ = analysis.osmnx_query(
        country="united states", city="claymont", state="delaware"
    )
    try:
        city_gdf = geocoder.geocode_to_gdf(structured_query)
    except TypeError:
        city_gdf = geocoder.geocode_to_gdf(q)
    city_gdf_type = city_gdf["class"].iloc[0]
    print(city_gdf_type)
    assert city_gdf_type == "boundary"


def test_create_synthetic_population_from_file(tmp_path: pathlib.Path) -> None:
    """Ensure the area of a file is divided into populated square blocks."""
    # A square of about 1.1 km x 0.8 km around Paris.
    area = gpd.GeoDataFrame(
        geometry=[shapely.geometry.box(2.34, 48.85, 2.35, 48.86)], crs="EPSG:4326"
    )  # ty:ignore[no-matching-overload]
    boundary_file = tmp_path / "paris.geojson"
    area.to_file(boundary_file)

    population = analysis.create_synthetic_population_from_file(
        boundary_file, block_size=500, population=50
    )

    assert population.crs == area.crs
    assert len(population) > 0
    assert set(population["POP20"]) == {50}
    assert population.geometry.intersects(area.geometry.iloc[0]).all()
