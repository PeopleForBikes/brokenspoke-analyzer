"""Test the `stress` pipeline stage.

Cover the segment rules per functional class and the shared intersection rule
table. Synthetic inputs throughout: no database, no city fixtures.
"""

import geopandas as gpd
import pandas as pd
import pytest
import shapely

from brokenspoke_analyzer.core.pipeline import stress

UTM13N = 32613


def ways(rows: list[dict]) -> gpd.GeoDataFrame:
    """Build a ways frame with sensible defaults."""
    for index, row in enumerate(rows):
        row.setdefault("road_id", index + 1)
        row.setdefault("geometry", shapely.LineString([(index, 0), (index, 100)]))
        row.setdefault("intersection_from", f"a{index}")
        row.setdefault("intersection_to", f"b{index}")
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{UTM13N}")


class TestSegmentStress:
    """Test the per-class segment rules."""

    def rate(self, row: dict, **kwargs: object) -> tuple[object, object]:
        """Return `(ft_seg_stress, tf_seg_stress)` for one road."""
        got = stress.derive_segment_stress(ways([row]), **kwargs).iloc[0]
        return got["ft_seg_stress"], got["tf_seg_stress"]

    @pytest.mark.parametrize(
        "functional_class", ["motorway", "trunk", "motorway_link", "trunk_link"]
    )
    def test_motorways_are_always_high_stress(self, functional_class: str) -> None:
        """A motorway or trunk is high stress regardless of anything else."""
        assert self.rate({"functional_class": functional_class}) == (3, 3)

    @pytest.mark.parametrize("functional_class", ["track", "path"])
    def test_tracks_and_paths_are_always_low_stress(
        self, functional_class: str
    ) -> None:
        """Off-road ways are low stress regardless of anything else."""
        assert self.rate({"functional_class": functional_class}) == (1, 1)

    def test_protected_track_is_always_low_stress(self) -> None:
        """A protected track beats speed and lane count."""
        got = self.rate(
            {
                "functional_class": "primary",
                "ft_bike_infra": "track",
                "speed_limit": 55,
                "ft_lanes": 4,
            },
        )
        assert got[0] == 1

    def test_buffered_lane_survives_to_25_mph(self) -> None:
        """A buffered lane is comfortable up to 25 mph on a single lane."""
        base = {"functional_class": "primary", "ft_bike_infra": "buffered_lane"}
        assert self.rate({**base, "speed_limit": 25, "ft_lanes": 1})[0] == 1
        assert self.rate({**base, "speed_limit": 26, "ft_lanes": 1})[0] == 3
        # More than one lane is high stress even when slow.
        assert self.rate({**base, "speed_limit": 25, "ft_lanes": 2})[0] == 3

    def test_conventional_lane_needs_speed_lanes_and_width(self) -> None:
        """A painted lane needs 20 mph or less, one lane, and 4 ft."""
        base = {"functional_class": "primary", "ft_bike_infra": "lane"}
        good = {**base, "speed_limit": 20, "ft_lanes": 1, "ft_bike_infra_width": 5}
        assert self.rate(good)[0] == 1
        assert self.rate({**good, "speed_limit": 21})[0] == 3
        assert self.rate({**good, "ft_lanes": 2})[0] == 3
        # A narrow lane is high stress even when slow and single-lane.
        assert self.rate({**good, "ft_bike_infra_width": 3})[0] == 3

    def test_shared_lane_needs_15_mph(self) -> None:
        """With no facility, only 15 mph or less on one lane is comfortable."""
        base = {"functional_class": "primary"}
        assert self.rate({**base, "speed_limit": 15, "ft_lanes": 1})[0] == 1
        assert self.rate({**base, "speed_limit": 16, "ft_lanes": 1})[0] == 3

    def test_class_defaults_fill_missing_tags(self) -> None:
        """Each class assumes its own speed and lane count.

        A primary assumes 40 mph and two lanes; a tertiary 30 and one. With no
        tags at all the assumption alone decides the rating.
        """
        assert self.rate({"functional_class": "primary"})[0] == 3
        assert self.rate({"functional_class": "tertiary"})[0] == 3

    def test_residential_uses_the_speed_defaults(self) -> None:
        """The residential default decides every untagged residential street."""
        row = {"functional_class": "residential"}
        assert self.rate(row, state_default_speed=25, city_default_speed=None) == (1, 1)
        assert self.rate(row, state_default_speed=30, city_default_speed=None) == (3, 3)

    def test_city_default_outranks_state_default(self) -> None:
        """A city that sets its own residential limit overrides the state."""
        row = {"functional_class": "residential"}
        assert self.rate(row, state_default_speed=30, city_default_speed=25) == (1, 1)

    def test_tagged_speed_outranks_both_defaults(self) -> None:
        """An explicit `maxspeed` beats every fallback."""
        row = {"functional_class": "residential", "speed_limit": 40}
        assert self.rate(row, state_default_speed=25, city_default_speed=25) == (3, 3)

    def test_living_street_is_low_unless_bikes_banned(self) -> None:
        """A living street is comfortable unless bikes are excluded."""
        assert self.rate({"functional_class": "living_street"}) == (1, 1)
        assert self.rate({"functional_class": "living_street", "bicycle": "no"}) == (
            3,
            3,
        )

    def test_unknown_class_is_left_unrated(self) -> None:
        """A class no script covers keeps a NULL rating."""
        ft, tf = self.rate({"functional_class": "proposed"})
        assert pd.isna(ft)
        assert pd.isna(tf)


class TestOneWayReset:
    """Test `stress_one_way_reset.sql`."""

    def test_forbidden_direction_is_cleared(self) -> None:
        """A one-way street has no rating against the flow."""
        frame = ways([{"functional_class": "path", "one_way": "ft"}])
        got = stress.derive_segment_stress(frame).iloc[0]
        assert got["ft_seg_stress"] == 1
        assert pd.isna(got["tf_seg_stress"])

    def test_reset_keys_off_the_bike_direction(self) -> None:
        """`one_way`, not `one_way_car`, drives the reset.

        A street one-way for cars but with contraflow bike infrastructure has
        `one_way` NULL, and keeps both directions rated.
        """
        frame = ways(
            [{"functional_class": "path", "one_way_car": "ft", "one_way": None}],
        )
        got = stress.derive_segment_stress(frame).iloc[0]
        assert got["ft_seg_stress"] == 1
        assert got["tf_seg_stress"] == 1


class TestCrossingHostility:
    """Test the shared intersection rule table."""

    def hostile(
        self, crossing: dict, *, rrfb: bool = False, island: bool = False
    ) -> bool:
        """Return whether one crossing road makes a junction high stress."""
        frame = pd.DataFrame([crossing])
        got = stress._crossing_is_hostile(
            frame,
            pd.Series([rrfb]),
            pd.Series([island]),
        )
        return bool(got.iloc[0])

    def test_motorway_is_always_hostile(self) -> None:
        """Crossing a motorway or trunk is always high stress."""
        assert self.hostile({"functional_class": "motorway"})
        assert self.hostile({"functional_class": "trunk"})

    def test_wide_two_way_is_hostile_regardless_of_speed(self) -> None:
        """More than four lanes is hostile however slow the traffic."""
        assert self.hostile(
            {
                "functional_class": "primary",
                "one_way": None,
                "ft_lanes": 3,
                "tf_lanes": 3,
                "speed_limit": 20,
            },
        )

    def test_island_rescues_a_moderate_crossing(self) -> None:
        """A refuge island makes an otherwise hostile crossing acceptable."""
        crossing = {
            "functional_class": "primary",
            "one_way": None,
            "ft_lanes": 1,
            "tf_lanes": 1,
            "speed_limit": 35,
        }
        assert self.hostile(crossing, island=False)
        assert not self.hostile(crossing, island=True)

    def test_beacon_raises_the_tolerated_speed(self) -> None:
        """An rrfb lets a four-lane crossing tolerate more speed."""
        crossing = {
            "functional_class": "primary",
            "one_way": None,
            "ft_lanes": 2,
            "tf_lanes": 2,
            "speed_limit": 35,
        }
        # Without a beacon, 35 > 30 is hostile outright.
        assert self.hostile(crossing, rrfb=False)
        # With one, 35 is only hostile absent an island.
        assert self.hostile(crossing, rrfb=True, island=False)
        assert not self.hostile(crossing, rrfb=True, island=True)

    def test_one_way_counts_a_single_direction(self) -> None:
        """A one-way crossing counts only the tagged direction's lanes.

        The thresholds are 2 rather than 4 because they describe the same
        roadway width counted one way instead of both.
        """
        assert self.hostile(
            {
                "functional_class": "primary",
                "one_way": "ft",
                "ft_lanes": 3,
                "speed_limit": 20,
            },
        )
        assert not self.hostile(
            {
                "functional_class": "primary",
                "one_way": "ft",
                "ft_lanes": 1,
                "speed_limit": 25,
            },
        )

    def test_class_defaults_apply_to_untagged_crossings(self) -> None:
        """An untagged primary assumes 40 mph over two lanes each way."""
        assert self.hostile({"functional_class": "primary", "one_way": None})

    def test_unlisted_class_is_not_hostile(self) -> None:
        """A residential crossing never makes a junction high stress."""
        assert not self.hostile({"functional_class": "residential", "one_way": None})
