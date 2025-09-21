# How to use custom input files

Before starting the analysis, the brokenspoke-analyzer will need to download
some input files in order to proceed. In most of the cases you want to let it
download the files automatically. However, if can happen that you would want to
use your own input files, for example for testing an hypothesis.

Doing so is very simple, you simply have to provide the file(s), and copy them
in the data directory for the city, following our naming conventions.

## What input files are being used

Let say that you want to analyze the city of Provincetown, MA in the United
States.

If you would let the brokenspoke-analyzer do the work automatically you would
obtain the following file structure:

```sh
.
└── data
   └── provincetown-massachusetts-united-states
       ├── city_fips_speed.csv
       ├── ma_od_aux_JT00_2022.csv
       ├── ma_od_main_JT00_2022.csv
       ├── massachusetts-latest.osm.pbf
       ├── massachusetts-latest.osm.pbf.md5
       ├── population.cpg
       ├── population.dbf
       ├── population.prj
       ├── population.shp
       ├── population.shx
       ├── population.xml
       ├── population.zip
       ├── provincetown-massachusetts-united-states.clipped.osm
       ├── provincetown-massachusetts-united-states.cpg
       ├── provincetown-massachusetts-united-states.dbf
       ├── provincetown-massachusetts-united-states.geojson
       ├── provincetown-massachusetts-united-states.osm
       ├── provincetown-massachusetts-united-states.prj
       ├── provincetown-massachusetts-united-states.shp
       ├── provincetown-massachusetts-united-states.shx
       └── state_fips_speed.csv
```

Let's see what these are in details.

### Data directory

First, the data directory. This is the location where all the necessary input
files are going to be written on disk.

By default it is named `data` in the folder where you cloned the repository.
This can be overridden with the `--data-dir` flag in most of the commands if
need be, but most of the time the default location will work just fine.

The name of the directory containing the data matches the following convention:
`<city>[-<region>]-<country>`.

All these values match the parameters that you passed on the CLI. Note that the
`region` parameter is optional for non-US cities, therefore you may end up with
a directory named `<city>-<country>`, like `valetta-malta` for instance.

### Boundary files

They represent the administrative boundaries of the city. For historical
reasons, this file exists in 2 formats:

- Geojson
- Shapefile

However only the shapefile is used for the analysis.

The name of the file is the same name as the directory, with the `.geojson`
extension, or all the extensions of a shapefile:

```sh
├── provincetown-massachusetts-united-states.cpg
├── provincetown-massachusetts-united-states.dbf
├── provincetown-massachusetts-united-states.geojson
├── provincetown-massachusetts-united-states.osm
├── provincetown-massachusetts-united-states.prj
├── provincetown-massachusetts-united-states.shp
├── provincetown-massachusetts-united-states.shx
```

### OSM region file

This is the `osm.pbf` file (OSM PBF files are binary files that contain
OpenStreetMap data in the Protocolbuffer Binary Format, which is more compact
and faster to process than the XML format) representing the region where the
city is located.

Note that if the region was omitted, this file will have the name of the country
instead.

The checksum file, `.md5`, is required to verify the integrity of the data.

```sh
├── massachusetts-latest.osm.pbf
├── massachusetts-latest.osm.pbf.md5
```

### Clipped city file

This is sn extract of the region file, matching the boudaries of the city to
analyze.

It has the same name as the directory, with the `.clipped.osm` extension.

```sh
├── provincetown-massachusetts-united-states.clipped.osm
```

### Population file

For US cities it is simply the shapefile provided by the US Census Bureau for
the state where the city is located.

For non-US cities, we generate synthetic population data to simulate the census.
Refer to the "Preparation workflow" tutorial for more details.

The shapefile is simply named "population".

```sh
├── population.cpg
├── population.dbf
├── population.prj
├── population.shp
├── population.shx
├── population.xml
```

### Employment files (US only)

These files are provided by the US census and contain information about US jobs.

```sh
├── ma_od_aux_JT00_2022.csv
├── ma_od_main_JT00_2022.csv
```

### Speed limits

There is a file containing the default speed limits per state (US only), and a
file for the speed limit of the cities if it differs from the default one.

```sh
├── city_fips_speed.csv
└── state_fips_speed.csv
```

Note that while these files can be edited, we recommend you use the
`--city-speed-limit` option on the CLI if you need to override the default
value.
