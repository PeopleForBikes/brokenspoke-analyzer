# Brokenspoke-analyzer

## Requirements

- **docker**: [get started](https://www.docker.com/get-started/)
- **gdal**: [official page](https://gdal.org/download.html)
- **osmosis**: [official page](https://osmcode.org/osmium-tool/)

### Build the Azavea docker image

```bash
git@github.com:azavea/pfb-network-connectivity.git
cd pfb-network-connectivity/src/
DOCKER_BUILDKIT=1 docker build -t azavea/analyzer:13-3.1 -f analysis/Dpckerfile
```

### US Census API key

- Go to <https://api.census.gov/data/key_signup.html> to request a census API key.
- Create a `.env` file at with the key at the root of this project:

  ```bash
  echo "CENSUS_API_KEY=7ff372e9483f5d8d60d7fd1bf0ec6f6b5997aa86" > .env
  ```

## Quickstart

In the `broken_analysis/main.py` file, in the `analyze()` function, adjust the
input to match the city you want to analyze:

```py
async def analyze():
    # Provided inputs.
    # Sample 00: regular
    state = "arizona"
    city = "flagstaff"
    osm_relation_id = "110844"
    await prepare(state, city, osm_relation_id)
```

A few remarks:

- The name of the sate and the city must all be lower case.
- The exaplanations to find the OSM relation of the city can be found on
  [James Chevalier'page](https://github.com/JamesChevalier/cities#how-to-get-the-poly-file-for-a-specific-city=)

Then from the root of the project, run the script, and all the steps will be
performed automatically:

```bash
$ poetry run python broken_analysis/main.py
[18:50:14] US Census file downloaded.
[18:50:15] Boundary file ready.
           Regional OSM file downloaded.
[18:50:16] Polygon file downloaded.
           OSM file for flagstaff ready.
           Analysis for flagstaff arizona complete.
```
