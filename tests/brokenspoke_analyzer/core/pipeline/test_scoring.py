"""Test the `scoring` pipeline stage.

Cover destination extraction, clustering, and the graduated access score.
Synthetic inputs throughout.
"""

import geopandas as gpd
import pandas as pd
import pytest
import shapely

from brokenspoke_analyzer.core.pipeline import (
    config,
    scoring,
)

# `features` is a local fixture helper in this module, so the rounding helper
# is imported by name rather than through the module.
from brokenspoke_analyzer.core.pipeline.features import _round_half_away

UTM13N = 32613


def features(rows: list[dict]) -> gpd.GeoDataFrame:
    """Build an OSM feature frame."""
    for index, row in enumerate(rows):
        row.setdefault("id", index + 1)
        row.setdefault("geometry", shapely.Point(index * 1000, 0))
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{UTM13N}")


def blocks(count: int = 1) -> gpd.GeoDataFrame:
    """Build census blocks covering the feature area."""
    return gpd.GeoDataFrame(
        {
            "geoid20": [f"b{index}" for index in range(count)],
            "geometry": [
                shapely.box(index * 1000 - 500, -500, index * 1000 + 500, 500)
                for index in range(count)
            ],
        },
        geometry="geometry",
        crs=f"EPSG:{UTM13N}",
    )


class TestClusterWithin:
    """Test the `ST_ClusterWithin` equivalent."""

    def test_nearby_geometries_merge(self) -> None:
        """Geometries within the tolerance become one cluster."""
        geometries = gpd.GeoSeries(
            [shapely.Point(0, 0), shapely.Point(30, 0), shapely.Point(500, 0)],
            crs=f"EPSG:{UTM13N}",
        )
        clusters = scoring.cluster_within(geometries, tolerance=50)
        assert sorted(len(c) for c in clusters) == [1, 2]

    def test_clustering_is_transitive(self) -> None:
        """A chain of near neighbours forms a single cluster.

        Each hop is inside the tolerance even though the ends are not, which
        is what makes a campus of many buildings one destination.
        """
        geometries = gpd.GeoSeries(
            [shapely.Point(x, 0) for x in (0, 40, 80, 120)],
            crs=f"EPSG:{UTM13N}",
        )
        assert len(scoring.cluster_within(geometries, tolerance=50)) == 1

    def test_zero_tolerance_leaves_everything_separate(self) -> None:
        """Without a tolerance every geometry is its own destination."""
        geometries = gpd.GeoSeries(
            [shapely.Point(0, 0), shapely.Point(1, 0)],
            crs=f"EPSG:{UTM13N}",
        )
        assert len(scoring.cluster_within(geometries, tolerance=0)) == 2


class TestExtractDestinations:
    """Test destination extraction."""

    def test_matches_any_listed_tag(self) -> None:
        """A rule's tag alternatives are OR-ed, as in the SQL."""
        frame = features(
            [{"amenity": "dentist"}, {"healthcare": "dentist"}, {"amenity": "cafe"}],
        )
        rule = scoring.DestinationRule(
            "dentists",
            (
                scoring.MatchBranch("amenity", ("dentist",)),
                scoring.MatchBranch("healthcare", ("dentist",)),
            ),
        )
        assert len(scoring.extract_destinations(frame, blocks(3), rule)) == 2

    def test_excludes_win_over_matches(self) -> None:
        """An excluded value disqualifies a feature that otherwise matched."""
        frame = features([{"shop": "bakery"}, {"shop": "supermarket"}])
        rule = scoring.DestinationRule(
            "retail",
            (scoring.MatchBranch("shop", (), excluded=("no", "supermarket")),),
        )
        assert len(scoring.extract_destinations(frame, blocks(2), rule)) == 1

    def test_an_exclusion_binds_to_its_own_branch(self) -> None:
        """Retail excludes supermarkets from its `shop` branch alone.

        A `landuse=retail` polygon stays retail even with a supermarket on
        it, because the SQL's `NOT IN` sits inside the `shop` branch's
        parentheses.
        """
        frame = features([{"landuse": "retail", "shop": "supermarket"}])
        rule = scoring.DestinationRule(
            "retail",
            (
                scoring.MatchBranch("landuse", ("retail",)),
                scoring.MatchBranch("shop", (), excluded=("no", "supermarket")),
            ),
        )
        assert len(scoring.extract_destinations(frame, blocks(1), rule)) == 1

    def test_empty_value_tuple_means_any_value(self) -> None:
        """`("shop", ())` matches any shop, which is how retail is defined."""
        frame = features([{"shop": "bakery"}, {"amenity": "cafe"}])
        rule = scoring.DestinationRule("retail", (scoring.MatchBranch("shop"),))
        assert len(scoring.extract_destinations(frame, blocks(2), rule)) == 1

    def test_records_the_blocks_touched(self) -> None:
        """Each destination lists the census blocks it intersects."""
        frame = features([{"amenity": "school"}])
        rule = scoring.DestinationRule(
            "schools",
            (scoring.MatchBranch("amenity", ("school",)),),
        )
        got = scoring.extract_destinations(frame, blocks(1), rule)
        assert got.iloc[0]["blockid20"] == ["b0"]

    def test_no_matches_yields_an_empty_frame(self) -> None:
        """A category with nothing in the city is empty, not an error."""
        frame = features([{"amenity": "cafe"}])
        rule = scoring.DestinationRule(
            "schools",
            (scoring.MatchBranch("amenity", ("school",)),),
        )
        assert scoring.extract_destinations(frame, blocks(1), rule).empty


class TestDestinationScore:
    """Test the graduated access score shared by every `access_*.sql`."""

    def score(self, low: int, high: int, access: config.Access) -> float | None:
        """Score one block."""
        got = scoring.destination_score(
            pd.Series([low]),
            pd.Series([high]),
            access,
        ).iloc[0]
        return None if pd.isna(got) else float(got)

    def test_nothing_reachable_is_unscored(self) -> None:
        """A block reaching no destination scores NULL, not zero.

        It is dropped from its category rather than dragging the score down.
        """
        assert self.score(0, 0, config.Access("x", first=0.7)) is None

    def test_none_low_stress_scores_zero(self) -> None:
        """Reachable only on hostile roads scores zero."""
        assert self.score(0, 5, config.Access("x", first=0.7)) == 0.0

    def test_all_low_stress_scores_the_maximum(self) -> None:
        """Every reachable destination reachable comfortably is full marks."""
        assert self.score(5, 5, config.Access("x", first=0.7)) == 1.0

    def test_plain_ratio_without_weights(self) -> None:
        """With no `first` weight the score is the bare ratio."""
        assert self.score(1, 4, config.Access("x")) == pytest.approx(0.25)

    def test_first_destination_carries_most_value(self) -> None:
        """Reaching one of several destinations already earns `first`.

        This is the heart of the scoring: the first supermarket you can reach
        safely is worth far more than the fourth.
        """
        access = config.Access("x", first=0.6, second=0.2)
        assert self.score(1, 4, access) == pytest.approx(0.6)

    def test_second_and_third_tiers(self) -> None:
        """The second and third reachable destinations earn their own weights."""
        access = config.Access("x", first=0.4, second=0.2, third=0.1)
        assert self.score(1, 6, access) == pytest.approx(0.4)
        assert self.score(2, 6, access) == pytest.approx(0.6)
        assert self.score(3, 6, access) == pytest.approx(0.7)

    def test_beyond_the_tiers_shares_the_remainder(self) -> None:
        """Destinations past the weighted tiers split what is left."""
        access = config.Access("x", first=0.4, second=0.2, third=0.1)
        # 4 of 6 low-stress: 0.7 + (0.3 * (4-3)) / (6-3) = 0.8
        assert self.score(4, 6, access) == pytest.approx(0.8)


class TestAccessWeights:
    """Test the weights moved out of `compute.py`."""

    def test_every_weighted_category_is_present(self) -> None:
        """The thirteen `Access` instances survived the move from compute.py."""
        weights = scoring.access_weights()
        assert len(weights) == 13
        assert weights["supermarkets"].first == 0.6
        assert weights["schools"].third == 0.2

    def test_weights_never_exceed_the_maximum(self) -> None:
        """The tiers cannot sum past the maximum score."""
        for access in scoring.ACCESS_WEIGHTS:
            total = access.first + access.second + access.third
            assert total <= access.max_score


class TestStepScore:
    """Test the piecewise curve used for population and jobs access."""

    def score(self, low: float, high: float) -> float | None:
        """Score one block against the default curve."""
        got = scoring.step_score(pd.Series([low]), pd.Series([high])).iloc[0]
        return None if pd.isna(got) else round(float(got), 6)

    def test_nothing_reachable_is_unscored(self) -> None:
        """No reachable population means no score, not a zero."""
        assert self.score(0, 0) is None

    def test_none_reachable_low_stress_scores_zero(self) -> None:
        """Reachable only on hostile roads scores zero."""
        assert self.score(0, 100) == 0.0

    def test_all_reachable_low_stress_is_full_marks(self) -> None:
        """Everything reachable comfortably is the maximum."""
        assert self.score(100, 100) == 1.0

    def test_breakpoints_hit_their_scores(self) -> None:
        """The curve passes through each configured breakpoint."""
        assert self.score(3, 100) == pytest.approx(0.1)
        assert self.score(20, 100) == pytest.approx(0.4)
        assert self.score(50, 100) == pytest.approx(0.8)

    def test_curve_is_front_loaded(self) -> None:
        """Early gains are worth far more than later ones.

        Reaching 3% of the population earns 0.1; the next 17 points of
        coverage earn only 0.3 more. A network that connects nobody is much
        worse than one that connects a little.
        """
        assert self.score(3, 100) == pytest.approx(0.1)
        # Half the coverage, but well over half the score.
        assert self.score(50, 100) == pytest.approx(0.8)

    def test_interpolates_between_breakpoints(self) -> None:
        """Between breakpoints the curve is linear."""
        # Midway between step2 (0.2 -> 0.4) and step3 (0.5 -> 0.8).
        assert self.score(35, 100) == pytest.approx(0.6)


class TestCategoryScores:
    """Test `category_scores.sql`'s renormalising weighted average."""

    def blocks(self, **scores: float | None) -> gpd.GeoDataFrame:
        """Build one block carrying the given destination scores."""
        return gpd.GeoDataFrame(
            {**{k: [v] for k, v in scores.items()}, "geometry": [shapely.Point(0, 0)]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )

    def test_weighted_average_of_members(self) -> None:
        """A full set of members averages by weight."""
        frame = self.blocks(
            parks_score=1.0,
            trails_score=1.0,
            community_centers_score=1.0,
        )
        got = scoring.derive_category_scores(frame)
        assert got["recreation_score"].iloc[0] == pytest.approx(1.0)

    def test_missing_member_is_dropped_from_the_divisor(self) -> None:
        """A category the city lacks is removed, not scored zero.

        A town with no community centre is not penalised for it -- the weight
        leaves the divisor, so the remaining members still reach 1.0.
        """
        frame = self.blocks(parks_score=1.0, trails_score=1.0)
        got = scoring.derive_category_scores(frame)
        assert got["recreation_score"].iloc[0] == pytest.approx(1.0)

    def test_zero_scores_still_count(self) -> None:
        """A present-but-zero score stays in the divisor.

        This is the distinction that makes NULL meaningful: unreachable is
        not the same as absent.
        """
        frame = self.blocks(parks_score=1.0, trails_score=0.0)
        got = scoring.derive_category_scores(frame)
        # 0.4 / (0.4 + 0.35), not 1.0.
        assert got["recreation_score"].iloc[0] == pytest.approx(0.4 / 0.75)

    def test_no_members_yields_null(self) -> None:
        """A block with nothing scored gets NULL, not zero."""
        frame = self.blocks()
        assert pd.isna(
            scoring.derive_category_scores(frame)["recreation_score"].iloc[0]
        )


class TestBlockJobs:
    """Test `census_block_jobs.sql`."""

    def test_sums_jobs_at_the_workplace_block(self) -> None:
        """Jobs are keyed on `w_geocode`, where the job is, not where the worker lives."""
        blocks = gpd.GeoDataFrame(
            {
                "geoid20": ["a", "b"],
                "geometry": [shapely.Point(0, 0), shapely.Point(1, 0)],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        jobs = pd.DataFrame(
            {
                "w_geocode": ["a", "a", "b"],
                "h_geocode": ["b", "b", "a"],
                "S000": [3, 4, 5],
            },
        )
        got = scoring.block_jobs(blocks, jobs)
        assert list(got) == [7, 5]

    def test_block_with_no_records_has_zero_jobs(self) -> None:
        """A block absent from LODES has zero jobs, not NULL."""
        blocks = gpd.GeoDataFrame(
            {"geoid20": ["a"], "geometry": [shapely.Point(0, 0)]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        assert scoring.block_jobs(blocks, pd.DataFrame()).iloc[0] == 0


class TestShedTotals:
    """Test the population and jobs sums over a block's reachable shed."""

    def blocks(self) -> gpd.GeoDataFrame:
        """Three blocks, only two of which are ever a source."""
        return gpd.GeoDataFrame(
            {
                "geoid20": ["a", "b", "c"],
                "pop20": [10, 20, 30],
                "geometry": [shapely.Point(index, 0) for index in range(3)],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )

    def connected(self) -> pd.DataFrame:
        """Pairs covering `a` and `b`, but never `c`."""
        return pd.DataFrame(
            {
                "source_blockid20": ["a", "a", "b"],
                "target_blockid20": ["a", "b", "b"],
                "low_stress": [True, False, True],
            },
        )

    def test_sums_the_shed(self) -> None:
        """The high-stress total covers every pair, the low-stress ones only."""
        got = scoring.shed_totals(self.blocks(), self.connected(), "pop20")
        assert list(got["high_stress"]) == [
            30.0,
            20.0,
            pytest.approx(float("nan"), nan_ok=True),
        ]
        assert got["low_stress"].iloc[0] == 10.0

    def test_blocks_with_no_pairs_are_null(self) -> None:
        """`SUM()` over no rows is NULL, not 0 (findings.md §1.16).

        The difference carries all the way to the published score: a NULL
        total scores NULL, a zero total scores zero.
        """
        got = scoring.shed_totals(self.blocks(), self.connected(), "pop20")
        assert pd.isna(got.loc[2, "low_stress"])
        assert pd.isna(got.loc[2, "high_stress"])

    def test_a_null_total_scores_null(self) -> None:
        """And the score built on it is NULL too, not zero."""
        got = scoring.shed_totals(self.blocks(), self.connected(), "pop20")
        score = scoring.step_score(got["low_stress"], got["high_stress"])
        assert pd.isna(score.iloc[2])


class TestRoundHalfUp:
    """Test the PostgreSQL rounding rule."""

    def test_rounds_a_tie_away_from_zero(self) -> None:
        """Python rounds 2.675 down to even; PostgreSQL rounds it up."""
        assert scoring._round_half_up(2.675, 2) == 0.01 * 268
        assert scoring._round_half_up(-2.675, 2) == -0.01 * 268

    def test_leaves_non_ties_alone(self) -> None:
        """Anything that is not a tie rounds the ordinary way."""
        assert scoring._round_half_up(0.12344, 4) == 0.1234
        assert scoring._round_half_up(0.12346, 4) == 0.1235

    def test_nan_passes_through(self) -> None:
        """A missing score stays missing."""
        assert pd.isna(scoring._round_half_up(float("nan"), 4))


class TestBlockOverallScore:
    """Test `access_overall.sql`'s per-block score."""

    def block(self, **columns: float | None) -> gpd.GeoDataFrame:
        """One block inside the boundary, carrying the given columns."""
        return gpd.GeoDataFrame(
            {
                **{name: [value] for name, value in columns.items()},
                "geometry": [shapely.box(0, 0, 10, 10)],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )

    def boundary(self) -> gpd.GeoDataFrame:
        """A boundary containing the block."""
        return gpd.GeoDataFrame(
            {"geometry": [shapely.box(-10, -10, 20, 20)]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )

    def test_employment_keeps_its_weight_when_null(self) -> None:
        """Employment's 0.35 is in the divisor unconditionally.

        `category_scores.sql` would drop it, because `emp_score` is NULL.
        `access_overall.sql` has no `emp_high_stress > 0` test to key it on,
        just the bare 0.35 -- so outside the US, where there is never any
        LODES data, the two disagree (findings.md §1.17).
        """
        block = self.block(
            pop_score=0.0,
            schools_score=1.0,
            schools_high_stress=1,
            emp_score=None,
        )
        got = scoring.derive_block_overall_score(block, self.boundary())
        # opportunity = 0.35 * 1.0 / (0.35 + 0.35), not 1.0.
        weights = config.Score()
        expected = (
            weights.total
            * weights.opportunity
            * 0.5
            / (weights.people + weights.opportunity)
        )
        assert got.iloc[0] == pytest.approx(expected)

    def test_blocks_outside_the_boundary_are_not_scored(self) -> None:
        """The SQL's `WHERE EXISTS (intersects boundary)` leaves them NULL."""
        block = self.block(pop_score=1.0)
        outside = gpd.GeoDataFrame(
            {"geometry": [shapely.box(100, 100, 110, 110)]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        assert pd.isna(scoring.derive_block_overall_score(block, outside).iloc[0])


class TestPopulationWeightedOverall:
    """Test the city's headline score."""

    def blocks(self) -> gpd.GeoDataFrame:
        """Three blocks: one scored, one empty of people, one unreachable."""
        return gpd.GeoDataFrame(
            {
                "geoid20": ["a", "b", "c"],
                "pop20": [100, 50, 70],
                "reachable_blocks": [3, 2, 0],
                "overall_score": [50.0, 100.0, 100.0],
                "geometry": [shapely.Point(index, 0) for index in range(3)],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )

    def test_weights_by_population_and_ignores_unreachable_blocks(self) -> None:
        """Blocks that reach nothing are outside both sum and divisor."""
        got = scoring._population_weighted_overall(self.blocks())
        assert got == pytest.approx((0.5 * 100 + 1.0 * 50) / 150)

    def test_uninhabited_blocks_still_count_in_the_divisor(self) -> None:
        """The divisor is the population of every block with reach.

        A block with reach but no population contributes nothing to the sum
        and nothing to the divisor either -- but one *with* population and no
        score contributes only to the divisor, which drags the city down
        (findings.md §1.19).
        """
        frame = self.blocks()
        frame.loc[1, "overall_score"] = None
        got = scoring._population_weighted_overall(frame)
        assert got == pytest.approx(0.5 * 100 / 150)


class TestPointGuardPrecedence:
    """Test which point branches the polygon guard applies to."""

    def frame(self) -> gpd.GeoDataFrame:
        """A polygon destination with a node of each tagging inside it."""
        return gpd.GeoDataFrame(
            {
                "id": [1, 2, 3],
                "amenity": ["dentist", "dentist", None],
                "healthcare": [None, None, "dentist"],
                "geometry": [
                    shapely.box(-100, -100, 100, 100),
                    shapely.Point(0, 0),
                    shapely.Point(10, 10),
                ],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )

    def test_an_unguarded_branch_survives_inside_a_polygon(self) -> None:
        """`amenity=dentist` binds before the `AND NOT EXISTS`.

        The SQL's `OR` list is unparenthesised, so a node matching the first
        branch is inserted even though a polygon already covers it
        (findings.md §1.21).
        """
        rule = scoring.DestinationRule(
            "dentists",
            (
                scoring.MatchBranch("amenity", ("dentist",), guarded=False),
                scoring.MatchBranch("healthcare", ("dentist",)),
            ),
        )
        got = scoring.extract_destinations(self.frame(), blocks(1), rule)
        # The polygon and the `amenity` node; the `healthcare` node is guarded.
        assert sorted(got["osm_id"]) == [1, 2]

    def test_a_guarded_branch_is_dropped_inside_a_polygon(self) -> None:
        """Parenthesised, as in `parks.sql`, every branch is guarded."""
        rule = scoring.DestinationRule(
            "dentists",
            (
                scoring.MatchBranch("amenity", ("dentist",)),
                scoring.MatchBranch("healthcare", ("dentist",)),
            ),
        )
        got = scoring.extract_destinations(self.frame(), blocks(1), rule)
        assert sorted(got["osm_id"]) == [1]


class TestTransitMatches:
    """Test `transit.sql`'s three-valued `WHERE`."""

    def features(self, **tags: str | None) -> gpd.GeoDataFrame:
        """One feature carrying the given tags."""
        return gpd.GeoDataFrame(
            {**{k: [v] for k, v in tags.items()}, "geometry": [shapely.Point(0, 0)]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )

    def test_a_bare_public_transport_station_does_not_match(self) -> None:
        """`NOT (NULL AND NULL)` is NULL, so the row is excluded.

        This is what keeps Jackson's ski gondolas out of the published
        results (findings.md §1.22).
        """
        frame = self.features(public_transport="station", railway=None, station=None)
        assert not scoring._transit_matches(frame).iloc[0]

    def test_a_railway_station_matches(self) -> None:
        """The second clause has no such NULL trap."""
        frame = self.features(public_transport=None, railway="station", station=None)
        assert scoring._transit_matches(frame).iloc[0]

    def test_a_known_non_miniature_station_matches(self) -> None:
        """One tag known not to be the excluded value is enough."""
        frame = self.features(
            public_transport="station",
            railway=None,
            station="regular",
        )
        assert scoring._transit_matches(frame).iloc[0]

    def test_a_miniature_railway_station_is_excluded(self) -> None:
        """The exclusion the clause was written for still works."""
        frame = self.features(
            public_transport="station",
            railway="station",
            station="miniature",
        )
        assert not scoring._transit_matches(frame).iloc[0]

    def test_a_bus_station_matches_on_amenity(self) -> None:
        """The first clause is a plain `IN`."""
        frame = self.features(amenity="bus_station", public_transport=None)
        assert scoring._transit_matches(frame).iloc[0]


class TestDestinationGeometryKinds:
    """Test which OSM geometries can be a destination at all."""

    def rule(self) -> scoring.DestinationRule:
        """A simple unclustered rule."""
        return scoring.DestinationRule(
            "supermarkets",
            (scoring.MatchBranch("shop", ("supermarket",)),),
        )

    def test_an_unclosed_way_is_not_a_destination(self) -> None:
        """`osm2pgsql` wrote it to the line table (findings.md §3.9)."""
        frame = gpd.GeoDataFrame(
            {
                "id": [1],
                "shop": ["supermarket"],
                "geometry": [shapely.LineString([(0, 0), (10, 0), (10, 10)])],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        assert scoring.extract_destinations(frame, blocks(1), self.rule()).empty

    def test_a_closed_way_becomes_a_polygon(self) -> None:
        """A closed way with an area tag was a polygon in the import."""
        ring = shapely.LinearRing([(0, 0), (10, 0), (10, 10), (0, 10)])
        frame = gpd.GeoDataFrame(
            {
                "id": [1],
                "shop": ["supermarket"],
                "geometry": [shapely.LineString(ring.coords)],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        got = scoring.extract_destinations(frame, blocks(1), self.rule())
        assert len(got) == 1
        assert got.geometry.iloc[0].geom_type == "Polygon"

    def test_an_invalid_polygon_is_dropped_not_repaired(self) -> None:
        """It never reached PostGIS, so it is not a destination.

        Repairing it instead invents one -- Jackson gained a seventh school
        that way (findings.md §3.8).
        """
        bowtie = shapely.Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
        assert not bowtie.is_valid
        frame = gpd.GeoDataFrame(
            {"id": [1], "shop": ["supermarket"], "geometry": [bowtie]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        assert scoring.extract_destinations(frame, blocks(1), self.rule()).empty


class TestBlocksTouched:
    """Test the block assignment."""

    def test_the_centroid_counts_as_well_as_the_shape(self) -> None:
        """A cluster wrapped around a block still credits it.

        The SQL tests `geom_poly` OR `geom_pt`, and a horseshoe's centroid
        lands in a block none of its parts touch (findings.md §3.10).
        """
        # Two bars either side of x=0, so the centroid sits in the gap.
        horseshoe = shapely.MultiPolygon(
            [
                shapely.box(-900, -100, -600, 100),
                shapely.box(600, -100, 900, 100),
            ],
        )
        destinations = gpd.GeoDataFrame(
            {"id": [1], "geometry": [horseshoe]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        middle = gpd.GeoDataFrame(
            {"geoid20": ["gap"], "geometry": [shapely.box(-100, -100, 100, 100)]},
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        assert not horseshoe.intersects(middle.geometry.iloc[0])
        assert scoring._blocks_touched(destinations, middle) == [["gap"]]


class TestWholePopulationMembers:
    """Test which city scores divide by the whole population."""

    def test_population_and_employment_only(self) -> None:
        """`score_inputs.sql`'s `tmp_pop` has no `emp` column.

        Employment divides by `tmp_pop.overall` like population does; every
        other member divides by its own reachable population
        (findings.md §1.23).
        """
        assert scoring.WHOLE_POPULATION_MEMBERS == {"pop", "emp"}
        members = {member for _, member in scoring.OVERALL_SCORE_ROWS}
        assert scoring.WHOLE_POPULATION_MEMBERS <= members


class TestTransitClustering:
    """Test the one category that clusters points but not polygons."""

    def test_polygons_stay_separate(self) -> None:
        """`transit.sql` inserts one row per polygon (findings.md §1.24).

        Two stations 40 m apart -- well inside the 75 m tolerance -- are two
        destinations, while two *points* the same distance apart are one.
        """
        rule = next(r for r in scoring.DESTINATION_RULES if r.name == "transit")
        assert rule.tolerance == 75
        assert not rule.cluster_polygons
        assert rule.cluster_points

        frame = gpd.GeoDataFrame(
            {
                "id": [1, 2],
                "amenity": ["bus_station", "bus_station"],
                "geometry": [
                    shapely.box(0, 0, 10, 10),
                    shapely.box(50, 0, 60, 10),
                ],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        assert len(scoring.extract_destinations(frame, blocks(1), rule)) == 2

    def test_points_merge(self) -> None:
        """The same two as nodes are one clustered destination."""
        rule = next(r for r in scoring.DESTINATION_RULES if r.name == "transit")
        frame = gpd.GeoDataFrame(
            {
                "id": [1, 2],
                "amenity": ["bus_station", "bus_station"],
                "geometry": [shapely.Point(0, 0), shapely.Point(40, 0)],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        assert len(scoring.extract_destinations(frame, blocks(1), rule)) == 1


class TestIntShedTotals:
    """Test the INT storage of the population and jobs sheds."""

    def test_totals_round_half_away_from_zero(self) -> None:
        """`pop_low_stress` and friends are `INT` columns (findings.md §1.27).

        A synthetic block population is fractional -- it comes from a raster
        -- so the sum is too, and the SQL rounded it on assignment before
        `access_population.sql` read it back to score it.
        """
        totals = pd.DataFrame({"low_stress": [5876.5], "high_stress": [16577.4]})
        rounded = totals.apply(_round_half_away)
        assert rounded["low_stress"].iloc[0] == 5877
        assert rounded["high_stress"].iloc[0] == 16577

    def test_a_null_total_stays_null(self) -> None:
        """Rounding must not turn a NULL shed into a zero (findings.md §1.16)."""
        totals = pd.DataFrame({"low_stress": [float("nan")]})
        assert pd.isna(totals.apply(_round_half_away)["low_stress"].iloc[0])
