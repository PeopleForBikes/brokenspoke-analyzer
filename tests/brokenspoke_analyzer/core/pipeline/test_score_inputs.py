"""Test `score_inputs.sql`'s diagnostic table."""

import geopandas as gpd
import pandas as pd
import pytest
import shapely

from brokenspoke_analyzer.core.pipeline import (
    score_inputs,
    scoring,
)

UTM13N = 32613


def blocks(**columns: list) -> gpd.GeoDataFrame:
    """Build blocks inside the boundary, one per list element."""
    count = len(next(iter(columns.values())))
    return gpd.GeoDataFrame(
        {
            **columns,
            "geometry": [shapely.box(i * 10, 0, i * 10 + 10, 10) for i in range(count)],
        },
        geometry="geometry",
        crs=f"EPSG:{UTM13N}",
    )


def boundary() -> gpd.GeoDataFrame:
    """A boundary covering every block the tests build."""
    return gpd.GeoDataFrame(
        {"geometry": [shapely.box(-10, -10, 1000, 20)]},
        geometry="geometry",
        crs=f"EPSG:{UTM13N}",
    )


def shed(low: list, high: list) -> gpd.GeoDataFrame:
    """Build a destination table carrying the given population sheds."""
    return gpd.GeoDataFrame(
        {
            "pop_low_stress": pd.array(low, dtype="Int64"),
            "pop_high_stress": pd.array(high, dtype="Int64"),
            "geometry": [shapely.Point(i, 5) for i in range(len(low))],
        },
        geometry="geometry",
        crs=f"EPSG:{UTM13N}",
    )


class TestTable:
    """Test the transcribed row table."""

    def test_has_every_insert_in_order(self) -> None:
        """132 rows, the first and last as `score_inputs.sql` inserts them."""
        assert len(score_inputs.SCORE_INPUTS) == 132
        assert (
            score_inputs.SCORE_INPUTS[0].score_name
            == "Median score of access to population"
        )
        assert (
            score_inputs.SCORE_INPUTS[-1].score_name
            == "30th percentile transit population shed score"
        )

    def test_flags_are_the_sixteen_overall_score_rows(self) -> None:
        """Exactly one flagged row per `OVERALL_SCORE_ROWS` member.

        The two tables order them differently: `score_inputs.sql` inserts
        retail between the pharmacies and grocery rows, `overall_scores.sql`
        after social services.
        """
        flagged = [r for r in score_inputs.SCORE_INPUTS if r.flag]
        assert [r.flag for r in flagged] == list(score_inputs.USE_FLAGS)
        assert {r.formula.member for r in flagged} == {  # type: ignore[union-attr]
            member for _, member in scoring.OVERALL_SCORE_ROWS
        }

    def test_prose_is_verbatim(self) -> None:
        """The hand-written text is carried as is, inconsistencies included.

        `social_services.sql`'s author wrote the category with an underscore
        in the shed rows; the published file says so too.
        """
        names = [r.score_name for r in score_inputs.SCORE_INPUTS]
        assert "Median social_services population shed score" in names
        assert "Median score of social services access" in names


class TestFormulas:
    """Test the five formula kinds against the SQL's edge cases."""

    def test_block_percentile_interpolates_and_skips_nulls(self) -> None:
        """`PERCENTILE_CONT` interpolates; `NULLIF(high, 0)` drops a block."""
        frame = blocks(
            schools_low_stress=[1, 2, 0, 3],
            schools_high_stress=[2, 2, 0, 4],
        )
        got = score_inputs.evaluate(
            score_inputs.BlockPercentile("schools", 0.5), frame, {}
        )
        # Ratios 0.5, 1.0, 0.75 (the 0/0 block is out): median 0.75.
        assert got == 0.75

    def test_block_ratio_divides_integers(self) -> None:
        """`SUM(low) / SUM(high)` on two INTs truncates -- the row is 0."""
        frame = blocks(schools_low_stress=[3, 1], schools_high_stress=[4, 2])
        assert (
            score_inputs.evaluate(
                score_inputs.BlockRatio("schools", float_division=False), frame, {}
            )
            == 0
        )
        assert score_inputs.evaluate(
            score_inputs.BlockRatio("pop", float_division=True),
            blocks(pop_low_stress=[3, 1], pop_high_stress=[4, 2]),
            {},
        ) == pytest.approx(4 / 6)

    def test_ratio_of_nothing_is_null_and_of_zero_is_zero(self) -> None:
        """`CASE WHEN SUM(high) = 0 THEN 0` -- but `SUM()` of NULLs is NULL."""
        empty = blocks(emp_low_stress=[None, None], emp_high_stress=[None, None])
        assert pd.isna(
            score_inputs.evaluate(
                score_inputs.BlockRatio("emp", float_division=True), empty, {}
            )
        )
        zero = blocks(emp_low_stress=[0, 0], emp_high_stress=[0, 0])
        assert (
            score_inputs.evaluate(
                score_inputs.BlockRatio("emp", float_division=True), zero, {}
            )
            == 0
        )

    def test_weighted_is_null_without_employment_data(self) -> None:
        """Unlike `overall_scores.sql`, no `COALESCE`: the jobs row is empty."""
        frame = blocks(pop20=[10, 20], emp_score=[None, None])
        assert pd.isna(score_inputs.evaluate(score_inputs.Weighted("emp"), frame, {}))

    def test_shed_rows_read_the_destination_table(self) -> None:
        """The shed ratio and percentiles run over the destinations' sheds."""
        tables = {"parks": shed(low=[10, 30, None], high=[40, 40, None])}
        assert score_inputs.evaluate(
            score_inputs.ShedRatio("parks"), blocks(pop20=[1]), tables
        ) == pytest.approx(0.5)
        assert score_inputs.evaluate(
            score_inputs.ShedPercentile("parks", 0.5), blocks(pop20=[1]), tables
        ) == pytest.approx(0.5)

    def test_shed_rows_are_null_without_destinations(self) -> None:
        """A city with no colleges publishes empty college shed rows."""
        assert pd.isna(
            score_inputs.evaluate(
                score_inputs.ShedRatio("colleges"), blocks(pop20=[1]), {}
            )
        )


class TestDeriveScoreInputs:
    """Test the assembled table."""

    def test_shape_and_flags(self) -> None:
        """132 rows, ids 1..132, one `t` per flagged row and NULL elsewhere."""
        frame = blocks(
            pop20=[10], pop_low_stress=[5], pop_high_stress=[10], pop_score=[0.5]
        )
        got = score_inputs.derive_score_inputs(frame, boundary(), {})
        assert list(got["id"]) == list(range(1, 133))
        assert list(got.columns[:6]) == [
            "id",
            "category",
            "score_name",
            "score",
            "notes",
            "human_explanation",
        ]
        assert bool(got.loc[4, "use_pop"])
        assert got["use_pop"].sum() == 1
        assert pd.isna(got.loc[0, "use_pop"])

    def test_scores_are_rounded_to_four_decimals(self) -> None:
        """`score NUMERIC(16, 4)`."""
        frame = blocks(
            pop20=[10], pop_low_stress=[1], pop_high_stress=[3], pop_score=[1 / 3]
        )
        got = score_inputs.derive_score_inputs(frame, boundary(), {})
        assert got.loc[0, "score"] == 0.3333


class TestOverallScoresShape:
    """Test the columns `overall_scores.sql` added around the numbers."""

    def test_rows_carry_id_and_explanation_in_table_order(self) -> None:
        """`recreation` precedes `transit`; totals have their own wording."""
        frame = blocks(pop20=[10], pop_score=[0.5], overall_score=[50.0])
        ways = gpd.GeoDataFrame(
            {"geometry": []}, geometry="geometry", crs=f"EPSG:{UTM13N}"
        )
        got = scoring.derive_overall_scores(frame, boundary(), ways)
        assert list(got.columns) == [
            "id",
            "score_id",
            "score_original",
            "score_normalized",
            "human_explanation",
        ]
        ids = list(got["score_id"])
        assert ids.index("recreation") == ids.index("transit") - 1
        assert ids.index("recreation") == ids.index("recreation_community_centers") + 1
        assert list(got["id"]) == list(range(1, len(got) + 1))
        assert (
            got.set_index("score_id").loc["people", "human_explanation"]
            == "On average, census blocks in the neighborhood received this population score."
        )
        assert got.set_index("score_id").loc[
            "population_total", "human_explanation"
        ] == ("Total population of boundary")
        assert pd.isna(got.set_index("score_id").loc["recreation", "human_explanation"])
