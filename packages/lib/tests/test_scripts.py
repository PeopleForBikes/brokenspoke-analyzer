"""Ensure the bundled scripts resolve from the ``bna.lib`` package.

The analysis loads its SQL scripts and its import configuration files through
``importlib.resources``, by package name. A renamed package or a packaging
change that drops them only shows up during a full run otherwise.
"""

from importlib import resources

import pytest

from bna.lib.core import ingestor


@pytest.mark.parametrize("folder", ["connectivity", "features", "stress"])
def test_sql_script_folders_resolve(folder: str) -> None:
    """Ensure each SQL script folder resolves and holds SQL scripts."""
    path = resources.files("bna.lib.scripts.sql") / folder
    assert path.is_dir()
    assert any(entry.name.endswith(".sql") for entry in path.iterdir())


@pytest.mark.parametrize(
    "name",
    ["mapconfig_cycleway.xml", "mapconfig_highway.xml", "pfb.style"],
)
def test_import_configuration_files_resolve(name: str) -> None:
    """Ensure the ingestor finds its osm2pgrouting and osm2pgsql configuration."""
    assert (ingestor.script_dir / name).is_file()
