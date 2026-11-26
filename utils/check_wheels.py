"""Check the contents of the workspace members' wheels.

Every workspace member ships its code under the shared ``bna`` namespace
package. This script checks the wheels built from the members:

- every member under ``packages/`` has a wheel;
- no wheel contains ``bna/__init__.py``, which would break the namespace for
  every other member once installed;
- each wheel holds exactly its member's source files (everything under
  ``packages/<member>/src/`` that git tracks or does not ignore, which is what
  hatchling packages), plus its ``.dist-info`` metadata.

Usage::

    uv run python utils/check_wheels.py <directory holding the wheels>
"""

import pathlib
import subprocess
import sys
import zipfile

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPOSITORY_ROOT / "packages"
NAMESPACE_INIT = "bna/__init__.py"


def member_name(wheel: pathlib.Path) -> str:
    """Return the name of the member directory a wheel was built from.

    Parameters
    ----------
    wheel
        Path of a wheel, named after its distribution (``bna_<member>-…``).

    Returns
    -------
    str
        The member directory name under ``packages/``.

    Examples
    --------
    >>> member_name(pathlib.Path("bna_cache_warmer-3.3.0-py3-none-any.whl"))
    'cache-warmer'
    """
    distribution = wheel.name.split("-", 1)[0]
    return distribution.removeprefix("bna_").replace("_", "-")


def source_files(member: pathlib.Path) -> set[str]:
    """List the files hatchling packages from a member.

    Parameters
    ----------
    member
        The member directory, e.g. ``packages/lib``.

    Returns
    -------
    set[str]
        Paths relative to the member's ``src/`` directory, for every file git
        tracks or does not ignore.
    """
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=member / "src",
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {name for name in listing.split("\0") if name}


def wheel_files(wheel: pathlib.Path) -> set[str]:
    """List the files of a wheel, without its ``.dist-info`` metadata.

    Parameters
    ----------
    wheel
        Path of the wheel.

    Returns
    -------
    set[str]
        Paths of the files inside the wheel.
    """
    with zipfile.ZipFile(wheel) as archive:
        return {
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and not name.split("/", 1)[0].endswith(".dist-info")
        }


def check_wheel(wheel: pathlib.Path) -> list[str]:
    """Check one wheel against its member's source files.

    Parameters
    ----------
    wheel
        Path of the wheel.

    Returns
    -------
    list[str]
        One message per problem; empty when the wheel is correct.
    """
    member = PACKAGES_DIR / member_name(wheel)
    if not (member / "pyproject.toml").is_file():
        return [f"{wheel.name}: no workspace member at packages/{member.name}"]
    shipped = wheel_files(wheel)
    expected = source_files(member)
    problems = []
    if NAMESPACE_INIT in shipped:
        problems.append(
            f"{wheel.name}: ships {NAMESPACE_INIT}, which breaks the shared "
            "bna namespace package",
        )
    problems.extend(
        f"{wheel.name}: unexpected file {name}"
        for name in sorted(shipped - expected - {NAMESPACE_INIT})
    )
    problems.extend(
        f"{wheel.name}: missing file {name}" for name in sorted(expected - shipped)
    )
    return problems


def main(argv: list[str]) -> int:
    """Check every member's wheel in a directory.

    Parameters
    ----------
    argv
        The command line: the script name and the directory holding the wheels.

    Returns
    -------
    int
        0 when every wheel is correct.

    Raises
    ------
    SystemExit
        With the list of problems, when the usage is wrong or a wheel is not
        correct.
    """
    if len(argv) != 2:  # noqa: PLR2004
        sys.exit(f"usage: {argv[0]} <directory holding the wheels>")
    wheels = sorted(pathlib.Path(argv[1]).glob("bna_*.whl"))
    members = {path.parent.name for path in PACKAGES_DIR.glob("*/pyproject.toml")}
    problems = [
        f"no wheel for packages/{name}"
        for name in sorted(members - {member_name(wheel) for wheel in wheels})
    ]
    problems.extend(problem for wheel in wheels for problem in check_wheel(wheel))
    if problems:
        sys.exit("\n".join(problems))
    sys.stdout.write(f"{len(wheels)} wheels checked: all correct.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
