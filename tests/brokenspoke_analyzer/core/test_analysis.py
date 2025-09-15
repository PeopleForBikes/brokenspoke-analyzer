"""Test the analysis module."""

from brokenspoke_analyzer.core import analysis

from osmnx import (
    geocoder,
    settings,
)


def test_osmnx_query_multipolygon():
    """Ensure the osmnx query returns a multypoligon."""
    settings.log_console = True
    structured_query, _ = analysis.osmnx_query(
        country="united states", city="claymont", state="delaware"
    )
    try:
        city_gdf = geocoder.geocode_to_gdf(structured_query)
    except TypeError as e:
        q = [structured_query["city"], structured_query["country"]]
        if structured_query.get("state"):
            q.insert(1, structured_query["state"])
        string_query = ", ".join(q)
        city_gdf = geocoder.geocode_to_gdf(string_query)
    city_gdf_type = city_gdf["class"].iloc[0]
    print(city_gdf_type)
    assert city_gdf_type == "boundary"
