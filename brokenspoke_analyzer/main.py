"""Define the main application module."""
import asyncio
import pathlib
import sys

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from slugify import slugify

from brokenspoke_analyzer.core import analysis
from brokenspoke_analyzer.core import processhelper


def main():
    """Define the application's main entrypoint."""
    # Setup.
    load_dotenv()
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    asyncio.run(run_analysis())


async def run_analysis():
    """Run analysis."""
    # Prepare the output directory.
    output_dir = pathlib.Path("data")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Provided inputs.
    # Sample 00: regular
    state = "arizona"
    city = "flagstaff"
    osm_relation_id = "110844"
    params = await prepare(state, city, osm_relation_id, output_dir)
    analyze(state, city, *params)

    # Sample 01: state with space
    # Status: Buggy
    state = "new mexico"
    city = "socorro"
    osm_relation_id = "171289"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    # analyze(state, city, *params)

    # Sample 02: city with space
    # Duration:  1h46m23s
    state = "texas"
    city = "san marcos"
    osm_relation_id = "113329"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    # analyze(state, city, *params)

    # Sample 03: small Texas town
    # Duration: 3h34m48s
    state = "texas"
    city = "brownsville"
    osm_relation_id = "115275"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    # analyze(state, city, *params)

    # Sample 04: small Massachusetts town
    # Duration:  4h50m48s
    state = "massachusetts"
    city = "cambridge"
    osm_relation_id = "1933745"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    # analyze(state, city, *params)


async def prepare(state, city, osm_relation_id, output_dir):
    # pylint: disable=too-many-locals
    """Prepare and kicks off the analysis."""
    # Prepare the Rich output.
    console = Console()

    # Computed inputs.
    region_file_name = f"{slugify(state)}-latest.osm.pbf"
    slugged_city_state = slugify(f"{city}-{state}")
    polygon_file_name = f"{slugged_city_state}.poly"
    pfb_osm_file = f"{slugged_city_state}.osm"
    state_abbrev, state_fips = analysis.state_info(state)

    # Retrieve the US Census file.
    async with aiohttp.ClientSession(raise_for_status=True) as session:
        # Download the census file.
        with console.status("[bold green]Downloading the US census file..."):
            tiger_file = await analysis.download_census_file(
                session, output_dir, state_fips
            )
            console.log("US Census file downloaded.")

        # Prepare the boudary file.
        with console.status("[bold green]Preparing the boudary file..."):
            city_shp = analysis.prepare_boundary_file(output_dir, city, tiger_file)
            console.log("Boundary file ready.")

        # Download the OSM region file.
        with console.status("[bold green]Downloading the US OSM file..."):
            region_file_path = await analysis.download_osm_us_region_file(
                session, output_dir, state, region_file_name
            )
            console.log("Regional OSM file downloaded.")

        # Download the polygon file.
        with console.status("[bold green]Downloading the polygon file..."):
            polygon_file_path = await analysis.download_polygon_file(
                session, output_dir, osm_relation_id, polygon_file_name
            )
            console.log("Polygon file downloaded.")

    # Reduce the osm file with osmium.
    # Osmium performs way better than osmosis.
    with console.status(f"[bold green]Reducing the OSM file for {city} with osmium..."):
        analysis.prepare_city_file(
            output_dir, region_file_path, polygon_file_path, pfb_osm_file
        )
        console.log(f"OSM file for {city} ready.")

    # Return the parameters required to perform the analysis.
    # pylint: disable=duplicate-code
    return (
        state_abbrev,
        state_fips,
        city_shp,
        pfb_osm_file,
        output_dir,
    )


# pylint: disable=too-many-arguments,duplicate-code
def analyze(
    state,
    city,
    state_abbrev,
    state_fips,
    city_shp,
    pfb_osm_file,
    output_dir,
):
    """Run the analysis."""
    console = Console()
    with console.status("[bold green]Running the full analysis (may take a while)..."):
        processhelper.run_analysis(
            state_abbrev,
            state_fips,
            city_shp,
            pfb_osm_file,
            output_dir,
        )
        console.log(f"Analysis for {city} {state} complete.")


if __name__ == "__main__":
    main()
