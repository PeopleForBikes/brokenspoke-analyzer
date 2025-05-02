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

from brokenspoke_analyzer.cli import (
    root,
    run_with,
)
from brokenspoke_analyzer.core import constant


def main():
    """Define the main function."""
    # Disable logging.
    root._verbose_callback(0)

    # Enable experimental features.
    os.environ["BNA_EXPERIMENTAL"] = "1"

    # Enable cache.
    os.environ["BNA_CACHING_STRATEGY"] = "USER_CACHE"

    # Read the CSV file.
    input_csv = pathlib.Path("cities.csv")
    with input_csv.open() as f:
        reader = csv.DictReader(f)

        # Process each entry.
        for row in reader:
            country = row["country"]
            city = row["city"]
            region = row["region"]
            fips_code = row["fips_code"]
            run_with.compose(
                country=country,
                city=city,
                region=region,
                fips_code=fips_code,
                with_parts=constant.ComputePart.MEASURE,
            )


if __name__ == "__main__":
    main()
