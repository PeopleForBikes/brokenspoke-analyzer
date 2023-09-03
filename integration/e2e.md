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
bna configure docker
bna prepare all usa "santa rosa" "new mexico" 3570670
bna import all usa "santa rosa" "new mexico" 3570670 --input-dir data/santa-rosa-new-mexico-usa
bna compute usa "santa rosa" "new mexico" --input-dir data/santa-rosa-new-mexico-usa
bna export local-calver usa "santa rosa" "new mexico"
docker-compose rm -sfv && docker volume rm brokenspoke-analyzer_postgres
```

## L'Ancienne-Lorette, Québec

```bash
docker compose up -d
bna configure docker
bna prepare all canada "ancienne-lorette" québec
bna import all canada "ancienne-lorette" québec --input-dir data/ancienne-lorette-quebec-canada
bna compute canada "ancienne-lorette" québec --input-dir data/ancienne-lorette-quebec-canada
bna export local-calver canada "ancienne-lorette" québec
docker-compose rm -sfv && docker volume rm brokenspoke-analyzer_postgres
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
# docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL peopleforbikes/bna:latest configure docker
# Use `docker info to get the `CPUs` and `Total Memory`.
docker run --rm --network brokenspoke-analyzer_default -e DATABASE_URL peopleforbikes/bna:latest configure custom 4 1943 postgres
docker run --rm -v ./data/container:/usr/src/app/data peopleforbikes/bna:latest prepare all usa "santa rosa" "new mexico" 3570670 --output-dir /usr/src/app/data
docker run --rm --network brokenspoke-analyzer_default -v ./data/container:/usr/src/app/data -e DATABASE_URL peopleforbikes/bna:latest import all usa "santa rosa" "new mexico" 3570670 --input-dir /usr/src/app/data/santa-rosa-new-mexico-usa
docker run --rm --network brokenspoke-analyzer_default -v ./data/container:/usr/src/app/data -e DATABASE_URL peopleforbikes/bna:latest compute usa "santa rosa" "new mexico" --input-dir /usr/src/app/data/santa-rosa-new-mexico-usa
```

## Might be useful later

- <https://stackoverflow.com/questions/55977611/how-to-connect-docker-compose-to-container-network-and-localhost-network>
