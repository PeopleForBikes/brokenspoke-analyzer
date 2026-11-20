"""Test the datasource module."""

import pytest

from brokenspoke_analyzer_lib.core import datasource

GEOFABRIK = "https://download.geofabrik.de"


@pytest.mark.parametrize(
    ("region", "expected_path"),
    [
        # From pyrosm.
        ("new mexico", "north-america/us/new-mexico/new-mexico-latest.osm.pbf"),
        (
            "district of columbia",
            "north-america/us/district-of-columbia/district-of-columbia-latest.osm.pbf",
        ),
        (
            "southern california",
            "north-america/us/california/socal/socal-latest.osm.pbf",
        ),
        ("usa", "north-america/us/us-latest.osm.pbf"),
        ("france", "europe/france/france-latest.osm.pbf"),
        ("ontario", "north-america/canada/ontario/ontario-latest.osm.pbf"),
        ("aragón", "europe/spain/aragon/aragon-latest.osm.pbf"),
        (
            "castilla y león",
            "europe/spain/castilla-y-leon/castilla-y-leon-latest.osm.pbf",
        ),
        # From the custom region name mapping.
        ("madrid", "europe/spain/madrid/madrid-latest.osm.pbf"),
        (
            "malaysia",
            "asia/malaysia-singapore-brunei/malaysia-singapore-brunei-latest.osm.pbf",
        ),
        # From the custom URL mapping.
        ("georgia", "north-america/us/georgia/georgia-latest.osm.pbf"),
        ("berlin", "europe/germany/berlin/berlin-latest.osm.pbf"),
        (
            "cocos islands",
            "australia-oceania/australia/cocos-islands/cocos-islands-latest.osm.pbf",
        ),
    ],
)
def test_osm_adapter_urls(region: str, expected_path: str) -> None:
    """Ensure the OSM adapter points to the current Geofabrik URLs."""
    expected_url = f"{GEOFABRIK}/{expected_path}"
    adapter = datasource.OSMAdapter(region)
    assert str(adapter.urls[0]) == expected_url
    assert str(adapter.urls[1]) == f"{expected_url}.md5"
    assert adapter.files[0].name == expected_path.rsplit("/", 1)[1]
