"""Test the main module."""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from bna.cache_warmer import main

if TYPE_CHECKING:
    from unittest.mock import (
        AsyncMock,
        MagicMock,
    )

    from pytest_mock import MockerFixture

runner = CliRunner()


@pytest.fixture
def run_downloads(mocker: MockerFixture) -> AsyncMock:
    """Replace the downloads."""
    return mocker.patch.object(main, "_run_downloads", new=mocker.AsyncMock())


@pytest.fixture
def build_store(mocker: MockerFixture) -> MagicMock:
    """Replace the store construction, which would touch the user cache."""
    return mocker.patch.object(main, "_build_store")


def test_help_lists_the_subcommands() -> None:
    """Ensure the help advertises every cache target."""
    result = runner.invoke(main.app, ["--help"])
    assert result.exit_code == 0
    for subcommand in ["local", "s3"]:
        assert subcommand in result.output


def test_app_exposes_the_version_option() -> None:
    """Ensure the app exposes ``--version``."""
    command = typer.main.get_command(main.app)
    names = {opt for param in command.params for opt in param.opts}
    assert "--version" in names


def test_version_prints_the_distribution_version() -> None:
    """Ensure ``--version`` prints the version of ``bna-cache-warmer``."""
    result = runner.invoke(main.app, ["--version"])
    assert result.exit_code == 0, result.output
    expected = f"bna-cache-warmer version: {metadata.version('bna-cache-warmer')}"
    assert expected in result.output


@pytest.mark.parametrize(
    ("flags", "clear_osm"),
    [([], False), (["--clear-osm"], True)],
)
def test_local_warms_the_user_cache(
    run_downloads: AsyncMock,
    build_store: MagicMock,
    flags: list[str],
    *,
    clear_osm: bool,
) -> None:
    """Ensure ``local`` downloads into the user cache store."""
    result = runner.invoke(main.app, ["local", "--mirror", "https://mirror", *flags])
    assert result.exit_code == 0, result.output
    build_store.assert_called_once_with("https://mirror")
    run_downloads.assert_awaited_once_with(
        build_store.return_value,
        cache_only=True,
        clear_osm=clear_osm,
    )


def test_s3_warms_the_bucket(
    mocker: MockerFixture,
    run_downloads: AsyncMock,
    build_store: MagicMock,
) -> None:
    """Ensure ``s3`` downloads into a store whose cache is the given bucket."""
    create_s3_store = mocker.patch.object(main.exporter, "create_s3_store")
    result = runner.invoke(main.app, ["s3", "--bucket", "warm-bucket"])
    assert result.exit_code == 0, result.output
    build_store.assert_called_once_with(None)
    create_s3_store.assert_called_once_with("warm-bucket")
    store = build_store.return_value
    assert store.cache is create_s3_store.return_value
    run_downloads.assert_awaited_once_with(store, cache_only=True, clear_osm=False)
