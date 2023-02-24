"""Show examples of analyzing US cities."""
import asyncio
import pathlib
import sys

from dotenv import load_dotenv
from loguru import logger

from brokenspoke_analyzer import cli


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
    output_dir = pathlib.Path("examples/data")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Provided inputs.
    # Sample 00: regular
    country = "usa"
    state = "arizona"
    city = "flagstaff"
    # osm_relation_id = "110844"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    await cli._prepare(country, state, city, output_dir)
    # analyze(state, city, *params)

    # Sample 01: state with space
    # Status: Buggy
    state = "new mexico"
    city = "socorro"
    # osm_relation_id = "171289"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    # analyze(state, city, *params)

    # Sample 02: city with space
    # Duration:  1h46m23s
    state = "texas"
    city = "san marcos"
    # osm_relation_id = "113329"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    # analyze(state, city, *params)

    # Sample 03: small Texas town
    # Duration: 3h34m48s
    state = "texas"
    city = "brownsville"
    # osm_relation_id = "115275"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    # analyze(state, city, *params)

    # Sample 04: small Massachusetts town
    # Duration:  4h50m48s
    state = "massachusetts"
    city = "cambridge"
    # osm_relation_id = "1933745"
    # params = await prepare(state, city, osm_relation_id, output_dir)
    # analyze(state, city, *params)

    # Sample 05:
    # Duration:
    state = "colorado"
    city = "englewood"
    # osm_relation_id = "7243979"
    # params = await cli.prepare_no_census(state, city, osm_relation_id, output_dir)


if __name__ == "__main__":
    main()
