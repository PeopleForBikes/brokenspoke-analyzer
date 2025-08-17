"""
Wraps the bna run-with command to process a batch of cities from a CSV file.

From the root of this repository run:
```bash
uv run python utils/bna-batch.py
```
## Usage

```bash
bna-batch.py [OPTIONS] [BATCH_FILE]
```

### options

- `batch_file` _batch-file_

    - CSV file containing the cities to process.

      Defaults to `./cities.csv`.

- `--lodes-year` _lodes-year_
    - Year to use to retrieve US job data.

      Defaults to 2022.

- `--with-parts` _parts_
  - Parts of the analysis to compute.

    Valid values are: `features`, `stress`, `connectivity`, and `measure`. This
    option can be repeated if multiple parts are needed.

    Defaults to `measure`.

### Batch file format

`cities.csv`:
```csv
country,region,city,fips_code
"united states","new mexico","santa rosa",3570670
"united states",massachusetts,provincetown,555535
```
"""

import csv
import logging
import os
import pathlib
import shutil
import subprocess

import rich
import typer
from loguru import logger
from tenacity import (
    Retrying,
    before_log,
    stop_after_attempt,
)
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import (
    common,
    root,
    run_with,
)
from brokenspoke_analyzer.core import (
    analysis,
    constant,
)

BatchFile = Annotated[
    pathlib.Path,
    typer.Argument(
        dir_okay=False,
        exists=True,
        file_okay=True,
        help="CSV file containing the cities to process",
        readable=True,
        resolve_path=True,
    ),
]
DATA_DIR = pathlib.Path("./data").resolve()
MAX_RETRIES = 2
OSM_CACHE_DIR = pathlib.Path("./osm_cache").resolve()
OSM_CACHE_FILE_SUFFIX = ".pbf.md5"


def main(
    batch_file: BatchFile = "cities.csv",
    lodes_year: common.LODESYear = common.DEFAULT_LODES_YEAR,
    parts: common.ComputeParts = [constant.ComputePart.MEASURE],
):
    """Process a batch of cities."""
    # Disable logging.
    root._verbose_callback(0)

    # Enable experimental features.
    os.environ["BNA_EXPERIMENTAL"] = "1"

    # Enable cache.
    os.environ["BNA_CACHING_STRATEGY"] = "USER_CACHE"

    # Simulate a caching mechanism for OSM data.
    osm_cache = OSM_CACHE_DIR
    osm_cache.mkdir(parents=True, exist_ok=True)

    # Prepare the Rich output.
    console = rich.get_console()

    # Create retrier instance to use for all downloads.
    retryer = Retrying(
        stop=stop_after_attempt(MAX_RETRIES),
        reraise=True,
        before=before_log(logger, logging.DEBUG),  # type: ignore
    )

    # Read the CSV file.
    with batch_file.open() as f:
        reader = csv.DictReader(f)

        # Process each entry.
        for row in reader:
            country = row["country"]
            city = row["city"]
            region = row.get("region") if row.get("region") else country
            fips_code = row["fips_code"]

            # Download the OSM data into the cache if necessary.
            console.log(
                f"[green]Caching the OSM region file for {region}...",
            )
            with console.status("Downloading..."):
                try:
                    cached_region_file = retryer(
                        analysis.retrieve_region_file, region, osm_cache
                    )
                    cached_region_file_md5 = cached_region_file.with_suffix(
                        OSM_CACHE_FILE_SUFFIX
                    )
                except Exception as e:
                    print(e)
                    return

            # Prepare the data directory ahead of the analysis.
            _, slug = analysis.osmnx_query(country, city, region)
            data_dir = DATA_DIR / slug
            data_dir.mkdir(parents=True, exist_ok=True)

            # Copy the OSM data into the data directory.
            shutil.copy(cached_region_file, data_dir)
            shutil.copy(cached_region_file_md5, data_dir)

            # Run the analysis.
            run_with.compose(
                city=city,
                country=country,
                fips_code=fips_code,
                lodes_year=lodes_year,
                region=region,
                with_parts=parts,
            )


def run_with_docker(
    country: str,
    city: str,
    region: str,
    fips_code: str,
):
    """
    Run with Docker.

    VERY EXPERIMENTAL ONLY. USED FOR TESTING.
    """
    try:
        os.environ["DATABASE_URL"] = (
            "postgresql://postgres:postgres@postgres:5432/postgres"
        )
        uid = os.getuid()
        gid = os.getgid()
        subprocess.run(
            ["docker", "compose", "up", "-d", "--wait"],
            check=True,
            capture_output=True,
        )
        docker_run_cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "brokenspoke-analyzer_default",
            "-e",
            "DATABASE_URL",
        ]
        docker_image = [
            "ghcr.io/peopleforbikes/brokenspoke-analyzer:2.6.3",
            "-vv",
        ]
        subprocess.run(
            docker_run_cmd
            + docker_image
            + [
                "configure",
                "custom",
                "4",
                "4096",
                "postgres",
            ]
        )
        subprocess.run(
            docker_run_cmd
            + docker_image
            + [
                "run",
                country,
                city,
                region,
                fips_code,
            ]
        )
        subprocess.run(
            docker_run_cmd
            + [
                "-u",
                f"{uid}:{gid}",
                "-v",
                "./results:/usr/src/app/results",
            ]
            + docker_image
            + [
                "export",
                "local",
                country,
                city,
                region,
            ]
        )

    finally:
        subprocess.run(
            ["docker", "compose", "rm", "-sfv"], check=True, capture_output=True
        )
        subprocess.run(
            ["docker", "volume", "rm", "-f", "brokenspoke-analyzer_postgres"],
            capture_output=True,
        )


if __name__ == "__main__":
    typer.run(main)
