# Usages

This page describes common usages of the Brokenspoke-analyzer as well as some
explanations related to its workflows and infrastructure.

## How does it work?

An analysis is composed of a few steps:

1. Collect the data required for the analysis
2. Import the data into a database
3. Run the computation on the data
4. Export the results to usable formats, like Shapefile, GeoJSON or CSV.

The brokenspoke-analyzer acts as a sort of orchestrator. The heavy lifting is
done by PostgreSQL/PostGIS.

Step 3 is where most of the magic happens. The computation part is done by
running hundreds of SQL queries against PostGIS.

> Note: Add a diagram here.

## Where to find the FIPS codes?

## Using the Docker Compose environment

A Docker [Compose file](https://) is provided with this project to simplify the
setup.

Using Compose is just a simpler way to run the PostGIS container with the right
parameters (environment variables, network, volume, etc.).

## Using brokenspoke-analyzer in the docker container

Installing all the required GIS tool can be a complicated task, especially on
Windows platforms.

For this reason, we provide a Docker container that be used instead of the
native tools.

## Using an existing database instance

If you would prefer to use an existing database, there is no problem with that.

Here are the requirements:

- PostgreSQL 13+
- PostGIS 3.1+
- Pgrouting
- Plpython3
- Enable the `uuid-ossp` and `plpython3u` extensions.
- Create the `generated`, `received` and `scratch`, schemas and make sure the
  user has the authorization to access them

> Note: We should provide a command which only creates the schemas and
> extensions required.
