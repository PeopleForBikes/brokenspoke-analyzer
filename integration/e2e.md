# e2e tests

This file describes the manual integration tests that are used to validate the
tool.

## Before all test

```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
```

## Santa Rosa, New Mexico, USA

```bash
docker compose up -d
bna -vv configure docker
bna -vv prepare all usa "santa rosa" "new mexico" 3570670
bna -vv import all usa "santa rosa" "new mexico" 3570670 --input-dir data/santa-rosa-new-mexico-usa
bna -vv compute usa "santa rosa" "new mexico" --input-dir data/santa-rosa-new-mexico-usa
bna -vv export local-calver usa "santa rosa" "new mexico"
docker compose rm -sfv && docker volume rm brokenspoke-analyzer_postgres
```

Or with the `run-with` command:

```bash
bna -vv run-with compose usa "santa rosa" "new mexico" 3570670
```

## L'Ancienne-Lorette, Québec

```bash
docker compose up -d
bna -vv configure docker
bna -vv prepare all canada "ancienne-lorette" québec
bna -vv import all canada "ancienne-lorette" québec --input-dir data/ancienne-lorette-quebec-canada
bna -vv compute canada "ancienne-lorette" québec --input-dir data/ancienne-lorette-quebec-canada
bna -vv export local-calver canada "ancienne-lorette" québec
docker compose rm -sfv && docker volume rm brokenspoke-analyzer_postgres
```

Or with the `run-with` command:

```bash
bna -vv run-with compose canada "ancienne-lorette" québec
```

## With Docker

Since we're interacting within the brokenspoke-analyze docker network, we need
to change the host to the name of the service we created instead of `localhost`.

```bash
export DATABASE_URL=postgresql://postgres:postgres@postgres:5432/postgres
```

```bash
# `configure docker`` does not work from from the container cause it needs to
# connect to the host.
# docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL hcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0-rc configure docker
# Use `docker info to get the `CPUs` and `Total Memory`.
docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0-rc configure custom 4 1943 postgres
docker run --rm -u $(id -u):$(id -g) -v ./data/container:/usr/src/app/data ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0-rc prepare all usa "santa rosa" "new mexico" 3570670 --output-dir /usr/src/app/data
docker run --rm --network brokenspoke-analyzer_default -v ./data/container:/usr/src/app/data -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0-rc import all usa "santa rosa" "new mexico" 3570670 --input-dir /usr/src/app/data/santa-rosa-new-mexico-usa
docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0-rc compute usa "santa rosa" "new mexico" --input-dir /usr/src/app/data/santa-rosa-new-mexico-usa
```

Or with the `run` command:

```bash
docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0-rc -vv run usa "santa rosa" "new mexico" 3570670
docker run --rm --network brokenspoke-analyzer_default -u $(id -u):$(id -g) -v ./results:/usr/src/app/results -e DATABASE_URL ghcr.io/peopleforbikes/brokenspoke-analyzer:2.0.0-rc  -vv export local-calver usa "santa rosa" "new mexico"
```

## Might be useful later

- <https://stackoverflow.com/questions/55977611/how-to-connect-docker-compose-to-container-network-and-localhost-network>

## JSON

### XS

```json
[
  {
    "country": "united states",
    "city": "provincetown",
    "region": "massachusetts",
    "fips_code": "555535"
  },
  {
    "country": "united states",
    "city": "santa rosa",
    "region": "new mexico",
    "fips_code": "3570670"
  },
  {
    "country": "united states",
    "city": "crested butte",
    "region": "colorado",
    "fips_code": "818310"
  },
  {
    "country": "canada",
    "city": "ancienne-lorette",
    "region": "québec"
  },
  {
    "country": "united states",
    "city": "rehoboth beach",
    "region": "delaware",
    "fips_code": "1060290"
  },
  {
    "country": "australia",
    "city": "orange",
    "region": "australia"
  }
]
```

### S

```json
[
  {
    "country": "united states",
    "city": "cañon city",
    "region": "colorado",
    "fips_code": "0811810"
  },
  {
    "country": "united states",
    "city": "jackson",
    "region": "wyoming",
    "fips_code": "5640120"
  },
  {
    "country": "united states",
    "city": "alvarado",
    "region": "texas",
    "fips_code": "4802260"
  }
]
```

### M

```json
[
  {
    "country": "united states",
    "city": "st. louis park",
    "region": "minnesota",
    "fips_code": "2757220"
  },
  {
    "country": "united states",
    "city": "arcata",
    "region": "california",
    "fips_code": "602476"
  },
  {
    "country": "france",
    "city": "chambéry",
    "region": "rhone-alpes"
  },
  {
    "country": "united states",
    "city": "flagstaff",
    "region": "arizona",
    "fips_code": "0423620"
  }
]
```

### L

```json
[
  {
    "country": "spain",
    "city": "valencia",
    "region": "valencia"
  }
]
```

### XXL

```json
[
  {
    "country": "united states",
    "city": "washington",
    "region": "district of columbia",
    "fips_code": "1150000"
  }
]
```
