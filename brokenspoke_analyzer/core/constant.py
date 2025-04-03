"""Define the general constants."""

from enum import Enum


class ComputePart(str, Enum):
    """Define the possible items to compute."""

    FEATURES = "features"
    STRESS = "stress"
    CONNECTIVITY = "connectivity"


COMPUTE_PARTS_ALL = list(ComputePart)
