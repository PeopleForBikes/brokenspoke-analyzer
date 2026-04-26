"""Define the general constants."""

import enum

APPNAME = "brokenspoke-analyzer"
APPAUTHOR = "PeopleForBikes"


class ComputePart(enum.StrEnum):
    """Define the possible items to compute."""

    FEATURES = "features"
    STRESS = "stress"
    CONNECTIVITY = "connectivity"
    MEASURE = "measure"


COMPUTE_PARTS_ALL = list(ComputePart)
GDF_CLASS_BOUNDARY = "boundary"
