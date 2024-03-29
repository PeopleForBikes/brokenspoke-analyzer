# Brokenspoke-analyzer

[![ci](https://github.com/PeopleForBikes/brokenspoke-analyzer/actions/workflows/ci.yaml/badge.svg)](https://github.com/PeopleForBikes/brokenspoke-analyzer/actions/workflows/ci.yaml)
[![Latest Version](https://img.shields.io/github/v/tag/PeopleForBikes/brokenspoke-analyzer?sort=semver&label=version)](https://github.com/PeopleForBikes/brokenspoke-analyzer/)
[![License](https://img.shields.io/badge/license-mit-blue.svg)](https://github.com/PeopleForBikes/brokenspoke-analyzer/blob/main/LICENSE)
[![Code of Conduct](https://img.shields.io/badge/code_of_conduct-🌐-ff69b4.svg?logoColor=white)](https://github.com/PeopleForBikes/brokenspoke-analyzer/blob/main/code-of-conduct.md)

The Brokenspoke Analyzer is a tool allowing the user to run “Bicycle Network
Analysis” locally.

## Requirements

- **docker**: [official page](https://www.docker.com/get-started/)
- **docker compose plugin V2**:
  [official page](https://docs.docker.com/compose/install/linux/)
- **osmium**: [official page](https://osmcode.org/osmium-tool/)
- **osm2pgrouting**:
  [official page](https://pgrouting.org/docs/tools/osm2pgrouting.html#)
- **osm2pgsql**: [official page](https://osm2pgsql.org/doc/install.html)
- **osmconvert**: [OSM wiki](https://wiki.openstreetmap.org/wiki/Osmconvert)
- **osmium-tool**: [official page](https://osmcode.org/osmium-tool/)
- **psql**:
  [official page](https://www.postgresql.org/docs/current/app-psql.html)
- **postgis**:
  [official page](https://postgis.net/documentation/getting_started/#installing-postgis)

## Quickstart

We recommend using [Poetry](https://python-poetry.org/) for installing the tool
and working in a virtual environment. Once you have Poetry set up:

```bash
git clone git@github.com:PeopleForBikes/brokenspoke-analyzer.git
cd brokenspoke-analyzer
poetry install
```

Activate the virtual environment in the cloned folder by using:

```bash
source .venv/bin/activate
```

The simplest way to run an analysis is to use docker compose.

```bash
bna run-with compose usa "santa rosa" "new mexico" 3570670
```

This command takes care of starting and stopping the PostgreSQL/PostGIS server,
running all the analysis commands, and exporting the results.

The data required to perform the analysis will be saved in
`data/santa-rosa-new-mexico-usa`, and the results exported in
`results/usa/new mexico/santa rosa/23.11`.

For more details about the different ways to run an analysis and how to adjust
the options, please refer to the full documentation.
