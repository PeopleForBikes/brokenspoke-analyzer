# Commands

## General information

Most of the commands require access to PostgreSQL/PostGIS. For this reason we
recommend setting the `DATABASE_URL` environment variable, even though it is
possible to specify it on the CLI. This will keep the commands shorter and
reduce the chance of error in the connection URL.

Not all the CLI flags will be described on this page. For more details, please
refer to the help screens by using the `--help` flag associated with the command
to review.

All the commands follow a very similar pattern, therefore they use almost all
the same parameters accross the board.

## Environment variables

- **DATABASE_URL**: Define the connection URL to the database.

  For instance: `postgresql://postgres:postgres@localhost:5432/postgres`.

- **BNA_OSMNX_CACHE**: Set it to 0 to disable the OSMNX cache.

  This is useful when used in an ephemeral environment where there is no real
  benefit of caching the downloads.

## Configure

Configure is a helper command, in the sense that it is completely optional to
the process, but may help to configure the PostgreSQL which will be used for the
analysis.

The most common use case is to configure a PostgreSQL instance which is running
in a Docker container (via the Docker Compose file that we provide for
instance). To do so, simply run:

```bash
bna configure docker
```

The command will autodetect the number of cores and the memory allocated to the
Docker daemon, and will use this information to determine the optimal values to
use to configure the PostgreSQL instance.

If for some reason a more fine grained configuration is prefered, another
command is provided where the user has to specify the information manually:

```bash
bna configure custom 4 4096 pguser
```

The parameters are:

- the number of cores to allocate
- the amount of memory to allocate, in MB
- the name of the PostgreSQL user to connect as

## Prepare

This command prepares all the input files required for an analysis.

```bash
Usage: bna prepare all [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

For US cities, the full name of the state as well as the city FIPS code are
required:

```bash
bna prepare all usa "santa rosa" "new mexico" 3570670
```

For non US cities, only the name and the country are required:

```bash
bna prepare all malta valletta
```

However, specifying a region can speed up the process since it will reduce the
size of the map to download. For instance this command will download the map of
the province of Québec in Canada. If `québec` was omitted, it would download the
map of the full country instead.

```bash
bna prepare all canada "ancienne-lorette" québec
```

For non US cities, the FIPS code is always ignored.

By default the files will be saved in their own sub-directory in the `./data`
directory, relative to where the command was executed. This can be changed with
the `--output-dir` option flag.

For the 3 previous examples, the files will be located in:

```bash
data
├── ancienne-lorette-quebec-canada
├── santa-rosa-new-mexico-usa
└── valletta-malta
```

All of this should already be enough to gather the information required to
perform an analysis, but a few more knobs are available to override the default
values:

- **--speed-limit**: overrides the city speed limit.
- **--block-size**: defines the size of a synthetic block (only used for non US
  cities)
- **--block-population**: defines the population of a synthetic block (only used
  for non US cities)
- **--census-year**: year to use to retrieve US census data (only used for US
  cities)

## Import

This command imports all files from the `prepare` command into the database.

The sub-command which is the most commonly used is `all`, but in case of
exploration, a particular type of import can be specified: `jobs`,
`neighborhood` and `osm`.

Since they all work the same way, only the `all` sub-command will be described
below.

### All

```bash
Usage: bna import all [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

Same conditions as before, `country` and `city` arguments are mandatory, while
the `region` and the `FIPS` code are required only for US cities.

<!-- prettier-ignore -->
:::{attention} The same parameters as for the `prepare` command must be used to
guarantee correct results.
:::

In addition to these parameters, the directory where the input files were stored
is also required and must be specified with the `--input-dir` option flag.

```bash
bna import all usa "santa rosa" "new mexico" 3570670 --input-dir data/santa-rosa-new-mexico-usa
```

## Compute

This is the command which actually computes the numbers.

```bash
Usage: bna compute [OPTIONS] COUNTRY CITY [STATE]
```

<!-- prettier-ignore -->
:::{attention} The same parameters as for the `prepare` command must be used to
guarantee correct results.
:::

In addition to these parameters, the directory where the files were stored is
also required and must be specified with the `--input-dir` option flag.

```bash
bna compute usa "santa rosa" "new mexico" --input-dir data/santa-rosa-new-mexico-usa
```

Several parts are available for computing:

- features
- stress
- connectivity
- measure (available in experimental mode only, to use set the
  `BNA_EXPERIMENTAL` environment variable to `1`)

It is possible to use only some parts for the analysis. In this case, the
`--with-parts` option can be used to specify which part to compute.

```bash
bna compute --with-parts stress usa "santa rosa" "new mexico" --input-dir data/santa-rosa-new-mexico-usa
```

You can also specify multiple parts by repeating the `--with-parts` option:

```bash
bna compute --with-parts stress --with-parts connectivity usa "santa rosa" "new mexico"
--input-dir data/santa-rosa-new-mexico-usa
```

If the `--with-parts` option is not specified, all the parts will be computed.

All the results will be stored in various tables in the database.

## Export

This command exports the tables from the database.

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

### local-custom

This sub-command exports the results to a local directory.

```bash
Usage: bna export local [OPTIONS] EXPORT_DIR
```

Example:

```bash
bna export local ~/bna/santa-rosa-new-mexico-usa
```

The directories will be created if they do not exist.

### local

This sub-command exports the results to a local directory created based on the
PeopleForBikes convention and [calver] versioning.

```bash
Usage: bna export local-calver [OPTIONS] COUNTRY CITY [REGION] [EXPORT_DIR]
```

The calver [scheme](https://calver.org/#scheme) used here is `YY.MINOR[.MICRO]`,
similar to what [pip](https://pip.pypa.io/en/stable/news/), the official package
manager for Python uses.

```bash
bna export local-calver usa "santa rosa" "new mexico"
```

The final directory structure follows the PeopleForBikes convention
`<output_dir>/<country>/<region>/<city>/<calver>` and the structure will look
like this:

```bash
results
└── usa
    └── new mexico
        └── santa rosa
            └── 23.9
              └── ...
```

### S3

This sub-command exports the result to an AWS S3 bucket, respecting the calver
representation.

```bash
Usage: bna export s3 [OPTIONS] BUCKET_NAME COUNTRY CITY [REGION]
```

Therefore the output is similar to the `local` export:

```bash
my_s3_bucket
└── usa
    └── new mexico
        └── santa rosa
            └── 23.9
              └── ...
```

### S3 Custom

This sub-command exports the results to a custom AWS S3 bucket.

```bash
Usage: bna export s3-custom [OPTIONS] BUCKET_NAME S3_DIR
```

And the output could look like that:

```bash
my_s3_bucket
└── usa-new mexico-santa rosa-23.9
  └── ...
```

## Run

This command runs the full analysis in one command.

```bash
Usage: bna run [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

Basically this command is a combination of the `prepare`, `import`, `compute`
and `export` sub-commands.

It still requires a configured, up and running database in order to complete.

```bash
bna run usa "santa rosa" "new mexico" 3570670
```

Like the for the [compute](#compute) command, the parts to be analyzed may be
specified individually with the `--with-parts` argument.

## Run-with

This command provides alternative ways to run the analysis.

### Compare

This sub-command runs the analysis with both the brokenspoke-analyzer and the
original BNA, then compares the results.

```bash
Usage: bna run-with compare [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

### Compose

This sub-command manages the Docker Compose environment automatically.

```bash
Usage: bna run-with compose [OPTIONS] COUNTRY CITY [STATE] [FIPS_CODE]
```

It combines the `configure`, `prepare`, `import`, `compute`, `export`
sub-commands and wraps them into the setup and tear-down of the Docker Compose
environment.

Like the for the [compute](#compute) command, the parts to be analyzed may be
specified individually with the `--with-parts` argument.

### Original-BNA

This sub-command runs an anlalysis using the original BNA.

```bash
Usage: bna run-with original-bna [OPTIONS] CITY_SHP PFB_OSM_FILE [CITY_FIPS]
```

It runs the Docker container of the original BNA with the appropriate parameters
for the city to analyze.

[calver]: https://calver.org
