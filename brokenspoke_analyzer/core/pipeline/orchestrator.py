"""
Chain the pipeline stages into one analysis.

Replace `run_with.run_`'s prepare -> import -> compute -> export sequence with
prepare -> ingest -> features -> stress -> network -> scoring -> export. No
database, no Docker, no `DATABASE_URL`.

Only the top level is `async`, and deliberately so (design.md §6): `prepare`'s
downloads and the S3 upload are I/O-bound and benefit from it, while every
analysis stage is CPU-bound and gains nothing from `await`. Those run
synchronously inside the coroutine, which is fine here -- the CLI analyses one
city at a time, so there is nothing to interleave with.
"""

import dataclasses
import pathlib
import re
import typing

import geopandas as gpd
import numpy as np
import pandas as pd
from loguru import logger

from brokenspoke_analyzer.core import analysis
from brokenspoke_analyzer.core.pipeline import (
    config,
    errors,
    export,
    features,
    ingest,
    network,
    scoring,
    stress,
)

# `bna prepare` writes LODES CSVs named `<state>_od_<part>_JT00_<year>.csv`.
_LODES_YEAR = re.compile(r"_(\d{4})\.csv$")


@dataclasses.dataclass(frozen=True)
class AnalysisInputs:
    """Everything the analysis needs beyond the files on disk.

    Parameters
    ----------
    country, city, region
        The place being analysed.
    fips_code
        City FIPS code; `0` for non-US cities.
    data_dir
        Root directory `prepare` wrote into.
    max_trip_distance
        Reachability cutoff, `nb_max_trip_distance`.
    boundary_buffer
        Distance beyond the boundary to keep roads, `nb_boundary_buffer`.
    city_speed_limit
        The `--city-speed-limit` override. It beats the city CSV lookup
        (findings.md §1.9), so it decides every untagged residential street.
    lodes_year
        LODES vintage; discovered from the data directory when omitted.
    """

    country: str
    city: str
    region: str | None
    fips_code: str
    data_dir: pathlib.Path
    max_trip_distance: int = network.DEFAULT_MAX_TRIP_DISTANCE
    boundary_buffer: int = features.DEFAULT_BOUNDARY_BUFFER
    city_speed_limit: int | None = stress.DEFAULT_CITY_SPEED_LIMIT
    lodes_year: int | None = None


def _discover_lodes_year(artifacts: ingest.PrepareArtifacts) -> int | None:
    """Find the LODES vintage `prepare` downloaded, if any."""
    found = sorted(artifacts.data_dir.glob("*_od_main_JT00_*.csv"))
    if not found:
        return None
    matched = _LODES_YEAR.search(found[0].name)
    return int(matched.group(1)) if matched else None


def _shed_totals_as_int(
    blocks: gpd.GeoDataFrame,
    connected: pd.DataFrame,
    value_column: str,
) -> pd.DataFrame:
    """Total a quantity across each block's shed, as the SQL stored it.

    `pop_low_stress`, `pop_high_stress`, `emp_low_stress` and
    `emp_high_stress` are `INT` columns, so each `SUM()` is rounded (half away
    from zero) when it lands there -- and `access_population.sql` reads those
    rounded columns back when it scores them (findings.md §1.1, §1.27).

    Invisible in the US, where `pop20` is a whole number and the sums already
    are. Valencia's population is distributed from a raster, so its block
    populations are fractional and the rounding moves 193 of 217 blocks.

    Returns
    -------
    pandas.DataFrame
        Columns `low_stress` and `high_stress`, as nullable integers.
    """
    totals = scoring.shed_totals(blocks, connected, value_column)
    return totals.apply(features._round_half_away)


def analyze(inputs: AnalysisInputs) -> dict[str, typing.Any]:
    """Run every analysis stage for one city.

    Stage order is the pipeline's data dependency order, and two orderings
    inside it are load-bearing:

    - the census blocks must be loaded *before* the OSM extract, because the
      extract is clipped to their extent (findings.md §3.2);
    - `features` must run before `stress`, which must run before `network`,
      because each stage's output is the next one's input -- the routing graph
      is weighted by stress, which is derived from the features.

    Parameters
    ----------
    inputs
        Where to read from and which constants to use.

    Returns
    -------
    dict
        Every frame the export stage publishes.

    Raises
    ------
    IngestError, InsufficientDataError
        If `prepare`'s outputs are missing or the area has no population.
    """
    artifacts = ingest.PrepareArtifacts.resolve(
        inputs.data_dir,
        inputs.country,
        inputs.city,
        inputs.region,
    )
    _, state_fips, _ = analysis.derive_state_info(inputs.region)
    state_speed, city_speed = stress.read_speed_defaults(
        artifacts.state_speed_limits,
        artifacts.city_speed_limits,
        state_fips,
        inputs.fips_code,
        inputs.city_speed_limit,
    )

    logger.info(f"ingesting {artifacts.slug}")
    ingested = ingest.ingest(
        inputs.data_dir,
        inputs.country,
        inputs.city,
        inputs.region,
    )
    boundary = ingested["boundary"]

    logger.info("deriving features")
    ways = features.derive(ingested["ways"], boundary, inputs.boundary_buffer)

    logger.info("classifying stress")
    segment = stress.derive_segment_stress(ways, state_speed, city_speed)
    ways = ways.assign(**{name: segment[name] for name in segment.columns})
    intersections = features.build_intersections(ways, ingested["nodes"])
    flags = features.derive_intersection_flags(
        intersections,
        ways,
        ingested["points"],
    )
    junction = stress.derive_intersection_stress(ways, intersections, flags)
    ways = ways.assign(**{name: junction[name] for name in junction.columns})
    intersections = intersections.join(flags)

    logger.info("computing reachability")
    blocks = ingested["census_blocks"].assign(
        road_ids=network.assign_block_roads(ingested["census_blocks"], ways),
    )
    reachability = network.compute_reachability(
        ways,
        blocks,
        boundary,
        inputs.max_trip_distance,
    )
    connected = network.connected_census_blocks(
        blocks,
        boundary,
        reachability["low_stress"],
        reachability["high_stress"],
        inputs.max_trip_distance,
    )

    logger.info("scoring")
    blocks, destinations = _score(
        blocks,
        ways,
        boundary,
        connected,
        reachability,
        ingested["destinations"],
        artifacts,
        inputs,
    )
    overall = scoring.derive_overall_scores(blocks, boundary, ways)

    return {
        "ways": ways,
        "census_blocks": blocks,
        "intersections": intersections,
        "boundary": boundary,
        "destinations": destinations,
        "connected": connected,
        "overall": overall,
        "mileage": features.calculate_mileage(ways),
        "residential_speed_limit": pd.DataFrame(
            [
                {
                    "state_fips_code": state_fips,
                    "city_fips_code": inputs.fips_code,
                    "state_speed": state_speed,
                    "city_speed": city_speed,
                },
            ],
        ),
        "srid": ingested["srid"],
    }


def _score(
    blocks: gpd.GeoDataFrame,
    ways: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    connected: pd.DataFrame,
    reachability: dict[str, typing.Any],
    osm_features: gpd.GeoDataFrame,
    artifacts: ingest.PrepareArtifacts,
    inputs: AnalysisInputs,
) -> tuple[gpd.GeoDataFrame, dict[str, gpd.GeoDataFrame]]:
    """Attach every access, category, and overall score to the blocks.

    Returns
    -------
    tuple
        The scored blocks and the extracted destinations by category.
    """
    weights = scoring.access_weights()
    destinations: dict[str, gpd.GeoDataFrame] = {}
    for rule in (*scoring.DESTINATION_RULES, scoring.RETAIL_RULE):
        found = scoring.extract_destinations(osm_features, blocks, rule)
        destinations[rule.name] = found
        counts = scoring.count_reachable(blocks, found, connected)
        access = weights.get(rule.name, config.Access(rule.name))
        blocks[f"{rule.name}_low_stress"] = counts["low_stress"].to_numpy()
        blocks[f"{rule.name}_high_stress"] = counts["high_stress"].to_numpy()
        blocks[f"{rule.name}_score"] = scoring.destination_score(
            counts["low_stress"],
            counts["high_stress"],
            access,
        ).to_numpy()

    # Population and jobs use the piecewise curve, not the place-counting
    # ladder (findings.md §1.12).
    population = _shed_totals_as_int(blocks, connected, "pop20")
    blocks["pop_low_stress"] = population["low_stress"].to_numpy()
    blocks["pop_high_stress"] = population["high_stress"].to_numpy()
    blocks["pop_score"] = scoring.step_score(
        population["low_stress"],
        population["high_stress"],
    ).to_numpy()

    # Outside the US there is no LODES data, so `census_block_jobs.sql` never
    # runs and every employment column stays NULL -- which is not the same as
    # a city where nobody works (findings.md §1.16).
    lodes_year = inputs.lodes_year or _discover_lodes_year(artifacts)
    if lodes_year:
        state_abbrev, _, _ = analysis.derive_state_info(inputs.region)
        jobs = ingest.load_jobs(artifacts, state_abbrev, lodes_year)
        blocks["jobs"] = scoring.block_jobs(blocks, jobs).to_numpy()
        employment = _shed_totals_as_int(blocks, connected, "jobs")
        blocks["emp_low_stress"] = employment["low_stress"].to_numpy()
        blocks["emp_high_stress"] = employment["high_stress"].to_numpy()
        blocks["emp_score"] = scoring.step_score(
            employment["low_stress"],
            employment["high_stress"],
        ).to_numpy()
    else:
        blocks["emp_low_stress"] = np.nan
        blocks["emp_high_stress"] = np.nan
        blocks["emp_score"] = np.nan

    # Trails are path clusters, reached at the road level, not block pairs.
    _, paths = features.cluster_paths(ways)
    trails = scoring.count_reachable_trails(
        blocks,
        ways,
        paths,
        reachability["low_stress"],
        reachability["high_stress"],
    )
    blocks["trails_low_stress"] = trails["low_stress"].to_numpy()
    blocks["trails_high_stress"] = trails["high_stress"].to_numpy()
    blocks["trails_score"] = scoring.destination_score(
        trails["low_stress"],
        trails["high_stress"],
        scoring.TRAILS_ACCESS,
    ).to_numpy()

    categories = scoring.derive_category_scores(blocks)
    for name in categories.columns:
        blocks[name] = categories[name].to_numpy()
    blocks["overall_score"] = scoring.derive_block_overall_score(
        blocks,
        boundary,
    ).to_numpy()
    reachable = connected.groupby("source_blockid20").size()
    blocks["reachable_blocks"] = (
        blocks["geoid20"].astype(str).map(reachable).fillna(0).astype("int64")
    ).to_numpy()
    # Internal working column; not part of the published schema.
    blocks = blocks.drop(columns=["jobs"], errors="ignore")
    return blocks, destinations


def analyze_and_export(
    inputs: AnalysisInputs,
    export_dir: pathlib.Path,
) -> list[pathlib.Path]:
    """Run the analysis and write its results.

    Parameters
    ----------
    inputs
        Analysis inputs.
    export_dir
        Where to write the published files.

    Returns
    -------
    list of pathlib.Path
        The files written.
    """
    results = analyze(inputs)
    return export.export_results(results, export_dir)


__all__ = [
    "AnalysisInputs",
    "analyze",
    "analyze_and_export",
    "errors",
]
