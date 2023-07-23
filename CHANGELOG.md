# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## Added

- Add an option to name the container running the analysis. [#215]
- Ensure the District of Columbia is considered as a US state. [#220]
- Add a dataset to represent California. [#223]
- Add a CLI flag to specify the city FIPS code. [#240]

## Fixed

- Bind the `population.zip` file to the internal `/data` directory. [#211]
- Ensure the boundary shapefile encoding is UTF-8. [#212]
- Fix the logic t0 retrieve the state information. [#213]
- Sanitize variables passed to the Docker container. [#214]
- Ensure regions use only ASCII characters. [#225]
- Use mph for the default speed limite instead of km/h. [#239]

[#211]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/211
[#212]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/212
[#213]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/213
[#214]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/214
[#215]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/215
[#220]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/220
[#223]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/223
[#225]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/225
[#239]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/239
[#240]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/240

## [1.2.1] - 2023-06-18

### Fixed

- Fix the Geofabrik downloader for Spain. [#205]
- Adjust synthetic population shapefile name. [#206]

[#205]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/205
[#206]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/206
[1.2.1]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.2.1

## [1.2.0] - 2023-06-14

### Added

- Update the `bna prepare` command to fetch all the required files even for US
  cities. [#192]

[#192]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/192

### Fixed

- Fix BNA run parameters in case the target is a US city. [#152]
- Fix invalid CLI arguments for the `bna prepare` command. [#190]
- Fix the `output_dir` option of the `bna prepare` command. [#191]

[#152]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/152
[#190]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/190
[#191]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/191
[1.2.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.2.0

## [1.1.0] - 2022-10-08

### Fixed

- Add better support for international cities. [#52]

### Changed

- Updated the analyzer image to 0.16.1. [#52]

[#52]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/52
[1.1.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.1.0

## [1.0.0] - 2022-08-14

First stable version.

[1.0.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.0.0

## [1.0.0-rc.1] - 2022-08-07

This is the first usable release. It is possible to run analysis for any city in
the world (although the analyzer will fail for some of them).

The tool is still a bit rough on the edges, that is why this is a release
candidate, but the quirks will be ironned out for 1.0.0.

[1.0.0-rc.1]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.0.0-rc.1
