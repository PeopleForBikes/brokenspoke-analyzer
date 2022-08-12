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

There is no official `azavea/pfb-network-connectivity` repository (yet 🤞), but
it is possible to pull the image from an unofficial one, and rename it to the
expected name.

```bash
docker pull rgreinho/pfb-network-connectivity:0.16
docker tag rgreinho/pfb-network-connectivity:0.16 azavea/pfb-network-connectivity:0.16
```

#### Build the Azavea docker image

The official repository does not have tags (yet 🤞), therefore the image must be
built from a fork.

```bash
git clone git@github.com:rgreinho/pfb-network-connectivity.git
cd pfb-network-connectivity
git checkout tags/0.16 -b 0.16
cd src/
DOCKER_BUILDKIT=1 docker build -t azavea/pfb-network-connectivity:0.16 -f analysis/Dockerfile .
```

## Install

Install the tool from GitHub directly:

```bash
pip install git+https://github.com/PeopleForBikes/brokenspoke-analyzer
```

This will add a new command named `bna`.

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
