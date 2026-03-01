set positional-arguments := true

src_dir := "brokenspoke_analyzer"
utils_dir := "utils"
docker_image := "ghcr.io/peopleforbikes/brokenspoke-analyzer"
e2e_test_dir := "integration"
e2e_cities_csv := e2e_test_dir / "e2e-cities.csv"
e2e_cities_json := e2e_test_dir / "e2e-cities.json"

# Meta task running ALL the CI tasks at onces.
ci: lint docs test

# Meta task running all the linters at once.
lint: lint-md lint-python lint-sql lint-uv

# Lint markown files.
lint-md:
    npx --yes markdownlint-cli2 "**/*.md" "#.venv"

# Lint python files.
lint-python:
    uv run isort --check .
    uv run ruff format --check {{ src_dir }} {{ utils_dir }}
    uv run ruff check {{ src_dir }} {{ utils_dir }}
    uv run mypy {{ src_dir }}

# Lint SQL files.
lint-sql:
    uv run sqlfluff lint brokenspoke_analyzer/scripts/sql/

# Check uv.lock is synced
lint-uv:
    uv lock --check

# Meta tasks running all formatters at once.
fmt: fmt-md fmt-python fmt-just

# Format the justfile.
fmt-just:
    just --fmt --unstable

# Format markdown files.
fmt-md:
    npx --yes prettier --write --prose-wrap always "**/*.md"

# Format python files.
fmt-python:
    uv run isort .
    uv run ruff format {{ src_dir }} {{ utils_dir }}
    uv run ruff check --fix {{ src_dir }} {{ utils_dir }}

# Run the unit tests.
test *extra_args='':
    uv run pytest --cov={{ src_dir }} -x $@

# Build the documentation
docs:
    cd docs && uv run make html
    @echo
    @echo "Click this link to open the documentation in the browser:"
    @echo "  file://${PWD}/docs/build/html/index.html"
    @echo

# Rebuild Sphinx documentation on changes, with live-reload in the browser
docs-autobuild:
    uv run sphinx-autobuild docs/source docs/build/html

# Clean the docs
docs-clean:
    rm -fr docs/build

# Build the Docker image for local usage.
docker-build:
    docker buildx build -t {{ docker_image }} --load .

# Build the dev container.
docker-build-devcontainer:
    docker buildx build -t {{ docker_image }}:dev --target dev --load .

docker-prepare-all *args:
    echo "$@"
    docker run --rm \
      -u $(id -u):$(id -g) \
      -v ./data/container:/usr/src/app/data peopleforbikes/brokenspoke-analyzer:latest \
      prepare \
      all \
      --output-dir /usr/src/app/data \
      "$@"

# Spin up Docker Compose.
compose-up:
    docker compose up -d

# Tear down Docker Compose.
compose-down:
    docker compose down
    docker compose rm -sfv
    docker volume rm -f brokenspoke-analyzer_postgres

# Setup the project
setup:
    uv sync --all-extras --dev

# List outdated dependencies from the venv.
list-outdated:
    uv pip list --outdated

# Generate the e2e test files and documentation.

# Uses https://github.com/medialab/xan.
test-e2e-prepare:
    xan sort -s country,region,city {{ e2e_cities_csv }}  -o {{ e2e_cities_csv }}
    xan partition --filename e2e-cities-{}.csv test_size {{ e2e_cities_csv }} -O {{ e2e_test_dir }}
    xan to json {{ e2e_cities_csv }} -o {{ e2e_cities_json }}
    uv run integration/x.py {{ e2e_cities_csv }} {{ e2e_test_dir }}/README.j2
