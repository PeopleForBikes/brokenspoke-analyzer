# Brokenspoke-analyzer

[![ci](https://github.com/PeopleForBikes/brokenspoke-analyzer/actions/workflows/ci.yaml/badge.svg)](https://github.com/PeopleForBikes/brokenspoke-analyzer/actions/workflows/ci.yaml)
[![Latest Version](https://img.shields.io/github/v/tag/PeopleForBikes/brokenspoke-analyzer?sort=semver&label=version)](https://github.com/PeopleForBikes/brokenspoke-analyzer/)
[![License](https://img.shields.io/badge/license-mit-blue.svg)](https://github.com/PeopleForBikes/brokenspoke-analyzer/blob/main/LICENSE)
[![Code of Conduct](https://img.shields.io/badge/code_of_conduct-🌐-ff69b4.svg?logoColor=white)](https://github.com/PeopleForBikes/brokenspoke-analyzer/blob/main/code-of-conduct.md)

The Brokenspoke Analyzer is a tool allowing the user to run “Bicycle Network
Analysis” locally.

## Requirements

- **docker**: [get started](https://www.docker.com/get-started/)
- **osmium**: [official page](https://osmcode.org/osmium-tool/)

### pfb-network-connectivity Docker image

Azavea provides the code to build the Docker image that is used to run an
analysis. There is no Image directly available at the time, thus it will be
necessary to build it manually, or pull it from an unofficial source.

#### Pull the image from an unofficial repository

There is no official `azavea/pfb-network-connectivity` docker repository (yet
🤞), but it is possible to pull the image from an unofficial one, and rename it
to the expected name. Please note that this image was built for the
`linux/amd64` platform.

```bash
docker pull rgreinho/pfb-network-connectivity:0.18.0
docker tag rgreinho/pfb-network-connectivity:0.18.0 azavea/pfb-network-connectivity:0.18.0
```

#### Build the Azavea docker image

Build the docker image from the latest tag.

```bash
git clone git@github.com:azavea/pfb-network-connectivity.git
cd pfb-network-connectivity
git checkout tags/0.18.0 -b 0.18.0
cd src/
docker buildx build -t azavea/pfb-network-connectivity:0.18.0 -f analysis/Dockerfile .
```

## Install

We recommend creating a virtual environment:

```bash
cd /tmp
mkdir brokenspoke-analyzer
cd brokenspoke-analyzer
python3 -m venv .venv
source .venv/bin/activate
```

Then, installing the tool from GitHub directly:

```bash
pip install git+https://github.com/PeopleForBikes/brokenspoke-analyzer@1.2.1
```

This will add a new command named `bna`.

### From source

If you are interested in using the source code from this repository directly,
you can execute the following instructions instead (note that
[poetry](https://python-poetry.org/) will be required):

```bash
git clone git@github.com:PeopleForBikes/brokenspoke-analyzer.git
cd brokenspoke-analyzer
git switch -c 1.2.1
poetry install
```

For more information about using the source code, please refer to the
[contributing](CONTRIBUTING.md) page.

## Quickstart

To run an analysis, the tools needs 2 parameters:

- The name of the country or dataset where the city is located.
- The name of the city.

Then simply run the tool, and all the steps will be performed automatically:

```bash
$ bna run arizona flagstaff
[17:00:55] Boundary files ready.
Downloaded Protobuf data 'arizona-latest.osm.pbf' (204.86 MB) to:
'data/arizona-latest.osm.pbf'
[17:07:21] OSM Region file downloaded.
           OSM file for flagstaff ready.
           Analysis for flagstaff complete.
```
