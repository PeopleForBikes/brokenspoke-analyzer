# Test cities

## Sizes

The sizes represent the duration of the tests.

- 🔵 XS: runs under 5 min
- 🟢 S: runs under 15 min
- 🟡 M: runs under 60 min
- 🟠 L: runs under 180 min (1/8 day)
- 🔴 XL: runs under 360 min (1/4 day)
- 🟣 XXL: runs under 720 min (1/2 day)

## Test suite

| **Test Size** | **Country** | **Region** | **City** | **FIPS Code** | **Issue Links** | **PR Links** | **Reason** |
|---------------|-------------|------------|----------|---------------|-----------------|--------------|------------|
|🔵|🇦🇺|australia|orange|0|||Australia has unusual ways of defining city boundaries, so alignment w/ OpenStreetMap named areas could be a challenge.|
|🔵|🇨🇦|québec|ancienne-lorette|0|||Apostrophe, dash, accent in name.|
|🟡|🇫🇷|rhone-alpes|chambéry|0|||Accented letter.|
|🔴|🇪🇸|valencia|valencia|0|||A non-US city with a fantastic bike network.|
|🟡|🇺🇸|arizona|flagstaff|0423620|||It was part of our initial test suite. Small enough, but quite complete.|
|🟡|🇺🇸|california|arcata|0602476|||Has two disconnected polygons for city boundary.|
|🟢|🇺🇸|colorado|cañon city|0811810|||Letter w/ tilde.|
|🔵|🇺🇸|colorado|crested butte|0818310|||The city has a space in its name.|
|🔵|🇺🇸|delaware|rehoboth beach|1060290|||Contains ocean within city boundary so would interact with water blocks census file.|
|🟣|🇺🇸|district of columbia|washington|1150000||[#956](https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/956)|A very multi-modal city which is often recommended in PostGIS tutorials due to its completeness. Also it is not a 'true' US state, therefore it is another edge case.|
|🔵|🇺🇸|massachusetts|provincetown|2555535|[#983](https://github.com/PeopleForBikes/brokenspoke-analyzer/issue/983)||This is the US city with the highest score in the city rating. It is also small enough to run the tests in a few minutes.|
|🟢|🇺🇸|michigan|ypsilanti|2689140|[#943](https://github.com/PeopleForBikes/brokenspoke-analyzer/issue/943)||The OSM data could not get imported due to invalid characters.|
|🟡|🇺🇸|minnesota|st. louis park|2757220|||Punctuation in name.|
|🔵|🇺🇸|new mexico|santa rosa|3570670|||The city and the state have a space in their names.|
|🟢|🇺🇸|puerto rico|san juan|7276770||[#978](https://github.com/PeopleForBikes/brokenspoke-analyzer/pull/978)|Puerto Rico is part of the US but the Census Bureau does not collect LODES data for it.|
|🟢|🇺🇸|texas|alvarado|4802260|||Two distinct polygons forming the city boundary.|
|🟢|🇺🇸|wyoming|jackson|5640120|||Local speed default of 25 mph that is different from the state's (30 mph).|

## Runinng the tests

### Batches

The test suites can either be ran in full (although it would take days to
complete...) or it can use the files partitioned by test sizes
(e.g. `e2e-cities-xs.csv).

```bash
uv run python utils/bna-batch.py e2e-cities-xs.csv
```

Specifying the analysis part to only be `measure` significantly speeds up the
tests while running through the full process:

```bash
uv run python utils/bna-batch.py --with-parts measure e2e-cities-xs.csv
```

### Individual

To run tests individualy we recommend using the `run-with compose` command.

Export the `DATABASE_URL`:

```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
```

Here is the list of commands for all the test cities:

```bash
uv run bna run-with compose "australia" "orange" "australia" 
uv run bna run-with compose "canada" "ancienne-lorette" "québec" 
uv run bna run-with compose "france" "chambéry" "rhone-alpes" 
uv run bna run-with compose "spain" "valencia" "valencia" 
uv run bna run-with compose "united states" "flagstaff" "arizona" 0423620
uv run bna run-with compose "united states" "arcata" "california" 0602476
uv run bna run-with compose "united states" "cañon city" "colorado" 0811810
uv run bna run-with compose "united states" "crested butte" "colorado" 0818310
uv run bna run-with compose "united states" "rehoboth beach" "delaware" 1060290
uv run bna run-with compose "united states" "washington" "district of columbia" 1150000
uv run bna run-with compose "united states" "provincetown" "massachusetts" 2555535
uv run bna run-with compose "united states" "ypsilanti" "michigan" 2689140
uv run bna run-with compose "united states" "st. louis park" "minnesota" 2757220
uv run bna run-with compose "united states" "santa rosa" "new mexico" 3570670
uv run bna run-with compose "united states" "san juan" "puerto rico" 7276770
uv run bna run-with compose "united states" "alvarado" "texas" 4802260
uv run bna run-with compose "united states" "jackson" "wyoming" 5640120

```

## Updating the tests

If tests need to be updated or added, the master file is `e2e-cities.csv`. This
is the entrypoint used for generating this file and the batch test files.

The `Justfile` contains tasks to do so easily. It requires the [xan] tool to be
installed locally.

[xan]: https://github.com/medialab/xan/

## JSON input

This is mostly used for validatin our AWS pipeline since the list of cities to
get processed is sent to AWS SQS in JSON format.

SQS requires the input to be passed as JSON. For this reason, the CSV test file
is being exported to JSON as well. Look for the `e2e-cities.json` file in this
folder.

## Adding more tests

Simply edit the `e2e-cities.csv` file and run the `just test-e2e-prepare` command.