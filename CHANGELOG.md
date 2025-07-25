# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning].

## [Unreleased]

## [2.6.2] - 2025-07-23

### Fixed

- Excluded golf courses paths from bicycle infrastructure. [#889]

[#889]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/870
[2.6.2]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.6.2

## [2.6.1] - 2025-06-29

### Fixed

- Fixed a bug preventing to export the results in some cases. [#883]

[#883]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/883
[2.6.1]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.6.1

## [2.6.0] - 2025-06-18

### Fixed

- Removed unused columns and indices in `neighborhood_connected_census_blocks`
  table. [#824]
- Fixed normalizing country name before building location slug in compute
  command. [#851]
- Fixed the calver algorithm to handle more than 10 revisions. [#856]
- Fixed issues preventing running cities in Malaysia. [#864]

### Changed

- Used new format for street parking tagging. [#807]
- Excluded ways with access=private or have access=no and do no explicitly allow
  bicycles. [#847]

### Added

- Added cache folder for downloads. [#842]
- Added ability to run partial analysis. [#845]
- Added ability to compute bike lane mileage. [#831] [#870]

### External contributor(s)

- [@mitchellhenke](https://github.com/mitchellhenke)

[#807]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/807
[#824]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/824
[#831]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/831
[#842]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/842
[#845]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/845
[#847]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/847
[#851]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/851
[#856]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/856
[#864]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/864
[#870]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/870
[2.6.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.6.0

## [2.5.0] - 2025-03-22

### Fixed

- Water blocks where not being deleted. [#832]
- `--export-dir` option was ignored. [#820]

### Changed

- Updated `width` calculation logic. [#800]

### Added

- Added the ability to use a development container for local development. [#718]

[#718]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/718
[#800]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/800
[#820]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/820
[#832]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/832
[2.5.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.5.0

## [2.4.0] - 2024-11-13

### Fixed

- Prevent database tables from being moved incorrectly. [#727]
- Extra dependencies were not being installed in the Docker image. [#729]

### Added

- Update the Docker Compose file to use PostgreSQL 17 and PostGIS 3.4. [#724]
- Export all tables as GeoJSON. [#726]

[#724]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/724
[#726]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/726
[#727]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/727
[#729]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/729
[2.4.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.4.0

## [2.3.0] - 2024-09-17

### Fixed

- Fixed table name in census block calculations. [#648]

### Changed

- Added indexes for intersection_to and intersection_from on neighborhood_ways.
  [#654]
- Reduced size of connected roads tables and indexes. [#660]

### New contributor(s)

A warm welcome and big thank you to our new contributor(s) for this release:

- [@mitchellhenke](https://github.com/mitchellhenke)

Thank you for joining our community and making a difference!

[#648]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/648
[#654]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/654
[#660]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/660
[2.3.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.3.0

## [2.2.1] - 2024-07-06

### Fixed

- Fixed the Docker image. [#652]

[#652]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/652
[2.2.1]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.2.1

## [2.2.0] - 2024-07-06 [YANKED]

### Added

- Added the ability to bundle the results. [#617]

[#617]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/617
[2.2.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.2.0

## [2.1.2] - 2024-05-14

### Fixed

- Added missing parameter to the `run` command. [#603]

[#603]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/603
[2.1.2]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.1.2

## [2.1.1] - 2024-03-16

This is a release to fix the release workflows.

[2.1.1]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.1.1

## [2.1.0] - 2024-03-16

### Added

- Added a new CLI sub-command to export results to a custom S3 bucket. [#518]

### Changed

- Updated dentists, doctors, hospitals, pharmacies, retail, and schools to
  incorporate alternate or new OSM tags. [#542]

[#518]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/518
[#542]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/542
[2.1.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.1.0

## [2.0.0] - 2024-02-19

We are incredibly proud to announce the release of version 2.0.0 of the
brokenspoke-analyzer, a significant milestone marking a comprehensive overhaul
of the original Bicycle Network Analyzer.

In the process of rewriting the original tool, and incorporating it into the
brokenspoke-analyzer, a myriad of changes and improvements were implemented to
enhance its functionality and performance.

However, given the extensive nature of these modifications, providing a detailed
changelog for every feature proved impractical and overwhelming.

Instead, the decision was made to focus on the overarching shift from Bash to
Python in the changelog, emphasizing the fundamental improvements and the
migration to a more robust programming language.

Moving forward, a commitment has been made to maintain a comprehensive and
up-to-date changelog, ensuring that all future enhancements and features will be
meticulously documented to provide transparency and facilitate user
understanding.

[2.0.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.0.0

## [2.0.0-alpha] - 2023-09-16

### Added

- Add Python scripts for importing data into database and configuring database.
  [#265]
- Enable MyPy to ensure coherence between the various parameters passed from the
  command line to the core modules. [#282]
- Add Python scripts for computing the analysis. [#291]
- Add Python scripts for exporting the results of the analysis using the calver
  naming scheme. [#294]
- Add the capability to package the application as a Docker container. [#301]
- Add the `run` sub-command. [#305]
- Add the `run-with` sub-command. [#310]
- Add the `run-with compare` sub-command. [#315]
- Add end-to-end testing for comparing the results between the brokenspokespoke
  analyzer and the original BNA. [#316]
- Add a new CI workflow to run end-to-end tests. [#321]
- Add a feature to validate downloaded PBF OpenStreetMap files using md5
  checksums and gzip files using the `gzip` package. [#329]

### Changed

- Update and reorganize the CLI. [#274]
- Update the documentation. [#330]

### Fixed

- Various SQL-related fixes. [#320]

[#265]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/265
[#274]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/274
[#282]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/282
[#291]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/291
[#294]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/294
[#301]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/301
[#305]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/305
[#310]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/310
[#315]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/315
[#316]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/316
[#320]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/320
[#321]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/321
[#329]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/329
[#330]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/330
[2.0.0-alpha]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/2.0.0-alpha

## [1.3.0] - 2023-08-20

### Added

- Add an option to name the container running the analysis. [#215]
- Add a dataset to represent California. [#223]
- Add a CLI flag to specify the city FIPS code. [#240]
- Add capability to retry and cleanup partial downloads. [#272]

### Changed

- Replaced GDAL dependency with pandas. [#259]

### Fixed

- Bind the `population.zip` file to the internal `/data` directory. [#211]
- Ensure the boundary shapefile encoding is UTF-8. [#212]
- Fix the logic to retrieve the state information. [#213]
- Sanitize variables passed to the Docker container. [#214]
- Ensure the District of Columbia is considered as a US state. [#220]
- Ensure regions use only ASCII characters. [#225]
- Use mph for the default speed limit instead of km/h. [#239]

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
[#259]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/259
[#272]: https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/272
[1.3.0]:
  https://github.com/PeopleForBikes/brokenspoke-analyzer/releases/tag/1.3.0

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
[Semantic Versioning]: https://semver.org/spec/v2.0.0.html
