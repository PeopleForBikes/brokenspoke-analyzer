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
import os
import pathlib
import shutil

import rich

from brokenspoke_analyzer.cli import (
    root,
    run_with,
)
from brokenspoke_analyzer.core import (
    analysis,
    constant,
)


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

    # Read the CSV file.
    input_csv = pathlib.Path("cities.csv")
    with input_csv.open() as f:
        reader = csv.DictReader(f)

        # Process each entry.
        for row in reader:
            country = row["country"]
            city = row["city"]
            region = row.get("region")
            fips_code = row["fips_code"]

            # Download the OSM data into the cache if necessary.
            console.log(
                f"[green]Caching the OSM region file for {region}...",
            )
            with console.status("Downloading..."):
                osm_region = region if region else country
                try:
                    cached_region_file = analysis.retrieve_region_file(
                        osm_region, osm_cache
                    )
                    cached_region_file_md5 = cached_region_file.with_suffix(".pbf.md5")
                except Exception as e:
                    print(e)

            # Prepare the data directory ahead of the analysis.
            data_dir = pathlib.Path("./data").resolve()
            _, slug = analysis.osmnx_query(country, city, region)
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


if __name__ == "__main__":
    main()
