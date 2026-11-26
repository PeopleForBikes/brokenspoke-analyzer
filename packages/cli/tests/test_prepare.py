"""Test the prepare module."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
)

import pytest

from bna.cli import prepare
from bna.lib.core import downloader

if TYPE_CHECKING:
    import pathlib


class FakeStore:
    """Record the downloads instead of performing them."""

    instances: ClassVar[list[FakeStore]] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        self.calls: list[str] = []
        FakeStore.instances.append(self)

    async def download_city_boundaries(self, **_: Any) -> None:
        self.calls.append("city_boundaries")

    async def download_osm_data(self, _session: Any, region: str) -> str:
        self.calls.append(f"osm_data:{region}")
        return "region.osm.pbf"

    async def download_state_speed_limits(self, _session: Any) -> None:
        self.calls.append("state_speed_limits")

    async def download_city_speed_limits(self, _session: Any) -> None:
        self.calls.append("city_speed_limits")

    async def download_lodes_data(self, _session: Any, state: str, year: int):
        self.calls.append(f"lodes:{state}:{year}")

    async def download_2020_census_blocks(self, _session: Any, state_fips: str):
        self.calls.append(f"census_blocks:{state_fips}")


@pytest.fixture
def autodetected_years(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fake the data store and the osmium reduction, and record autodetections."""
    FakeStore.instances = []
    monkeypatch.setattr(prepare.datastore, "BNADataStore", FakeStore)
    monkeypatch.setattr(prepare.analysis, "prepare_city_file", lambda *_: None)
    autodetected: list[str] = []

    async def autodetect(_session: Any, state: str) -> int:
        autodetected.append(state)
        return 2023

    monkeypatch.setattr(downloader, "autodetect_latest_lodes_year", autodetect)
    return autodetected


async def _prepare_santa_rosa(tmp_path: pathlib.Path, lodes_year: int | None) -> None:
    await prepare.prepare_(
        block_population=100,
        block_size=500,
        cache_dir=None,
        city_speed_limit=None,
        city="santa rosa",
        country="united states",
        data_dir=tmp_path,
        fips_code="3570670",
        no_cache=True,
        lodes_year=lodes_year,
        mirror=None,
        region="new mexico",
        retries=0,
        worldpop_year=2026,
    )


@pytest.mark.asyncio
async def test_prepare_downloads_the_given_lodes_year(
    tmp_path: pathlib.Path, autodetected_years: list[str]
) -> None:
    """Ensure an explicit LODES year is downloaded, without autodetection."""
    await _prepare_santa_rosa(tmp_path, lodes_year=2021)

    (store,) = FakeStore.instances
    assert "lodes:NM:2021" in store.calls
    assert autodetected_years == []


@pytest.mark.asyncio
async def test_prepare_downloads_the_autodetected_lodes_year(
    tmp_path: pathlib.Path, autodetected_years: list[str]
) -> None:
    """Ensure the latest LODES year is detected and downloaded by default."""
    await _prepare_santa_rosa(tmp_path, lodes_year=None)

    (store,) = FakeStore.instances
    assert store.calls == [
        "city_boundaries",
        "osm_data:new mexico",
        "state_speed_limits",
        "city_speed_limits",
        "lodes:NM:2023",
        "census_blocks:35",
    ]
    assert autodetected_years == ["NM"]
