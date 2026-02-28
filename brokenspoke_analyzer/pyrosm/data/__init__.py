# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=too-many-return-statements
# pylint: disable=protected-access
# pylint: disable=too-many-instance-attributes
# pylint: disable=too-few-public-methods
# pylint: disable=redefined-outer-name

import os
import warnings

from brokenspoke_analyzer.pyrosm.data.bbbike import Cities
from brokenspoke_analyzer.pyrosm.data.geofabrik import (
    Africa,
    Antarctica,
    Asia,
    AustraliaOceania,
    CentralAmerica,
    Europe,
    NorthAmerica,
    SouthAmerica,
    SubRegions,
)
from brokenspoke_analyzer.pyrosm.utils.download import download

__all__ = ["available", "get_download_data"]
_module_path = os.path.dirname(__file__)

class DataSources:
    def __init__(self):
        self.africa = Africa()
        self.antarctica = Antarctica()
        self.asia = Asia()
        self.australia_oceania = AustraliaOceania()
        self.europe = Europe()
        self.north_america = NorthAmerica()
        self.south_america = SouthAmerica()
        self.central_america = CentralAmerica()

        self.cities = Cities()
        self.subregions = SubRegions()

        self.available = {
            "africa": self.africa.available,
            "antarctica": self.antarctica.available,
            "asia": self.asia.available,
            "australia_oceania": self.australia_oceania.available,
            "central_america": self.central_america.available,
            "europe": self.europe.available,
            "north_america": self.north_america.available,
            "south_america": self.south_america.available,
            "cities": self.cities.available,
            "subregions": self.subregions.available,
        }

        # Gather all data sources
        # Keep hidden to avoid encouraging iteration of the whole
        # world at once which most likely would end up
        # in memory error / filling the disk etc.
        self._all_sources = [
            k for k in self.available if k not in ["cities", "subregions"]
        ]

        for _source, available_ in self.available.items():
            self._all_sources += available_

        for subregion in self.subregions.available:
            self._all_sources += self.subregions.__dict__[subregion].available

        self._all_sources = [src.lower() for src in self._all_sources]

        self._all_sources = list(set(self._all_sources))


# Initialize DataSources
sources = DataSources()

available = {
    "regions": {
        k: v for k, v in sources.available.items() if k not in ["cities", "subregions"]
    },
    "subregions": sources.subregions.available,
    "cities": sources.cities.available,
}


def search_source(name):
    for source, available in sources.available.items():
        # Cities are kept as CamelCase, so need to make lower
        if source == "cities":
            available = [src.lower() for src in available]
        if isinstance(available, list):
            if name in available:
                return sources.__dict__[source].__dict__[name]
        elif isinstance(available, dict):
            # Sub-regions should be looked one level further down
            for subregion, available2 in available.items():
                if name in available2:
                    return sources.subregions.__dict__[subregion].__dict__[name]
    raise ValueError(f"Could not retrieve url for '{name}'.")


def get_download_data(dataset):
    """
    Parameters
    ----------
    dataset : str
        The name of the dataset. Run ``pyrosm.data.available`` for
        all available options.
    """

    if dataset in sources._all_sources:
        return search_source(dataset)

    # Users might pass city names with spaces (e.g. Rio De Janeiro)
    if dataset.replace(" ", "") in sources._all_sources:
        return search_source(dataset.replace(" ", ""))

    # Users might pass country names without underscores (e.g. North America)
    if dataset.replace(" ", "_") in sources._all_sources:
        return search_source(dataset.replace(" ", "_"))

    # Users might pass country names with dashes instead of underscores
    # (e.g. canary-islands)
    if dataset.replace("-", "_") in sources._all_sources:
        return search_source(dataset.replace("-", "_"))

    msg = f"The dataset '{dataset}' is not available. "
    msg += f"Available datasets are {', '.join(sources._all_sources)}"
    raise ValueError(msg)
