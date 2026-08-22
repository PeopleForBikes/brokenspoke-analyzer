"""Define functions used to download files."""

import re

import aiohttp
import yarl
from bs4 import BeautifulSoup
from loguru import logger

PFB_PUBLIC_DOCUMENTS_URL = "https://s3.amazonaws.com/pfb-public-documents"
TIGER_URL = "https://www2.census.gov/geo/tiger"
CHUNK_SIZE = 65536
LODES_URL = "https://lehd.ces.census.gov/data/lodes/LODES8"


async def fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    params: dict[str, str] | None = None,
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
        >>>         <td>
        >>>             <a href="tx_od_aux_JT00_2002.csv.gz">
        >>>                 tx_od_aux_JT00_2002.csv.gz
        >>>             </a>
        >>>         </td>
        >>>         <td align="right">2023-04-03 12:30 </td>
        >>>         <td align="right">544K</td>
        >>>         <td>&nbsp;</td>
        >>>     </tr>
        >>>     <tr>
        >>>         <td valign="top"><img src="/icons/compressed.gif" alt="[ ]" /></td>
        >>>         <td>
        >>>             <a href="tx_od_aux_JT00_2003.csv.gz">
        >>>                 tx_od_aux_JT00_2003.csv.gz
        >>>             </a>
        >>>         </td>
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
        raise ValueError(f"cannot identify the latest LODES year for `{parts}`")

    return max(years)


async def autodetect_latest_lodes_year(
    session: aiohttp.ClientSession,
    state_abbrev: str,
) -> int:
    """Return the latest year of LODES data available for a specific US state."""
    # Puerto Rico is part of the US but the US Census Bureau never collected
    # employment data. As a result we are just skipping it.
    part = "aux"
    type_ = "JT00"
    lehd_url = yarl.URL(LODES_URL) / state_abbrev.lower() / "od"
    logger.debug(f"Looking up latest LODES year for {state_abbrev} {part} {type_}")
    html_dir = await fetch_text(session=session, url=str(lehd_url))
    latest_year = parse_latest_lodes_year(html_dir, state_abbrev, part, type_)
    logger.debug(f"Found latest LODES year: {latest_year}")
    return latest_year
