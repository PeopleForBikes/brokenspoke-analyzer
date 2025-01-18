# Contributing

## General guidelines

The Brokenspoke-analyzer project follows the
[BNA Mechanics Contributing Guidelines](https://peopleforbikes.github.io/contributing/).
Refer to them for general principles.

Specific instructions will be described in other sections on this page.

## Developer environment

### Requirements

- [Just] (See the "Administration tasks" section for details)
- [Uv]
- [Python] 3.12+
- [Docker]
- [Osmium]

### Setup

Fork [brokenspoke-analyzer] into your account. Clone your fork for local
development:

```bash
git clone git@github.com:your_username/brokenspoke-analyzer.git
```

Then `cd` into `brokenspoke-analyzer`, and to setup the project and install
dependencies, run:

```bash
uv sync --all-extras --dev
```

#### Database

The [brokenspoke-analyzer] requires a PosgreSQL/PostGIS server to run the
analysis.

We provide 2 options to make it easy for the developpers to set it up:

- a Docker compose file which spins up the server with all the required
  extensions
- a `configure` sub-command which helps configuring the server

## Serving the documentation site

To render the site when adding new content, run the following command:

```bash
just docs-autobuild
```

Then open the <http://127.0.0.1:1111> URL to view the site.

The content will automatically be refreshed when a file is saved on disk.

## Administration tasks

Administration tasks are being provided as convenience in a `justfile`.

More information about [Just] can be found in their repository. The
[installation](https://github.com/casey/just#installation) section of their
documentation will guide you through the setup process.

Run `just -l` to see the list of provided tasks.

[just]: https://github.com/casey/just
[uv]: https://docs.astral.sh/uv/
[python]: https://www.python.org/downloads/
[docker]: https://www.docker.com/get-started/
[osmium]: https://osmcode.org/osmium-tool/

### Running the BNA using Brokenspoke-analyzer

To run using the virtual environment, prefix all your commands with:

```bash
uv run
```

See the
[command reference manual](https://docs.astral.sh/uv/reference/cli/#uv-run) for
more details.

The `brokenspoke-analyzer` can be run using the `bna` script defined in
`pyproject.toml` or by activating the virtual environment that was created by
[uv] inside the project and running the cli commands. To run the modified BNA
for a city in the US, for example Flagstaff, AZ, using the `bna` script:

```bash
uv run bna --help
```

For example to run an analysis for Santa Rosa, NM:

```bash
uv run bna run usa "santa rosa" "new mexico" 3570670
```

[brokenspoke-analyzer]: https://github.com/PeopleForBikes/brokenspoke-analyzer
