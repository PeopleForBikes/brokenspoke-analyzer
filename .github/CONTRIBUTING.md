# Contributing

## General guidelines

The Brokenspoke-analyzer project follows the
[BNA Mechanics Contributing Guidelines](https://peopleforbikes.github.io/contributing/).
Refer to them for general principles.

Specific instructions will be described in other sections on this page.

## Developer environment

### Requirements

- [Just] (See the "Administration tasks" section for details)
- [Poetry]
- [Python] 3.10+
- [Docker]
- [Osmium]

### Setup

Fork [brokenspoke-analyzer](https://github.com/PeopleForBikes/brokenspoke-analyzer)
into your account. Clone your fork for local development:

```bash
git clone git@github.com:your_username/brokenspoke-analyzer.git
```

Then `cd` into `brokenspoke-analyzer`, and to setup the project and install
dependencies, run:

```bash
poetry install
```

## Serving the documentation site

To render the site when adding new content, run the following command:

```bash
just docs-autobuild
```

Then open the <http://127.0.0.1:1111> URL to view the site.

The content will automatically be refreshed when a file is saved on disk.

## Administration tasks

Administration tasks are being provided as convenience in a `justfile`.

More information about [Just] can be found in their repository. The
[installation](https://github.com/casey/just#installation) section of their
documentation will guide you through the setup process.

Run `just -l` to see the list of provided tasks.

[just]: https://github.com/casey/just
[poetry]: https://python-poetry.org/
[python]: https://www.python.org/downloads/
[docker]: https://www.docker.com/get-started/
[osmium]: https://osmcode.org/osmium-tool/

## PFB Bicycle Network Analysis

The [Bicycle Network Analysis (BNA)](https://github.com/azavea/pfb-network-connectivity/tree/develop/src/analysis)
is a data analysis tool that measures how well
bike networks connect people with the places they want to go. It is
implemented in [PostgreSQL](https://www.postgresql.org/) using
the [PostGIS](https://postgis.net/) spatial extension. As shown below, a
series of shell
scripts, running inside a [Docker] container, are used to build the database and
run the analysis.

### Script organization of the BNA

The figure below shows where each shell script is called from.

```{graphviz}
digraph {
bgcolor="#fcfaf6";
node [shape="box", style="rounded"];
{rank = same; "entrypoint.sh"}
{rank = same; "run_analysis.sh"}
{rank = same; "import.sh" "run_connectivity.sh" "export_connectivity.sh"}
{rank = same; "import/import_neighborhood.sh" "import/import_jobs.sh" "import/import_osm.sh"}
{rank = same; "prepare_tables.sql" "clip_osm.sql" "features/*.sql" "stress/*.sql"}
{rank = same; "connectivity/destinations/*.sql" "connectivity/*.sql"}
"entrypoint.sh" -> "run_analysis.sh";
"run_analysis.sh" -> "import.sh";
"run_analysis.sh" -> "run_connectivity.sh";
"run_analysis.sh" -> "export_connectivity.sh";
"import.sh" -> "import/import_neighborhood.sh";
"import.sh" -> "import/import_jobs.sh";
"import.sh" -> "import/import_osm.sh";
"import/import_osm.sh" -> "prepare_tables.sql";
"import/import_osm.sh" -> "clip_osm.sql";
"import/import_osm.sh" -> "features/*.sql";
"import/import_osm.sh" -> "stress/*.sql";
"run_connectivity.sh" -> "connectivity/destinations/*.sql";
"run_connectivity.sh" -> "connectivity/*.sql";
}
```

```{note}
The PostgreSQL Docker image will automatically run scripts found in `/docker-entrypoint-initdb.d/`. So
`setup_database.sh`, which is not shown in the figure above, will run automatically.
```

### Control flow of the BNA

The figure below shows the order in which the shell scripts are run.

```{graphviz}
digraph {
bgcolor="#fcfaf6";
node [shape="box", style="rounded"];
{rank = same; "entrypoint.sh" "run_analysis.sh" "import.sh"}
{rank = same; "import/import_neighborhood.sh" "import/import_jobs.sh" "import/import_osm.sh"}
{rank = same; "prepare_tables.sql" "clip_osm.sql" "features/*.sql" "stress/*.sql"}
{rank = same; "run_connectivity.sh" "connectivity/destinations/*.sql" "connectivity/*.sql" "export_connectivity.sh"}
"entrypoint.sh" -> "run_analysis.sh" -> "import.sh";
"import.sh" -> "import/import_neighborhood.sh" -> "import/import_jobs.sh" -> "import/import_osm.sh";
"import/import_osm.sh" -> "prepare_tables.sql" -> "clip_osm.sql" -> "features/*.sql" -> "stress/*.sql";
"stress/*.sql" -> "run_connectivity.sh" -> "connectivity/destinations/*.sql" -> "connectivity/*.sql" -> "export_connectivity.sh";
"entrypoint.sh" -> "import/import_neighborhood.sh" [style=invis];
"import/import_neighborhood.sh" -> "prepare_tables.sql" [style=invis];
"prepare_tables.sql" -> "run_connectivity.sh" [style=invis];
}
```

### BNA container setup for development

To develop the BNA, setup a development container by following these steps:

1. Fork the [azavea/pfb-network-connectivity](https://github.com/azavea/pfb-network-connectivity)
   repository.

2. Do SQL/Shell development on your fork. For more details on
   which SQL/Shell files implement the BNA see [Control flow of the BNA](#control-flow-of-the-bna).

3. Build the docker image using the `Dockerfile` in your fork by running the
   following from the `src` folder of your fork:

```bash
   docker buildx build -t azavea/pfb-network-connectivity:0.16.1 -f analysis/Dockerfile .
```

:::{note}
You can use any other name besides `azavea/pfb-network-connectivity:0.16.1`
:::

1. Rename the built image from step 3, if desired

```bash
   docker tag azavea/pfb-network-connectivity:0.16.1 your_username/bna:0.0
```

### Running the BNA using Brokenspoke-analyzer

The `brokenspoke-analyzer` can be run using the `bna` script defined in
`pyproject.toml` or by
activating the virtual environment that was created by [Poetry] inside the
project (given the poetry config file, `poetry.toml`)
and running the cli commands. To run the modified BNA for a city in the US, for
example Flagstaff, AZ, using the `bna` script:

```bash
bna run arizona flagstaff
```

To run using the virtual environment, activate the virtual environment:

```bash
poetry shell
```

Then run any of the cli commands, for example:

```bash
python main.py run arizona flagstaff
```

To exit the virtual environment:

```bash
exit
```
