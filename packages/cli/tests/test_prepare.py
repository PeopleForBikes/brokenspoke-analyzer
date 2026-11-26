"""Test the prepare sub-command."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
)

import pytest
from typer.testing import CliRunner

from bna.cli import (
    common,
    prepare,
    root,
)
from bna.lib.core import downloader

if TYPE_CHECKING:
    import pathlib

runner = CliRunner()


class FakeStore:
    """Record the downloads instead of performing them."""

    instances: ClassVar[list[FakeStore]] = []

    def __init__(self, data_dir: pathlib.Path, *_: Any, **__: Any) -> None:
        self.data_dir = data_dir
        self.calls: list[str] = []
        FakeStore.instances.append(self)

    async def download_city_boundaries(self, **_: Any) -> None:
        self.calls.append("city_boundaries")

    async def download_osm_data(self, _session: Any, region: str) -> str:
        self.calls.append(f"osm_data:{region}")
        return "region.osm.pbf"

    async def download_worldpop(self, _session: Any, iso: str, year: int, *_: Any):
        self.calls.append(f"worldpop:{iso}:{year}")

    async def download_state_speed_limits(self, _session: Any) -> None:
        self.calls.append("state_speed_limits")

    async def download_city_speed_limits(self, _session: Any) -> None:
        self.calls.append("city_speed_limits")

    async def download_lodes_data(self, _session: Any, state: str, year: int):
        self.calls.append(f"lodes:{state}:{year}")

    async def download_2020_census_blocks(self, _session: Any, state_fips: str):
        self.calls.append(f"census_blocks:{state_fips}")


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Replace the data store and the GIS operations with recorders."""
    FakeStore.instances = []
    monkeypatch.setattr(prepare.datastore, "BNADataStore", FakeStore)
    calls: dict[str, list[Any]] = {"speed_limit": [], "synthetic": []}
    monkeypatch.setattr(prepare.analysis, "prepare_city_file", lambda *_: None)
    monkeypatch.setattr(
        prepare.analysis,
        "change_speed_limit",
        lambda _dir, city, state, speed: calls["speed_limit"].append(
            (city, state, speed)
        ),
    )
    monkeypatch.setattr(
        prepare.analysis,
        "create_synthetic_population_from_file",
        lambda path, size, population: (path.name, size, population),
    )
    monkeypatch.setattr(
        prepare.analysis,
        "simulate_census_blocks",
        lambda _dir, population: calls["synthetic"].append(population),
    )
    return calls


def fake_lodes_autodetection(
    monkeypatch: pytest.MonkeyPatch, year: int | None
) -> list[str]:
    """Fake the LODES year autodetection, and record the states it is asked."""
    autodetected: list[str] = []

    async def autodetect(_session: Any, state: str) -> int:
        autodetected.append(state)
        if year is None:
            raise ValueError("no LODES data")
        return year

    monkeypatch.setattr(downloader, "autodetect_latest_lodes_year", autodetect)
    return autodetected


def prepare_kwargs(tmp_path: pathlib.Path, **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "block_population": 100,
        "block_size": 500,
        "cache_dir": None,
        "city_speed_limit": None,
        "city": "santa rosa",
        "country": "united states",
        "data_dir": tmp_path,
        "fips_code": "3570670",
        "no_cache": True,
        "lodes_year": None,
        "mirror": None,
        "region": "new mexico",
        "retries": 0,
        "worldpop_year": 2026,
    }
    kwargs.update(overrides)
    return kwargs


@pytest.mark.asyncio
async def test_prepare_downloads_the_given_lodes_year(
    tmp_path: pathlib.Path,
    fakes: dict[str, list[Any]],  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure an explicit LODES year is downloaded, without autodetection."""
    autodetected = fake_lodes_autodetection(monkeypatch, 2023)
    await prepare.prepare_(**prepare_kwargs(tmp_path, lodes_year=2021))

    (store,) = FakeStore.instances
    assert "lodes:NM:2021" in store.calls
    assert autodetected == []


@pytest.mark.asyncio
async def test_prepare_downloads_the_autodetected_lodes_year(
    tmp_path: pathlib.Path,
    fakes: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure the latest LODES year is detected and downloaded by default."""
    autodetected = fake_lodes_autodetection(monkeypatch, 2023)
    await prepare.prepare_(**prepare_kwargs(tmp_path))

    (store,) = FakeStore.instances
    assert store.data_dir == tmp_path / "santa-rosa-new-mexico-united-states"
    assert store.calls == [
        "city_boundaries",
        "osm_data:new mexico",
        "state_speed_limits",
        "city_speed_limits",
        "lodes:NM:2023",
        "census_blocks:35",
    ]
    assert autodetected == ["NM"]
    assert fakes["speed_limit"] == []


@pytest.mark.asyncio
async def test_prepare_reports_failed_lodes_autodetection(
    tmp_path: pathlib.Path,
    fakes: dict[str, list[Any]],  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ensure a failed LODES year autodetection is reported, then raised."""
    fake_lodes_autodetection(monkeypatch, None)
    with pytest.raises(ValueError, match="no LODES data"):
        await prepare.prepare_(**prepare_kwargs(tmp_path))

    assert "Autodetection failed: no LODES data." in capsys.readouterr().out
    (store,) = FakeStore.instances
    assert "census_blocks:35" not in store.calls


@pytest.mark.asyncio
async def test_prepare_skips_lodes_for_puerto_rico(
    tmp_path: pathlib.Path,
    fakes: dict[str, list[Any]],  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure no LODES data is fetched for Puerto Rico."""
    autodetected = fake_lodes_autodetection(monkeypatch, 2023)
    await prepare.prepare_(
        **prepare_kwargs(
            tmp_path, city="san juan", region="puerto rico", fips_code="7276770"
        )
    )

    (store,) = FakeStore.instances
    assert store.calls == [
        "city_boundaries",
        "osm_data:puerto rico",
        "state_speed_limits",
        "city_speed_limits",
        "census_blocks:72",
    ]
    assert autodetected == []


@pytest.mark.asyncio
async def test_prepare_non_us_city_with_worldpop(
    tmp_path: pathlib.Path, fakes: dict[str, list[Any]]
) -> None:
    """Ensure a known country gets the WorldPop data and the default speed."""
    await prepare.prepare_(
        **prepare_kwargs(
            tmp_path,
            city="paris",
            country="france",
            region="ile-de-france",
            fips_code=common.DEFAULT_CITY_FIPS_CODE,
        )
    )

    (store,) = FakeStore.instances
    assert store.calls == [
        "city_boundaries",
        "osm_data:ile-de-france",
        "worldpop:FRA:2026",
    ]
    assert fakes["synthetic"] == []
    assert fakes["speed_limit"] == [
        ("paris", "ZZ", common.DEFAULT_CITY_SPEED_LIMIT),
    ]


@pytest.mark.asyncio
async def test_prepare_non_us_city_with_synthetic_population(
    tmp_path: pathlib.Path, fakes: dict[str, list[Any]]
) -> None:
    """Ensure an unknown country gets a synthetic population."""
    await prepare.prepare_(
        **prepare_kwargs(
            tmp_path,
            city="springfield",
            country="atlantis",
            region=None,
            fips_code=common.DEFAULT_CITY_FIPS_CODE,
            city_speed_limit=25,
            block_size=250,
            block_population=50,
        )
    )

    (store,) = FakeStore.instances
    assert store.calls == ["city_boundaries", "osm_data:atlantis"]
    assert fakes["synthetic"] == [("springfield-atlantis.geojson", 250, 50)]
    assert fakes["speed_limit"] == [("springfield", "ZZ", 25)]


def record_prepare(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace the prepare coroutine with a recorder."""
    calls: list[dict[str, Any]] = []

    async def fake_prepare(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(prepare, "prepare_", fake_prepare)
    return calls


def test_prepare_cmd_normalizes_its_options(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure the command normalizes its options before preparing."""
    calls = record_prepare(monkeypatch)
    result = runner.invoke(
        root.app,
        [
            "prepare",
            "usa",
            "santa rosa",
            "new mexico",
            "3570670",
            "--data-dir",
            str(tmp_path),
            "--no-cache",
        ],
    )

    assert result.exit_code == 0, result.output
    (kwargs,) = calls
    assert kwargs["country"] == "united states"
    assert kwargs["fips_code"] == "3570670"
    assert kwargs["data_dir"] == tmp_path
    assert kwargs["no_cache"] is True


def test_prepare_cmd_resets_the_fips_code_of_non_us_cities(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure a non-US city is prepared with the default FIPS code."""
    calls = record_prepare(monkeypatch)
    result = runner.invoke(
        root.app,
        [
            "prepare",
            "france",
            "paris",
            "ile-de-france",
            "75056",
            "--data-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    (kwargs,) = calls
    assert kwargs["fips_code"] == common.DEFAULT_CITY_FIPS_CODE


def test_prepare_cmd_requires_the_fips_code_of_us_cities(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure a US city cannot be prepared without its FIPS code."""
    calls = record_prepare(monkeypatch)
    result = runner.invoke(
        root.app,
        ["prepare", "usa", "santa rosa", "new mexico", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert calls == []
