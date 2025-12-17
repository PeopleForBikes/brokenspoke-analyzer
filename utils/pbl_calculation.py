# utils/pbl_calculation.py
"""
This script identifies cycleways that should actually be classified as protected bike lanes.
Cycleways are assumed to be one-way unless explicitly tagged as one-way=no.
The total distance of protected bike lanes is calculated, and the distance is doubled for two-way lanes.
A shapefile of the cycleways, which includes the PBL flag, is exported, along with the total distance.
If a mileage.csv is created during the same run (using measure) of the brokenspoke-analyzer (by running bna-batch-pbl.py,
the miles of PBls is added into the mileage file. Otherwise, the PBL outputs will be created in a new folder.

Required inputs are country, region (state), and city. This script is specifically created with US cities in mind.
"""
from pathlib import Path
import subprocess
import geopandas as gpd
import numpy as np
import math
from shapely.geometry import LineString
from shapely.strtree import STRtree
from shapely.ops import nearest_points
import ast
import tempfile
from datetime import date
import typer
import pandas as pd
import warnings
import sys
import unicodedata

# Silence pandas SettingWithCopy
warnings.simplefilter("ignore", category=pd.errors.SettingWithCopyWarning)

# Silence pyogrio truncation warnings
warnings.filterwarnings(
    "ignore",
    message=".*has been truncated to 254 characters.*",
    category=RuntimeWarning,
)

app = typer.Typer(help="Compute Protected Bike Lanes (PBL) for a city.")

# Thresholds / parameters (tweakable)
roads_buffer_m = 100        # buffer around cycleway for candidate parallel roads (meters)
angle_threshold = 20        # allowed difference between cycleway angle and road angle at sample points (degrees)
distance_threshold = 10     # distance threshold between cycleway point and closest road point (meters)
fraction_threshold = 0.8    # fraction of sample points that must be within the distance threshold
n_sample_points = 30        # number of sample points to create


def sample_line(line, n):
    '''
    Generate `n` evenly spaced points along a LineString.

    Returns list of shapely Points or [] on invalid input.
    '''
    if line is None or line.is_empty or not isinstance(line, LineString):
        return []
    fractions = np.linspace(0, 1, n)
    return [line.interpolate(f, normalized=True) for f in fractions]


def parse_osm_tags(tag_str):
    '''
    Convert OpenStreetMap 'other_tags' string into a dictionary.
    '''
    if not tag_str or tag_str.strip() == "":
        return {}
    python_style = "{" + tag_str.replace('"=>"', '": "').replace('","', '", "') + "}"
    try:
        return ast.literal_eval(python_style)
    except Exception:
        return {}


def local_tangent_angle(sample_points, idx):
    '''
    Compute the tangent angle (degrees) at a sampled point.
    '''
    if idx < len(sample_points) - 1:
        p1, p2 = sample_points[idx], sample_points[idx + 1]
    else:
        p1, p2 = sample_points[idx - 1], sample_points[idx]
    dx, dy = p2.x - p1.x, p2.y - p1.y
    return math.degrees(math.atan2(dy, dx))


def road_tangent_angle(road_geom, pt, delta=1):
    '''
    Compute tangent angle for a road near pt by interpolating ±delta along the road.
    '''
    nearest_on_road = nearest_points(pt, road_geom)[1]
    d = road_geom.project(nearest_on_road)
    d1 = max(d - delta, 0)
    d2 = min(d + delta, road_geom.length)
    p1, p2 = road_geom.interpolate(d1), road_geom.interpolate(d2)
    return math.degrees(math.atan2(p2.y - p1.y, p2.x - p1.x))


def is_parallel(pt_angle, road_angle, angle_threshold):
    '''
    Return True if angles are within angle_threshold, treating 0 and 180 as equivalent.
    '''
    pa = pt_angle % 180
    ra = road_angle % 180
    angle_diff = min(abs(pa - ra), 180 - abs(pa - ra))
    return angle_diff <= angle_threshold


def slugify(name: str) -> str:
    """Lowercase and replace spaces with dashes."""
    name = name.replace(".","")
    return name.lower().replace(" ", "-")

def slugify_for_osm_file(name: str) -> str:
    """Removed special characters to match the osm file"""
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = text.replace("' ", "-")
    text = text.replace(" ", "-")
    text = text.replace(".", "")
    text = text.replace("'", "-")
    return text


def _calver_candidates(parent: Path, name_stem: str):
    """
    Return list of (path, suffix_int) for directories under parent that start with name_stem.
    Suffix is 0 for the exact name_stem (no suffix), otherwise integer parsed from final '.' part.
    """
    if not parent.exists():
        return []
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
                # ignore weird names
                continue
    return candidates


def get_calver_folder(base_dir: Path, country: str, region: str, city: str, batch_folder: Path | str | None = None) -> Path:
    """
    Return the folder where PBL outputs should be written.

    Behavior:
    - If batch_folder is provided, it is used as-is (and created if missing).
    - Otherwise create/find a calver folder like: <base_dir>/<country>/<region>/<city>/YY.MM
      If that base already exists, the next revision will be appended: .1, .2, etc.
      (This will NOT create a `.0`).
    """
    if batch_folder:
        bf = Path(batch_folder)
        bf.mkdir(parents=True, exist_ok=True)
        return bf

    today = date.today()
    name_stem = today.strftime("%y.%m")
    parent = base_dir / country / region / city

    # find existing candidates
    candidates = _calver_candidates(parent, name_stem)
    if not candidates:
        target = parent / name_stem
        target.mkdir(parents=True, exist_ok=True)
        return target

    # compute highest suffix, then choose next revision (max + 1)
    max_suffix = max(suffix for _, suffix in candidates)
    next_rev = max_suffix + 1
    target = parent / f"{name_stem}.{next_rev}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def compute_pbls(city: str, region: str, country: str = "united-states", data_dir: str | Path | None = None):
    """
    Compute PBLs for a given city/state. Returns (GeoDataFrame, total_miles).
    If no cycleways exist, returns an empty GeoDataFrame and 0.0 total_miles.
    """
    if data_dir is None:
        data_dir = Path("data")
    else:
        data_dir = Path(data_dir)

    slug = "-".join([slugify_for_osm_file(city), slugify_for_osm_file(region), slugify_for_osm_file(country)])
    input_file = data_dir / slug / f"{slug}.clipped.osm"
    if not input_file.exists():
        raise FileNotFoundError(f"Expected OSM input file not found: {input_file}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_highways = Path(tmpdir) / f"{slug}_highways.osm"
        cmd = [
            "osmfilter",
            str(input_file),
            "--keep=highway=",
            "--drop-relations",
            f"-o={tmp_highways}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"osmfilter failed: {result.stderr}")

        all_roads = gpd.read_file(tmp_highways, layer="lines")
        utm = all_roads.estimate_utm_crs()
        all_roads_proj = all_roads.to_crs(utm)

        cycleways = all_roads_proj[all_roads_proj["highway"] == "cycleway"]
        car_roads = all_roads_proj[
            ~all_roads_proj["highway"].isin(["cycleway", "footway", "pedestrian", "service", "path", "steps","track"])
        ]

    # empty-case: return empty gdf + 0 miles
    if cycleways.empty:
        empty_gdf = gpd.GeoDataFrame(
            columns=["PBL_flag", "fraction", "direction", "length_m", "length_adj", "geometry"],
            geometry="geometry",
            crs=all_roads_proj.crs
        )
        return empty_gdf, 0.0

    road_tree = STRtree(list(car_roads.geometry))

    for idx, row in cycleways.iterrows():
        tags = parse_osm_tags(row.get("other_tags", ""))

        # Skip definitely unsegregated shared paths
        if ((tags.get("pedestrian") in ["yes", "designated"] or tags.get("foot") in ["yes", "designated"])
                and tags.get("segregated") == "no"):
            cycleways.at[idx, "PBL_flag"] = False
            cycleways.at[idx, "fraction"] = 0.0
            continue

        sample_points = sample_line(row.geometry, n_sample_points)
        candidate_indices = road_tree.query(row.geometry, "dwithin", roads_buffer_m)
        candidate_gdf = car_roads.iloc[candidate_indices]

        distances = []
        for i, pt in enumerate(sample_points):
            pt_angle = local_tangent_angle(sample_points, i)
            parallel_candidates = []
            for rd in candidate_gdf.geometry:
                nearest_pt = nearest_points(pt, rd)[1]
                road_angle = road_tangent_angle(rd, nearest_pt)
                if is_parallel(pt_angle, road_angle, angle_threshold):
                    parallel_candidates.append(nearest_pt)
            d = min((pt.distance(p) for p in parallel_candidates), default=None)
            distances.append(d)

        fraction_close = sum(d <= distance_threshold for d in distances if d is not None) / len(distances) if distances else 0.0
        cycleways.at[idx, "fraction"] = fraction_close
        cycleways.at[idx, "PBL_flag"] = fraction_close >= fraction_threshold

        if cycleways.at[idx, "PBL_flag"]:
            direction = "one-way"
            if tags.get("oneway") == "no" or tags.get("cycleway:oneway") == "no" or tags.get("cycleway:oneway:bicycle") == "no":
                direction = "two-way"
            if tags.get("cycleway:both") in ["track", "separate"]:
                direction = "two-way"
            cycleways.at[idx, "direction"] = direction

    # length fields
    cycleways["length_m"] = cycleways.geometry.length
    cycleways["length_adj"] = cycleways.apply(
        lambda r: r["length_m"] * 2 if r.get("direction") == "two-way" else r["length_m"], axis=1
    )

    total_pbl_length_m = cycleways.loc[cycleways["PBL_flag"], "length_adj"].sum()
    total_pbl_length_miles = total_pbl_length_m / 1609.344
    return cycleways, total_pbl_length_miles


@app.command()
def main(
    city: str,
    region: str,
    country: str,
    data_dir: str = None,
    output_dir: str = None,
    batch_folder: str = None,  # always a string
):
    if data_dir is None:
        data_dir = Path("data")
    else:
        data_dir = Path(data_dir)

    if output_dir is None:
        output_dir = Path("results")
    else:
        output_dir = Path(output_dir)

    if batch_folder is not None:
        batch_folder = Path(batch_folder)  # convert string to Path

    print(f"Computing PBLs in {city}, {region}...")

    df, total_length = compute_pbls(city, region, country, data_dir)

    calver_folder = get_calver_folder(output_dir, country, region, city, batch_folder=batch_folder)

    # Ensure output dir exists
    calver_folder.mkdir(parents=True, exist_ok=True)

    slug = "-".join([slugify(city), slugify(region), slugify(country)])
    shapefile_path = calver_folder / f"{slug}_pbl.shp"
    # Make sure folder exists before writing shapefile (prevents CPLE_AppDefinedError)
    shapefile_path.parent.mkdir(parents=True, exist_ok=True)

    # Write shapefile (if df empty, geopandas will still write a valid empty shapefile)
    df.to_file(shapefile_path)
    print(f"Saved PBL shapefile to {shapefile_path}")

    # If mileage.csv exists, append total PBL length
    mileage_file = calver_folder / "mileage.csv"

    if mileage_file.exists():
        if total_length > 0:
            df_mileage = pd.read_csv(mileage_file)
            df_mileage = pd.concat([
                df_mileage,
                pd.DataFrame([{'feature_type': 'pbl', 'total_mileage': total_length}])
            ], ignore_index=True)
            df_mileage.to_csv(mileage_file, index=False)
            print(f"Updated mileage.csv with total PBL distance: {total_length} miles")
        else:
            print("No PBL distance found; mileage.csv left unchanged")
    else:
        if total_length > 0:
            df_mileage = pd.DataFrame([{'feature_type': 'pbl', 'total_mileage': total_length}])
            df_mileage.to_csv(mileage_file, index=False)
            print(f"Created new mileage.csv with total PBL distance: {total_length} miles")
        else:
            print("No PBL distance found; no mileage.csv created")

   


if __name__ == "__main__":
    app()
