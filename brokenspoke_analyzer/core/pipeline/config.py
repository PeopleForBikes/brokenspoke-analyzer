"""
Define the runtime constants driving the BNA computation.

Hold the tolerances, path constraints, and scoring weights the pipeline runs
with. These dataclasses are the single source of truth for those values: the
SQL scripts never carried defaults of their own, they received these as bound
parameters at runtime, and the weights quoted in the SQL comment blocks are
stale and illustrative. Treat the values here as authoritative and port them
unchanged -- altering one changes published scores.
"""

import dataclasses


@dataclasses.dataclass
class Tolerance:
    """Cluster tolerances given in units of `output_srid`."""

    colleges: int = 100
    community_centers: int = 50
    doctors: int = 50
    dentists: int = 50
    hospitals: int = 50
    pharmacies: int = 50
    parks: int = 50
    retail: int = 50
    transit: int = 75
    universities: int = 150


@dataclasses.dataclass
class PathConstraint:
    """Define the Path Constraints."""

    # Minimum path length to be considered for recreation access.
    min_length: int = 4800
    # Minimum corner-to-corner span of path bounding box to be considered for
    # recreation access.
    min_bbox: int = 3300


@dataclasses.dataclass
class BlockRoad:
    """Define the Block Road items."""

    # Buffer distance to find roads associated with a block.
    buffer: int = 15
    # Minimum length road must overlap with block buffer to be associated .
    min_length: int = 30


@dataclasses.dataclass
class Score:
    """Define the Score parts."""

    total: int = 100
    people: int = 15
    opportunity: int = 20
    core_services: int = 20
    retail: int = 15
    recreation: int = 15
    transit: int = 15


@dataclasses.dataclass
class Access:
    """Define the Access parts."""

    name: str
    first: float = 0.0
    second: float = 0.0
    third: float = 0.0
    max_score: int = 1
