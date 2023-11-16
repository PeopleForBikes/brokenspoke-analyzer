from brokenspoke_analyzer.pyrosm import data


def test_truthy():
    assert True


def test_available_regions():
    regions = []
    for region in data.available["regions"]:
        regions.extend(data.available["regions"][region])
    subregions = []
    for subregion in data.available["subregions"]:
        subregions.extend(data.available["subregions"][subregion])
    _all = []
    _all.extend(regions)
    _all.extend(subregions)
    _all.extend(data.available["cities"])
    # print(f"{len(_all)=}")
    # print(f"{_all=}")
    _all.sort()
    for i, v in enumerate(_all):
        spacer = "   * - " if i % 2 == 0 else "     - "
        print(f"{spacer}{v.title()}")
