# Brokenspoke-analyzer

The Brokenspoke Analyzer is a tool allowing the user to run “Bicycle Network
Analysis”

## Requirements

- **docker**: [get started](https://www.docker.com/get-started/)
- **osmosis**: [official page](https://osmcode.org/osmium-tool/)

### Build the Azavea docker image

Azavea provides the code to build the Docker image that is used to run an
analysis. There is no Image directly available at the time, thus it will
necessary to build it manually.

```bash
git clone git@github.com:azavea/pfb-network-connectivity.git
cd pfb-network-connectivity/src/
DOCKER_BUILDKIT=1 docker build -t azavea/analyzer:13-3.1 -f analysis/Dpckerfile
```

### US Census API key

- Go to <https://api.census.gov/data/key_signup.html> to request a census API key.
- Export the `CENSUS_API_KEY` variable:

  ```bash
  export "CENSUS_API_KEY=7ff372e9483f5d8d60d7fd1bf0ec6f6b5997aa86"
  ```

## Install

Install the tool from GitHub directly:

```bash
pip install git+https://github.com/PeopleForBikes/brokenspoke-analyzer
```

This will add a new command named `bna`.

## Quickstart

To run an analysis, the tools needs 3 parameters:

- The name of the state.
- The name of the city.
- The OSM Relation of ID of the city.
  - The exaplanations to find the OSM relation of the city can be found on
    [James Chevalier'page](https://github.com/JamesChevalier/cities#how-to-get-the-poly-file-for-a-specific-city=)

Then simply run the tool, and all the steps will be performed automatically:

```bash
$ bna run arizona flagstaff 110844
[18:50:14] US Census file downloaded.
[18:50:15] Boundary file ready.
           Regional OSM file downloaded.
[18:50:16] Polygon file downloaded.
           OSM file for flagstaff ready.
           Analysis for flagstaff arizona complete.
```

> **Be Aware that running an analysis can take several hours!**
