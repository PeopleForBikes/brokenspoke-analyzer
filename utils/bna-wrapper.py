"""
Wraps the bna run-with command to process the cities from a csv file.

`cities.csv`:
```csv
country,region,city,fips_code
"united states","new mexico","santa rosa",3570670
"united states",massachusetts,provincetown,555535
```

From the root of this repository run:
```bash
uv run python utils/bna-wrapper.py
```
"""

import csv
import logging
import os
import pathlib
import shutil
import subprocess

import rich
from loguru import logger
from tenacity import (
    Retrying,
    before_log,
    stop_after_attempt,
)

from brokenspoke_analyzer.cli import (
    root,
    run_with,
)
from brokenspoke_analyzer.core import (
    analysis,
    constant,
)

MAX_RETRIES = 2


def main():
    """Define the main function."""
    # Disable logging.
    root._verbose_callback(0)

    # Enable experimental features.
    os.environ["BNA_EXPERIMENTAL"] = "1"

    # Enable cache.
    os.environ["BNA_CACHING_STRATEGY"] = "USER_CACHE"

    # Simulate a caching mechanism for OSM data.
    osm_cache = pathlib.Path("./osm_cache").resolve()
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
    input_csv = pathlib.Path("cities.csv")
    with input_csv.open() as f:
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
                    cached_region_file_md5 = cached_region_file.with_suffix(".pbf.md5")
                except Exception as e:
                    print(e)

            # Prepare the data directory ahead of the analysis.
            data_dir = pathlib.Path("./data").resolve()
            _, _, slug = analysis.osmnx_query(country, city, region)
            data_dir /= slug
            data_dir.mkdir(parents=True, exist_ok=True)

            # Copy the OSM data into the data directory.
            shutil.copy(cached_region_file, data_dir)
            shutil.copy(cached_region_file_md5, data_dir)

            # Run the analysis.
            run_with.compose(
                country=country,
                city=city,
                region=region,
                fips_code=fips_code,
                with_parts=constant.ComputePart.MEASURE,
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
    main()
