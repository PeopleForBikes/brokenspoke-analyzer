"""
Compare the Python pipeline's output against the SQL pipeline's results.

From the root of this repository run:

```bash
just validate-parity            # the XS/S iteration corpus
just validate-parity jackson    # one city
```

## What it compares

For every corpus city it runs the new pipeline (`bna run --skip-prepare`, in
process) and compares what it writes against the frozen `results/**` tree the
SQL pipeline produced, one dimension at a time:

| Dimension                  | Key            | Rule                          |
| -------------------------- | -------------- | ----------------------------- |
| `overall_scores`           | `score_id`     | raw `1e-4`, display exact     |
| `census_blocks`            | `geoid20`      | row-for-row, numeric + geom   |
| `ways`                     | `road_id`      | row-for-row, numeric + geom   |
| `ways_intersections`       | `int_id`       | row-for-row, numeric + geom   |
| `connected_census_blocks`  | block pair     | row-for-row, cost + stress    |
| `mileage`                  | `feature_type` | raw `1e-4`                    |
| `residential_speed_limit`  | (single row)   | exact                         |

The report is per city *and* per dimension (design.md §5.4): a single-column
regression names its column, so it can be diagnosed without re-running the
corpus.

Reference files carry the legacy `neighborhood_` prefix; the new pipeline
drops it. That rename is expected (requirements.md FR-EXPORT-2), so it is
resolved when the pair is loaded, never reported as a difference.
"""

import csv
import dataclasses
import json
import pathlib
import time
import typing
from typing import Annotated

import geopandas as gpd
import pandas as pd
import shapely
import typer

from brokenspoke_analyzer.cli import (
    common,
    root,
)
from brokenspoke_analyzer.core.pipeline import (
    errors,
    export,
    orchestrator,
)

# NFR-PARITY-1: raw scores agree to this absolute difference.
RAW_TOLERANCE = 1e-4
# NFR-PARITY-1: and agree exactly once rounded for display.
DISPLAY_DIGITS = 2
# NFR-PARITY-2: geometry is compared by shape, not by WKB bytes, so that an
# equivalent representation (vertex order, a closing coordinate) still passes.
GEOMETRY_TOLERANCE = 1e-6

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "integration"
ITERATION_CORPUS = ("XS", "S")

# Each dimension: the file basename, its stable key, and whether rows have to
# be paired on geometry because both pipelines assign their own ids.
DIMENSIONS = (
    ("overall_scores", "score_id", False),
    # `score_name` repeats ("Average score of access to population" is two
    # rows), and the serial `id` is the insertion order, which is fixed.
    ("score_inputs", "id", False),
    ("census_blocks", "geoid20", False),
    ("ways", "road_id", True),
    ("ways_intersections", "int_id", True),
    ("connected_census_blocks", ("source_blockid20", "target_blockid20"), False),
    ("mileage", "feature_type", False),
    ("residential_speed_limit", "state_fips_code", False),
)

# `gid` is a `pgsql2shp` export artifact: a row number, not data. Every other
# name here is a surrogate key the database handed out as it inserted rows --
# `road_id`, `int_id`, and the two intersection references are sequences, and
# the Python pipeline numbers its own rows independently. Comparing them would
# report the insertion order, not the analysis.
IGNORED_COLUMNS = frozenset(
    {
        "gid",
        # The destination tables' serial primary key.
        "id",
        "tdg_id",
        "tag_id",
        "road_id",
        "int_id",
        "intersection_from",
        "intersection_to",
        # A list of `road_id`s, so surrogate for the same reason.
        "road_ids",
    },
)

# `path_id` is a cluster label: which cluster a path landed in is arbitrary,
# but *whether* it is in one is not. Compare only that.
NULLNESS_ONLY_COLUMNS = frozenset({"path_id"})

# How precisely a coordinate has to agree for two rows to be the same row.
# Five decimal degrees is about a metre: below any segmentation difference
# this harness looks for, and above the rounding the two export paths differ
# by in the seventh decimal.
KEY_PRECISION = 5


@dataclasses.dataclass(frozen=True)
class KnownDeviation:
    """A documented, accepted difference from the baseline.

    Parameters
    ----------
    reason
        One line for the report, naming where it is written up.
    extra_segments
        The `ways` rows the new pipeline produces and the baseline lacks,
        as `(osm_id, {node, node})`. Listing them exactly is the point: the
        city is excused for *these* rows and nothing else, so a new problem
        there still fails the gate.
    """

    reason: str
    extra_segments: frozenset[tuple[int, frozenset[int]]]


# requirements.md §6.1a. `osm2pgrouting` drops an edge that duplicates one
# inserted in an earlier 20,000-way processing chunk, so three of Chambéry's
# segments are missing from the baseline through an import artifact rather
# than any analysis rule (findings.md §1.26). It is keyed to a way's ordinal
# position in the extract, so it is unmatchable by any rule over the data --
# and it moves as soon as the extract does.
KNOWN_DEVIATIONS = {
    "chambéry": KnownDeviation(
        reason="osm2pgrouting chunk-boundary edge loss (findings.md §1.26)",
        extra_segments=frozenset(
            {
                (1038105016, frozenset({1523885116, 3257144810})),
                (1038105016, frozenset({3257144810, 290143766})),
                (850421039, frozenset({7933888679, 2634514696})),
            },
        ),
    ),
}


def extra_segments(
    reference: gpd.GeoDataFrame,
    actual: gpd.GeoDataFrame,
) -> set[tuple[int, frozenset[int]]]:
    """Name the road rows the new pipeline has and the baseline lacks.

    The rows are found by geometry, as everywhere else in this harness --
    `road_id` is a database sequence (§9.1) -- but they are *named* by OSM way
    id and the two OSM nodes they run between, which is stable enough to write
    down in `KNOWN_DEVIATIONS`. The baseline's own `intersection_*` columns
    are database ids and cannot be used for this.
    """
    known = set(_as_key(reference, "road_id", spatial=True))
    keys = _as_key(actual, "road_id", spatial=True)
    columns = {"osm_id", "intersection_from", "intersection_to"}
    if not columns <= set(actual.columns):
        return set()
    found: set[tuple[int, frozenset[int]]] = set()
    for position, key in enumerate(keys):
        if key in known:
            continue
        row = actual.iloc[position]
        if any(pd.isna(row[column]) for column in columns):
            continue
        found.add(
            (
                int(row["osm_id"]),
                frozenset({int(row["intersection_from"]), int(row["intersection_to"])}),
            ),
        )
    return found


@dataclasses.dataclass
class Difference:
    """One failing column within one dimension.

    Parameters
    ----------
    column
        The column that differs, or `(rows)` for a row-count mismatch.
    rows
        How many keys differ.
    detail
        A sample difference, for diagnosis.
    """

    column: str
    rows: int
    detail: str


@dataclasses.dataclass
class DimensionResult:
    """The outcome of comparing one dimension for one city."""

    name: str
    status: str
    reference_rows: int = 0
    actual_rows: int = 0
    differences: list[Difference] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether this dimension matched (a skip is not a failure)."""
        return self.status in {"pass", "skip"}


@dataclasses.dataclass
class CityResult:
    """Every dimension's outcome for one city, plus its wall-clock time."""

    city: str
    region: str
    country: str
    reference: pathlib.Path | None = None
    seconds: float = 0.0
    error: str = ""
    excepted: str = ""
    dimensions: list[DimensionResult] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the city matched on every dimension."""
        return not self.error and all(d.ok for d in self.dimensions)

    @property
    def acceptable(self) -> bool:
        """Whether the gate passes: a clean match, or a documented deviation."""
        return self.ok or bool(self.excepted)


def read_corpus(sizes: typing.Sequence[str]) -> list[dict[str, str]]:
    """Read the corpus cities of the given `test_size`s.

    Parameters
    ----------
    sizes
        `test_size` values to include, e.g. `("XS", "S")`.

    Returns
    -------
    list of dict
        One row per city, in corpus order.

    Examples
    --------
    >>> rows = read_corpus(["XS"])
    >>> {row["test_size"] for row in rows}
    {'XS'}
    """
    rows: list[dict[str, str]] = []
    for size in sizes:
        corpus = CORPUS_DIR / f"e2e-cities-{size}.csv"
        with corpus.open() as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def read_every_corpus_city() -> list[dict[str, str]]:
    """Read every city, whatever its `test_size`.

    Naming a city explicitly should find it wherever it lives -- the manual
    validation passes in tasks.md 10.3 are `just validate-parity valencia`
    (`XL`) and `just validate-parity washington` (`XXL`), neither of which is
    in any automated corpus.

    Returns
    -------
    list of dict
        One row per city, in corpus order.

    Examples
    --------
    >>> {row["city"] for row in read_every_corpus_city()} >= {"valencia"}
    True
    """
    with (CORPUS_DIR / "e2e-cities.csv").open() as handle:
        return list(csv.DictReader(handle))


def version_key(name: str) -> tuple[int, ...]:
    """Order calver directory names numerically, not lexically.

    `26.09.10` is newer than `26.09.2`, which string ordering gets wrong.

    Examples
    --------
    >>> sorted(["26.09.10", "26.09.2", "26.09"], key=version_key)[-1]
    '26.09.10'
    """
    return tuple(int(part) for part in name.split(".") if part.isdigit())


def latest_reference(
    results_dir: pathlib.Path,
    row: dict[str, str],
) -> pathlib.Path | None:
    """Find the newest complete reference run for one city.

    A city can have several version directories (a re-run bumps the calver
    micro). Only directories holding an `overall_scores` file count: an
    interrupted run leaves a partial tree behind, and comparing against that
    would report the interruption as a parity failure.

    Returns
    -------
    pathlib.Path or None
        The newest complete run, or None when the city has never been run.
    """
    city_dir = results_dir / row["country"] / row["region"] / row["city"]
    if not city_dir.is_dir():
        return None
    complete = [
        candidate
        for candidate in city_dir.iterdir()
        if candidate.is_dir()
        and (candidate / "neighborhood_overall_scores.csv").is_file()
    ]
    if not complete:
        return None
    return max(complete, key=lambda path: version_key(path.name))


def load_pair(
    reference_dir: pathlib.Path,
    actual_dir: pathlib.Path,
    name: str,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Load one dimension from both trees, resolving the prefix rename.

    Returns
    -------
    tuple
        The reference and actual frames; either is None when absent.
    """

    def load(directory: pathlib.Path, basename: str) -> pd.DataFrame | None:
        geojson = directory / f"{basename}.geojson"
        if geojson.is_file():
            return gpd.read_file(geojson)
        csv_file = directory / f"{basename}.csv"
        if csv_file.is_file():
            return pd.read_csv(csv_file)
        return None

    reference = load(reference_dir, f"neighborhood_{name}")
    if reference is None:
        # `mileage` and `residential_speed_limit` were never prefixed.
        reference = load(reference_dir, name)
    return reference, load(actual_dir, name)


def _endpoint_key(frame: gpd.GeoDataFrame) -> pd.Series:
    """Key spatial rows by where they are, not by the id they were given.

    `road_id` and `int_id` are database sequences, so the two pipelines
    number the same road differently and there is no id to join on. What is
    stable is the geometry: a road is identified by its OSM way plus its two
    endpoints, an intersection by its point. Endpoints are sorted so that a
    segment stored in the opposite direction still pairs up -- a direction
    flip then shows as the `ft_*`/`tf_*` difference it is, instead of
    vanishing into an unmatched row.
    """
    # `pgsql2shp` exported the roads as single-part MultiLineStrings, so read
    # the coordinates off the whole geometry rather than off `.coords`, which
    # multi-part geometries do not have.
    ends = []
    for shape in frame.geometry:
        coordinates = shapely.get_coordinates(shape)
        points = "/".join(
            sorted(
                f"{point[0]:.{KEY_PRECISION}f},{point[1]:.{KEY_PRECISION}f}"
                for point in (coordinates[0], coordinates[-1])
            ),
        )
        # The two halves of a split loop share both endpoints, so the endpoints
        # alone do not identify a road. Their lengths differ.
        ends.append(f"{points}#{shapely.length(shape):.7f}")
    if "osm_id" in frame.columns:
        prefix = frame["osm_id"].astype("Int64").astype(str).to_numpy()
        ends = [f"{osm}@{end}" for osm, end in zip(prefix, ends, strict=True)]
    keys = pd.Series(ends, index=frame.index)
    # Anything still tied -- a way doubled back on itself -- is disambiguated
    # by occurrence, which is stable as long as both sides hold the same rows.
    return keys.str.cat(keys.groupby(keys).cumcount().astype(str), sep="~")


def _as_key(
    frame: pd.DataFrame,
    key: str | tuple[str, ...],
    *,
    spatial: bool,
) -> pd.Series:
    """Normalise a key so both sides index the same way.

    Block ids are zero-padded in the SQL export and numeric in ours, so the
    key is compared with the padding stripped -- `080519638001077` and
    `80519638001077` are the same block.
    """
    if spatial and isinstance(frame, gpd.GeoDataFrame) and frame.geometry.notna().all():
        return _endpoint_key(frame)
    columns = (key,) if isinstance(key, str) else key
    parts = [
        frame[column].astype(str).str.strip().str.lstrip("0") for column in columns
    ]
    if len(parts) == 1:
        return parts[0]
    return parts[0].str.cat(parts[1:], sep="|")


def _sample(values: pd.Series, key: typing.Any) -> str:
    """Show one value from a series, tolerating a repeated index."""
    found = values.loc[[key]].iloc[0]
    text = found.wkt if hasattr(found, "wkt") else repr(found)
    return text[:60]


def _column_difference(
    name: str,
    left: pd.Series,
    right: pd.Series,
) -> Difference | None:
    """Compare one aligned column, numerically where both sides are numeric.

    Returns
    -------
    Difference or None
        None when the column matches.
    """
    if name in NULLNESS_ONLY_COLUMNS:
        differing = left.isna() != right.isna()
    elif pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
        lhs = left.astype(float)
        rhs = right.astype(float)
        raw = (lhs - rhs).abs() > RAW_TOLERANCE
        display = lhs.round(DISPLAY_DIGITS) != rhs.round(DISPLAY_DIGITS)
        # A NaN on one side only is a real difference; on both sides it is not.
        missing = lhs.isna() != rhs.isna()
        differing = ((raw | display) & ~lhs.isna() & ~rhs.isna()) | missing
    else:
        lhs = left.astype(str).str.strip()
        rhs = right.astype(str).str.strip()
        # A column the SQL pipeline exported as all-NULL text and the Python
        # one as all-NaN float is the same emptiness, not a difference.
        differing = (lhs != rhs) & ~(left.isna() & right.isna())
    count = int(differing.sum())
    if not count:
        return None
    where = differing[differing].index[0]
    return Difference(
        column=name,
        rows=count,
        detail=f"{where}: {_sample(left, where)} != {_sample(right, where)}",
    )


def _geometry_difference(
    left: gpd.GeoSeries,
    right: gpd.GeoSeries,
) -> Difference | None:
    """Compare geometry by shape within `GEOMETRY_TOLERANCE`.

    `equals_exact` compares vertex by vertex, so a reprojection rounding
    difference passes while a genuinely different shape does not.
    """
    same = left.geom_equals_exact(right, tolerance=GEOMETRY_TOLERANCE)
    # Fall back to topological equality: a line split at the same place but
    # stored with its vertices reversed is the same geometry.
    same = same | left.geom_equals(right)
    # And to distance, which is the only one of the three that sees through a
    # representation difference. PostGIS typed its columns `MULTI*`, so the
    # reference wraps every block in a MultiPolygon and every road in a
    # MultiLineString; `equals_exact` compares structure and calls that a
    # difference, while `equals` is exact-arithmetic and trips on the
    # fourteenth decimal of a reprojection (NFR-PARITY-2 allows both).
    same = same | (
        shapely.hausdorff_distance(left.to_numpy(), right.to_numpy())
        <= GEOMETRY_TOLERANCE
    )
    differing = ~same.fillna(value=False)
    count = int(differing.sum())
    if not count:
        return None
    where = differing[differing].index[0]
    return Difference(
        column="geometry",
        rows=count,
        detail=f"{where}: {_sample(left, where)} != {_sample(right, where)}",
    )


def _missing_file(
    name: str,
    reference: pd.DataFrame | None,
    actual: pd.DataFrame | None,
) -> DimensionResult | None:
    """Report a dimension one side does not have.

    Returns
    -------
    DimensionResult or None
        None when both sides have the file and can be compared.
    """
    if reference is None and actual is None:
        return DimensionResult(name, "skip")
    if reference is None:
        rows = len(actual) if actual is not None else 0
        return DimensionResult(
            name,
            "fail",
            0,
            rows,
            [Difference("(file)", 0, "no reference file")],
        )
    if actual is None:
        return DimensionResult(
            name,
            "fail",
            len(reference),
            0,
            [Difference("(file)", 0, "not produced")],
        )
    return None


def compare_dimension(
    name: str,
    key: str | tuple[str, ...],
    reference: pd.DataFrame | None,
    actual: pd.DataFrame | None,
    *,
    spatial: bool = False,
) -> DimensionResult:
    """Compare one dimension row-for-row on its stable key.

    Parameters
    ----------
    name
        Dimension name, used in the report.
    key
        The column pairing reference rows with actual rows. Ignored for
        spatial dimensions, which pair on geometry instead.
    reference, actual
        The two frames, or None when the file is absent.
    spatial
        Whether to pair rows by geometry rather than by `key`.

    Returns
    -------
    DimensionResult
        `pass`, `fail`, or `skip` when neither side has the file.
    """
    absent = _missing_file(name, reference, actual)
    if absent:
        return absent

    result = DimensionResult(name, "pass", len(reference), len(actual))
    columns = (key,) if isinstance(key, str) else key
    if not spatial and any(
        column not in reference.columns or column not in actual.columns
        for column in columns
    ):
        result.status = "fail"
        result.differences.append(Difference("(key)", 0, f"{key} missing"))
        return result

    left = reference.set_index(_as_key(reference, key, spatial=spatial))
    right = actual.set_index(_as_key(actual, key, spatial=spatial))
    only_reference = left.index.difference(right.index)
    only_actual = right.index.difference(left.index)
    if len(only_reference) or len(only_actual):
        result.status = "fail"
        result.differences.append(
            Difference(
                "(rows)",
                len(only_reference) + len(only_actual),
                f"{len(only_reference)} missing (e.g. {list(only_reference[:3])}), "
                f"{len(only_actual)} extra (e.g. {list(only_actual[:3])})",
            ),
        )
    shared = left.index.intersection(right.index)
    left = left.loc[shared].sort_index()
    right = right.loc[shared].sort_index()

    # The schema is part of the contract (FR-EXPORT-1): a column one side
    # lacks is a difference, not something to skip over.
    missing = [
        c for c in left.columns if c not in right.columns and c not in IGNORED_COLUMNS
    ]
    extra = [
        c for c in right.columns if c not in left.columns and c not in IGNORED_COLUMNS
    ]
    if missing or extra:
        result.differences.append(
            Difference(
                "(columns)",
                len(missing) + len(extra),
                f"missing {missing}, extra {extra}",
            ),
        )

    for column in left.columns:
        if column in IGNORED_COLUMNS or column not in right.columns:
            continue
        if column == "geometry":
            difference = _geometry_difference(left.geometry, right.geometry)
        else:
            difference = _column_difference(column, left[column], right[column])
        if difference:
            result.differences.append(difference)
    if result.differences:
        result.status = "fail"
    return result


def run_city(
    row: dict[str, str],
    data_dir: pathlib.Path,
    output_dir: pathlib.Path,
) -> pathlib.Path:
    """Run the new pipeline for one corpus city.

    Returns
    -------
    pathlib.Path
        The directory the results were written to.
    """
    city_output = output_dir / row["country"] / row["region"] / row["city"]
    inputs = orchestrator.AnalysisInputs(
        country=row["country"],
        city=row["city"],
        region=row["region"],
        fips_code=row["fips_code"],
        data_dir=data_dir,
    )
    orchestrator.analyze_and_export(inputs, city_output)
    return city_output


def _normalise_block_lists(frame: pd.DataFrame) -> pd.DataFrame:
    """Make `blockid20` arrays comparable as text.

    The SQL built each array with `array((SELECT ...))`, in whatever order
    the scan returned, and exported the ids zero-padded; the Python pipeline
    sorts them and may carry them unpadded. Neither is a difference.
    """
    if "blockid20" not in frame.columns:
        return frame

    def normalise(value: object) -> object:
        if not isinstance(value, typing.Iterable) or isinstance(value, str):
            return value
        return "|".join(sorted(str(v).strip().lstrip("0") for v in value))

    return frame.assign(blockid20=frame["blockid20"].map(normalise))


def compare_destinations(
    reference_dir: pathlib.Path,
    actual_dir: pathlib.Path,
) -> DimensionResult:
    """Compare every published destination layer, as one dimension.

    Each layer is paired on its point geometry (the published centroid) and
    the OSM id where the category records one, then compared column by
    column: the blocks it sits in, its name, and the population shed
    (`pop_low_stress`, `pop_high_stress`, `pop_score`). Differences are
    reported per layer.

    Returns
    -------
    DimensionResult
        `pass`, `fail`, or `skip` when no layer exists on either side.
    """
    result = DimensionResult("destinations", "skip")
    for layer in export.DESTINATION_LAYERS:
        reference, actual = load_pair(reference_dir, actual_dir, layer)
        if reference is not None:
            reference = _normalise_block_lists(reference)
        if actual is not None:
            actual = _normalise_block_lists(actual)
        compared = compare_dimension(layer, "id", reference, actual, spatial=True)
        if compared.status == "skip":
            continue
        result.status = "pass" if result.status == "skip" else result.status
        result.reference_rows += compared.reference_rows
        result.actual_rows += compared.actual_rows
        for difference in compared.differences:
            result.differences.append(
                Difference(
                    f"{layer}.{difference.column}",
                    difference.rows,
                    difference.detail,
                ),
            )
    if result.differences:
        result.status = "fail"
    return result


def compare_city(
    row: dict[str, str],
    data_dir: pathlib.Path,
    output_dir: pathlib.Path,
    results_dir: pathlib.Path,
) -> CityResult:
    """Run and compare one city, never raising on a single city's failure.

    Returns
    -------
    CityResult
        Every dimension's outcome, or the error that stopped the run.
    """
    result = CityResult(
        city=row["city"],
        region=row["region"],
        country=row["country"],
    )
    result.reference = latest_reference(results_dir, row)
    if result.reference is None:
        result.error = "no reference results"
        return result

    started = time.monotonic()
    try:
        actual_dir = run_city(row, data_dir, output_dir)
    except (errors.PipelineError, OSError, ValueError) as exception:
        result.seconds = time.monotonic() - started
        result.error = f"{type(exception).__name__}: {exception}"
        return result
    result.seconds = time.monotonic() - started

    for name, key, spatial in DIMENSIONS:
        reference, actual = load_pair(result.reference, actual_dir, name)
        result.dimensions.append(
            compare_dimension(name, key, reference, actual, spatial=spatial),
        )
    result.dimensions.append(compare_destinations(result.reference, actual_dir))

    deviation = KNOWN_DEVIATIONS.get(row["city"].casefold())
    if deviation and not result.ok:
        reference, actual = load_pair(result.reference, actual_dir, "ways")
        if (
            reference is not None
            and actual is not None
            and extra_segments(reference, actual) == deviation.extra_segments
        ):
            result.excepted = deviation.reason
    return result


def report(results: list[CityResult]) -> None:
    """Print the per-city, per-dimension report."""
    for result in results:
        place = f"{result.city}, {result.region}"
        if result.error:
            typer.echo(f"FAIL {place}: {result.error}")
            continue
        mark = "PASS" if result.ok else ("EXCEPT" if result.excepted else "FAIL")
        typer.echo(f"{mark} {place} ({result.seconds:.1f}s)")
        if result.excepted:
            typer.echo(f"       accepted deviation: {result.excepted}")
        for dimension in result.dimensions:
            if dimension.status == "skip":
                continue
            state = "ok  " if dimension.ok else "FAIL"
            typer.echo(
                f"       {state} {dimension.name:<24} "
                f"{dimension.reference_rows:>6} rows",
            )
            for difference in dimension.differences:
                typer.echo(
                    f"              {difference.column}: "
                    f"{difference.rows} rows -- {difference.detail}",
                )
    passed = sum(1 for result in results if result.ok)
    excepted = sum(1 for result in results if result.excepted)
    summary = f"\n{passed}/{len(results)} cities at parity"
    if excepted:
        summary += f", {excepted} within a documented deviation"
    typer.echo(summary)


def main(
    cities: Annotated[
        list[str] | None,
        typer.Argument(help="City names to validate. Defaults to the XS/S corpus."),
    ] = None,
    data_dir: common.DataDir = common.DEFAULT_DATA_DIR,
    results_dir: Annotated[
        pathlib.Path,
        typer.Option(help="Tree of SQL-pipeline results to compare against."),
    ] = pathlib.Path("results"),
    output_dir: Annotated[
        pathlib.Path,
        typer.Option(help="Where to write the new pipeline's results."),
    ] = pathlib.Path("results-parity"),
    sizes: Annotated[
        list[str] | None,
        typer.Option("--size", help="`test_size`s to validate. Defaults to XS and S."),
    ] = None,
    json_report: Annotated[
        pathlib.Path | None,
        typer.Option("--json", help="Also write the report as JSON."),
    ] = None,
    verbose: Annotated[
        int,
        typer.Option("--verbose", "-v", count=True, help="verbosity level"),
    ] = 0,
) -> None:
    """Validate the Python pipeline against the SQL pipeline's results."""
    root._verbose_callback(verbose)
    if sizes:
        corpus = read_corpus(sizes)
    elif cities:
        # A named city is looked up across every size, not just the default
        # corpus: `validate-parity valencia` has to reach an `XL` city.
        corpus = read_every_corpus_city()
    else:
        corpus = read_corpus(ITERATION_CORPUS)

    if cities:
        wanted = {city.casefold() for city in cities}
        corpus = [row for row in corpus if row["city"].casefold() in wanted]
        missing = wanted - {row["city"].casefold() for row in corpus}
        if missing:
            known = ", ".join(sorted(row["city"] for row in read_every_corpus_city()))
            message = (
                f"not in the corpus: {', '.join(sorted(missing))}."
                f" Known cities: {known}"
            )
            raise typer.BadParameter(message)

    results = [compare_city(row, data_dir, output_dir, results_dir) for row in corpus]
    report(results)
    if json_report:
        json_report.write_text(
            json.dumps(
                [dataclasses.asdict(result) for result in results],
                default=str,
                indent=2,
            ),
        )
    if not all(result.acceptable for result in results):
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
