"""Represent the source adapter module."""

import pathlib
import string
from abc import (
    ABC,
    abstractmethod,
)
from collections import abc

import geopandas as gpd
import numpy as np
import rasterio
import rasterio.features
import yarl
from loguru import logger
from pyrosm import data
from shapely.geometry import shape

from brokenspoke_analyzer_lib import (
    utils,
)
from brokenspoke_analyzer_lib.utils import unzip

# TIGER base URL -- Topologically Integrated Geographic Encoding and Referencing.
TIGER_URL = yarl.URL("https://www2.census.gov/geo/tiger/")


class SourceAdapter(ABC):
    """Abstract base class for data source adapters."""

    # Define the URL of the source.
    SOURCE_URL: yarl.URL | None = None

    def __init__(self, mirror: str | None = None) -> None:
        """Initialize the SourceAdapter.

        Example:
            >>> adapter = CitySpeedLimitAdapter()
            >>> adapter.mirror is None
            True
        """
        self.mirror = mirror

    @staticmethod
    @abstractmethod
    def key() -> str:
        """Return the source key.

        Example:
            >>> adapter = CitySpeedLimitAdapter()
            >>> adapter.key()
            'city_speed_limits'
        """

    @property
    @abstractmethod
    def files(self) -> abc.Sequence[pathlib.Path]:
        """Return the source data files.

        Example:
            >>> adapter = StateSpeedLimitAdapter()
            >>> len(adapter.files)
            1
        """

    @property
    def keyed_files(self) -> abc.Sequence[pathlib.Path]:
        """
        Return the source data files with the source key prefixed.

        This is useful to access cache files
        """
        return [pathlib.Path(self.key()) / f.name for f in self.files]

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
        return pathlib.Path(self.key())

    def prepare(self, datastore: pathlib.Path) -> None:  # noqa: ARG002
        """Prepare the data files.

        Example:
            >>> import tempfile
            >>> adapter = CitySpeedLimitAdapter()
            >>> with tempfile.TemporaryDirectory() as tmpdir:
            >>>     adapter.prepare(pathlib.Path(tmpdir))
        """
        return

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
        mirror: str | None = None,
    ) -> None:
        """Initialize the CensusAdapter."""
        super().__init__(mirror)
        self.fips = fips

    @staticmethod
    def key() -> str:
        """Return the source key."""
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
                f"only 1 file was expected, {len(self.files)} found: {self.files}",
            )
        tabblk_file = datastore / self.files[0]
        output_dir = datastore.resolve()

        # Unzip it.
        unzip(tabblk_file.resolve(strict=True), output_dir, delete_after=False)

        # Rename the tabulation block files to "population".
        # But keep the original file.
        tabblk2020_files = output_dir.glob(f"{tabblk_file.stem}.*")
        for file in tabblk2020_files:
            file.rename(output_dir / f"population{file.suffix}")

    def validate(self, datastore: pathlib.Path) -> None:
        """Validate downloaded data."""
        for f in datastore.glob("population.*"):
            if not f.exists():
                raise ValueError(f"{f} does not exist")
            if f.stat().st_size < 1:
                raise ValueError(f"{f} is empty")


class WorldPopAdapter(SourceAdapter):
    """Adapter for WorldPop 1km resolution data."""

    SOURCE_URL = yarl.URL(
        "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/"
    )

    def __init__(
        self,
        country_iso_3166: str,
        year: int,
        mirror: str | None = None,
    ) -> None:
        """
        Initialize the WorldPopAdapter.

        country must conform to using an ISO_3166 country code
        https://en.wikipedia.org/wiki/List_of_ISO_3166_country_codes
        """
        super().__init__(mirror)
        self.country_iso_3166 = country_iso_3166
        self.year = year

    @staticmethod
    def key() -> str:
        """Return the source key."""
        return "worldpop"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """
        Return the source data files.

        Example:
            >>> adapter = WorldPopAdapter("can", "2026")
            >>> adapter.files[0].name
            can_pop_2026_CN_1km_R2025A_UA_v1.tif
        """
        return [
            pathlib.Path(
                f"{self.country_iso_3166.lower()}_pop_{self.year}_CN_1km_R2025A_UA_v1.tif"
            )
        ]

    @property
    def urls(self) -> abc.Sequence[yarl.URL]:
        """Return the source data URLs."""
        base_url = (
            self.source_url
            / str(self.year)
            / self.country_iso_3166
            / "v1/1km_ua/constrained"
        )
        return [base_url / str(f) for f in self.files]

    def prepare(self, datastore: pathlib.Path) -> None:
        """Prepare the data files."""
        if len(self.files) != 1:
            raise ValueError(
                f"only 1 file was expected, {len(self.files)} found: {self.files}"
            )
        file_geotiff = datastore / self.files[0]
        output_dir = datastore.resolve()
        file_shp = output_dir / "population.shp"

        if file_shp.exists():
            return
        logger.debug(f"{file_shp} doesn't exist, creating shapefile")
        with rasterio.open(file_geotiff) as src:
            # Read the population count as a numpy array
            band_data = src.read(1)

            # Get spatial metadata
            transform = src.transform
            crs = src.crs
            nodata_val = src.nodata

            # Mask to ignore NoData values
            mask = (
                band_data != nodata_val if nodata_val is not None else band_data > 0
            )  # Fallback: ignore 0 population pixels

            # Generate shapes from the raster pixels
            shapes_generator = rasterio.features.shapes(
                band_data, mask=mask, transform=transform
            )

            # Convert the extracted shapes into Shapely geometries
            records = [
                {"geometry": shape(geom), "POP20": val}
                for geom, val in shapes_generator
            ]

        # Load into a GeoDataFrame
        gdf = gpd.GeoDataFrame(records)
        gdf.set_crs(crs, inplace=True)

        # Generate GEOID20 column, with random 15 character lowercase ACII string,
        # to simulate US census data.
        n_rows = len(gdf)
        rng = np.random.default_rng()
        random_array = rng.choice(list(string.ascii_lowercase), size=(n_rows, 15))
        gdf["GEOID20"] = ["".join(row) for row in random_array]

        # Export to Shapefile
        gdf.to_file(file_shp)
        logger.debug(f"Shapefile successfully saved to {file_shp}")


class CitySpeedLimitAdapter(SourceAdapter):
    """Adapter for city speed limit data."""

    SOURCE_URL = yarl.URL("https://s3.amazonaws.com/pfb-public-documents")

    @staticmethod
    def key() -> str:
        """Return the source key."""
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
        mirror: str | None = None,
    ) -> None:
        """Initialize the CensusAdapter."""
        super().__init__(mirror)
        self.region = region

    @staticmethod
    def key() -> str:
        """Return the source key."""
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

    def map_region_name(self, region: str) -> str:
        """
        Map the region to the Geofabrik dataset name.

        If no custom mapping is found, return the original region name.

        Exception list:
        ---------------
        - As per https://github.com/PeopleForBikes/brokenspoke-analyzer/issues/863
          we must define an exception for the countries of Malaysia, Singapore
          and Brunei as they have been grouped together in the Geofabrik
          dataset.

        """
        custom_region_mapping: dict[str, str] = {
            "brunei": "malaysia_singapore_brunei",
            "malaysia": "malaysia_singapore_brunei",
            "singapore": "malaysia_singapore_brunei",
        }
        return custom_region_mapping.get(region, region)

    def map_region_url(self, region: str) -> yarl.URL | None:
        """
        Map the region to the Geofabrik dataset URL.

        If no custom URL mapping is found, return None.

        Exception list:
        ---------------
        - Spanish regions are not yet supported upstream due to a bug in `pyrosm`
            (https://github.com/pyrosm/pyrosm/pull/381).
        - Australian regions are not yet supported upstream.
        - Georgia points to the US state on purpose.
        - Removing `pyrosm` ambiguities between cities and regions for multiple cities:
            - Berlin (DE)
            - Bremen (DE)
            - Bristol (UK)
            - Groningen (NL)
            - Hamburg (DE)
            - Utrecht (NL)
        """
        u = yarl.URL("https://download.geofabrik.de")
        custom_url_mapping: dict[str, yarl.URL] = {
            "act": u / "australia-oceania/australia/act-latest.osm.pbf",
            "australian_capital_territory": u
            / "australia-oceania/australia/act-latest.osm.pbf",
            "andalucia": u / "europe/spain/andalucia-latest.osm.pbf",
            "aragon": u / "europe/spain/aragón-latest.osm.pbf",
            "ashmore_cartier": u
            / "australia-oceania/australia/ashmore-cartier-latest.osm.pbf",
            "asturias": u / "europe/spain/asturias-latest.osm.pbf",
            "berlin": u / "europe/germany/berlin-latest.osm.pbf",
            "bremen": u / "europe/germany/bremen-latest.osm.pbf",
            "bristol": u / "europe/united-kingdom/england/bristol-latest.osm.pbf",
            "cantabria": u / "europe/spain/cantabria-latest.osm.pbf",
            "castilla_y_leon": u / "europe/spain/castilla-y-leon-latest.osm.pbf",
            "castilla_la_mancha": u / "europe/spain/castilla-la-mancha-latest.osm.pbf",
            "cataluna": u / "europe/spain/cataluna-latest.osm.pbf",
            "ceuta": u / "europe/spain/ceuta-latest.osm.pbf",
            "christmas_island": u
            / "australia-oceania/australia/christmas-island-latest.osm.pbf",
            "cocos_islands": u
            / "australia-oceania/australia/cocos-keeling-latest.osm.pbf",
            "coral_sea_islands": u
            / "australia-oceania/australia/coral-sea-islands-latest.osm.pbf",
            "extremadura": u / "europe/spain/extremadura-latest.osm.pbf",
            "galicia": u / "europe/spain/galicia-latest.osm.pbf",
            "georgia": u / "north-america/us/georgia-latest.osm.pbf",
            "groningen": u / "europe/netherlands/groningen-latest.osm.pbf",
            "hamburg": u / "europe/germany/hamburg-latest.osm.pbf",
            "heard_mcdonald": u
            / "australia-oceania/australia/heard-mcdonald-latest.osm.pbf",
            "ireland": u / "europe/ireland-and-northern-ireland-latest.osm.pbf",
            "islas_baleares": u / "europe/spain/islas-baleares-latest.osm.pbf",
            "la_rioja": u / "europe/spain/la-rioja-latest.osm.pbf",
            "madrid": u / "europe/spain/madrid-latest.osm.pbf",
            "melilla": u / "europe/spain/melilla-latest.osm.pbf",
            "murcia": u / "europe/spain/murcia-latest.osm.pbf",
            "navarra": u / "europe/spain/navarra-latest.osm.pbf",
            "new_south_wales": u
            / "australia-oceania/australia/new-south-wales-latest.osm.pbf",
            "norfolk_island": u
            / "australia-oceania/australia/norfolk-island-latest.osm.pbf",
            "northern_territory": u
            / "australia-oceania/australia/northern-territory-latest.osm.pbf",
            "northern_ireland": u
            / "europe/ireland-and-northern-ireland-latest.osm.pbf",
            "pais_vasco": u / "europe/spain/pais-vasco-latest.osm.pbf",
            "queensland": u / "australia-oceania/australia/queensland-latest.osm.pbf",
            "south_australia": u
            / "australia-oceania/australia/south-australia-latest.osm.pbf",
            "tasmania": u / "australia-oceania/australia/tasmania-latest.osm.pbf",
            "utrecht": u / "europe/netherlands/utrecht-latest.osm.pbf",
            "valencia": u / "europe/spain/valencia-latest.osm.pbf",
            "victoria": u / "australia-oceania/australia/victoria-latest.osm.pbf",
            "western_australia": u
            / "australia-oceania/australia/western-australia-latest.osm.pbf",
        }
        return custom_url_mapping.get(region)

    def get_dataset(self) -> dict[str, str]:
        """Retrieve the OSM dataset metadata."""
        # Normalize the region name.
        region = utils.normalize_unicode_name(self.region, separator="_")

        # Lookup for a custom URL mapping for the region.
        if custom_url := self.map_region_url(region):
            return {"name": custom_url.name, "url": str(custom_url)}

        # lookup for a custom region mapping for the region.
        region = self.map_region_name(region)

        # Retrieve the dataset metadata from pyrosm.
        return data.search_source(region)

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

    @staticmethod
    def key() -> str:
        """Return the source key."""
        return "state_speed_limits"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """Return the source data files."""
        return [pathlib.Path("state_fips_speed.csv")]


class LodesAdapter(SourceAdapter):
    """
    Adapter for US LODES data.

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
        mirror: str | None = None,
    ) -> None:
        """Initialize the LodesAdapter."""
        super().__init__(mirror)
        self.state_abbrev = state_abbrev
        self.lodes_year = lodes_year

    @staticmethod
    def key() -> str:
        """Return the source key."""
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
                f"{self.state_abbrev.lower()}_od_{part}_JT00_{self.lodes_year}.csv.gz",
            )
            for part in ["main", "aux"]
        ]

    @property
    def urls(self) -> abc.Sequence[yarl.URL]:
        """Return the source data URLs."""
        base_url = yarl.URL(self.source_url / self.state_abbrev / "od")
        return [yarl.URL(base_url / str(f)) for f in self.files]

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


class PlaceAdapter(SourceAdapter):
    """
    Adapter for downloading US Census Places (TIGER).

    TIGER places are defined by the U.S. Census Bureau as concentrations of
    population that have a name, are locally recognized, and are not part of
    any other place. They typically include residential areas with a closely
    spaced street pattern and may also contain commercial properties and
    urban land uses.

    Census URL: f"https://www2.census.gov/geo/tiger/TIGER{year}/PLACE/tl_{year}_{state}_place.zip"
    """

    SOURCE_URL = TIGER_URL

    def __init__(
        self,
        year: int,
        state_fips: str,
        mirror: str | None = None,
    ) -> None:
        """Initialize the PlaceAdapter."""
        super().__init__(mirror)
        self.year = year
        self.state_fips = state_fips

    @staticmethod
    def key() -> str:
        """Return the source key."""
        return "place"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """
        Return the source data files.

        Example:
            >>> adapter = PlaceAdapter(2024, "06")
            >>> adapter.files[0].name
            tl_2024_06_place.zip
        """
        return [pathlib.Path(f"tl_{self.year}_{self.state_fips}_place.zip")]

    @property
    def urls(self) -> abc.Sequence[yarl.URL]:
        """Return the source data URLs."""
        base_url = yarl.URL(self.source_url / f"TIGER{self.year}" / "PLACE")
        return [yarl.URL(base_url / str(f)) for f in self.files]


class CountySubdivisionAdapter(SourceAdapter):
    """
    Adapter for downloading US Census County Subdivision (TIGER).

    TIGER county subdivisions are Census Bureau's statistical entities
    that subdivide counties and county equivalents such as parishes,
    boroughs, and census areas.

    Census URL: f"https://www2.census.gov/geo/tiger/TIGER{year}/COUSUB/tl_{year}_{state}_cousub.zip"
    """

    SOURCE_URL = TIGER_URL

    def __init__(
        self,
        year: int,
        state_fips: str,
        mirror: str | None = None,
    ) -> None:
        """Initialize the CountySubdivisionAdapter."""
        super().__init__(mirror)
        self.year = year
        self.state_fips = state_fips

    @staticmethod
    def key() -> str:
        """Return the source key."""
        return "cousub"

    @property
    def files(self) -> abc.Sequence[pathlib.Path]:
        """
        Return the source data files.

        Example:
            >>> adapter = CountySubdivisionAdapter(2024, "06")
            >>> adapter.files[0].name
            tl_2024_06_cousub.zip
        """
        return [pathlib.Path(f"tl_{self.year}_{self.state_fips}_cousub.zip")]

    @property
    def urls(self) -> abc.Sequence[yarl.URL]:
        """Return the source data URLs."""
        base_url = yarl.URL(self.source_url / f"TIGER{self.year}" / "COUSUB")
        return [yarl.URL(base_url / str(f)) for f in self.files]
