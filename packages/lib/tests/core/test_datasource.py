"""Test the datasource module."""

import pytest

from bna.lib.core import datasource

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
        ("act", "australia-oceania/australia/act/act-latest.osm.pbf"),
        (
            "cocos islands",
            "australia-oceania/australia/cocos-islands/cocos-islands-latest.osm.pbf",
        ),
        # From the custom region name mapping.
        (
            "australian capital territory",
            "australia-oceania/australia/act/act-latest.osm.pbf",
        ),
        ("berlin", "europe/germany/berlin/berlin-latest.osm.pbf"),
        ("bremen", "europe/germany/bremen/bremen-latest.osm.pbf"),
        (
            "bristol",
            "europe/united-kingdom/england/bristol/bristol-latest.osm.pbf",
        ),
        (
            "brunei",
            "asia/malaysia-singapore-brunei/malaysia-singapore-brunei-latest.osm.pbf",
        ),
        ("czechia", "europe/czech-republic/czech-republic-latest.osm.pbf"),
        ("georgia", "north-america/us/georgia/georgia-latest.osm.pbf"),
        ("groningen", "europe/netherlands/groningen/groningen-latest.osm.pbf"),
        ("hamburg", "europe/germany/hamburg/hamburg-latest.osm.pbf"),
        (
            "ireland",
            "europe/ireland-and-northern-ireland/ireland-and-northern-ireland-latest.osm.pbf",
        ),
        ("madrid", "europe/spain/madrid/madrid-latest.osm.pbf"),
        (
            "malaysia",
            "asia/malaysia-singapore-brunei/malaysia-singapore-brunei-latest.osm.pbf",
        ),
        (
            "northern ireland",
            "europe/ireland-and-northern-ireland/ireland-and-northern-ireland-latest.osm.pbf",
        ),
        (
            "singapore",
            "asia/malaysia-singapore-brunei/malaysia-singapore-brunei-latest.osm.pbf",
        ),
        ("utrecht", "europe/netherlands/utrecht/utrecht-latest.osm.pbf"),
        (
            "victoria",
            "australia-oceania/australia/victoria/victoria-latest.osm.pbf",
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
