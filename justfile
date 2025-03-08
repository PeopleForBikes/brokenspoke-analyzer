set positional-arguments := true

src_dir := "brokenspoke_analyzer"
docker_image := "ghcr.io/peopleforbikes/brokenspoke-analyzer"

# Meta task running ALL the CI tasks at onces.
ci: lint docs test

# Meta task running all the linters at once.
lint: lint-md lint-python lint-sql

# Lint markown files.
lint-md:
    npx --yes markdownlint-cli2 "**/*.md" "#.venv"

# Lint python files.
lint-python:
    uv run isort --check .
    uv run ruff format --check {{ src_dir }}
    uv run ruff check {{ src_dir }}
    uv run mypy {{ src_dir }}

# Lint SQL files.
lint-sql:
    uv run sqlfluff lint brokenspoke_analyzer/scripts/sql/

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
    uv run ruff format {{ src_dir }}
    uv run ruff check --fix {{ src_dir }}

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
