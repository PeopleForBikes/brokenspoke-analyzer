"""Test the export stage.

The file set, column names, and column order are a published contract
(FR-EXPORT-1); only the file *names* change, dropping the `neighborhood_`
prefix (FR-EXPORT-2).
"""

import pathlib

import geopandas as gpd
import pandas as pd
import shapely

from brokenspoke_analyzer.core.pipeline import export

UTM13N = 32613


def layer(**columns: object) -> gpd.GeoDataFrame:
    """Build a one-row geo layer."""
    return gpd.GeoDataFrame(
        {**{k: [v] for k, v in columns.items()}, "geometry": [shapely.Point(0, 0)]},
        geometry="geometry",
        crs=f"EPSG:{UTM13N}",
    )


class TestColumnOrdering:
    """Test that the published schema is preserved."""

    def test_missing_columns_are_emitted_as_null(self) -> None:
        """A column the pipeline never derived is still written.

        The schema is the contract; a consumer reading by position must not
        shift because one value was unavailable.
        """
        got = export._ordered(pd.DataFrame({"b": [1]}), ("a", "b", "c"))
        assert list(got.columns) == ["a", "b", "c"]
        assert pd.isna(got["a"].iloc[0])

    def test_column_order_is_enforced_not_inherited(self) -> None:
        """Columns come out in the declared order, not the frame's."""
        frame = pd.DataFrame({"c": [1], "a": [2], "b": [3]})
        assert list(export._ordered(frame, ("a", "b", "c")).columns) == ["a", "b", "c"]

    def test_geometry_stays_last(self) -> None:
        """Geometry is appended after the declared columns."""
        got = export._ordered(layer(b=1), ("a", "b"))
        assert list(got.columns) == ["a", "b", "geometry"]

    def test_ways_schema_matches_the_sql_table(self) -> None:
        """The declared ways columns are the `neighborhood_ways` schema."""
        assert export.WAYS_COLUMNS[0] == "road_id"
        assert "ft_seg_stress" in export.WAYS_COLUMNS
        assert "geometry" not in export.WAYS_COLUMNS


class TestGidAndCasing:
    """Test the two artifacts of the old `shp2pgsql` import path."""

    def test_gid_is_a_one_based_serial(self) -> None:
        """`gid` reproduces the primary key `shp2pgsql` added."""
        frame = gpd.GeoDataFrame(
            {"x": [1, 2, 3], "geometry": [shapely.Point(i, 0) for i in range(3)]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        got = export._with_gid(frame)
        assert list(got["gid"]) == [1, 2, 3]
        assert list(got.columns)[0] == "gid"

    def test_columns_are_lowercased(self) -> None:
        """PostgreSQL folded unquoted identifiers, so the exports are lower case."""
        got = export._lowercase_columns(layer(STATEFP="08", NAME="x"))
        assert "statefp" in got.columns
        assert "STATEFP" not in got.columns


class TestExportResults:
    """Test the published file set."""

    def results(self) -> dict:
        """Build a minimal pipeline result."""
        return {
            "ways": layer(road_id=1, functional_class="residential"),
            "census_blocks": layer(geoid20="b1", pop20=10),
            "intersections": layer(osm_id=5, legs=3),
            "boundary": layer(NAME="Town"),
            "destinations": {"schools": layer(osm_id=9)},
            "mileage": pd.DataFrame({"feature_type": ["lane"], "total_mileage": [1.0]}),
        }

    def test_drops_the_neighborhood_prefix(self, tmp_path: pathlib.Path) -> None:
        """Published names lose the legacy prefix (FR-EXPORT-2)."""
        export.export_results(self.results(), tmp_path)
        written = {p.name for p in tmp_path.iterdir()}
        assert "ways.geojson" in written
        assert "census_blocks.geojson" in written
        assert not any(n.startswith("neighborhood_") for n in written)

    def test_writes_shapefiles_only_for_the_two_layers_that_had_them(
        self, tmp_path: pathlib.Path
    ) -> None:
        """`ways` and `census_blocks` get shapefiles; nothing else does."""
        export.export_results(self.results(), tmp_path)
        shapefiles = {p.stem for p in tmp_path.glob("*.shp")}
        assert shapefiles == {"ways", "census_blocks"}

    def test_geojson_is_published_in_wgs84(self, tmp_path: pathlib.Path) -> None:
        """GeoJSON is reprojected to EPSG:4326 whatever the analysis CRS."""
        export.export_results(self.results(), tmp_path)
        got = gpd.read_file(tmp_path / "ways.geojson")
        assert got.crs.to_epsg() == export.EXPORT_CRS

    def test_tabular_results_are_written_as_csv(self, tmp_path: pathlib.Path) -> None:
        """A frame without geometry becomes a CSV."""
        export.export_results(self.results(), tmp_path)
        assert (tmp_path / "mileage.csv").exists()

    def test_destination_layers_are_written(self, tmp_path: pathlib.Path) -> None:
        """Each destination category gets its own GeoJSON."""
        export.export_results(self.results(), tmp_path)
        assert (tmp_path / "schools.geojson").exists()

    def test_absent_layers_are_skipped_silently(self, tmp_path: pathlib.Path) -> None:
        """A result missing a layer writes fewer files rather than failing."""
        written = export.export_results({"ways": layer(road_id=1)}, tmp_path)
        assert written
        assert not (tmp_path / "census_blocks.geojson").exists()


class TestOnewayLabels:
    """Test the `osm2pgrouting` spelling of the `oneway` column."""

    def test_maps_the_tag_values(self) -> None:
        """Each accepted tag value has a published spelling."""
        got = export._oneway_labels(pd.Series(["yes", "1", "no", "0", "-1", "reverse"]))
        assert list(got) == ["YES", "YES", "NO", "NO", "REVERSED", "REVERSED"]

    def test_an_unknown_value_is_upper_cased(self) -> None:
        """`REVERSIBLE` reaches the reference exports that way."""
        assert list(export._oneway_labels(pd.Series(["reversible"]))) == ["REVERSIBLE"]

    def test_absent_is_unknown(self) -> None:
        """No tag is `UNKNOWN`, not NULL."""
        assert list(export._oneway_labels(pd.Series([None]))) == ["UNKNOWN"]

    def test_a_roundabout_is_one_way_without_a_tag(self) -> None:
        """`junction=roundabout` implies a direction (findings.md §1.15)."""
        got = export._oneway_labels(
            pd.Series([None, None]),
            pd.Series(["roundabout", "circular"]),
        )
        assert list(got) == ["YES", "UNKNOWN"]

    def test_the_roundabout_beats_an_explicit_tag(self) -> None:
        """The implication overrules the tag, as the baseline shows.

        San Juan has a roundabout tagged `oneway=no` published as `YES`
        (findings.md §1.25).
        """
        got = export._oneway_labels(pd.Series(["no"]), pd.Series(["roundabout"]))
        assert list(got) == ["YES"]


class TestPostgresCsv:
    """Test the CSV spelling `COPY ... TO` produced."""

    def test_booleans_become_t_and_f(self) -> None:
        """Downstream consumers parse `t`/`f`, not `True`/`False`."""
        got = export._postgres_csv(pd.DataFrame({"low_stress": [True, False]}))
        assert list(got["low_stress"]) == ["t", "f"]

    def test_whole_floats_lose_their_decimal(self) -> None:
        """An `INTEGER` column never gained a `.0` in the reference export."""
        got = export._postgres_csv(pd.DataFrame({"cost": [730.0, 0.0]}))
        assert list(got["cost"]) == [730, 0]

    def test_genuine_floats_are_left_alone(self) -> None:
        """Only columns that are whole throughout are narrowed."""
        got = export._postgres_csv(pd.DataFrame({"score": [0.5, 1.0]}))
        assert list(got["score"]) == [0.5, 1.0]

    def test_a_motorway_is_one_way_without_a_tag(self) -> None:
        """`osm2pgrouting` implied it, and it beats an unrecognised value.

        `oneway=reversible` on a motorway published as `YES`, while the same
        tag on a `motorway_link` published as `REVERSIBLE`
        (findings.md §1.25).
        """
        got = export._oneway_labels(
            pd.Series(["reversible", "reversible", None]),
            None,
            pd.Series(["motorway", "motorway_link", "motorway"]),
        )
        assert list(got) == ["YES", "REVERSIBLE", "YES"]

    def test_the_implication_also_overrules_on_a_motorway(self) -> None:
        """Same rule, same strength -- `osm2pgrouting` applies both alike."""
        got = export._oneway_labels(
            pd.Series(["no"]),
            None,
            pd.Series(["motorway"]),
        )
        assert list(got) == ["YES"]

    def test_an_unrecognised_value_is_unknown(self) -> None:
        """The published column holds five values and nothing else.

        `oneway=alternating` publishes as `UNKNOWN`, not `ALTERNATING` --
        Valencia has one (findings.md §1.15).
        """
        got = export._oneway_labels(pd.Series(["alternating", "reversible"]))
        assert list(got) == ["UNKNOWN", "REVERSIBLE"]
