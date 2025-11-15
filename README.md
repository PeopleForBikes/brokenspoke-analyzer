---
orphan: true
---

# Brokenspoke-analyzer

[![ci](https://github.com/PeopleForBikes/brokenspoke-analyzer/actions/workflows/ci.yaml/badge.svg)](https://github.com/PeopleForBikes/brokenspoke-analyzer/actions/workflows/ci.yaml)
[![Latest Version](https://img.shields.io/github/v/tag/PeopleForBikes/brokenspoke-analyzer?sort=semver&label=version)](https://github.com/PeopleForBikes/brokenspoke-analyzer/)
[![License](https://img.shields.io/badge/license-mit-blue.svg)](https://github.com/PeopleForBikes/brokenspoke-analyzer/blob/main/LICENSE)
[![Code of Conduct](https://img.shields.io/badge/code_of_conduct-🌐-ff69b4.svg?logoColor=white)](https://github.com/PeopleForBikes/brokenspoke-analyzer/blob/main/code-of-conduct.md)

The Brokenspoke Analyzer is a tool allowing the user to run the Bicycle Network
Analysis locally.

## Requirements

Install the software below only if using the native Python method for running
the Brokenspoke Analyzer as described under Quickstart.

- **docker**: [official page](https://www.docker.com/get-started/)
- **docker compose plugin V2**:
  [official page](https://docs.docker.com/compose/install/linux/)
- **osm2pgrouting 3**:
  [official page](https://pgrouting.org/docs/tools/osm2pgrouting.html#)
- **osm2pgsql**: [official page](https://osm2pgsql.org/doc/install.html)
- **osmconvert**: [OSM wiki](https://wiki.openstreetmap.org/wiki/Osmconvert)
- **osmium-tool**: [official page](https://osmcode.org/osmium-tool/)
- **psql**:
  [official page](https://www.postgresql.org/docs/current/app-psql.html)
- **postgis**:
  [official page](https://postgis.net/documentation/getting_started/#installing-postgis)

## Quickstart

There are 2 main ways to use the Brokenspoke Analyzer:

- All in Docker
- Native Python with the database running in a Docker container

The two methods are described in the sections below along with their advantages
and inconveniences.

For more details about the different ways to run an analysis and how to adjust
the options, please refer to the full documentation.

### All in Docker

The benefit of running everything using the provided Docker images, is that
there is no need to install any of the required dependencies, except Docker
itself. This guarantees that the user will have the right versions of the
multiple tools that are combined to run an analysis. This is the simplest and
recommended way for people who just want to run the analyzer.

Export the database URL:

```bash
export DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres
```

Start the database from Docker Compose, in the background:

```bash
docker compose up -d
```

And configure it:

```bash
docker run \
  --rm \
  --network brokenspoke-analyzer_default \
  -e DATABASE_URL \
  ghcr.io/peopleforbikes/brokenspoke-analyzer:2.6.5 \
  -vv configure custom 4 4096 postgres
```

**Remark: refer to the last section of this guide to find the optimal values for
your system**

Run the analysis:

```bash
docker run \
  --rm \
  --network brokenspoke-analyzer_default \
  -e DATABASE_URL \
  ghcr.io/peopleforbikes/brokenspoke-analyzer:2.6.5 \
  -vv run --no-cache "united states" "santa rosa" "new mexico" 3570670
```

Export the results:

```bash
docker run \
  --rm \
  --network brokenspoke-analyzer_default \
  -u $(id -u):$(id -g) \
  -v ./results:/usr/src/app/results \
  -e DATABASE_URL \
  ghcr.io/peopleforbikes/brokenspoke-analyzer:2.6.5 \
  -vv export local "united states" "santa rosa" "new mexico"
```

Clean up (required before attempting to run another analysis):

```bash
docker compose down
docker volume rm brokenspoke-analyzer_postgres
```

### Native w/ Database-only in Docker

This method gives you the most control, and is recommended if you intend to work
on the project.

Export the database URL:

```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
```

At this point, all the requirements must be installed locally. Otherwise the
brokenspoke-analyzer will not install.

Once all the tools are installed, the brokenspoke-analyzer can be installed. We
recommend using [uv] for installing the tool and working in a virtual
environment. Once you have [uv] set up:

```bash
git clone git@github.com:PeopleForBikes/brokenspoke-analyzer.git
cd brokenspoke-analyzer
uv sync --all-extras --dev
```

Run the analysis:

```bash
uv run bna run-with compose "united states" "santa rosa" "new mexico" 3570670
```

This command takes care of starting and stopping the PostgreSQL/PostGIS server,
running all the analysis commands, and exporting the results.

The data required to perform the analysis will be saved in
`data/santa-rosa-new-mexico-united-states`, and the results exported in
`results/united-states/new mexico/santa rosa/23.11`.

### Configure the database manually

In most cases, the brokenspoke-analyzer will auto-detect this information. But
sometimes the auto-detection might fail. Here are the commands that will help
retrieve the resource allocation values.

Get the number of vCPUs allocated to Docker:

```bash
docker info --format json | jq .NCPU
```

Get the amount of memory (in MB) allocated to Docker:

```bash
docker info --format json | jq .MemTotal | numfmt --to-unit=1M
```

And then run the command to configure the database with custom values:

```bash
uv run bna configure custom 4 4096 postgres
```

[uv]: https://docs.astral.sh/uv
