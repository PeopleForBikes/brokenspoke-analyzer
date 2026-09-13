# About

The Brokenspoke-Analyzer is an open source tool that streamlines running People
for Bikes' “Bicycle Network Analysis” locally and on cloud resources. For the
user, it simplifies the process of preparing datasets, running analyses, and
exporting results through a command line interface (CLI).

## How does it work?

An analysis is composed of a few steps:

1. Collect the data required for the analysis
2. Run the computation on the data
3. Export the results to usable formats, like Shapefile, GeoJSON or CSV

Step 2 is where most of the magic happens. The computation runs entirely in
Python -- `geopandas` for the spatial work and `networkx` for the routing -- so
an analysis needs no database and no Docker. Earlier versions ran hundreds of
SQL queries against PostGIS; that implementation was migrated to Python and
removed.

The CLI allows the user to run all steps, or just the data collection, depending
on the user's needs.

The architecture of the “Bicycle Network Analysis” is shown below. However, not
all components are necessarily active all the time. Some components are only
created for certain steps.

```{figure} _static/brokenspoke-analyzer-architecture.svg
:alt: Brokenspoke-analyzer Architecture
:width: 800px
:align: center

Brokenspoke-analyzer Architecture, commands shown in **bold**.
```

In the **prepare** step shown in the diagram, the data required for the analysis
includes:

- City Boundary Shapefile: The bicycle network analysis is limited to the area
  described in this Shapefile.
- City Boundary GeoJSON: A copy of the City Boundary Shapefile in GeoJSON
  format.
- OSM region file: OSM region file obtained from
  [Geofabrik](https://download.geofabrik.de/) or
  [BBike](https://download.bbbike.org/osm/bbbike). This typically corresponds to
  the first-level administrative division of a country (state in the USA,
  autonomous community in Spain, province in Canada, etc.).
- OSM city file: A clipping of the OSM region corresponding to the area within
  the city boundary. This file is generated using
  [Osmium Tool](https://osmcode.org/osmium-tool/) and the bicycle network
  analysis runs on this geographic area.
- Census data: Population and employment data required for the analysis.
- Speed limit data: Region and city roadway speed limit data required for the
  analysis.

More information on the **prepare** step and the data required is available in
{doc}`workflow`.

## Where to find the FIPS codes

FIPS codes (Federal Information Processing Series) in the BNA are 7-digit codes
which are a combination of a State FIPS code (2-digit) and a Place FIPS code
(5-digit).

For example Austin, TX FIPS code is `4805000`, where `48` is for the state of
Texas and `05000` for Austin city.

The State and Place FIPS codes can be found on the US census website:
<https://www.census.gov/library/reference/code-lists/ansi.html#place>

The full 7-digit number can also be found in the census place files in the
`GEOID` column.

### Remark

A portion of cities are defined by the census as county sub units instead of
places. These tend to be in eastern states. Unfortunately, those FIPS codes (or
rather the GEOID column) are 10 digits instead of 7: state (2-digit) + county
(3-digit) + county sub (5-digit).

In order to get them to match the Place codes for the BNA, which only allows 7
digits, the county value is removed.

So for Darien, CT, for example, the GEOID is 0919018850, but its entry in the
BNA will be `0918850`.

## Using brokenspoke-analyzer in the docker container

Installing the GIS tools can be a complicated task, especially on Windows
platforms. For this reason, we provide a Docker container that can be used
instead of the native tools.

Collect the data and run the analysis in one command, mounting a directory to
collect the results:

```bash
docker run --rm -u $(id -u):$(id -g) -v ./results:/usr/src/app/results \
  ghcr.io/peopleforbikes/brokenspoke-analyzer:latest \
  -vv run "united states" "santa rosa" "new mexico" 3570670
```

To keep the downloaded data between runs, mount the data directory too and pass
`--skip-prepare` on subsequent runs:

```bash
docker run --rm -u $(id -u):$(id -g) \
  -v ./data:/usr/src/app/data -v ./results:/usr/src/app/results \
  ghcr.io/peopleforbikes/brokenspoke-analyzer:latest \
  -vv run --skip-prepare "united states" "santa rosa" "new mexico" 3570670
```
