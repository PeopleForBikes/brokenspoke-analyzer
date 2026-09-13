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

The analysis runs entirely in Python -- **no database, no Docker required**.
Install the software below only if using the native Python method for running
the Brokenspoke Analyzer as described under Quickstart.

- **just**:
  [official page](https://github.com/casey/just?tab=readme-ov-file#installation)
- **osmconvert**: [OSM wiki](https://wiki.openstreetmap.org/wiki/Osmconvert)
- **osmium-tool**: [official page](https://osmcode.org/osmium-tool/)
- **uv**:
  [official page](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)

### Homebrew

OSX users can use `homebrew` to install all the requirements:

```bash
brew install just osmium-tool osmctools uv
```

## Quickstart

There are 2 main ways to use the Brokenspoke Analyzer:

- All in Docker
- Native Python

The two methods are described in the sections below along with their advantages
and inconveniences.

For more details about the different ways to run an analysis and how to adjust
the options, please refer to the full documentation.

### All in Docker

The benefit of running everything using the provided Docker image is that there
is no need to install any of the required dependencies, except Docker itself.
This guarantees that the user will have the right versions of the tools that are
combined to run an analysis. This is the simplest and recommended way for people
who just want to run the analyzer.

Run the analysis, mounting a directory to collect the results:

```bash
docker run \
  --rm \
  -u $(id -u):$(id -g) \
  -v ./results:/usr/src/app/results \
  ghcr.io/peopleforbikes/brokenspoke-analyzer:latest \
  -vv run "united states" "santa rosa" "new mexico" 3570670
```

That single command downloads the data, runs the whole analysis, and writes the
results. There is nothing to start beforehand and nothing to clean up
afterwards.

### Native Python

This method gives you the most control, and is recommended if you intend to work
on the project.

All the requirements above must be installed locally. Otherwise the
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
uv run bna run "united states" "santa rosa" "new mexico" 3570670
```

This command takes care of downloading the data, running every analysis stage,
and exporting the results.

The data required to perform the analysis will be saved in
`data/santa-rosa-new-mexico-united-states`, and the results exported in
`results/united states/new mexico/santa rosa/<version>/`.

[uv]: https://docs.astral.sh/uv
