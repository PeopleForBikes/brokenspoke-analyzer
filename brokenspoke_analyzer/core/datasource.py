"""Represent the source adapter module."""

import pathlib
import typing
import zipfile
from abc import (
    ABC,
    abstractmethod,
)
from collections import abc

import aiohttp
import yarl
from loguru import logger
from obstore.store import ObjectStore

from brokenspoke_analyzer import pyrosm
from brokenspoke_analyzer.core import (
    downloader,
    file_utils,
    utils,
)
from brokenspoke_analyzer.core.utils import unzip
from brokenspoke_analyzer.pyrosm import data


class SourceAdapter(ABC):
    """Abstract base class for data source adapters."""

    # Define the URL of the source.
    SOURCE_URL: typing.Optional[yarl.URL] = None

    def __init__(self, mirror: typing.Optional[str] = None):
        """Initialize the SourceAdapter.

        Example:
            >>> adapter = CitySpeedLimitAdapter()
            >>> adapter.mirror is None
            True
        """
        self.mirror = mirror

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the source name.

        Example:
            >>> adapter = CitySpeedLimitAdapter()
            >>> adapter.name
            'city_speed_limits'
        """
        pass

    @property
    @abstractmethod
    def files(self) -> abc.Sequence[pathlib.Path]:
        """Return the source data files.

        Example:
            >>> adapter = StateSpeedLimitAdapter()
            >>> len(adapter.files)
            1
        """
        pass

    @property
    def source_url(self) -> yarl.URL:
        """Return the source URL."""
        if self.SOURCE_URL is None:
            raise ValueError(f"{self.__class__.__name__} must define SOURCE_URL")
        return yarl.URL(self.mirror) if self.mirror else self.SOURCE_URL

    @property
    def urls(self) -> abc.Sequence[yarl.URL]:
        """Return the source data URLs."""
        return [self.source_url / str(f) for f in self.files]

    @property
    def subpath(self) -> pathlib.Path:
        """Return the sub-directory for the source data."""
        return pathlib.Path(self.name)

    def prepare(self, datastore: pathlib.Path) -> None:
        """Prepare the data files.

        Example:
            >>> import tempfile
            >>> adapter = CitySpeedLimitAdapter()
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            >>>     adapter.prepare(pathlib.Path(tmpdir))
        """
        pass

    def validate(self, datastore: pathlib.Path) -> None:
        """Validate downloaded data.

        Raises `ValueError` if a required file does not exist or is empty.

        Example:
            >>> import tempfile, pathlib
            >>> adapter = CitySpeedLimitAdapter()
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            >>>     try:
            >>>         adapter.validate(pathlib.Path(tmpdir))
            >>>     except ValueError as e:
            >>>         print("Validation failed as expected")
            Validation failed as expected
        """
        files = [datastore / f for f in self.files]
        for f in files:
            if not f.exists():
                raise ValueError(f"{f} does not exist")
            if f.stat().st_size < 1:
                raise ValueError(f"{f} is empty")


class CensusAdapter(SourceAdapter):
    """Adapter for US Census blocks data."""

    SOURCE_URL = yarl.URL("https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20")

    def __init__(
        self,
        fips: str,
        mirror: typing.Optional[str] = None,
    ):
        """Initialize the CensusAdapter."""
        super().__init__(mirror)
        self.fips = fips

    @property
    def name(self) -> str:
        """Return the source name."""
        return "census"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """
        Return the source data files.

        Example:
            >>> adapter = CensusAdapter("06")
            >>> adapter.files[0].name
            tl_2020_06_tabblock20.zip
        """
        return [pathlib.Path(f"tl_2020_{self.fips}_tabblock20.zip")]

    def prepare(self, datastore: pathlib.Path) -> None:
        """Prepare the data files."""
        if len(self.files) != 1:
            raise ValueError(
                f"only 1 file was expected, {len(self.files)} found: {self.files}"
            )
        tabblk_file = datastore / self.files[0]
        output_dir = datastore.resolve()

        # Unzip it.
        unzip(tabblk_file.resolve(strict=True), output_dir, False)

        # Rename the tabulation block files to "population".
        # But keep the original file.
        tabblk2020_files = output_dir.glob(f"{tabblk_file.stem}.*")
        for file in tabblk2020_files:
            file.rename(output_dir / f"population{file.suffix}")

    def validate(self, datastore: pathlib.Path) -> None:
        """Validate downloaded data."""
        for f in datastore.glob(f"population.*"):
            if not f.exists():
                raise ValueError(f"{f} does not exist")
            if f.stat().st_size < 1:
                raise ValueError(f"{f} is empty")


class CitySpeedLimitAdapter(SourceAdapter):
    """Adapter for city speed limit data."""

    SOURCE_URL = yarl.URL("https://s3.amazonaws.com/pfb-public-documents")

    @property
    def name(self) -> str:
        """Return the source name."""
        return "city_speed_limits"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """
        Return the source data files.

        Example:
            >>> adapter = CitySpeedLimitAdapter()
            >>> adapter.files[0].name
            city_fips_speed.csv
        """
        return [pathlib.Path("city_fips_speed.csv")]


class OSMAdapter(SourceAdapter):
    """Adapter for Openstreetmap data."""

    def __init__(
        self,
        region: str,
        mirror: typing.Optional[str] = None,
    ):
        """Initialize the CensusAdapter."""
        super().__init__(mirror)
        self.region = region

    @property
    def name(self) -> str:
        """Return the source name."""
        return "osm"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """Return the source data files."""
        return [pathlib.Path(f.name) for f in self.urls]

    @property
    def urls(self) -> abc.Sequence[yarl.URL]:
        """Return the source data URLs."""
        ds = self.get_dataset()
        return [yarl.URL(ds["url"]), yarl.URL(ds["url"] + ".md5")]

    def get_dataset(self) -> typing.Any:
        """Retrieve the OSM dataset metadata."""
        # Define the region.
        region = self.region

        # As per https://github.com/PeopleForBikes/brokenspoke-analyzer/issues/863
        # we must define an exception for the countries of Malaysia, Singapore and
        # Brunei as they have been grouped together in the Geofabrik dataset.
        if region in {"malaysia", "singapore", "brunei"}:
            region = "malaysia_singapore_brunei"

        # Normalize and fetch the dataset metadata.
        dataset = utils.normalize_unicode_name(region)
        return data.get_download_data(dataset)

    def validate(self, datastore: pathlib.Path) -> None:
        """Validate downloaded data."""
        ds = self.get_dataset()
        region_file = datastore / ds["name"]
        region_file_md5 = region_file.with_suffix(f"{region_file.suffix}.md5")
        if not utils.file_checksum_ok(region_file, region_file_md5):
            raise ValueError(f"invalid OSM region file: {region_file}")


class StateSpeedLimitAdapter(SourceAdapter):
    """Adapter for state speed limit data."""

    SOURCE_URL = yarl.URL("https://s3.amazonaws.com/pfb-public-documents")

    @property
    def name(self) -> str:
        """Return the source name."""
        return "state_speed_limits"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """Return the source data files."""
        return [pathlib.Path("state_fips_speed.csv")]


class LodesAdapter(SourceAdapter):
    """
    Adapter for LODES data.

    Download employment data from the US census website: https://lehd.ces.census.gov/.

    LODES stands for LEHD Origin-Destination Employment Statistics.

    OD means Origin-Data, which represents the jobs that are associated with
    both a home census block and a work census block.

    The filename is composed of the following parts:
    ``[ST]_od_[PART]_[TYPE]_[YEAR].csv.gz``.

    * [ST] = lowercase, 2-letter postal code for a chosen state
    * [PART] = Part of the state file, can have a value of either "main" or
        "aux".
        Complimentary parts of the state file, the main part includes jobs with
        both workplace and residence in the state and the aux part includes jobs
        with the workplace in the state and the residence outside of the state.
    * [TYPE] = Job Type, can have a value of "JT00 for All Jobs, "JT01" for
        Primary Jobs, "JT02" for All Private Jobs, "JT03" for Private Primary
        Jobs, "JT04" for All Federal Jobs, or "JT05" for Federal Primary Jobs.
    * [YEAR] = Year of job data. Can have the value of 2002-2020 for most
        states.

    As an example, the main OD file of Primary Jobs in 2007 for California would
    be the file: ``ca_od_main_JTO1_2007.csv.gz``.

    More information about the formast can be found on the website:
    https://lehd.ces.census.gov/data/#lodes.
    """

    SOURCE_URL = yarl.URL("https://lehd.ces.census.gov/data/lodes/LODES8/")

    def __init__(
        self,
        state_abbrev: str,
        lodes_year: int,
        mirror: typing.Optional[str] = None,
    ):
        """Initialize the CensusAdapter."""
        super().__init__(mirror)
        self.state_abbrev = state_abbrev
        self.lodes_year = lodes_year

    @property
    def name(self) -> str:
        """Return the source name."""
        return "lodes"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """
        Return the source data files.

        Example:
            >>> adapter = LodesAdapter("ca", 2019)
            >>> adapter.files[0].name
            ca_od_main_JT00_2019.csv.gz
        """
        return [
            pathlib.Path(
                f"{self.state_abbrev.lower()}_od_{part}_JT00_{self.lodes_year}.csv.gz"
            )
            for part in ["main", "aux"]
        ]

    @property
    def urls(self) -> abc.Sequence[yarl.URL]:
        """Return the source data URLs."""
        return [
            yarl.URL(self.source_url / self.state_abbrev / "od" / str(f))
            for f in self.files
        ]

    def prepare(self, datastore: pathlib.Path) -> None:
        """Prepare the data files."""
        for f in self.files:
            target = datastore / f.stem
            logger.debug(f"Preparing {f} into {target}")
            if target.exists():
                logger.debug(f"{target} already exists, skipping decompression")
                continue
            utils.gunzip(datastore / f, target)

    def validate(self, datastore: pathlib.Path) -> None:
        """Validate downloaded data."""
        for f in self.files:
            target = datastore / f.stem
            if not target.exists():
                raise ValueError(f"{target} does not exist")
            if target.stat().st_size < 1:
                raise ValueError(f"{target} is empty")
