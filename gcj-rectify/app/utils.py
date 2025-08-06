import json
from io import BytesIO
from math import atan, cos, log, pi, sinh, tan
from pathlib import Path

from PIL import Image

from .transform import wgs2gcj

APP_DIR = Path(__file__).parent


def get_config():
    return json.load(open(str(APP_DIR.joinpath("config.json")), "r", encoding="utf-8"))


def get_maps():
    return json.load(open(str(APP_DIR.joinpath("maps.json")), "r", encoding="utf-8"))


def save_config(config):
    with open(str(APP_DIR.joinpath("config.json")), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def set_cache_dir(cache_dir: Path):
    """
    Set the cache directory in the configuration file.

    Args:
        cache_dir (str): The path to the cache directory.
    """
    config = get_config()
    config["cache_dir"] = str(cache_dir)
    save_config(config)


def bytes_to_image(content: bytes) -> Image:
    """
    Convert bytes to a PIL Image.

    Args:
        content (bytes): Image data in bytes.

    Returns:
        Image: PIL Image object.
    """
    return Image.open(BytesIO(content))


def image_to_bytes(image: Image, format: str = "PNG") -> bytes:
    """
    Convert a PIL Image to bytes.

    Args:
        image (Image): PIL Image object.
        format (str): Format to save the image, default is "PNG".

    Returns:
        bytes: Image data in bytes.
    """
    img_buffer = BytesIO()
    image.save(img_buffer, format=format)
    img_bytes = img_buffer.getvalue()
    img_buffer.close()
    return img_bytes


def xyz_to_lonlat(x: int, y: int, z: int) -> tuple:
    """
    将XYZ瓦片坐标转换为经纬度（左上角点）。

    Args:
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.
        z (int): Zoom level.

    Returns:
        tuple: Longitude and latitude in degrees.
    """
    n = 2.0**z
    lon_deg = x / n * 360.0 - 180.0
    lat_rad = atan(sinh(pi * (1 - 2 * y / n)))
    lat_deg = lat_rad * 180.0 / pi
    return lon_deg, lat_deg


def lonlat_to_xyz(lon: float, lat: float, z: int) -> tuple:
    """
    Convert longitude and latitude to XYZ tile coordinates.

    Args:
        lon (float): Longitude in degrees.
        lat (float): Latitude in degrees.
        z (int): Zoom level.

    Returns:
        tuple: Tile X and Y coordinates.
    """
    n = 2.0**z
    x = (lon + 180.0) / 360.0 * n
    lat_rad = lat * pi / 180.0
    t = log(tan(lat_rad) + 1 / cos(lat_rad))
    y = (1 - t / pi) * n / 2
    return int(x), int(y)


def xyz_to_bbox(x, y, z):
    """
    Convert XYZ tile coordinates to bounding box coordinates.

    Args:
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.
        z (int): Zoom level.

    Returns:
        tuple: Bounding box in the format (min_lon, min_lat, max_lon, max_lat).
    """
    left_upper_lon, left_upper_lat = xyz_to_lonlat(x, y, z)
    right_lower_lon, right_lower_lat = xyz_to_lonlat(x + 1, y + 1, z)

    return (left_upper_lon, left_upper_lat), (right_lower_lon, right_lower_lat)


def wgsbbox_to_gcjbbox(wgs_bbox):
    """
    Convert WGS84 bounding box to GCJ02 bounding box.

    Args:
        wgs_bbox (tuple): Bounding box in the format (min_lon, min_lat, max_lon, max_lat).

    Returns:
        tuple: GCJ02 bounding box in the same format.
    """
    left_upper, right_lower = wgs_bbox
    gcj_left_upper = wgs2gcj(left_upper[0], left_upper[1])
    gcj_right_lower = wgs2gcj(right_lower[0], right_lower[1])
    return gcj_left_upper, gcj_right_lower
