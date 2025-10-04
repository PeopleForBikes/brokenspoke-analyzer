"""
Define functions to run SQL scripts.

Define functions to run the various SQL scripts performing the operations to
compute the BNA scores.
"""

import concurrent.futures
import dataclasses
import os
import pathlib
import typing
from random import uniform

from loguru import logger
from sqlalchemy.engine import Engine

from brokenspoke_analyzer.cli import common
from brokenspoke_analyzer.core import constant
from brokenspoke_analyzer.core.database import dbcore

NB_SIGCTL_SEARCH_DIST = 25


def execute_sqlfile_with_substitutions(
    engine: Engine,
    sqlfile: pathlib.Path,
    bind_params: typing.Optional[typing.Mapping[str, typing.Any]] = None,
    log_level: str = "DEBUG",
) -> None:
    """Execute SQL statements with substitutions."""
    logger.log(log_level, f"Execute {sqlfile}")
    logger.log(log_level, f"{bind_params=}")
    statements = sqlfile.read_text()
    if bind_params:
        binding_names = sorted(bind_params.keys(), key=len, reverse=True)
        for binding_name in binding_names:
            param = bind_params[binding_name]
            substitute = param if param is not None else "NULL"
            statements = statements.replace(f":{binding_name}", f"{substitute}")
    dbcore.execute_query(engine, statements)


def features(
    engine: Engine,
    sql_script_dir: pathlib.Path,
    output_srid: int,
    boundary_buffer: int,
) -> None:
    """Compute the BNA features."""
    sql_script_dir = sql_script_dir.resolve(strict=True)
    sql_feature_script_dir = sql_script_dir / "features"

    # Update field names.
    logger.info("Update field names")
    sql_script = sql_script_dir / "prepare_tables.sql"
    bind_params = {"nb_output_srid": output_srid}
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Clip.
    logger.info("Clip OSM source data to boundary + buffer")
    sql_script = sql_script_dir / "clip_osm.sql"
    bind_params = {"nb_boundary_buffer": boundary_buffer}
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Remove paths that prohibit bicycles.
    logger.info("Removing paths that prohibit bicycles")
    dbcore.execute_query(
        engine,
        "DELETE FROM neighborhood_osm_full_line WHERE bicycle='no' and highway='path';",
    )

    # Setting values on road segments.
    logger.info("Setting values on road segments")
    sql_scripts = ["one_way.sql", "width_ft.sql", "functional_class.sql"]
    for script in sql_scripts:
        sql_script = sql_feature_script_dir / script
        dbcore.execute_sql_file(engine, sql_script)
    sql_script = sql_feature_script_dir / "paths.sql"
    bind_params = {"nb_output_srid": output_srid}
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)
    sql_scripts = [
        "speed_limit.sql",
        "lanes.sql",
        "park.sql",
        "bike_infra.sql",
        "class_adjustments.sql",
        "legs.sql",
    ]
    for script in sql_scripts:
        sql_script = sql_feature_script_dir / script
        dbcore.execute_sql_file(engine, sql_script)
    sql_scripts = ["signalized.sql", "stops.sql", "rrfb.sql", "island.sql"]
    bind_params = {"sigctl_search_dist": NB_SIGCTL_SEARCH_DIST}
    for script in sql_scripts:
        sql_script = sql_feature_script_dir / script
        execute_sqlfile_with_substitutions(engine, sql_script, bind_params)


def stress(
    engine: Engine,
    sql_script_dir: pathlib.Path,
    state_default_speed: int | None,
    city_default_speed: int | None,
) -> None:
    """Compute stress levels."""
    sql_script_dir = sql_script_dir.resolve(strict=True)
    sql_stress_script_dir = sql_script_dir / "stress"

    # Calculating stress.
    logger.info("Calculating stress")
    sql_script = sql_stress_script_dir / "stress_motorway-trunk.sql"
    dbcore.execute_sql_file(engine, sql_script)

    # Primary.
    logger.info("Primary")
    sql_script = sql_stress_script_dir / "stress_segments_higher_order.sql"
    bind_params = {
        "class": "primary",
        "default_speed": 40,
        "default_lanes": 2,
        "default_parking": 1,
        "default_parking_width": 8,
        "default_facility_width": 5,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Secondary.
    logger.info("Secondary")
    sql_script = sql_stress_script_dir / "stress_segments_higher_order.sql"
    bind_params = {
        "class": "secondary",
        "default_speed": 40,
        "default_lanes": 2,
        "default_parking": 1,
        "default_parking_width": 8,
        "default_facility_width": 5,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Tertiary.
    logger.info("Tertiary")
    sql_script = sql_stress_script_dir / "stress_segments_higher_order.sql"
    bind_params = {
        "class": "tertiary",
        "default_speed": 30,
        "default_lanes": 1,
        "default_parking": 1,
        "default_parking_width": 8,
        "default_facility_width": 5,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Residential.
    logger.info("Residential")
    sql_script = sql_stress_script_dir / "stress_segments_lower_order_res.sql"
    bind_params = {
        "class": "residential",
        "default_lanes": 1,
        "default_parking": 1,
        "default_roadway_width": 27,
        "state_default": state_default_speed,
        "city_default": city_default_speed,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Unclassified.
    logger.info("Unclassified")
    sql_script = sql_stress_script_dir / "stress_segments_lower_order.sql"
    bind_params = {
        "class": "unclassified",
        "default_speed": 25,
        "default_lanes": 1,
        "default_parking": 1,
        "default_roadway_width": 27,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)
    sql_scripts = [
        "stress_living_street.sql",
        "stress_track.sql",
        "stress_path.sql",
        "stress_one_way_reset.sql",
        "stress_motorway-trunk_ints.sql",
        "stress_primary_ints.sql",
        "stress_secondary_ints.sql",
    ]
    for script in sql_scripts:
        sql_script = sql_stress_script_dir / script
        dbcore.execute_sql_file(engine, sql_script)

    # Tertiary intersections.
    logger.info("Tertiary intersections")
    sql_script = sql_stress_script_dir / "stress_tertiary_ints.sql"
    bind_params = {
        "primary_speed": 40,
        "secondary_speed": 40,
        "primary_lanes": 2,
        "secondary_lanes": 2,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)
    sql_script = sql_stress_script_dir / "stress_lesser_ints.sql"
    bind_params = {
        "primary_speed": 40,
        "secondary_speed": 40,
        "tertiary_speed": 30,
        "primary_lanes": 2,
        "secondary_lanes": 2,
        "tertiary_lanes": 1,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)
    sql_script = sql_stress_script_dir / "stress_link_ints.sql"
    dbcore.execute_sql_file(engine, sql_script)


@dataclasses.dataclass
class Tolerance:
    """Cluster tolerances given in units of `output_srid`."""

    colleges: int = 100
    community_centers: int = 50
    doctors: int = 50
    dentists: int = 50
    hospitals: int = 50
    pharmacies: int = 50
    parks: int = 50
    retail: int = 50
    transit: int = 75
    universities: int = 150


@dataclasses.dataclass
class PathConstraint:
    """Define the Path Constraints."""

    # Minimum path length to be considered for recreation access.
    min_length: int = 4800
    # Minimum corner-to-corner span of path bounding box to be considered for
    # recreation access.
    min_bbox: int = 3300


@dataclasses.dataclass
class BlockRoad:
    """Define the Block Road items."""

    # Buffer distance to find roads associated with a block.
    buffer: int = 15
    # Minimum length road must overlap with block buffer to be associated .
    min_length: int = 30


@dataclasses.dataclass
class Score:
    """Define the Score parts."""

    total: int = 100
    people: int = 15
    opportunity: int = 20
    core_services: int = 20
    retail: int = 15
    recreation: int = 15
    transit: int = 15


@dataclasses.dataclass
class Access:
    """Define the Access parts."""

    name: str
    first: float = 0.0
    second: float = 0.0
    third: float = 0.0
    max_score: int = 1


def connectivity(
    engine: Engine,
    sql_script_dir: pathlib.Path,
    output_srid: int,
    import_jobs: bool,
    max_trip_distance: typing.Optional[int] = common.DEFAULT_MAX_TRIP_DISTANCE,
) -> None:
    """Compute BNA connectivity scores."""
    # Makes MyPy happy.
    assert max_trip_distance

    # Prepare computation variables.
    tolerance = Tolerance()
    path_constraint = PathConstraint()
    block_road = BlockRoad()
    score = Score()

    # Prepare the paths.
    sql_script_dir = sql_script_dir.resolve(strict=True)
    sql_connectivity_script_dir = sql_script_dir / "connectivity"

    # Building network.
    logger.info("BUILDING: Building network")
    sql_script = sql_connectivity_script_dir / "build_network.sql"
    bind_params = {"nb_output_srid": output_srid}
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    sql_script = sql_connectivity_script_dir / "census_blocks.sql"
    bind_params = {
        "block_road_buffer": block_road.buffer,
        "block_road_min_length": block_road.min_length,
        "nb_output_srid": output_srid,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Fetch all road_ids and then calculate stress for them individually but in parallel
    result = dbcore.execute_query_with_result(
        engine, "select road_id FROM neighborhood_ways"
    )
    road_ids = [e for l in result for e in l]
    road_ids.sort()

    # Reachable roads stress.
    for stress_level in ["high", "low"]:
        logger.info(f"CONNECTIVITY: Reachable roads {stress_level} stress")

        # Prep.
        logger.info(f"Reachable roads {stress_level} stress: prep")
        sql_script = (
            sql_connectivity_script_dir
            / f"reachable_roads_{stress_level}_stress_prep.sql"
        )
        dbcore.execute_sql_file(engine, sql_script)

        # Calculations
        logger.info(f"Reachable roads {stress_level} stress: calculations")
        sql_script = (
            sql_connectivity_script_dir
            / f"reachable_roads_{stress_level}_stress_calc.sql"
        )
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_road_id = {
                executor.submit(
                    execute_sqlfile_with_substitutions,
                    engine,
                    sql_script,
                    {"road_id": i, "nb_max_trip_distance": max_trip_distance},
                    "TRACE",
                ): i
                for i in road_ids
            }
            for future in concurrent.futures.as_completed(future_to_road_id):
                url = future_to_road_id[future]
                data = future.result()

        # Cleanup.
        logger.info(f"Reachable roads {stress_level} stress: cleanup")
        sql_script = (
            sql_connectivity_script_dir
            / f"reachable_roads_{stress_level}_stress_cleanup.sql"
        )
        dbcore.execute_sql_file(engine, sql_script)

    # Connected census blocks.
    logger.info("CONNECTIVITY: Connected census blocks")
    sql_script = sql_connectivity_script_dir / "connected_census_blocks_prep.sql"
    dbcore.execute_sql_file(engine, sql_script)

    sql_script = sql_connectivity_script_dir / "connected_census_blocks_calc.sql"

    # Fetch all blockids and then calculate stress for them individually but in parallel
    result = dbcore.execute_query_with_result(
        engine, "select blockid10 FROM neighborhood_census_blocks"
    )
    census_block_ids = [e for l in result for e in l]
    census_block_ids.sort()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_census_block_id = {
            executor.submit(
                execute_sqlfile_with_substitutions,
                engine,
                sql_script,
                {
                    "nb_max_trip_distance": max_trip_distance,
                    "nb_output_srid": output_srid,
                    "block_id": f"'{i}'",
                },
                "TRACE",
            ): i
            for i in census_block_ids
        }
        for future in concurrent.futures.as_completed(future_to_census_block_id):
            _census_block_id = future_to_census_block_id[future]
            data = future.result()

    sql_script = sql_connectivity_script_dir / "connected_census_blocks.sql"
    dbcore.execute_sql_file(engine, sql_script)

    # Access: population
    logger.info("METRICS: Access: population")
    sql_script = sql_connectivity_script_dir / "access_population.sql"
    bind_params: typing.Mapping[str, float] = {  # type: ignore
        "max_score": 1,
        "step1": 0.03,
        "score1": 0.1,
        "step2": 0.2,
        "score2": 0.4,
        "step3": 0.5,
        "score3": 0.8,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Import jobs.
    if import_jobs:
        logger.info("METRICS: Access: jobs")
        sql_script = sql_connectivity_script_dir / "census_block_jobs.sql"
        dbcore.execute_sql_file(engine, sql_script)

        sql_script = sql_connectivity_script_dir / "access_jobs.sql"
        bind_params: typing.Mapping[str, float] = {  # type: ignore
            "max_score": 1,
            "step1": 0.03,
            "score1": 0.1,
            "step2": 0.2,
            "score2": 0.4,
            "step3": 0.5,
            "score3": 0.8,
        }
        execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Destinations.
    logger.info("METRICS: Destinations")
    destinations = [
        (tolerance.colleges, "colleges"),
        (tolerance.community_centers, "community_centers"),
        (tolerance.doctors, "doctors"),
        (tolerance.dentists, "dentists"),
        (tolerance.hospitals, "hospitals"),
        (tolerance.pharmacies, "pharmacies"),
        (tolerance.parks, "parks"),
        (tolerance.retail, "retail"),
        (tolerance.transit, "transit"),
        (tolerance.universities, "universities"),
    ]
    sql_destination_script_dir = sql_connectivity_script_dir / "destinations"
    for destination in destinations:
        sql_script = sql_destination_script_dir / f"{destination[1]}.sql"
        bind_params = {
            "cluster_tolerance": destination[0],
            "nb_output_srid": output_srid,
        }
        execute_sqlfile_with_substitutions(engine, sql_script, bind_params)
    destinations = ["schools", "social_services", "supermarkets"]  # type: ignore
    for destination in destinations:
        sql_script = sql_destination_script_dir / f"{destination}.sql"
        bind_params = {"nb_output_srid": output_srid}
        execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Accesses.
    logger.info("METRICS: Accesses")
    accesses = [
        Access("colleges", first=0.7),
        Access("community_centers", first=0.4, second=0.2, third=0.1),
        Access("doctors", first=0.4, second=0.2, third=0.1),
        Access("dentists", first=0.4, second=0.2, third=0.1),
        Access("hospitals", first=0.7),
        Access("pharmacies", first=0.4, second=0.2, third=0.1),
        Access("parks", first=0.3, second=0.2, third=0.2),
        Access("retail", first=0.4, second=0.2, third=0.1),
        Access("schools", first=0.3, second=0.2, third=0.2),
        Access("social_services", first=0.7),
        Access("supermarkets", first=0.6, second=0.2),
        Access("transit", first=0.6),
        Access("universities", first=0.7),
    ]
    for access in accesses:
        sql_script = sql_connectivity_script_dir / f"access_{access.name}.sql"
        bind_params = {
            "first": access.first,  # type: ignore
            "second": access.second,  # type: ignore
            "third": access.third,  # type: ignore
            "max_score": access.max_score,
        }
        execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Access_trails.
    sql_script = sql_connectivity_script_dir / "access_trails.sql"
    bind_params = {
        "first": 0.7,  # type: ignore
        "second": 0.2,  # type: ignore
        "third": 0,
        "max_score": 1,
        "min_path_length": path_constraint.min_length,
        "min_bbox_length": path_constraint.min_bbox,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Access_overall.
    sql_script = sql_connectivity_script_dir / "access_overall.sql"
    bind_params = {
        "total": score.total,
        "people": score.people,
        "opportunity": score.opportunity,
        "core_services": score.core_services,
        "retail": score.retail,
        "recreation": score.recreation,
        "transit": score.transit,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)

    # Prepare score inputs.
    sql_script = sql_connectivity_script_dir / "score_inputs.sql"
    dbcore.execute_sql_file(engine, sql_script)

    # Overall score.
    sql_script = sql_connectivity_script_dir / "overall_scores.sql"
    bind_params = {
        "total": score.total,
        "people": score.people,
        "opportunity": score.opportunity,
        "core_services": score.core_services,
        "retail": score.retail,
        "recreation": score.recreation,
        "transit": score.transit,
    }
    execute_sqlfile_with_substitutions(engine, sql_script, bind_params)


def measure(
    engine: Engine,
    sql_script_dir: pathlib.Path,
) -> None:
    """Compute BNA mileage."""
    # Prepare the paths.
    sql_script_dir = sql_script_dir.resolve(strict=True)
    sql_connectivity_script_dir = sql_script_dir / "features"

    # Calculating mileage.
    logger.info("MILEAGE: Calculating mileage")
    sql_script = sql_connectivity_script_dir / "calculate_mileage.sql"
    execute_sqlfile_with_substitutions(engine, sql_script)


def all(
    database_url: common.DatabaseURL,
    sql_script_dir: pathlib.Path,
    output_srid: int,
    state_default_speed: int | None,
    city_default_speed: int | None,
    import_jobs: bool,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
) -> None:
    """Compute all features."""
    parts(
        database_url=database_url,
        sql_script_dir=sql_script_dir,
        output_srid=output_srid,
        state_default_speed=state_default_speed,
        city_default_speed=city_default_speed,
        import_jobs=import_jobs,
        buffer=buffer,
        max_trip_distance=max_trip_distance,
        compute_parts=constant.COMPUTE_PARTS_ALL,
    )


def parts(
    database_url: common.DatabaseURL,
    sql_script_dir: pathlib.Path,
    output_srid: int,
    state_default_speed: int | None,
    city_default_speed: int | None,
    import_jobs: bool,
    buffer: common.Buffer = common.DEFAULT_BUFFER,
    max_trip_distance: common.MaxTripDistance = common.DEFAULT_MAX_TRIP_DISTANCE,
    compute_parts: common.ComputeParts = common.DEFAULT_COMPUTE_PARTS,
) -> None:
    """Cherry pick the parts of the analysis to compute."""
    # Make mypy happy.
    if not buffer:
        raise ValueError("`buffer` must be set")
    if not compute_parts:
        raise ValueError("`compute_parts` must be set")

    if not compute_parts:
        logger.info("no compute action was specified")

    # Prepare the database connection.
    engine = dbcore.create_psycopg_engine(database_url)

    # Compute features.
    # Features are required to compute ALL the other parts, therefore are being
    # run every time.
    logger.info("Compute features")
    features(engine, sql_script_dir, output_srid, buffer)

    # Compute stress.
    if constant.ComputePart.STRESS in compute_parts:
        logger.info("Compute stress")
        stress(
            engine,
            sql_script_dir,
            state_default_speed,
            city_default_speed,
        )

    # Compute connectivity.
    if constant.ComputePart.CONNECTIVITY in compute_parts:
        logger.info("Compute connectivity")
        connectivity(
            engine,
            sql_script_dir,
            output_srid,
            import_jobs,
            max_trip_distance,
        )

    # Compute mileage.
    if (
        constant.ComputePart.MEASURE in compute_parts
        and os.getenv("BNA_EXPERIMENTAL", "0") == "1"
    ):
        logger.info("Compute mileage")
        measure(
            engine,
            sql_script_dir,
        )
