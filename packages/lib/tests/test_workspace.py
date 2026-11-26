"""Guard the settings every workspace member must share with the root.

uv cannot make members inherit ``[project]`` fields from the workspace root, so
each member repeats ``requires-python``. The root ``pyproject.toml`` is the one
that decides it: these tests fail when a member drifts from it.

A member cannot simply leave ``requires-python`` out either: its wheel would
then carry no ``Requires-Python`` and be tagged ``py2.py3`` instead of ``py3``,
which the ``Dockerfile`` does not install.
"""

import pathlib
import tomllib

# packages/lib/tests/test_workspace.py -> packages/lib -> repository root.
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _project(directory: pathlib.Path) -> dict:
    """Return the ``[project]`` table of a ``pyproject.toml``."""
    with (directory / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]


def _members() -> list[pathlib.Path]:
    """Return the workspace member directories, as the root declares them."""
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as f:
        members = tomllib.load(f)["tool"]["uv"]["workspace"]["members"]
    return [REPOSITORY_ROOT / member for member in members]


def test_the_workspace_declares_its_members() -> None:
    """Ensure the members list matches the member directories."""
    declared = {member.name for member in _members()}
    on_disk = {
        path.parent.name
        for path in (REPOSITORY_ROOT / "packages").glob("*/pyproject.toml")
    }
    assert declared == on_disk


def test_members_require_the_workspace_python_version() -> None:
    """Ensure every member's ``requires-python`` equals the root's."""
    expected = _project(REPOSITORY_ROOT)["requires-python"]
    mismatches = {
        member.name: _project(member).get("requires-python", "<missing>")
        for member in _members()
        if _project(member).get("requires-python") != expected
    }
    message = f"set requires-python = {expected!r} in: {mismatches}"
    assert not mismatches, message
