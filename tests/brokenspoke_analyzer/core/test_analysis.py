"""Test the analysis module."""

from osmnx import (
    geocoder,
    settings,
)

from brokenspoke_analyzer.core import analysis


def test_osmnx_query_multipolygon():
    """Ensure the osmnx query returns a multypoligon."""
    settings.log_console = True
    structured_query, q, _ = analysis.osmnx_query(
        country="united states", city="claymont", state="delaware"
    )
    try:
        city_gdf = geocoder.geocode_to_gdf(structured_query)
    except TypeError as e:
        city_gdf = geocoder.geocode_to_gdf(q)
    city_gdf_type = city_gdf["class"].iloc[0]
    print(city_gdf_type)
    assert city_gdf_type == "boundary"
