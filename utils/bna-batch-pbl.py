# utils/bna-batch-pbl.py
"""
Batch runner that downloads OSM, runs the analyzer (measure) and then runs
the PBL calculation script, placing PBL outputs into the same calver folder
that measure exported to.
"""
import csv
import logging
import os
from pathlib import Path
import shutil
import subprocess
from datetime import date
import sys

import rich
import typer
from loguru import logger
from tenacity import Retrying, before_log, stop_after_attempt
from typing_extensions import Annotated

from brokenspoke_analyzer.cli import common, root, run_with
from brokenspoke_analyzer.core import analysis, constant

# Import the names for typing/behaviour
from pbl_calculation import get_calver_folder as _get_calver_folder  # we won't call this, but kept for parity

BatchFile = Annotated[
    Path,
    typer.Argument(
        dir_okay=False,
        exists=True,
        file_okay=True,
        help="CSV file containing the cities to process",
        readable=True,
        resolve_path=True,
    ),
]

DATA_DIR = Path("./data").resolve()
OSM_CACHE_DIR = Path("./osm_cache").resolve()
OSM_CACHE_FILE_SUFFIX = ".pbf.md5"
MAX_RETRIES = 2

app = typer.Typer(help="Run BNA batch then PBL calculation (places PBL outputs into the same export folder).")


def _find_latest_calver_folder(results_root: Path, country: str, region: str, city: str) -> Path:
    """
    Return the calver folder that measure/export wrote to.

    Logic:
    - Look in results_root / country / region / city
    - Build name_stem = YY.MM for today
    - If there are no matching folders, return parent / name_stem (not created).
    - If there are matching folders, choose the one with highest suffix:
        - exact 'YY.MM' -> suffix 0
        - 'YY.MM.N' -> suffix N
      Return the Path to the highest-suffix folder (existing).
    """
    parent = results_root / country / region / city
    name_stem = date.today().strftime("%y.%m")

    if not parent.exists():
        # measure should have created the parent; but if not, return candidate base
        return parent / name_stem

    candidates = []
    for p in parent.iterdir():
        if not p.is_dir():
            continue
        if p.name == name_stem:
            candidates.append((p, 0))
        elif p.name.startswith(name_stem + "."):
            parts = p.name.split(".")
            try:
                suffix = int(parts[-1])
                candidates.append((p, suffix))
            except ValueError:
                continue

    if not candidates:
        # no existing calver folder; return the base candidate (not created)
        return parent / name_stem

    # pick the candidate with highest suffix
    picked = max(candidates, key=lambda ps: ps[1])[0]
    return picked


@app.command()
def main(
    batch_file: BatchFile = "cities.csv",
    lodes_year: common.LODESYear = None,
    parts: common.ComputeParts = [constant.ComputePart.MEASURE],
):
    """Process a batch of cities and run PBL calculation into the same export folder."""
    # Disable verbose logging inside the analyzer
    root._verbose_callback(0)

    os.environ["BNA_EXPERIMENTAL"] = "1"
    os.environ["BNA_CACHING_STRATEGY"] = "USER_CACHE"
    osm_cache = OSM_CACHE_DIR
    osm_cache.mkdir(parents=True, exist_ok=True)

    console = rich.get_console()
    retryer = Retrying(stop=stop_after_attempt(MAX_RETRIES), reraise=True, before=before_log(logger, logging.DEBUG))

    with batch_file.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            country = row["country"]
            city = row["city"]
            region = row.get("region") if row.get("region") else country
            fips_code = row.get("fips_code", "")

            console.log(f"[green]Caching the OSM region file for {region}...")
            with console.status("Downloading..."):
                try:
                    cached_region_file = retryer(analysis.retrieve_region_file, region, osm_cache)
                    cached_region_file_md5 = cached_region_file.with_suffix(OSM_CACHE_FILE_SUFFIX)
                except Exception as e:
                    print(e)
                    return

            _, _, slug = analysis.osmnx_query(country, city, region)
            data_dir = DATA_DIR / slug
            data_dir.mkdir(parents=True, exist_ok=True)

            # copy cached files into data folder for analyzer
            shutil.copy(cached_region_file, data_dir)
            shutil.copy(cached_region_file_md5, data_dir)

            # run the analyzer (measure/export etc)
            run_with.compose(
                city=city,
                country=country,
                fips_code=fips_code,
                lodes_year=lodes_year,
                region=region,
                with_parts=parts,
            )

            # find the folder measure/export wrote into
            results_root = Path("results")
            batch_folder = _find_latest_calver_folder(results_root, country, region, city)

            # If the folder doesn't yet exist, create it (defensive)
            batch_folder.mkdir(parents=True, exist_ok=True)

            # Choose python interpreter for the PBL script:
            # If you need a different environment (eg. your geo venv), set env var PBL_PYTHON to an absolute path.
            python_exec = os.environ.get("PBL_PYTHON", sys.executable)

            # Call PBL script and pass the existing batch folder
            subprocess.run(
                [
                    python_exec,
                    "utils/pbl_calculation.py",
                    city,
                    region,
                    country,
                    "--data-dir",
                    str(Path("data")),
                    "--output-dir",
                    str(results_root),
                    "--batch-folder",
                    str(batch_folder),
                ],
                check=True,
            )


if __name__ == "__main__":
    app()
