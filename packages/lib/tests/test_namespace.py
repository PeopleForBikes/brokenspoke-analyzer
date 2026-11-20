"""Guard the shared ``bna`` namespace package.

Every workspace member installs its code under ``bna`` (``bna.lib``,
``bna.cli``, ...), which only works while ``bna`` is a PEP 420 namespace
package. A single ``src/bna/__init__.py`` in any member turns ``bna`` into a
regular package rooted in that member, and the other members' subpackages can
no longer be imported.
"""

import pathlib

import bna

# packages/lib/tests/test_namespace.py -> packages/lib -> repository root.
LIB_MEMBER_DIR = pathlib.Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = LIB_MEMBER_DIR.parents[1]


def test_no_member_ships_a_bna_init() -> None:
    """Ensure no workspace member has a ``src/bna/__init__.py``."""
    offenders = sorted(
        str(path.relative_to(REPOSITORY_ROOT))
        for path in REPOSITORY_ROOT.glob("packages/*/src/bna/__init__.py")
    )
    message = f"bna must stay a namespace package; remove: {', '.join(offenders)}"
    assert not offenders, message


def test_bna_is_a_namespace_package() -> None:
    """Ensure ``bna`` imports as a namespace package including this member."""
    assert bna.__file__ is None, f"bna is a regular package from {bna.__file__}"
    # Compare resolved paths: sys.path entries keep symlinks as given.
    portions = {pathlib.Path(portion).resolve() for portion in bna.__path__}
    assert LIB_MEMBER_DIR / "src" / "bna" in portions
