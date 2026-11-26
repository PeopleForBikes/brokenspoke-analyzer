set positional-arguments

pkg := "packages"
lib_pkg := pkg / "lib"
cache_warmer_pkg := pkg / "cache-warmer"
cli_pkg := pkg / "cli"
batch_pkg := pkg / "batch"
src_dirs := lib_pkg / "src" + " " + cli_pkg / "src" + " " + cache_warmer_pkg / "src" + " " + batch_pkg / "src"
test_dirs := lib_pkg / "tests" + " " + cli_pkg / "tests" + " " + cache_warmer_pkg / "tests" + " " + batch_pkg / "tests"
sql_dir := lib_pkg / "src/bna/lib/scripts/sql"
utils_dir := "utils"
docker_image := "ghcr.io/peopleforbikes/brokenspoke-analyzer"
e2e_test_dir := "integration"
e2e_cities_csv := e2e_test_dir / "e2e-cities.csv"
e2e_cities_json := e2e_test_dir / "e2e-cities.json"

# Meta task running ALL the CI tasks at onces.
ci: lint docs test check-wheels

# Meta task running all the linters at once.
lint: lint-md lint-python lint-sql lint-uv

# Lint markown files.
lint-md:
    npx --yes markdownlint-cli2 "**/*.md" "#.venv"

# Lint python files.
lint-python:
    uv run isort --check .
    uv run ruff format --check {{ src_dirs }} {{ test_dirs }} {{ utils_dir }}
    uv run ruff check {{ src_dirs }} {{ test_dirs }} {{ utils_dir }}
    uv run ty check {{ src_dirs }} {{ test_dirs }}

# Lint SQL files.
# Only the repository configuration is read, in a single process, so the
# recipe also runs inside sandboxes denying access outside the repository.
lint-sql:
    uv run sqlfluff lint --ignore-local-config --config pyproject.toml --processes 1 {{ sql_dir }}

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
    uv run ruff format {{ src_dirs }} {{ test_dirs }} {{ utils_dir }}
    uv run ruff check --fix {{ src_dirs }} {{ test_dirs }} {{ utils_dir }}

# Run the unit tests across all the workspace members.
test *extra_args='':
    uv run pytest --cov=bna.lib --cov=bna.cli --cov=bna.cache_warmer --cov=bna.batch -x $@

# Build every member's wheel and check its contents.
check-wheels:
    #!/usr/bin/env bash
    set -euo pipefail
    wheel_dir="$(mktemp -d)"
    trap 'rm -rf "${wheel_dir}"' EXIT
    uv build --all-packages --wheel --quiet --out-dir "${wheel_dir}"
    uv run python utils/check_wheels.py "${wheel_dir}"

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
      -v ./data/container:/usr/src/app/data {{ docker_image }}:dev \
      prepare \
      --no-cache \
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
test-e2e-prepare:
    xan sort -s country,region,city {{ e2e_cities_csv }}  -o {{ e2e_cities_csv }}
    xan partition --filename e2e-cities-{}.csv test_size {{ e2e_cities_csv }} -O {{ e2e_test_dir }}
    xan to json {{ e2e_cities_csv }} --strings fips_code -o {{ e2e_cities_json }}
    uv run integration/x.py {{ e2e_cities_csv }} {{ e2e_test_dir }}/README.j2
    npx --yes prettier --write --prose-wrap always {{ e2e_test_dir }}/README.md

# Use nono sandbox to login with Claude.
nono-claude-login:
    nono run --profile nolabs-ai/claude --allow-launch-services -- claude "/login"

# Use nono sandbox for Claude.
nono-claude profile="pfb-claude":
    nono run --allow-cwd --profile {{ profile }} -- claude

# Use nono sandbox for Claude -- no internet, skip-permissions.
nono-claude-danger profile="pfb-claude":
    nono run \
    --allow-cwd \
    --profile {{ profile }} \
    -- claude --dangerously-skip-permissions
