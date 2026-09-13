# Commands

## General information

The analysis runs entirely in Python: there is no database to configure and no
environment variable is required. All the commands follow a very similar
pattern, therefore they use almost all the same parameters accross the board.

## Environment variables

- **BNA_OSMNX_CACHE**: Set it to 0 to disable the OSMNX cache.

  This is useful when used in an ephemeral environment where there is no real
  benefit of caching the downloads.

## Prepare

Prepare all the input files required for an analysis.

```bash
bna prepare [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

For US cities, the full name of the state as well as the city FIPS code are
required:

```bash
bna prepare "united states" "santa rosa" "new mexico" 3570670
```

For non US cities, only the name and the country are required:

```bash
bna prepare malta valletta
```

However, specifying a region can speed up the process since it will reduce the
size of the map to download. For instance this command will download the map of
the province of Québec in Canada. If `québec` was omitted, it would download the
map of the full country instead.

```bash
bna prepare canada "ancienne-lorette" québec
```

For non US cities, the FIPS code is always ignored.

By default the files will be saved in their own sub-directory in the `./data`
directory, relative to where the command was executed. This can be changed with
the `--data-dir` option flag.

For the 3 previous examples, the files will be located in:

```bash
data
├── ancienne-lorette-quebec-canada
├── santa-rosa-new-mexico-united-states
└── valletta-malta
```

All of this should already be enough to gather the information required to
perform an analysis, but a few more knobs are available to override the default
values in the options.

### options

- `--block-population` _block-population_
  - Population of a synthetic block for non-US cities.

    Defaults to 100.

- `--block-size` _block-size_
  - Size of a synthetic block for non-US cities (in meters).

    Defaults to 500.

- `--cache-dir` _cache-dir_
  - Path to the custom cache directory.

    Defaults to `./data`.

    When sets, it replaces the default user cache directory (platform specific,
    see [bna cache dir](#cache)).

- `--city-speed-limit` _city-speed-limit_

- Override the default speed limit (in mph).

  Defaults to 30.

- `--data-dir` _data-dir_
  - Directory where to store the files required for the analysis.

    Defaults to `./data`.

- `--lodes-year` _lodes-year_
  - Year to use to retrieve US job data.

    Defaults to 2022.

- `--mirror` _mirror_
  - Use a mirror to fetch the US census files.

    Defaults to `None`, meaning it fetches the data from the US census sites.

- `--no-cache`
  - Disable the cache folder.

    Defaults to `False`.

- `--retries` _retries_
  - Number of times to retry downloading files.

    Defaults to 2.

- `--worldpop-year` _worldpop-year_
  - Year to use to retrieve WorldPop data for international cities.

    Defaults to the current year.

## Run

Run the full analysis in one command.

```bash
bna run [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

This is the end-to-end entry point: it downloads the data, runs every analysis
stage in-process, and exports the results. No database, no Docker, nothing to
start beforehand.

Pass `--skip-prepare` to re-run the analysis against files already downloaded
into the data directory.

```bash
bna run "united states" "santa rosa" "new mexico" 3570670
```

### options

- `--block-population` _block-population_
  - Population of a synthetic block for non-US cities.

    Defaults to 100.

- `--block-size` _block-size_
  - Size of a synthetic block for non-US cities (in meters).

    Defaults to 500.

- `--buffer` _buffer_
  - Define the buffer area

    Defaults to 2680.

- `--cache-dir` _cache-dir_
  - Path to the custom cache directory.

    When sets, it replaces the default user cache directory (platform specific,
    see [bna cache dir](#cache)).

- `--city-speed-limit` _city-speed-limit_ <
  - Override the default speed limit (in mph).

    Defaults to 30.

- `--data-dir` _data-dir_
  - Directory where to store the files required for the analysis.

    Defaults to `./data`.

- `--skip-prepare`
  - Skip the download step and analyse the files already in the data directory.

- `--lodes-year` _lodes-year_ <
  - Year to use to retrieve US job data.

    Defaults to 2022.

- `--max-trip-distance` _max-trip-distance_
  - Distance maximal of a trip.

    Defaults to 2680.

- `--mirror` _mirror_
  - Use a mirror to fetch the US census files.

    Defaults to `None`, meaning it fetches the data from the US census sites.

- `--no-cache`
  - Disable the cache folder.

    Defaults to `False`.

- `--retries` _retries_
  - Number of times to retry downloading files.

    Defaults to 2.

- `--s3-bucket` _s3-bucket_
  - S3 bucket to use to store the result files.

- `--s3-dir` _s3-dir_
  - Directory where to store the results within the S3 bucket.

    Defaults to the root of the bucket.

- `--with-bundle`
  - Add a zip archive which bundles the result files altogether.

    Defaults to no bundle.

- `--with-export` _with-export_
  - Export strategy

    Valid values are: `none` `local` `s3` `s3_custom`.

    Defaults to `local`.

- `--with-parts` _parts_
  - Parts of the analysis to compute.

    Valid values are: `features`, `stress`, `connectivity`, and `measure`. This
    option can be repeated if multiple parts are needed.

    Defaults to all the parts (features, stress, connectivity, measure).

- `--worldpop-year` _worldpop-year_
  - Year to use to retrieve WorldPop data for international cities.

    Defaults to the current year.

## Cache

Manage the cache.

### clean

Clean the cache directory.

```bash
bna cache clean [OPTIONS]
```

#### options

- `--dry-run`, `-n`
  - Dry run.

    Does not actually perform any action, but show the simulated results.

- `--quiet`, `-q`
  - Quiet mode.

    Does not display any information on the output.

### dir

Show the cache directory.

```bash
bna cache dir [OPTIONS]
```

[calver]: https://calver.org
