"""Test the `features` pipeline stage.

Cover the rules that decide which roads exist and what they are called:
`clip_osm.sql`, `one_way.sql`, `width_ft.sql`, `functional_class.sql`, and the
bicycle-prohibited-path delete that lives in `compute.features()` rather than
in any `.sql` file. Synthetic inputs throughout.
"""

import geopandas as gpd
import pandas as pd
import pytest
import shapely

from brokenspoke_analyzer.core.pipeline import features

UTM13N = 32613


def ways(rows: list[dict]) -> gpd.GeoDataFrame:
    """Build a ways frame, defaulting the geometry to a unit segment."""
    for index, row in enumerate(rows):
        row.setdefault("geometry", shapely.LineString([(index, 0), (index, 1)]))
        row.setdefault("intersection_from", f"a{index}")
        row.setdefault("intersection_to", f"b{index}")
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{UTM13N}")


class TestNullSafeComparison:
    """Test the NULL-safe tag comparison.

    A plain `==` on a nullable column yields `pd.NA` for an absent tag, and the
    `NA` then survives `~` and `&`. Used as a mask, pandas drops those rows --
    so an *untagged* way gets treated as though it matched. This silently
    deleted 16 untagged paths from Crested Butte before it was caught.
    """

    def test_null_compares_false(self) -> None:
        """A missing tag never equals a value."""
        tags = pd.Series(["no", None, "yes"], dtype="string")
        assert list(features._eq(tags, "no")) == [True, False, False]

    def test_negation_keeps_nulls(self) -> None:
        """Negating the comparison keeps untagged rows, rather than dropping them."""
        tags = pd.Series(["no", None, "yes"], dtype="string")
        assert list(~features._eq(tags, "no")) == [False, True, True]

    def test_mask_never_contains_na(self) -> None:
        """The result is a plain boolean mask, safe to index with."""
        tags = pd.Series([None, None], dtype="string")
        mask = features._eq(tags, "x")
        assert mask.dtype == bool
        assert not mask.isna().any()


class TestDeriveOneWay:
    """Test `one_way.sql`."""

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [("yes", "ft"), ("1", "ft"), ("-1", "tf"), (" yes ", "ft")],
    )
    def test_recognised_values(self, tag: str, expected: str) -> None:
        """The tag values the SQL matches, including surrounding whitespace."""
        assert features.derive_one_way(ways([{"oneway": tag}])).iloc[0] == expected

    @pytest.mark.parametrize("tag", ["no", "reversible", "alternating", None])
    def test_everything_else_is_two_way(self, tag: str | None) -> None:
        """Any other value leaves the road two-way.

        `reversible` and `alternating` are real OSM values the SQL does not
        handle; they must stay two-way rather than being "improved".
        """
        assert pd.isna(features.derive_one_way(ways([{"oneway": tag}])).iloc[0])

    def test_missing_column(self) -> None:
        """An extract with no `oneway` tag at all yields all-null."""
        assert pd.isna(
            features.derive_one_way(ways([{"highway": "residential"}])).iloc[0]
        )


class TestDeriveWidthFt:
    """Test `width_ft.sql`'s four passes."""

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("10 ft", 10),
            # 3 m = 9.84 ft, rounded to the INT column's 10.
            ("3 m", 10),
            ("12'", 12),
            # 12.5 rounds away from zero, to 13 rather than NumPy's 12.
            ("12'6\"", 13),
            ("2.5", 8),
            ("0.5", 2),
        ],
    )
    def test_parses_each_notation(self, tag: str, expected: int) -> None:
        """Feet, metres, feet-and-inches, and unitless-as-metres.

        Results are integers: `neighborhood_ways.width_ft` is declared INT, so
        the SQL rounds on assignment and every later reader sees the integer.
        """
        got = features.derive_width_ft(ways([{"width": tag}])).iloc[0]
        assert got == expected

    def test_unitless_over_twenty_is_discarded(self) -> None:
        """A large unitless value is bogus rather than metres.

        The SQL weeds these out explicitly: 25 would be 82 feet as metres.
        """
        assert pd.isna(features.derive_width_ft(ways([{"width": "25"}])).iloc[0])

    def test_unitless_boundary(self) -> None:
        """The cutoff is strict: 20 is discarded, just under is kept."""
        assert pd.isna(features.derive_width_ft(ways([{"width": "20"}])).iloc[0])
        assert features.derive_width_ft(ways([{"width": "19"}])).iloc[0] > 0

    def test_missing_width(self) -> None:
        """No tag means no width."""
        assert pd.isna(features.derive_width_ft(ways([{"width": None}])).iloc[0])


class TestFunctionalClass:
    """Test `functional_class.sql`'s classification and access rules."""

    def classify(self, row: dict) -> str | None:
        """Return the functional class derived for one way."""
        frame = ways([row])
        width = features.derive_width_ft(frame)
        result, _ = features.derive_functional_class(frame, width)
        value = result.iloc[0]
        return None if pd.isna(value) else str(value)

    @pytest.mark.parametrize(
        "highway",
        ["residential", "primary", "motorway", "tertiary_link", "living_street"],
    )
    def test_direct_classes_pass_through(self, highway: str) -> None:
        """Ordinary road classes map straight through."""
        assert self.classify({"highway": highway}) == highway

    def test_unroutable_highway_is_unclassified(self) -> None:
        """A highway value outside every rule stays NULL and is dropped."""
        assert self.classify({"highway": "proposed"}) is None

    def test_cycleway_becomes_path(self) -> None:
        """Cycleways and paths become `path`."""
        assert self.classify({"highway": "cycleway"}) == "path"
        assert self.classify({"highway": "path"}) == "path"

    def test_track_needs_grade1(self) -> None:
        """Only a grade1 track is routable."""
        assert self.classify({"highway": "track", "tracktype": "grade1"}) == "track"
        assert self.classify({"highway": "track", "tracktype": "grade3"}) is None

    def test_footway_crossing_is_a_path(self) -> None:
        """A footway crossing becomes a path and is flagged as a crosswalk."""
        frame = ways([{"highway": "footway", "footway": "crossing"}])
        result, xwalk = features.derive_functional_class(
            frame, features.derive_width_ft(frame)
        )
        assert result.iloc[0] == "path"
        assert xwalk.iloc[0] == 1

    def test_footway_needs_designation_or_width(self) -> None:
        """A bikeable footway must be designated or at least 8 ft wide."""
        assert self.classify({"highway": "footway", "bicycle": "designated"}) == "path"
        # Allowed but narrow: not a path.
        assert (
            self.classify({"highway": "footway", "bicycle": "yes", "width": "1 ft"})
            is None
        )
        # Allowed and wide enough.
        assert (
            self.classify({"highway": "footway", "bicycle": "yes", "width": "10 ft"})
            == "path"
        )

    def test_access_private_is_rejected_even_for_bikes(self) -> None:
        """`access=private` is rejected even when bikes are designated.

        The SQL's bicycle exemption applies only to `access='no'`, not to
        `access='private'`. The asymmetry looks like an oversight but is
        reproduced deliberately -- our SQL is the reference implementation.
        """
        assert (
            self.classify(
                {"highway": "residential", "access": "private", "bicycle": "designated"}
            )
            is None
        )

    def test_access_no_is_exempted_for_bikes(self) -> None:
        """`access=no` is routable when bikes are explicitly allowed."""
        assert (
            self.classify(
                {"highway": "residential", "access": "no", "bicycle": "designated"}
            )
            == "residential"
        )
        assert self.classify({"highway": "residential", "access": "no"}) is None

    def test_untagged_access_is_permitted(self) -> None:
        """A way with no `access` tag is routable."""
        assert self.classify({"highway": "residential"}) == "residential"


class TestDropBicyclePropibitedPaths:
    """Test the delete that lives in `compute.features()`, not in the SQL files."""

    def test_drops_bicycle_no_paths(self) -> None:
        """`highway=path` with `bicycle=no` is removed."""
        frame = ways(
            [
                {"highway": "path", "bicycle": "no"},
                {"highway": "path", "bicycle": "yes"},
            ],
        )
        kept = features.drop_bicycle_prohibited_paths(frame)
        assert len(kept) == 1
        assert kept.iloc[0]["bicycle"] == "yes"

    def test_keeps_untagged_paths(self) -> None:
        """A path with no `bicycle` tag is kept.

        This is the NULL-handling regression: an untagged path must not be
        treated as though it were tagged `no`.
        """
        frame = ways([{"highway": "path"}, {"highway": "path", "bicycle": None}])
        assert len(features.drop_bicycle_prohibited_paths(frame)) == 2

    def test_keeps_bicycle_no_on_other_highways(self) -> None:
        """The rule is scoped to paths; a road with `bicycle=no` stays."""
        frame = ways([{"highway": "residential", "bicycle": "no"}])
        assert len(features.drop_bicycle_prohibited_paths(frame)) == 1


class TestClipToBoundary:
    """Test `clip_osm.sql`'s boundary-buffer delete."""

    def boundary(self) -> gpd.GeoDataFrame:
        """Return a small boundary polygon at the origin."""
        return gpd.GeoDataFrame(
            {"geometry": [shapely.box(0, 0, 10, 10)]}, crs=f"EPSG:{UTM13N}"
        )

    def test_keeps_roads_within_the_buffer(self) -> None:
        """A road just inside the buffer distance survives."""
        frame = ways([{"geometry": shapely.LineString([(50, 5), (60, 5)])}])
        assert len(features.clip_to_boundary(frame, self.boundary(), buffer=100)) == 1

    def test_drops_roads_beyond_the_buffer(self) -> None:
        """A road past the buffer distance is dropped."""
        frame = ways([{"geometry": shapely.LineString([(500, 5), (600, 5)])}])
        assert len(features.clip_to_boundary(frame, self.boundary(), buffer=100)) == 0

    def test_uses_true_distance_not_an_approximated_buffer(self) -> None:
        """The test is an exact distance comparison.

        Buffering approximates arcs with straight segments, so a road sitting
        almost exactly `buffer` away from a corner falls inside a true distance
        test but outside a segmented buffer. `ST_DWithin` is exact.
        """
        # Diagonally off the (10, 10) corner, at distance 100 - epsilon.
        offset = 100 / (2**0.5) - 0.01
        point = (10 + offset, 10 + offset)
        frame = ways([{"geometry": shapely.LineString([point, point])}])
        assert len(features.clip_to_boundary(frame, self.boundary(), buffer=100)) == 1


class TestDropOrphans:
    """Test the orphan delete in `functional_class.sql`."""

    def test_keeps_connected_roads(self) -> None:
        """Roads sharing an endpoint are all kept."""
        frame = ways(
            [
                {"intersection_from": "a", "intersection_to": "b"},
                {"intersection_from": "b", "intersection_to": "c"},
            ],
        )
        assert len(features.drop_orphans(frame)) == 2

    def test_drops_a_fully_isolated_road(self) -> None:
        """A road sharing neither endpoint is dropped."""
        frame = ways(
            [
                {"intersection_from": "a", "intersection_to": "b"},
                {"intersection_from": "b", "intersection_to": "c"},
                {"intersection_from": "y", "intersection_to": "z"},
            ],
        )
        kept = features.drop_orphans(frame)
        assert len(kept) == 2
        assert "y" not in set(kept["intersection_from"])

    def test_keeps_a_road_connected_at_one_end(self) -> None:
        """One shared endpoint is enough; the SQL requires *neither* to match."""
        frame = ways(
            [
                {"intersection_from": "a", "intersection_to": "b"},
                {"intersection_from": "b", "intersection_to": "c"},
                {"intersection_from": "c", "intersection_to": "dangling"},
            ],
        )
        assert len(features.drop_orphans(frame)) == 3

    def test_is_not_iterated_to_a_fixed_point(self) -> None:
        """A dangling two-road chain survives, as it does in the SQL.

        The SQL runs the delete once. Removing the outer road would orphan the
        inner one, but that second pass never happens -- so neither goes.
        """
        frame = ways(
            [
                {"intersection_from": "a", "intersection_to": "b"},
                {"intersection_from": "b", "intersection_to": "c"},
                {"intersection_from": "x", "intersection_to": "y"},
                {"intersection_from": "y", "intersection_to": "z"},
            ],
        )
        assert len(features.drop_orphans(frame)) == 4


class TestRoundHalfAway:
    """Test the PostgreSQL-compatible rounding used for `INT` columns."""

    def test_rounds_half_away_from_zero(self) -> None:
        """2.5 rounds to 3, not to 2 as NumPy's half-to-even would."""
        values = pd.Series([2.5, 3.5, -2.5, 8.2, 9.84])
        assert list(features._round_half_away(values)) == [3, 4, -3, 8, 10]

    def test_preserves_nulls(self) -> None:
        """A missing value stays missing rather than becoming 0."""
        result = features._round_half_away(pd.Series([float("nan"), 1.2]))
        assert pd.isna(result.iloc[0])
        assert result.iloc[1] == 1


class TestDeriveSpeedLimit:
    """Test `speed_limit.sql`."""

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("30 mph", 30),
            ("25 mph", 25),
            # km/h converts and rounds to the nearest 5 mph.
            ("50 kmph", 30),
            ("80 kmph", 50),
            # A bare number has no unit and is read as km/h.
            ("50", 30),
            ("30", 20),
        ],
    )
    def test_parses_each_notation(self, tag: str, expected: int) -> None:
        """mph verbatim; km/h converted and rounded to a multiple of 5."""
        assert (
            features.derive_speed_limit(ways([{"maxspeed": tag}])).iloc[0] == expected
        )

    @pytest.mark.parametrize("tag", ["walk", "none", "signals", None])
    def test_unparseable_is_null(self, tag: str | None) -> None:
        """A non-numeric limit leaves the column NULL for a default to fill."""
        assert pd.isna(features.derive_speed_limit(ways([{"maxspeed": tag}])).iloc[0])

    def test_mph_wins_over_kmph(self) -> None:
        """The mph pass runs second and overwrites the km/h reading."""
        assert features.derive_speed_limit(ways([{"maxspeed": "30 mph"}])).iloc[0] == 30


class TestDeriveLanes:
    """Test `lanes.sql`'s ordered CASE ladder."""

    def lanes(self, row: dict) -> dict:
        """Return the derived lane columns for one way."""
        return features.derive_lanes(ways([row])).iloc[0].to_dict()

    def test_directional_turn_lanes_win(self) -> None:
        """`turn:lanes:forward` beats every later branch."""
        got = self.lanes(
            {"turn:lanes:forward": "left|through|right", "lanes": "9", "oneway": "yes"}
        )
        assert got["ft_lanes"] == 3

    def test_right_only_lanes_excluded_from_crossing(self) -> None:
        """Crossing stress ignores right-only turn lanes; plain counts do not."""
        got = self.lanes({"turn:lanes:forward": "left|through|right"})
        assert got["ft_lanes"] == 3
        assert got["ft_cross_lanes"] == 2

    def test_shared_turn_lanes_need_a_matching_oneway(self) -> None:
        """Undirected `turn:lanes` only counts forward on a forward one-way."""
        assert (
            self.lanes({"turn:lanes": "left|right", "oneway": "yes"})["ft_lanes"] == 2
        )
        assert pd.isna(
            self.lanes({"turn:lanes": "left|right", "oneway": "no"})["ft_lanes"]
        )

    def test_shared_turn_lanes_count_backward_on_reversed_oneway(self) -> None:
        """`oneway=-1` routes the shared turn lanes to the backward direction."""
        got = self.lanes({"turn:lanes": "left|right", "oneway": "-1"})
        assert got["tf_lanes"] == 2
        assert pd.isna(got["ft_lanes"])

    def test_two_way_halves_the_shared_lane_count(self) -> None:
        """A shared `lanes` on a two-way road is halved, rounding up."""
        got = self.lanes({"lanes": "5", "oneway": "no"})
        assert got["ft_lanes"] == 3
        assert got["tf_lanes"] == 3

    def test_one_way_takes_all_shared_lanes(self) -> None:
        """A one-way road gets the whole shared lane count in its direction."""
        got = self.lanes({"lanes": "4", "oneway": "yes"})
        assert got["ft_lanes"] == 4
        assert pd.isna(got["tf_lanes"])

    def test_untagged_oneway_counts_as_two_way(self) -> None:
        """No `oneway` tag behaves like `oneway=no`."""
        assert self.lanes({"lanes": "5"})["ft_lanes"] == 3

    def test_twltl_flag(self) -> None:
        """Either both-ways tag raises the two-way-left-turn-lane flag."""
        assert self.lanes({"lanes:both_ways": "1"})["twltl_cross_lanes"] == 1
        assert self.lanes({"turn:lanes:both_ways": "left"})["twltl_cross_lanes"] == 1
        assert pd.isna(self.lanes({"lanes": "2"})["twltl_cross_lanes"])

    def test_no_lane_tags_yields_nothing(self) -> None:
        """A way with no lane tags gets no lane counts."""
        got = self.lanes({"highway": "residential"})
        assert all(pd.isna(got[c]) for c in ("ft_lanes", "tf_lanes"))


class TestAdjustFunctionalClass:
    """Test `class_adjustments.sql`."""

    def adjust(self, row: dict) -> str:
        """Return the adjusted functional class for one way."""
        return str(features.adjust_functional_class(ways([row])).iloc[0])

    @pytest.mark.parametrize("original", ["residential", "unclassified"])
    def test_speed_promotes_to_tertiary(self, original: str) -> None:
        """30 mph or more promotes a low-order road."""
        assert (
            self.adjust({"functional_class": original, "speed_limit": 30}) == "tertiary"
        )

    def test_below_threshold_is_untouched(self) -> None:
        """Just under the threshold does not promote."""
        assert (
            self.adjust({"functional_class": "residential", "speed_limit": 29})
            == "residential"
        )

    def test_multiple_lanes_promote(self) -> None:
        """More than one lane in either direction promotes."""
        assert (
            self.adjust({"functional_class": "residential", "ft_lanes": 2})
            == "tertiary"
        )
        assert (
            self.adjust({"functional_class": "residential", "tf_lanes": 2})
            == "tertiary"
        )
        assert (
            self.adjust({"functional_class": "residential", "ft_lanes": 1})
            == "residential"
        )

    def test_bike_facilities_must_be_on_both_sides(self) -> None:
        """One-sided bike infrastructure does not promote."""
        assert (
            self.adjust(
                {
                    "functional_class": "residential",
                    "ft_bike_infra": "lane",
                    "tf_bike_infra": "lane",
                }
            )
            == "tertiary"
        )
        assert (
            self.adjust({"functional_class": "residential", "ft_bike_infra": "lane"})
            == "residential"
        )

    def test_higher_classes_are_never_adjusted(self) -> None:
        """Only residential and unclassified are eligible."""
        assert (
            self.adjust({"functional_class": "primary", "speed_limit": 60}) == "primary"
        )
        assert self.adjust({"functional_class": "path", "speed_limit": 60}) == "path"

    def test_missing_values_do_not_promote(self) -> None:
        """NULL comparisons are false, as in SQL."""
        assert self.adjust({"functional_class": "residential"}) == "residential"


class TestDeriveBikeInfra:
    """Test `bike_infra.sql`'s two large CASE ladders."""

    def infra(self, row: dict) -> tuple[str | None, str | None]:
        """Return `(ft_bike_infra, tf_bike_infra)` for one way."""
        ft, tf = features.derive_bike_infra(ways([row]))

        def value(series: pd.Series) -> str | None:
            got = series.iloc[0]
            return None if pd.isna(got) else str(got)

        return value(ft), value(tf)

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("shared_lane", "sharrow"),
            ("buffered_lane", "buffered_lane"),
            ("lane", "lane"),
            ("track", "track"),
        ],
    )
    def test_cycleway_both_applies_to_both_directions(
        self, tag: str, expected: str
    ) -> None:
        """`cycleway:both` sets the same facility in each direction."""
        assert self.infra({"cycleway:both": tag}) == (expected, expected)

    def test_buffer_upgrades_a_lane(self) -> None:
        """A buffered lane is recognised through either buffer tag."""
        assert self.infra({"cycleway:both": "lane", "cycleway:buffer": "yes"}) == (
            "buffered_lane",
            "buffered_lane",
        )
        assert self.infra(
            {"cycleway:both": "lane", "cycleway:both:buffer": "right"}
        ) == ("buffered_lane", "buffered_lane")

    def test_two_way_reads_the_matching_kerb(self) -> None:
        """On a two-way street `ft` reads the right kerb and `tf` the left."""
        assert self.infra({"cycleway:right": "lane"}) == ("lane", None)
        assert self.infra({"cycleway:left": "lane"}) == (None, "lane")

    def test_undirected_cycleway_applies_both_ways(self) -> None:
        """A plain `cycleway` tag counts in both directions."""
        assert self.infra({"cycleway": "track"}) == ("track", "track")

    def test_contraflow_lane_on_a_one_way(self) -> None:
        """`opposite_lane` gives the against-the-flow direction a lane."""
        assert self.infra({"cycleway": "opposite_lane", "one_way_car": "ft"}) == (
            None,
            "lane",
        )
        assert self.infra({"cycleway": "opposite_lane", "one_way_car": "tf"}) == (
            "lane",
            None,
        )

    def test_oneway_bicycle_no_makes_a_track_two_way(self) -> None:
        """`oneway:bicycle=no` promotes a one-sided track to both directions."""
        assert self.infra({"cycleway": "track", "oneway:bicycle": "no"}) == (
            "track",
            "track",
        )

    def test_reversed_cycleway_oneway_excludes_the_with_flow_direction(self) -> None:
        """A facility tagged `-1` does not serve the with-the-flow direction."""
        got = self.infra(
            {
                "one_way_car": "ft",
                "cycleway:left": "lane",
                "cycleway:left:oneway": "-1",
            },
        )
        assert got[0] is None

    def test_unreachable_tf_guard_is_reproduced(self) -> None:
        """The dead `one_way_car='tf'` guard stays dead.

        Inside `tf_bike_infra`'s `one_way_car = 'ft'` block the SQL guards two
        rules on `one_way_car = 'tf'`, which can never hold there. A road
        whose only bike tag is `cycleway:left=opposite_track` therefore gets
        nothing, even though the rule looks like it should apply. Reproduced
        deliberately: our SQL is the reference implementation.
        """
        assert self.infra({"one_way_car": "ft", "cycleway:left": "opposite_track"}) == (
            None,
            None,
        )
        # The same tag on the live side does apply.
        assert self.infra({"one_way_car": "tf", "cycleway:left": "opposite_track"}) == (
            "track",
            None,
        )

    def test_no_tags_means_no_infrastructure(self) -> None:
        """A road with no cycleway tags has no facility."""
        assert self.infra({"highway": "residential"}) == (None, None)


class TestDeriveBikeOneWay:
    """Test the `one_way` column, which is about bikes, not cars."""

    def one_way(self, row: dict) -> str | None:
        """Return the derived bike direction constraint."""
        got = features.derive_bike_one_way(ways([row])).iloc[0]
        return None if pd.isna(got) else str(got)

    def test_two_way_street_stays_two_way(self) -> None:
        """No car restriction means no bike restriction."""
        assert self.one_way({"one_way_car": None}) is None

    def test_one_way_without_contraflow_keeps_the_restriction(self) -> None:
        """A plain one-way street is one-way for bikes too."""
        assert self.one_way({"one_way_car": "ft"}) == "ft"

    def test_contraflow_infrastructure_frees_the_reverse_direction(self) -> None:
        """Infrastructure against the flow makes the road two-way for bikes."""
        assert self.one_way({"one_way_car": "ft", "tf_bike_infra": "lane"}) is None

    def test_oneway_bicycle_no_frees_the_reverse_direction(self) -> None:
        """`oneway:bicycle=no` alone lifts the restriction."""
        assert self.one_way({"one_way_car": "ft", "oneway:bicycle": "no"}) is None

    def test_infrastructure_on_the_same_side_does_not_free_it(self) -> None:
        """A facility in the direction of travel changes nothing."""
        assert self.one_way({"one_way_car": "ft", "ft_bike_infra": "lane"}) == "ft"


class TestDeriveBikeInfraWidth:
    """Test the bike facility widths."""

    def widths(self, row: dict) -> tuple[float | None, float | None]:
        """Return `(ft_bike_infra_width, tf_bike_infra_width)`."""
        ft, tf = features.derive_bike_infra_width(ways([row]))

        def value(series: pd.Series) -> float | None:
            got = series.iloc[0]
            return None if pd.isna(got) else float(got)

        return value(ft), value(tf)

    def test_width_requires_infrastructure(self) -> None:
        """A width tag is ignored where that direction has no facility."""
        assert self.widths({"cycleway:right:width": "5 ft"}) == (None, None)

    def test_feet_and_metres(self) -> None:
        """Explicit units are honoured; bare numbers are metres."""
        ft, _ = self.widths(
            {"ft_bike_infra": "lane", "cycleway:right:width": "5 ft"},
        )
        assert ft == pytest.approx(5.0)
        ft, _ = self.widths({"ft_bike_infra": "lane", "cycleway:right:width": "2 m"})
        assert ft == pytest.approx(6.56, abs=0.01)
        ft, _ = self.widths({"ft_bike_infra": "lane", "cycleway:right:width": "2"})
        assert ft == pytest.approx(6.56, abs=0.01)

    def test_each_direction_reads_its_own_kerb(self) -> None:
        """`ft` reads the right kerb, `tf` the left."""
        ft, tf = self.widths(
            {
                "ft_bike_infra": "lane",
                "tf_bike_infra": "lane",
                "cycleway:right:width": "4 ft",
                "cycleway:left:width": "6 ft",
            },
        )
        assert (ft, tf) == (4.0, 6.0)

    def test_falls_back_to_both_then_generic(self) -> None:
        """`cycleway:both:width` and `cycleway:width` are the fallbacks."""
        ft, tf = self.widths(
            {
                "ft_bike_infra": "lane",
                "tf_bike_infra": "lane",
                "cycleway:both:width": "7 ft",
            },
        )
        assert (ft, tf) == (7.0, 7.0)
        ft, _ = self.widths({"ft_bike_infra": "lane", "cycleway:width": "3 ft"})
        assert ft == pytest.approx(3.0)


class TestDeriveParking:
    """Test `park.sql`."""

    def park(self, row: dict) -> tuple[object, object]:
        """Return `(ft_park, tf_park)` for one way."""
        got = features.derive_parking(ways([row])).iloc[0]
        return got["ft_park"], got["tf_park"]

    @pytest.mark.parametrize(
        "value", ["parallel", "diagonal", "perpendicular", "paralell"]
    )
    def test_parking_present(self, value: str) -> None:
        """Each parking layout counts as parking, misspelling included.

        `paralell` is in the SQL on purpose -- it occurs in real OSM data.
        """
        assert self.park({"parking:lane:right": value})[0] == 1

    @pytest.mark.parametrize("value", ["no_parking", "no_stopping"])
    def test_parking_absent(self, value: str) -> None:
        """An explicit prohibition records 0, not NULL."""
        assert self.park({"parking:lane:right": value})[0] == 0

    def test_sides_are_independent(self) -> None:
        """The right kerb drives `ft_park`, the left drives `tf_park`."""
        ft, tf = self.park(
            {"parking:lane:right": "parallel", "parking:lane:left": "no_parking"},
        )
        assert (ft, tf) == (1, 0)

    def test_both_tag_alone_has_no_effect(self) -> None:
        """`parking:lane:both` is overwritten by the later side passes.

        The SQL's right/left updates assign unconditionally, so a road with
        no side tag ends up NULL even though the "both" pass set a value.
        This is the SQL's behaviour and is reproduced deliberately.
        """
        ft, tf = self.park({"parking:lane:both": "parallel"})
        assert pd.isna(ft)
        assert pd.isna(tf)

    def test_parking_and_restriction_tags(self) -> None:
        """The `parking:*` and `parking:*:restriction` fallbacks apply."""
        assert self.park({"parking:right": "lane"})[0] == 1
        assert self.park({"parking:right": "no"})[0] == 0
        assert self.park({"parking:right:restriction": "no_stopping"})[0] == 0

    def test_untagged_is_null(self) -> None:
        """No parking tag means unknown, not absent."""
        assert pd.isna(self.park({"highway": "residential"})[0])


class TestIntersectionLegs:
    """Test `legs.sql`."""

    def test_counts_roads_at_each_node(self) -> None:
        """Each road touching a node adds a leg."""
        frame = ways(
            [
                {"road_id": 1, "intersection_from": "a", "intersection_to": "x"},
                {"road_id": 2, "intersection_from": "b", "intersection_to": "x"},
                {"road_id": 3, "intersection_from": "c", "intersection_to": "x"},
            ],
        )
        legs = features.derive_intersection_legs(frame, ["x", "a", "zz"])
        assert legs.loc["x"] == 3
        assert legs.loc["a"] == 1
        # A node no road touches has no legs.
        assert legs.loc["zz"] == 0

    def test_a_loop_counts_its_road_once(self) -> None:
        """`int_id IN (from, to)` matches a self-looping road a single time."""
        frame = ways([{"road_id": 1, "intersection_from": "x", "intersection_to": "x"}])
        assert features.derive_intersection_legs(frame, ["x"]).loc["x"] == 1


class TestCalculateMileage:
    """Test `calculate_mileage.sql`."""

    def roads(self, rows: list[dict]) -> gpd.GeoDataFrame:
        """Build roads each exactly one mile long."""
        mile = features.METRES_PER_MILE
        for index, row in enumerate(rows):
            row["geometry"] = shapely.LineString(
                [(index * 10_000, 0), (index * 10_000, mile)],
            )
        return gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{UTM13N}")

    def test_totals_by_feature_type(self) -> None:
        """Each facility type accumulates its own mileage."""
        frame = self.roads(
            [
                {"ft_bike_infra": "lane", "tf_bike_infra": None},
                {"ft_bike_infra": "track", "tf_bike_infra": None},
            ],
        )
        got = features.calculate_mileage(frame).set_index("feature_type")
        assert got.loc["lane", "total_mileage"] == pytest.approx(1.0)
        assert got.loc["track", "total_mileage"] == pytest.approx(1.0)

    def test_both_directions_count_twice(self) -> None:
        """A facility on both sides contributes the length twice.

        These are directional facility miles, not centreline miles.
        """
        frame = self.roads([{"ft_bike_infra": "lane", "tf_bike_infra": "lane"}])
        got = features.calculate_mileage(frame).set_index("feature_type")
        assert got.loc["lane", "total_mileage"] == pytest.approx(2.0)

    def test_paths_count_but_crosswalks_do_not(self) -> None:
        """A path adds path mileage unless it is a crosswalk."""
        frame = self.roads(
            [
                {"functional_class": "path", "xwalk": None},
                {"functional_class": "path", "xwalk": 1},
            ],
        )
        got = features.calculate_mileage(frame).set_index("feature_type")
        assert got.loc["path", "total_mileage"] == pytest.approx(1.0)

    def test_unknown_types_are_ignored(self) -> None:
        """Only the five recognised feature types are totalled."""
        frame = self.roads([{"ft_bike_infra": "something_else"}])
        assert features.calculate_mileage(frame).empty


class TestClusterPaths:
    """Test `paths.sql`'s clustering."""

    def test_touching_paths_form_one_cluster(self) -> None:
        """Contiguous path roads become a single path."""
        frame = gpd.GeoDataFrame(
            {
                "functional_class": ["path", "path", "path"],
                "geometry": [
                    shapely.LineString([(0, 0), (10, 0)]),
                    shapely.LineString([(10, 0), (20, 0)]),
                    # Disconnected, so its own path.
                    shapely.LineString([(500, 0), (510, 0)]),
                ],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        path_id, table = features.cluster_paths(frame)
        assert len(table) == 2
        assert path_id.iloc[0] == path_id.iloc[1]
        assert path_id.iloc[2] != path_id.iloc[0]

    def test_records_length_and_bbox_span(self) -> None:
        """Each path records its length and bounding-box diagonal."""
        frame = gpd.GeoDataFrame(
            {
                "functional_class": ["path"],
                "geometry": [shapely.LineString([(0, 0), (30, 40)])],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        _, table = features.cluster_paths(frame)
        assert table.iloc[0]["path_length"] == pytest.approx(50.0)
        # 3-4-5 triangle: the bbox diagonal is also 50.
        assert table.iloc[0]["bbox_length"] == pytest.approx(50.0)

    def test_non_paths_get_no_path_id(self) -> None:
        """A road that is not a path is not clustered."""
        frame = gpd.GeoDataFrame(
            {
                "functional_class": ["residential"],
                "geometry": [shapely.LineString([(0, 0), (10, 0)])],
            },
            geometry="geometry",
            crs=f"EPSG:{UTM13N}",
        )
        path_id, table = features.cluster_paths(frame)
        assert pd.isna(path_id.iloc[0])
        assert table.empty
