import asyncio
import logging
import multiprocessing
import pathlib
import subprocess
import sys

import aiohttp
import geopandas as gpd
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from slugify import slugify
from us import states


def main():
    # Setup.
    load_dotenv()
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    asyncio.run(analyze())


async def analyze():
    # Provided inputs.
    # Sample 00: regular
    state = "arizona"
    city = "flagstaff"
    osm_relation_id = "110844"
    await prepare(state, city, osm_relation_id)

    # Sample 01: state with space
    # Status: Buggy
    state = "new mexico"
    city = "socorro"
    osm_relation_id = "171289"
    # await prepare(state, city, osm_relation_id)

    # Sample 02: city with space
    # Duration:  1h46m23s
    state = "texas"
    city = "san marcos"
    osm_relation_id = "113329"
    # await prepare(state, city, osm_relation_id)

    # Sample 03: small Texas town
    # Duration: 3h34m48s
    state = "texas"
    city = "brownsville"
    osm_relation_id = "115275"
    # await prepare(state, city, osm_relation_id)

    # Sample 04: small Massachusetts town
    # Duration:  4h50m48s
    state = "massachusetts"
    city = "cambridge"
    osm_relation_id = "1933745"
    # await prepare(state, city, osm_relation_id)


async def prepare(state, city, osm_relation_id):
    # Prepare the Rich output.
    console = Console()

    # Computed inputs.
    region_file_name = f"{slugify(state)}-latest.osm.pbf"
    slugged_city_state = slugify(f"{city}-{state}")
    poly_file_name = f"{slugged_city_state}.poly"
    pfb_osm_file = f"{slugged_city_state}.osm"
    state_abbrev = states.mapping("name", "abbr").get(state.title())
    st = states.lookup(state_abbrev)
    state_fips = st.fips

    # Static inputs.
    region = "north-america"
    country = "us"
    output_dir = pathlib.Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Retrieve the US Census file.
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        # Download the census file.
        tiger_url = f"https://www2.census.gov/geo/tiger/TIGER2021/PLACE/tl_2021_{state_fips}_place.zip"
        tiger_file = output_dir / f"tl_2021_{state_fips}_place.zip"
        with console.status("[bold green]Downloading the US census file...") as status:
            await download_file(session, tiger_url, tiger_file)
            console.log("US Census file downloaded.")
        census_place = gpd.read_file(tiger_file)

        # Prepare the boudary file.
        with console.status("[bold green]Preparing the boudary file...") as status:
            city_shp = output_dir / f"{slugify(city)}.shp"
            logger.debug(f"Saving data into {city_shp}...")
            city_gdf = census_place.loc[census_place["NAME"] == city.title()]
            city_gdf.to_file(city_shp)
            console.log("Boundary file ready.")

        # Download the OSM region file.
        state_slug = state.lower().replace(" ", "-")
        region_file_url = f"https://download.geofabrik.de/{region}/{country}/{state_slug}-latest.osm.pbf"
        region_file_path = output_dir / region_file_name
        with console.status("[bold green]Downloading the US OSM file...") as status:
            await download_file(session, region_file_url, region_file_path)
            console.log("Regional OSM file downloaded.")

        # Download the polygon file.
        polygon_url = f"http://polygons.openstreetmap.fr/get_poly.py"
        polygon_file_path = output_dir / poly_file_name
        with console.status("[bold green]Downloading the polygon file...") as status:
            # Need to warm up the database first.
            await fetch_text(
                session, f"http://polygons.openstreetmap.fr/", {"id": osm_relation_id}
            )
            polygon_file_path.write_text(
                await fetch_text(
                    session, polygon_url, {"id": osm_relation_id, "params": 0}
                )
            )
            console.log("Polygon file downloaded.")

    # Reduce the osm file with osmosis.
    with console.status(
        f"[bold green]Reducing the OSM file for {city} with osmium..."
    ) as status:
        reduced_file_path = output_dir / pfb_osm_file
        if reduced_file_path.exists():
            logger.debug(f"{city} osm file already exists, skipping...")
        else:
            # logger.info(f"Reducing the osm file for {city} with osmosis...")
            # osmosis_cmd = " ".join(
            #     [
            #         "osmosis",
            #         "--read-pbf-fast",
            #         f'file="{region_file_name}"',
            #         f"workers={multiprocessing.cpu_count()}",
            #         "--bounding-polygon",
            #         f'file="{poly_file_name}"',
            #         "--write-xml",
            #         f'file="{pfb_osm_file}"',
            #     ]
            # )
            # run(osmosis_cmd)

            # Osmium seems to perform way better than osmosis.
            osmium_cmd = " ".join(
                [
                    "osmium",
                    "extract",
                    "-p",
                    f'"{polygon_file_path}"',
                    f'"{region_file_path}"',
                    "-o",
                    f'"{reduced_file_path}"',
                ]
            )
            run(osmium_cmd)
        console.log(f"OSM file for {city} ready.")

    # Run the analysis.
    docker_cmd = " ".join(
        [
            "docker",
            "run",
            "--rm",
            f'-e PFB_SHPFILE="/{city_shp}"',
            f'-e PFB_OSM_FILE="/{output_dir / pfb_osm_file}"',
            f"-e PFB_STATE={state_abbrev.lower()}",
            f"-e PFB_STATE_FIPS={state_fips}",
            f"-e NB_OUTPUT_DIR=/{output_dir / slugify(country) / slugify(state) / slugify(city)}",
            f'-v "{pathlib.Path.cwd()}/{output_dir}/":/{output_dir}/',
            "bna-mechanics/analyzer:13-3.1",
        ]
    )
    with console.status(
        "[bold green]Running the full analysis (may take a while)..."
    ) as status:
        run(docker_cmd)
        console.log(f"Analysis for {city} {state} complete.")


async def download_file(session, url, output):
    """
    Download payload stream into a file.
    """
    if output.exists():
        logger.debug(f"the file {output} already exists, skipping...")
        return
    logger.debug(f"Downloading file from {url} to {output}...")
    async with session.get(url) as resp:
        with open(output, "wb") as fd:
            async for chunk in resp.content.iter_chunked(8096):
                fd.write(chunk)


async def fetch_text(session, url, params=None):
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


def run(cmd):
    """
    Run an external command.
    """
    logger.debug(f"{cmd=}")
    try:
        pass
        # subprocess.run(cmd, shell=True, check=True, capture_output=True, cwd=None)
    except subprocess.CalledProcessError as cpe:
        print(
            f'"{cpe.cmd}" failed to execute with error code {cpe.returncode} for the following reason:\n'
            f"{cpe.stderr.decode('utf-8')}."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
