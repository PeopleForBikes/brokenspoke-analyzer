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

# Default values shared by the library and its frontends.
DEFAULT_BUFFER = 2680
DEFAULT_CITY_FIPS_CODE = "0"  # "0" means an non-US city.
DEFAULT_COMPUTE_PARTS = COMPUTE_PARTS_ALL
DEFAULT_MAX_TRIP_DISTANCE = 2680
