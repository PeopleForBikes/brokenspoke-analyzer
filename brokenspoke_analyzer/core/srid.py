"Define SRID functions."
import math
import typing

from osgeo import (
    ogr,
    osr,
)

# Type alias defining a boundary box.
# A BBox is composed of 4 float values: (minx, maxx, miny, maxy)
BBox = typing.Tuple[float, float, float, float]


def check_bbox_latlng(bbox: BBox) -> None:
    """
    Checks to see if the file coordinates are in lat/lng.

    Raises an exception if ``bbox`` is invalid.

    Example:
        >>> santa_rosa_nm_bbox = (-104.714757, -104.629528, 34.905372, 34.955892)
        >>> check_bbox_latlng(santa_rosa_nm_bbox)
        None
    """
    if not all(-180 < point < 180 for point in bbox):
        raise ValueError("This file is already projected.")


def check_bbox_width(bbox: BBox) -> None:
    """
    Checks to see if the bounding box fits in a UTM zone.

    Raises an exception if ``bbox`` is invalid.

    Example:
        >>> santa_rosa_nm_bbox = (-104.714757, -104.629528, 34.905372, 34.955892)
        >>> check_bbox_width(santa_rosa_nm_bbox)
        None
    """
    width = bbox[1] - bbox[0]
    if width > 4:
        raise ValueError("This file is too many degrees wide for UTM")


def get_zone(coord: float) -> int:
    """
    Finds the UTM zone of a WGS84 coordinate.

    There are 60 longitudinal projection zones numbered 1 to 60 starting at
    180W.

    Examples:
        >>> get_zone(-180)
        0
        >>> get_zone(-174)
        1
        >>> get_zone(-168)
        2
    """
    zone = (coord - -180) / 6.0
    return int(math.ceil(zone))


def get_bbox(shapefile: str) -> BBox:
    """
    Gets the bounding box of a shapefile in EPSG 4326.

    If shapefile is not in WGS84, bounds are reprojected.
    """
    driver = ogr.GetDriverByName("ESRI Shapefile")
    data_source = driver.Open(shapefile, 0)
    if data_source is None:
        raise ValueError(f"Could not open {shapefile}")

    # Process the shapefile.
    layer = data_source.GetLayer()
    shape_bbox = layer.GetExtent()
    spatialRef = layer.GetSpatialRef()
    target = osr.SpatialReference()
    target.ImportFromEPSG(4326)

    if target.ExportToProj4() == spatialRef.ExportToProj4():
        return (shape_bbox[0], shape_bbox[1], shape_bbox[2], shape_bbox[3])

    # This check for non-WGS84 projections gets some false positives, but that's ok.
    transform = osr.CoordinateTransformation(spatialRef, target)
    point1 = ogr.Geometry(ogr.wkbPoint)
    point1.AddPoint(shape_bbox[0], shape_bbox[2])
    point2 = ogr.Geometry(ogr.wkbPoint)
    point2.AddPoint(shape_bbox[1], shape_bbox[3])
    point1.Transform(transform)
    point2.Transform(transform)
    return (point1.GetX(), point2.GetX(), point1.GetY(), point2.GetY())


def compute_srid(latitude: float, utm_zone: int) -> str:
    """
    Convert the UTM zone the SRID.

    The format is: 32<hemisphere><2_digit_utm_zone>.

    For ``<hemisphere>``, 6 represents the Northern hemisphere, 7 the southern
    one.

    Example:
        >>> compute_srid(60, 18)
        32618
    """
    # 6 represents the Northern hemisphere, 7 the southern one.
    hemisphere = 7 if latitude < 0 else 6
    return f"32{hemisphere}{utm_zone:02}"


def get_srid(shapefile: str) -> str:
    """Get the SRID of a shapefile."""
    # Get the boundary box.
    bbox = get_bbox(shapefile)

    # Validate it.
    check_bbox_latlng(bbox)
    check_bbox_width(bbox)

    # Compute the UTM zone.
    avg_longitude = ((bbox[1] - bbox[0]) / 2) + bbox[0]
    utm_zone = get_zone(avg_longitude)

    # Compute the average latitude.
    avg_latitude: float = ((bbox[3] - bbox[2]) / 2) + bbox[2]

    # Convert UTM zone to SRID.
    srid = compute_srid(avg_latitude, utm_zone)
    return srid
