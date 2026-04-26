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

      Defaults to auto-detect.

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
    run_with,
)
from brokenspoke_analyzer.core import (
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


def main(
    batch_file: BatchFile = pathlib.Path("cities.csv"),
    lodes_year: common.LODESYear = None,
    parts: common.ComputeParts = None,
) -> None:
    """Process a batch of cities."""
    # Disable logging.
    root._verbose_callback(0)

    # Enable experimental features.
    os.environ["BNA_EXPERIMENTAL"] = "1"

    # Enable cache.
    os.environ["BNA_CACHING_STRATEGY"] = "USER_CACHE"

    if not parts:
        parts = [constant.ComputePart.MEASURE]

    # Read the CSV file.
    with batch_file.open() as f:
        reader = csv.DictReader(f)

        # Process each entry.
        for row in reader:
            country = row["country"]
            city = row["city"]
            region = row.get("region") or country
            fips_code = row["fips_code"]

            # Run the analysis.
            run_with.compose(
                city=city,
                country=country,
                fips_code=fips_code,
                lodes_year=lodes_year,
                region=region,
                with_parts=parts,
            )


if __name__ == "__main__":
    typer.run(main)
