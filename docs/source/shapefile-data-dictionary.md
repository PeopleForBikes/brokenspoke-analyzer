# Data Dictionary

Describe the fields in the analysis outputs.

## Shapefiles

Describe the fields that exist in shapefiles like `neighborhood_ways.shp`.

| **Attribute** | **Description**                                                                              |
| ------------- | -------------------------------------------------------------------------------------------- |
| ROAD_ID       | Unique identifier                                                                            |
| NAME          | Road name                                                                                    |
| INTERSECTI    | Intersection identifier for the "from" node                                                  |
| INTERSE_01    | Intersection identifier for the "to" node                                                    |
| OSM_ID        | OpenStreetMap ID                                                                             |
| TDG_ID        | Unique identifier                                                                            |
| FUNCTIONAL    | OSM Functional Class                                                                         |
| PATH_ID       | Identifier for parent path/trail (where applicable)                                          |
| SPEED_LIMI    | Speed limit                                                                                  |
| ONE_WAY_CA    | One way for car traffic                                                                      |
| ONE_WAY       | One way for bike traffic                                                                     |
| WIDTH_FT      | Roadway width                                                                                |
| FT_BIKE_IN    | Bike infrastructure in the "from-to" (forward) direction                                     |
| FT_BIKE_01    | Width of bike infrastructure in the "from-to" (forward) direction                            |
| TF_BIKE_IN    | Bike infrastructure in the "to-from" (backward) direction                                    |
| TF_BIKE_01    | Width of bike infrastructure in the "to-from" (backward) direction                           |
| FT_LANES      | Number of travel lanes in the "from-to" (forward) direction                                  |
| TF_LANES      | Number of travel lanes in the "to-from" (backward) direction                                 |
| FT_CROSS_L    | Number of lanes to be crossed at the "to" intersection                                       |
| TF_CROSS_L    | Number of lanes to be crossed at the "from" intersection                                     |
| TWLTL_CROS    | Flag for whether a TWLTL (center turn lane) is present on the cross street                   |
| FT_PARK       | Flag for whether on-street parking is allowed on the "from-to" (forward) side of the street  |
| TF_PARK       | Flag for whether on-street parking is allowed on the "to-from" (backward) side of the street |
| FT_SEG_STR    | Stress for the street segment in the "from-to" (forward) direction                           |
| FT_INT_STR    | Stress for the intersection crossing at the "to" intersection                                |
| TF_SEG_STR    | Stress for the street segment in the "to-from" (backward) direction                          |
| TF_INT_STR    | Stress for the intersection crossing at the "from" intersection                              |

## mileage.csv

Total miles of bike infrastructure inside the city boundary, by type. Shared
lane markings (sharrows) are not included, because they are not tagged
consistently in OpenStreetMap. Segments that extend past the boundary count only
the part inside it.

| **feature_type** | **What it includes**                                                                                      | **How it is counted**                                                                                         |
| ---------------- | --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `track`          | Protected bike lanes: on-street `cycleway=track`, and separate paths detected as running alongside a road | Per direction. A separate path counts once unless it is mapped as two-way for bikes (`oneway=no`), then twice |
| `buffered_lane`  | Buffered bike lanes                                                                                       | Per direction                                                                                                 |
| `lane`           | Bike lanes                                                                                                | Per direction                                                                                                 |
| `path`           | Off-street paths not detected as protected bike lanes                                                     | Once: a two-way path counts its length once                                                                   |
