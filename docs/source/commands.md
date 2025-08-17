# Commands

## General information

Most of the commands require access to PostgreSQL/PostGIS. For this reason we
recommend setting the `DATABASE_URL` environment variable, even though it is
possible to specify it on the CLI. This will keep the commands shorter and
reduce the chance of error in the connection URL.

All the commands follow a very similar pattern, therefore they use almost all
the same parameters accross the board.

## Environment variables

- **DATABASE_URL**: Define the connection URL to the database.

  For instance: `postgresql://postgres:postgres@localhost:5432/postgres`.

- **BNA_OSMNX_CACHE**: Set it to 0 to disable the OSMNX cache.

  This is useful when used in an ephemeral environment where there is no real
  benefit of caching the downloads.

## Configure

Configure a database for an analysis.

Configure is a helper command, in the sense that it is completely optional to
the process, but may help to configure the PostgreSQL instance which will be
used for the analysis.

```bash
bna configure [OPTIONS] COMMAND [ARGS]
```

### configure docker

Configure a database running in a Docker container.

```bash
bna configure docker [OPTIONS]
```

The most common use case is to configure a PostgreSQL instance which is running
in a Docker container (via the Docker Compose file that we provide for example).

The command will autodetect the number of cores and the memory allocated to the
Docker daemon, and will use this information to set the values to use to
configure the PostgreSQL instance.

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

### configure custom

Configure a database with custom values.

```bash
bna configure custom [OPTIONS] CORES MEMORY_MB PGUSER
```

If for some reason a more fine grained configuration is prefered, another
command is provided where the user has to specify the information manually.

The parameters are:

- the number of cores to allocate
- the amount of memory to allocate, in MB
- the name of the PostgreSQL user to connect as

### configure reset

The reset comand is a convenience command that resets the database. It deletes
tables associated with an analysis and recreates the necessary schema. Its main
use case is when developing/debugging locally and you need to try out another
analysis without having to swith to your host system and using Docker to
stop/remove the database associated with the previous analysis.

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

### configure system

Configure the database system parameters.

```bash
bna configure system [OPTIONS] CORES MEMORY_MB
```

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

### configure extensions

Configure the database extensions.

```bash
bna configure extensions [OPTIONS]
```

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

### configure schemas

Configure the database schemas.

```bash
bna configure schemas [OPTIONS] PGUSER
```

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

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

- `--city-speed-limit` _city-speed-limit_

  - Override the default speed limit (in mph).

    Defaults to 30.

- `--data-dir` _data-dir_

  - Directory where to store the files required for the analysis.

    Defaults to `./data`.

- `--lodes-year` _lodes-year_

  - Year to use to retrieve US job data.

    Defaults to 2022.

- `--retries` _retries_

  - Number of times to retry downloading files.

    Defaults to 2.

## Import

Import files from the `prepare` command into the database.

The sub-command which is the most commonly used is `all`, but in case of
exploration, a particular type of import can be specified: `jobs`,
`neighborhood` and `osm`.

### import all

Import all files into the database.

```bash
bna import all [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

Same conditions as before, `country` and `city` arguments are mandatory, while
the `region` and the `FIPS` code are required only for US cities.

<!-- prettier-ignore -->
:::{attention} The same parameters as for the `prepare` command must be used to
guarantee correct results.
:::

In addition to these parameters, the directory where the input files were stored
is also required and must be specified with the `--data-dir` option flag.

```bash
bna import all "united states" "santa rosa" "new mexico" 3570670 --data-dir data/santa-rosa-new-mexico-united-states
```

#### options

- `--buffer` _buffer_

  - Define the buffer area

    Defaults to 2680.

- `--data-dir` _data-dir_

  - Directory where the files to import are located.

    This is usually the output directory of the `prepare` command.

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

- `--lodes-year` _lodes-year_

  - Year to use to retrieve US job data.

    Defaults to 2022

### import neighborhood

Import neighborhood data.

```bash
bna import neighborhood [OPTIONS] COUNTRY CITY [REGION]
```

### import jobs

Import US census job data.

```bash
bna import jobs [OPTIONS] STATE_ABBREVIATION
```

#### options

- `--buffer` _buffer_

  - Define the buffer area

    Defaults to 2680.

- `--data-dir` _data-dir_

  - Directory where the files to import are located.

    This is usually the output directory of the `prepare` command.

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

### import osm

Import OSM data.

```bash
bna import osm [OPTIONS] COUNTRY CITY [REGION] [FIPS_CODE]
```

#### options

- `--data-dir` _data-dir_

  - Directory where the files to import are located.

    This is usually the output directory of the `prepare` command.

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

## Compute

Compute the numbers.

This is the command which actually computes the scores and generates the geojson
files resulting from the analysis.

```bash
bna compute [OPTIONS] COUNTRY CITY [REGION]
```

<!-- prettier-ignore -->
:::{attention} The same parameters as for the `prepare` command must be used to
guarantee correct results.
:::

In addition to these parameters, the directory where the files were stored is
also required and must be specified with the `--data-dir` option flag.

```bash
bna compute "united states" "santa rosa" "new mexico" --data-dir data/santa-rosa-new-mexico-united-states
```

Several parts are available for computing:

- features
- stress
- connectivity
- measure

It is possible to use only some parts for the analysis. In this case, the
`--with-parts` option can be used to specify which part to compute.

```bash
bna compute --with-parts stress "united states" "santa rosa" "new mexico" --data-dir data/santa-rosa-new-mexico-united-states
```

You can also specify multiple parts by repeating the `--with-parts` option:

```bash
bna compute --with-parts stress --with-parts connectivity "united states" "santa rosa" "new mexico"
--data-dir data/santa-rosa-new-mexico-united-states
```

If the `--with-parts` option is not specified, all the parts will be computed.

All the results will be stored in various tables in the database.

### options

- `--buffer` _buffer_

  - Define the buffer area

    Defaults to 2680.

- `--data-dir` _data-dir_

  - Directory where the files to import are located.

    This is usually the output directory of the `prepare` command.

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

- `--with-parts` _parts_

  - Parts of the analysis to compute.

    Valid values are: `features`, `stress`, `connectivity`, and `measure`. This
    option can be repeated if multiple parts are needed.

    Defaults to all the parts (features, stress, connectivity, measure).

## Export

Export the tables from the database.

Several exporters are available to export the results that where previously
computed.

The following files will be created from the PostgreSQL tables:

```bash
.
├── neighborhood_census_blocks.cpg
├── neighborhood_census_blocks.dbf
├── neighborhood_census_blocks.geojson
├── neighborhood_census_blocks.prj
├── neighborhood_census_blocks.shp
├── neighborhood_census_blocks.shx
├── neighborhood_colleges.geojson
├── neighborhood_community_centers.geojson
├── neighborhood_connected_census_blocks.csv
├── neighborhood_dentists.geojson
├── neighborhood_doctors.geojson
├── neighborhood_hospitals.geojson
├── neighborhood_overall_scores.csv
├── neighborhood_parks.geojson
├── neighborhood_pharmacies.geojson
├── neighborhood_retail.geojson
├── neighborhood_schools.geojson
├── neighborhood_score_inputs.csv
├── neighborhood_social_services.geojson
├── neighborhood_supermarkets.geojson
├── neighborhood_transit.geojson
├── neighborhood_universities.geojson
├── neighborhood_ways.cpg
├── neighborhood_ways.dbf
├── neighborhood_ways.prj
├── neighborhood_ways.shp
├── neighborhood_ways.shx
└── residential_speed_limit.csv
```

### export local

Export the results to a local directory following the PeopleForBikes [calver]
convention.

```bash
bna export local [OPTIONS] COUNTRY CITY [REGION] [EXPORT_DIR]
```

The final directory structure follows the PeopleForBikes convention
`<export_dir>/<country>/<region>/<city>/<calver_version>`.

The directories will be created if they do not exist.

The calver [scheme](https://calver.org/#scheme) used here is `YY.0M[.MINOR]`,
similar to what [Ubuntu](https://en.wikipedia.org/wiki/Ubuntu_version_history)
does.

#### Example

Running:

```bash
bna export local "united states" "santa rosa" "new mexico" ~/bna/
```

Would export the results into `~/bna/united states/new mexico/santa rosa/25.06`
if the analysis was run in June 2025 for the first time.

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

- `--with-bundle`

  - Add a zip archive which bundles the result files altogether.

    Defaults to no bundle.

### export local-custom

Export results to a custom directory.

```bash
bna export local-custom [OPTIONS] EXPORT_DIR
```

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

- `--with-bundle`

  - Add a zip archive which bundles the result files altogether.

    Defaults to no bundle.

### S3

Export the result to an AWS S3 bucket, respecting the calver representation.

```bash
bna export s3 [OPTIONS] BUCKET_NAME COUNTRY CITY [REGION]
```

Therefore the output is similar to the `local` export:

```bash
my_s3_bucket
└── united states
    └── new mexico
        └── santa rosa
            └── 23.9
              └── ...
```

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

- `--with-bundle`

  - Add a zip archive which bundles the result files altogether.

    Defaults to no bundle.

### S3 Custom

Export the results to a custom AWS S3 bucket.

```bash
bna export s3-custom [OPTIONS] BUCKET_NAME
```

And the output could look like that:

```bash
my_s3_bucket
└── united-states-new mexico-santa rosa-23.9
  └── ...
```

#### options

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

- `--s3-dir` _s3-dir_

  - Directory where to store the results within the S3 bucket.

    Defaults to the root of the bucket.

- `--with-bundle`

  - Add a zip archive which bundles the result files altogether.

    Defaults to no bundle.

## Run

Run the full analysis in one command.

```bash
bna run [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

Basically this command is a combination of the `prepare`, `import`, `compute`
and `export` sub-commands.

It still requires a configured, up and running database in order to complete.

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

- `--city-speed-limit` _city-speed-limit_

  - Override the default speed limit (in mph).

    Defaults to 30.

- `--data-dir` _data-dir_

  - Directory where to store the files required for the analysis.

    Defaults to `./data`.

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

- `--lodes-year` _lodes-year_

  - Year to use to retrieve US job data.

    Defaults to 2022.

- `--max-trip-distance` _max-trip-distance_

  - Distance maximal of a trip.

    Defaults to 2680.

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

## Run-with

Provide alternative ways to run the analysis.

### Compose

Manage the Docker Compose environment automatically.

```bash
bna run-with compose [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

It combines the `configure`, `prepare`, `import`, `compute`, `export`
sub-commands and wraps them into the setup and tear-down of the Docker Compose
environment.

#### options

- `--block-population` _block-population_

  - Population of a synthetic block for non-US cities.

    Defaults to 100.

- `--block-size` _block-size_

  - Size of a synthetic block for non-US cities (in meters).

    Defaults to 500.

- `--buffer` _buffer_

  - Define the buffer area

    Defaults to 2680.

- `--city-speed-limit` _city-speed-limit_

  - Override the default speed limit (in mph).

    Defaults to 30.

- `--data-dir` _data-dir_

  - Directory where to store the files required for the analysis.

    Defaults to `./data`.

- `--database-url` _database-url_

  - Set the database URL

    May also be set with the `DATABASE_URL` environment variable.

- `--export-dir` _export-dir_

  - Directory where to export the results.

    Defaults to `./results`

- `--lodes-year` _lodes-year_

  - Year to use to retrieve US job data.

    Defaults to 2022.

- `--max-trip-distance` _max-trip-distance_

  - Distance maximal of a trip.

    Defaults to 2680.

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

[calver]: https://calver.org
