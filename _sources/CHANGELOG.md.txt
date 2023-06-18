# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.2.1] - 2023-06-18

### Fixed

- Fix the Geofabrik downloader for Spain. [#205]
- Adjust synthetic population shapefile name. [#206]

[#205]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/205
[#206]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/206
[1.2.1]: https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.2.1

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
[1.2.0]: https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.2.0

## [1.1.0] - 2022-10-08

### Fixed

- Add better support for international cities. [#52]

### Changed

- Updated the analyzer image to 0.16.1. [#52]

[#52]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/52
[1.1.0]: https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.1.0

## [1.0.0] - 2022-08-14

First stable version.

[1.0.0]: https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.0.0

## [1.0.0-rc.1] - 2022-08-07

This is the first usable release. It is possible to run analysis for any city in
the world (although the analyzer will fail for some of them).

The tool is still a bit rough on the edges, that is why this is a release
candidate, but the quirks will be ironned out for 1.0.0.

[1.0.0-rc.1]: https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.0.0-rc.1
