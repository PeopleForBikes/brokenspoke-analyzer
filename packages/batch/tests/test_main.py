"""Test the main module."""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from bna.batch import main
from bna.lib import constant

if TYPE_CHECKING:
    import pathlib
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

runner = CliRunner()

app = typer.Typer()
app.command()(main.main)

CITIES_CSV = """country,region,city,fips_code
"united states","new mexico","santa rosa",3570670
spain,,valencia,0
"""


@pytest.fixture
def compose(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the analysis run, and restore the environment ``main`` changes."""
    monkeypatch.setenv("BNA_EXPERIMENTAL", "")
    monkeypatch.setenv("BNA_CACHING_STRATEGY", "")
    return mocker.patch.object(main.run_with, "compose")


@pytest.fixture
def batch_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a batch file with a US city and a city without a region."""
    path = tmp_path / "cities.csv"
    path.write_text(CITIES_CSV)
    return path


def test_command_exposes_the_options() -> None:
    """Ensure the command exposes the batch file and every option."""
    command = typer.main.get_command(app)
    names = {opt for param in command.params for opt in param.opts}
    assert {
        "batch_file",
        "--export-dir",
        "--lodes-year",
        "--with-parts",
        "--worldpop-year",
        "--version",
    } <= names


def test_version_does_not_need_a_batch_file(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure ``--version`` works even when the batch file does not exist."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["missing.csv", "--version"])
    assert result.exit_code == 0, result.output
    assert f"bna-batch version: {metadata.version('bna-batch')}" in result.output


def test_runs_one_analysis_per_city(
    compose: MagicMock,
    batch_file: pathlib.Path,
) -> None:
    """Ensure every row runs an analysis, the region defaulting to the country."""
    result = runner.invoke(app, [str(batch_file)])
    assert result.exit_code == 0, result.output
    assert compose.call_count == 2
    first, second = (call.kwargs for call in compose.call_args_list)
    assert (first["country"], first["region"], first["city"], first["fips_code"]) == (
        "united states",
        "new mexico",
        "santa rosa",
        "3570670",
    )
    assert (second["country"], second["region"], second["city"]) == (
        "spain",
        "spain",
        "valencia",
    )
    for kwargs in (first, second):
        assert kwargs["with_parts"] == [constant.ComputePart.MEASURE]


def test_with_parts_is_passed_through(
    compose: MagicMock,
    batch_file: pathlib.Path,
) -> None:
    """Ensure ``--with-parts`` replaces the default parts."""
    result = runner.invoke(
        app,
        [str(batch_file), "--with-parts", "features", "--with-parts", "stress"],
    )
    assert result.exit_code == 0, result.output
    for call in compose.call_args_list:
        assert call.kwargs["with_parts"] == [
            constant.ComputePart.FEATURES,
            constant.ComputePart.STRESS,
        ]


def test_enables_experimental_features_and_the_user_cache(
    compose: MagicMock,  # noqa: ARG001
    batch_file: pathlib.Path,
) -> None:
    """Ensure a batch runs with experimental features and the user cache."""
    result = runner.invoke(app, [str(batch_file)])
    assert result.exit_code == 0, result.output
    assert main.os.environ["BNA_EXPERIMENTAL"] == "1"
    assert main.os.environ["BNA_CACHING_STRATEGY"] == "USER_CACHE"
