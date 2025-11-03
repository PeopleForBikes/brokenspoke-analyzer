"""Define functions used to download files."""

import pathlib
import re
import typing

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger

from brokenspoke_analyzer.core import utils

PFB_PUBLIC_DOCUMENTS_URL = "https://s3.amazonaws.com/pfb-public-documents"
TIGER_URL = "https://www2.census.gov/geo/tiger"
CHUNK_SIZE = 65536
LODES_URL = "https://lehd.ces.census.gov/data/lodes/LODES8"


async def download_file(
    session: aiohttp.ClientSession,
    url: str,
    output: pathlib.Path,
    skip_existing: bool = True,
) -> None:
    """
    Download payload stream into a file.

    :param session: aiohttp session
    :param url: request URL
    :param output: path where to write the file
    :param skip_existing: skip the download if the output file already exists
    """
    output = output.resolve()
    if skip_existing and output.exists():
        logger.debug(f"the file {output} already exists, skipping...")
        return
    logger.debug(f"Downloading file from {url} to {output}...")
    async with session.get(url) as resp:
        with open(output, "wb") as fd:
            async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                fd.write(chunk)


async def fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    params: typing.Optional[dict[str, str]] = None,
) -> str:
    """
    Fetch the data from a URL as text.

    :param session: aiohttp session
    :param url: request URL
    :param params: request parameters, defaults to None
    :return: the data from a URL as text.
    """
    logger.debug(f"Fetching text from {url}...")
    if not params:
        params = {}
    async with session.get(url, params=params) as response:
        return await response.text()


async def download_lodes_data(
    session: aiohttp.ClientSession,
    output_dir: pathlib.Path,
    state: str,
    part: str,
    year: int,
) -> None:
    """
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
    * [TYPE] = Job Type, can have a value of "JT00" for All Jobs, "JT01" for
        Primary Jobs, "JT02" for All Private Jobs, "JT03" for Private Primary
        Jobs, "JT04" for All Federal Jobs, or "JT05" for Federal Primary Jobs.
    * [YEAR] = Year of job data. Can have the value of 2002-2020 for most
        states.

    As an example, the main OD file of Primary Jobs in 2007 for California would
    be the file: ``ca_od_main_JTO1_2007.csv.gz``.

    More information about the formast can be found on the website:
    https://lehd.ces.census.gov/data/#lodes.
    """
    lehd_url = f"{LODES_URL}/{state.lower()}/od"
    lehd_filename = f"{state.lower()}_od_{part.lower()}_JT00_{year}.csv.gz"
    gzipped_lehd_file = output_dir / lehd_filename
    decompressed_lefh_file = output_dir / gzipped_lehd_file.stem
    decompressed_lefh_file = decompressed_lefh_file.resolve()
    gzipped_lehd_file = gzipped_lehd_file.resolve()

    # Skip the download if the target file already exists.
    if decompressed_lefh_file.exists():
        return

    # Download the file.
    await download_file(session, f"{lehd_url}/{lehd_filename}", gzipped_lehd_file)

    # Decompress it.
    utils.gunzip(gzipped_lehd_file, decompressed_lefh_file, False)


async def download_2020_census_blocks(
    session: aiohttp.ClientSession, output_dir: pathlib.Path, state_fips: str
) -> None:
    """Download a 2021 census tabulation block code for a specific state."""
    tiger_url = f"{TIGER_URL}/TIGER2020/TABBLOCK20/tl_2020_{state_fips}_tabblock20.zip"
    tabblk2020_filename = f"tl_2020_{state_fips}_tabblock20.zip"
    tabblk_file = output_dir / f"tl_2020_{state_fips}_tabblock20.zip"
    tabblk_file = tabblk_file.resolve()

    tabblk2020_file = output_dir / tabblk2020_filename
    tabblk2020_file = tabblk2020_file.resolve()
    population_file = output_dir / "population.shp"
    population_file = population_file.resolve()

    # Skip the download if the target file already exists.
    if population_file.exists():
        return

    # Download the file.
    await download_file(session, tiger_url, tabblk_file)

    # Unzip and rename the tabulation block files to "population".
    utils.prepare_census_blocks(tabblk_file, output_dir.resolve(strict=True))


async def download_state_speed_limits(
    session: aiohttp.ClientSession, output_dir: pathlib.Path
) -> None:
    """Download the state speed limits."""
    state_speed_filename = "state_fips_speed.csv"
    state_speed_url = f"{PFB_PUBLIC_DOCUMENTS_URL}/{state_speed_filename}"
    state_speed_file = output_dir / state_speed_filename
    state_speed_file = state_speed_file.resolve()

    # Download the file.
    await download_file(session, state_speed_url, state_speed_file)


async def download_city_speed_limits(
    session: aiohttp.ClientSession, output_dir: pathlib.Path
) -> None:
    """Download the city speed limits."""
    city_speed_filename = "city_fips_speed.csv"
    city_speed_url = f"{PFB_PUBLIC_DOCUMENTS_URL}/{city_speed_filename}"
    city_speed_file = output_dir / city_speed_filename
    city_speed_file = city_speed_file.resolve()

    # Download the file.
    await download_file(session, city_speed_url, city_speed_file)


def parse_latest_lodes_year(html: str, state: str, part: str, type_: str) -> int:
    """
    Parse the latest year of lodes data available for a specific state.

    Parses an Apache/Nginx-style directory listing and return the latest year
    from filenames that contain the given pattern matching the state, the part,
    the type type and end with ".csv.gz".

    Example:
        >>> html = '''
        >>> <table>
        >>>     <tr>
        >>>         <th valign="top"><img src="/icons/blank.gif" alt="[ICO]" /></th>
        >>>         <th><a href="?C=N;O=D">Name</a></th>
        >>>         <th><a href="?C=M;O=A">Last modified</a></th>
        >>>         <th><a href="?C=S;O=A">Size</a></th>
        >>>         <th><a href="?C=D;O=A">Description</a></th>
        >>>     </tr>
        >>>     <tr>
        >>>         <td valign="top"><img src="/icons/compressed.gif" alt="[ ]" /></td>
        >>>         <td><a href="tx_od_aux_JT00_2002.csv.gz">tx_od_aux_JT00_2002.csv.gz</a></td>
        >>>         <td align="right">2023-04-03 12:30 </td>
        >>>         <td align="right">544K</td>
        >>>         <td>&nbsp;</td>
        >>>     </tr>
        >>>     <tr>
        >>>         <td valign="top"><img src="/icons/compressed.gif" alt="[ ]" /></td>
        >>>         <td><a href="tx_od_aux_JT00_2003.csv.gz">tx_od_aux_JT00_2003.csv.gz</a></td>
        >>>         <td align="right">2023-04-03 12:30 </td>
        >>>         <td align="right">527K</td>
        >>>         <td>&nbsp;</td>
        >>>     </tr>
        >>> </table>
        >>> '''
        >>> parse_latest_lodes_year(html, "tx", "aux", "JT00")
        2003
    """
    soup = BeautifulSoup(html, "html.parser")
    parts = f"{state.lower()}_od_{part.lower()}_{type_}_"
    years = []

    for row in soup.find_all("tr"):
        link = row.find("a")
        if not link:
            continue

        name = link.text.strip()
        match = re.search(parts + r"(\d{4})\.csv\.gz$", name)
        if match:
            years.append(int(match.group(1)))

    if not years:
        raise ValueError(f"cannot identify the lastest LODES year for `{parts}`")

    return max(years)


async def autodetect_latest_lodes_year(
    session: aiohttp.ClientSession, state: str
) -> int:
    """."""
    PART = "aux"
    TYPE = "JT00"
    lehd_url = f"{LODES_URL}/{state.lower()}/od"
    logger.debug(f"Looking up latest LODES year for {state} {PART} {TYPE}")
    html_dir = await fetch_text(session=session, url=lehd_url)
    latest_year = parse_latest_lodes_year(html_dir, state, PART, TYPE)
    logger.debug(f"Found year: {latest_year}")
    return latest_year
