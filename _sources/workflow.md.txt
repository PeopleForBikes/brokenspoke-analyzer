# Preparation Workflow

This page describes the steps to execute to manually prepare the files required
to run an analysis.

Normally the `bna prepare` command (or `bna run`) would execute all the actions
automatically, but there can be some edge cases where the tool is not able to
complete them all, therefore requiring the user to finalize them by hand.

## Steps

This example will depict the process for the city of Valencia, Spain.

### Retrieve the city boundaries

The first step consists in retrieving the city boundaries.

For this we're using the [OSMNX] library.

```{figure} _static/valencia-spain-boundaries.png
:alt: Valencia, Spain boundaries
:width: 300px
:align: center

Administrative boundaries of the city of Valencia, Spain.
```

### Download the OSM region file

Then we need to download the OSM planet file for the region where the city is
located.

We can retrieve these files on the [Geofabrik.de] site. They are orgranised by
continents, regions, countries, and even some times cities themselves.

We will need to download the `valencia-latest.osm.pbf` file from the page of the
[region of Valencia](https://download.geofabrik.de/europe/spain/valencia.html).

```{figure} _static/comunidad-valenciana-spain-geofabrik.png
:alt: Comunidad Valenciana, Spain on Geofabrik.de
:width: 300px
:align: center

Comunidad Valenciana, Spain on [Geofabrik.de](https://download.geofabrik.de/europe/spain/valencia.html).
```

### Reduce the OSM file to the city limits

Once we have both pieces, we can use them to extract the information from the
planet file, which are contained within the city limits.

This is done using a tool like [osmium]. We will use it to generate a file named
`valencia-spain.osm`.

```{admonition} Note
:class: note

In a future version, these 3 steps will be combined.
```

### Retrieve US state information

If the city is located in the US, we need to retrieve the FIPS State Numeric
Code andthe Official USPS Code (i.e. abbreviation).

For example, the state of Texas is abbreviated "TX" and has a FIPS code of 48.

This information can be found on the
[census page](https://www.census.gov/library/reference/code-lists/ansi.html).

For non-US cities, an abbreviation of "ZZ" is used, and a FIPS code of 91.

### Extra steps for non-US cities

For non-US cities we need to simulate the information from the US census.

#### Create synthetic population

We need to create a grid which just overlaps the city boundaries. Each cell of
the grid will contain the same amount of population.

In our case, each cell is a square of 1000m x 1000m, and contains 100 people.

```{figure} _static/valencia-spain-synthetic-population.png
:alt: Synthetic popupaltion for Valencia, Spain
:width: 300px
:align: center

Synthetic popupaltion for Valencia, Spain
```

#### Simulate census blocks

This grid then needs to be exported to a shapefile, zipped without a top level
folder. This will simulate the census dataset representing
[Census Blocks with Population and Housing Counts](https://www.census.gov/geographies/mapping-files/2010/geo/tiger-line-file.html).

This file must be named `tabblock2010_91_pophu.zip` and stored in the `data`
directory.

#### Adjust default speed limit

Default speed limits are different in each country, and infering them from Open
Street Map is not always possible.

In this case, a CSV file overriding the default values must be created with the
following format:

```text
city,state,fips_code_city,speed
valencia,al,1234567,50
```

This file must be named `city_fips_speed.csv` and stored in the `data`
directory.

### Final results

At the end of the process, the `./data` folder should contain the following
files:

```bash
./data
├── city_fips_speed.csv
├── spain-latest.osm.pbf
├── tabblock2010_91_pophu.zip
├── valencia-spain.cpg
├── valencia-spain.dbf
├── valencia-spain.geojson
├── valencia-spain.osm
├── valencia-spain.prj
├── valencia-spain.shp
└── valencia-spain.shx
```

You can then run the analysis with the following command:

```bash
bna analyze spain valencia valencia-spain.shp valencia-spain.osm
```

After several hours (7+ hours), the result will be generated in a subfolder of
the `data` directory and will look like this:

```bash
.
├── neighborhood_census_blocks.geojson
├── neighborhood_census_blocks.zip
├── neighborhood_colleges.geojson
├── neighborhood_community_centers.geojson
├── neighborhood_connected_census_blocks.csv.zip
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
├── neighborhood_ways.zip
└── residential_speed_limit.csv
```

[geofabrik.de]: https://download.geofabrik.de
[osmium]: https://osmcode.org/osmium-tool/
[osmnx]: https://osmnx.readthedocs.io/en/stable/
