import os

from brokenspoke_analyzer.core.database import dbcore
from brokenspoke_analyzer.pyrosm import data


def test_truthy():
    assert True


# def test_available_regions():
#     regions = []
#     for region in data.available["regions"]:
#         regions.extend(data.available["regions"][region])
#     subregions = []
#     for subregion in data.available["subregions"]:
#         subregions.extend(data.available["subregions"][subregion])
#     _all = []
#     _all.extend(regions)
#     _all.extend(subregions)
#     _all.extend(data.available["cities"])
#     # print(f"{len(_all)=}")
#     # print(f"{_all=}")
#     _all.sort()
#     for i, v in enumerate(_all):
#         spacer = "   * - " if i % 2 == 0 else "     - "
#         print(f"{spacer}{v.title()}")


# def test_table_exists():
#     """Checks whether a table exists or not."""
#     engine = dbcore.create_psycopg_engine(os.getenv("DATABASE_URL"))
#     res = dbcore.table_exists(engine=engine, table="neighborhood_colleges")
#     assert res == True
