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
