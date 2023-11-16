# About

The Brokenspoke-Analyzer is an open source tool that streamlines running People
for Bikes' “Bicycle Network Analysis” locally and on cloud resources. For the
user, it simplifies the process of preparing datasets, setting up PostGIS
databases, running analyses, and exporting results through a command line
interface (CLI).

## How does it work?

An analysis is composed of a few steps:

1. Collect the data required for the analysis
2. Import the data into a database
3. Run the computation on the data
4. Export the results to usable formats, like Shapefile, GeoJSON or CSV

The brokenspoke-analyzer acts as a sort of orchestrator. The heavy lifting is
done by PostgreSQL/PostGIS. Step 3 is where most of the magic happens. The
computation part is done by running hundreds of SQL queries against PostGIS.

The CLI allows the user to run all steps, or just some of them depending on the
user's needs.

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

## Using the Docker Compose environment

Using Docker Compose is just a simpler way to run the PostGIS container with the
right parameters (environment variables, network, volume, etc.) and the required
extensions.

A
[Docker Compose file](https://github.com/PeopleForBikes/brokenspoke-analyzer/blob/main/compose.yml)
is provided with this project to simplify the setup.

To start it, retrieve the manifest file and compose up:

```bash
mkdir -p /tmp/bna
cd /tmp/bna
curl -sLO https://raw.githubusercontent.com/PeopleForBikes/brokenspoke-analyzer/main/compose.yml
docker compose up
```

## Using brokenspoke-analyzer in the docker container

Installing all the required GIS tool can be a complicated task, especially on
Windows platforms.

For this reason, we provide a Docker container that be used instead of the
native tools.

Here is an example depicting how to use it:

Start by exporting the `DATABASE_URL` environment variable:

```bash
export DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres
```

Then run each command using the container:

```bash
# The `configure docker` command does not work from the container because it
# needs to connect to the host to get the info.
# Use `docker info` to get the `CPUs` and `Total Memory` values and configure the
# database using the `configure custom` command accordingly.
docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0 configure custom 4 1943 postgres
docker run --rm -u $(id -u):$(id -g) -v ./data/container:/usr/src/app/data ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0 prepare all usa "santa rosa" "new mexico" 3570670 --output-dir /usr/src/app/data
docker run --rm --network brokenspoke-analyzer_default -v ./data/container:/usr/src/app/data -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0 import all usa "santa rosa" "new mexico" 3570670 --input-dir /usr/src/app/data/santa-rosa-new-mexico-usa
docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0 compute usa "santa rosa" "new mexico" --input-dir /usr/src/app/data/santa-rosa-new-mexico-usa
```

Or with the `run` command:

```bash
docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0 -vv run usa "santa rosa" "new mexico" 3570670
docker run --rm --network brokenspoke-analyzer_default -u $(id -u):$(id -g) -v ./results:/usr/src/app/results -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0  -vv export local usa "santa rosa" "new mexico"
```

## Using an existing database instance

If you would prefer to use an existing database, there is no problem with that.

Here are the requirements:

- PostgreSQL 13+
- PostGIS 3.1+
- Pgrouting
- Plpython3
- Enable the `uuid-ossp` and `plpython3u` extensions.
- Create the `generated`, `received` and `scratch`, schemas and make sure the
  user has the authorization to access them

The brokenspoke-analyzer also provides the `configure` command to assist you
with the configuration. Refer to the [configure](./commands.md#configure)
section in the command page to get more help.
