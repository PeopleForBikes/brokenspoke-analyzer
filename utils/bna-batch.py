"""
Wraps the bna run command to process a batch of cities from a CSV file.

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

- `--export-dir` _export_dir_

    - Directory where to export the results

      Defaults to `./results`.

- `--lodes-year` _lodes-year_

    - Year to use to retrieve US job data.

      Defaults to auto-detect.

### Batch file format

`cities.csv`:
```csv
country,region,city,fips_code
"united states","new mexico","santa rosa",3570670
"united states",massachusetts,provincetown,2555535
```
"""

import csv
import os
import pathlib
from typing import Annotated

import typer

from brokenspoke_analyzer.cli import (
    common,
    root,
    run,
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


def main(
    batch_file: BatchFile = pathlib.Path("cities.csv"),
    export_dir: common.ExportDirOpt = common.DEFAULT_EXPORT_DIR,
    lodes_year: common.LODESYear = None,
    worldpop_year: common.WorldPopYear = common.DEFAULT_WORLDPOP_YEAR,
) -> None:
    """Process a batch of cities."""
    # Disable logging.
    root._verbose_callback(0)

    # Enable experimental features.
    os.environ["BNA_EXPERIMENTAL"] = "1"

    # Enable cache.
    os.environ["BNA_CACHING_STRATEGY"] = "USER_CACHE"

    # Read the CSV file.
    with batch_file.open() as f:
        reader = csv.DictReader(f)

        # Process each entry.
        for row in reader:
            country = row["country"]
            city = row["city"]
            region = row.get("region") or country
            fips_code = row["fips_code"]

            # Run the analysis. No database, no Docker.
            run.run(
                country=country,
                city=city,
                region=region,
                fips_code=fips_code,
                export_dir=export_dir,
                lodes_year=lodes_year,
                worldpop_year=worldpop_year,
            )


if __name__ == "__main__":
    typer.run(main)
