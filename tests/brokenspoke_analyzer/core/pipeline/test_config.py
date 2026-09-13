"""Test the pipeline runtime constants.

Pin the values that determine published BNA scores. These are not style
assertions: `Score`'s weights in particular are the authoritative set
(the weights quoted in the SQL comment blocks are stale), so an accidental
edit here silently changes every city's overall score.
"""

import importlib.util

from brokenspoke_analyzer.core.pipeline import config


def test_score_weights_are_authoritative() -> None:
    """The category weights match the values the SQL was invoked with."""
    score = config.Score()
    assert score.people == 15
    assert score.opportunity == 20
    assert score.core_services == 20
    assert score.retail == 15
    assert score.recreation == 15
    assert score.transit == 15


def test_score_weights_sum_to_total() -> None:
    """The six category weights account for the whole 100-point score."""
    score = config.Score()
    weights = [
        score.people,
        score.opportunity,
        score.core_services,
        score.retail,
        score.recreation,
        score.transit,
    ]
    assert sum(weights) == score.total


def test_tolerance_defaults() -> None:
    """Cluster tolerances are unchanged from the SQL-era values."""
    tolerance = config.Tolerance()
    assert tolerance.colleges == 100
    assert tolerance.universities == 150
    assert tolerance.transit == 75
    # Everything else clusters at 50.
    assert tolerance.doctors == 50
    assert tolerance.parks == 50


def test_path_constraint_and_block_road_defaults() -> None:
    """Recreation-path and block-road constraints are unchanged."""
    path = config.PathConstraint()
    assert (path.min_length, path.min_bbox) == (4800, 3300)
    block_road = config.BlockRoad()
    assert (block_road.buffer, block_road.min_length) == (15, 30)


def test_access_defaults_to_zero_weights() -> None:
    """An `Access` carries no weight until one is given explicitly."""
    access = config.Access("parks")
    assert access.name == "parks"
    assert (access.first, access.second, access.third) == (0.0, 0.0, 0.0)
    assert access.max_score == 1


def test_config_is_the_only_home_for_the_runtime_constants() -> None:
    """`compute.py` re-exported these until task 11 deleted it.

    The dataclasses moved here in task 2.3 while the SQL path still aliased
    them as `compute.Tolerance` and friends. That path is gone, so this
    module is now the single source of truth and nothing should resurrect a
    second copy.
    """
    assert importlib.util.find_spec("brokenspoke_analyzer.core.compute") is None
