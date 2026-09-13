"""Test the stage orchestration.

The pipeline's stage order is load-bearing, and two orderings in particular
are easy to get wrong: census blocks must load before the OSM extract (the
extract is clipped to their extent), and features must precede stress, which
must precede the network.
"""

import inspect
import pathlib

import pandas as pd
import pytest

from brokenspoke_analyzer.core.pipeline import (
    errors,
    features,
    network,
    orchestrator,
    scoring,
    stress,
)


class TestAnalysisInputs:
    """Test the analysis input contract."""

    def test_defaults_come_from_the_stage_modules(self) -> None:
        """Constants are not re-declared here; they come from their stage."""
        inputs = orchestrator.AnalysisInputs(
            country="united states",
            city="somewhere",
            region="texas",
            fips_code="4800000",
            data_dir=pathlib.Path("data"),
        )
        assert inputs.max_trip_distance == network.DEFAULT_MAX_TRIP_DISTANCE
        assert inputs.boundary_buffer == features.DEFAULT_BOUNDARY_BUFFER
        assert inputs.city_speed_limit == stress.DEFAULT_CITY_SPEED_LIMIT

    def test_is_immutable(self) -> None:
        """Inputs are frozen, so a stage cannot alter them mid-run."""
        inputs = orchestrator.AnalysisInputs(
            country="c",
            city="x",
            region=None,
            fips_code="0",
            data_dir=pathlib.Path("data"),
        )
        with pytest.raises(AttributeError):
            inputs.city = "other"  # type: ignore[misc]


class TestMissingInputs:
    """Test the failure mode when `prepare` has not run."""

    def test_missing_prepare_output_raises_ingest_error(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A missing data directory fails with a typed, actionable error."""
        inputs = orchestrator.AnalysisInputs(
            country="united states",
            city="nowhere",
            region="texas",
            fips_code="4800000",
            data_dir=tmp_path,
        )
        with pytest.raises(errors.IngestError, match="prepare"):
            orchestrator.analyze(inputs)


class TestLodesDiscovery:
    """Test the LODES vintage discovery."""

    def artifacts(self, tmp_path: pathlib.Path) -> object:
        """Build an artifact set rooted at a temporary directory."""
        from brokenspoke_analyzer.core.pipeline import ingest  # noqa: PLC0415

        return ingest.PrepareArtifacts(data_dir=tmp_path, slug="somewhere")

    def test_finds_the_year_from_the_filename(self, tmp_path: pathlib.Path) -> None:
        """The vintage is read off the file `prepare` downloaded."""
        (tmp_path / "co_od_main_JT00_2023.csv").write_text("")
        assert orchestrator._discover_lodes_year(self.artifacts(tmp_path)) == 2023

    def test_absent_lodes_yields_none(self, tmp_path: pathlib.Path) -> None:
        """Puerto Rico has no LODES data; that is not an error."""
        assert orchestrator._discover_lodes_year(self.artifacts(tmp_path)) is None


class TestEmploymentWithoutLodes:
    """Test what happens where the Census Bureau collects no jobs data."""

    def test_the_lodes_branch_is_keyed_on_the_discovered_year(self) -> None:
        """No LODES file means no employment columns at all.

        Outside the US `census_block_jobs.sql` never runs, so every
        employment column stays NULL -- which is not the same as a city where
        nobody works, and scores differently (findings.md §1.16).
        """
        source = inspect.getsource(orchestrator._score)
        assert "if lodes_year:" in source
        assert 'blocks["emp_low_stress"] = np.nan' in source

    def test_a_null_employment_total_scores_null(self) -> None:
        """The score built on a NULL total is NULL, not zero."""
        totals = pd.Series([float("nan"), 0.0])
        score = scoring.step_score(totals, totals)
        assert pd.isna(score.iloc[0])
        assert pd.isna(score.iloc[1])
