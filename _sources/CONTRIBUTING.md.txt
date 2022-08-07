# Contributing

## General guidelines

The Brokenspoke-analyzer project follows the
[BNA Mechanics Contributing Guidelines](https://peopleforbikes.github.io/contributing/).
Refer to them for general principles.

Specific instructions will be described in other sections on this page.

## Developer environment

### Requirements

- [Just] (See the "Administration tasks" section for details)
- [Poetry]
- [Python] 3.10+

### Setup

```bash
poetry install
```

## Serving the documentation site

To render the site when adding new content, run the following command:

```bash
just docs-autobuild
```

Then open the <http://127.0.0.1:1111> URL to view the site.

The content will automatically be refreshed when a file is saved on disk.

## Administration tasks

Administration tasks are being provided as convenience in a `justfile`.

More information about [Just] can be find in their repository. The
[installation](https://github.com/casey/just#installation) section of their
documentation will guide you through the setup process.

Run `just -l` to see the list of provided tasks.

[just]: https://github.com/casey/just
[poetry]: https://python-poetry.org/
[python]: https://www.python.org/downloads/
