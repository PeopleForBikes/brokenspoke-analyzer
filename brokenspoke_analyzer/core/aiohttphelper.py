"""Define helper functions for aiohttp."""
import pathlib
import typing

import aiohttp
from loguru import logger


async def download_file(
    session: aiohttp.ClientSession, url: str, output: pathlib.Path
) -> None:
    """Download payload stream into a file."""
    if output.exists():
        logger.debug(f"the file {output} already exists, skipping...")
        return
    logger.debug(f"Downloading file from {url} to {output}...")
    async with session.get(url) as resp:
        with open(output, "wb") as fd:
            async for chunk in resp.content.iter_chunked(8096):
                fd.write(chunk)


async def fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    params: typing.Optional[dict[str, str]] = None,
) -> str:
    """
    Fetch the data from a URL as text.

    :param aiohttp.ClientSession session: aiohttp session
    :param str url: request URL
    :param dict params: request parameters, defaults to None
    :return: the data from a URL as text.
    :rtype: str
    """
    logger.debug(f"Fetching text from {url}...")
    if not params:
        params = {}
    async with session.get(url, params=params) as response:
        return await response.text()
