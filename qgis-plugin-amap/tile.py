import asyncio
from io import BytesIO
from math import atan, cos, log, pi, sinh, tan
from typing import Optional

import httpx
import requests
from PIL import Image

# 来自 Geohey 的转换算法 https://github.com/GeoHey-Team/qgis-geohey-toolbox
from .transform import wgs2gcj
from .utils import CACHE_DIR

AMAP_HOST = "https://wprd02.is.autonavi.com"

amap_url = {
    "vec": f"{AMAP_HOST}/appmaptile?lang=zh_cn&size=1&scale=1&style=7&x={{x}}&y={{y}}&z={{z}}",
    "vec_note": f"{AMAP_HOST}/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={{x}}&y={{y}}&z={{z}}",
}

amap_name = {"vec": "矢量地图", "vec_note": "矢量注记"}

# 全局异步HTTP客户端
_async_client: Optional[httpx.AsyncClient] = None


def get_async_client() -> httpx.AsyncClient:
    """获取或创建异步HTTP客户端"""
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(timeout=30.0)
    return _async_client


async def close_async_client():
    """关闭异步HTTP客户端"""
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None


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


async def get_tile_gcj_async(x: int, y: int, z: int, mapid: str) -> Image:
    """
    异步获取指定瓦片的图像，如果缓存中存在则直接返回，否则从服务器下载。
    这里下载的是高德地图的GCJ02坐标系瓦片。
    该函数会检查缓存目录，如果瓦片已经存在，则直接从缓存中读取并返回。

    Args:
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.
        z (int): Zoom level.
        mapid (str): Map Id

    Returns:
        Image: Tile image.
    """
    url = amap_url[mapid]
    url = url.format(x=x, y=y, z=z)
    map_name = amap_name[mapid]

    # 如果缓存中存在，直接返回缓存的瓦片
    tile_file_path = CACHE_DIR.joinpath(f"./{map_name}/gcj/{z}/{x}/{y}.png")
    if tile_file_path.exists():
        return Image.open(tile_file_path)

    # 使用异步HTTP客户端获取瓦片
    client = get_async_client()
    async with client.stream("GET", url) as response:
        if response.status_code != 200:
            raise Exception(f"Failed to fetch tile from {url}")

        # 读取响应内容
        content = await response.aread()

        # 保存瓦片图像到缓存
        file_path = CACHE_DIR.joinpath(f"./{map_name}/gcj/{z}/{x}/{y}.png")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

        return Image.open(BytesIO(content))


def get_tile_gcj(x: int, y: int, z: int, mapid: str) -> Image:
    """
    获取指定瓦片的图像，如果缓存中存在则直接返回，否则从服务器下载。
    这里下载的是高德地图的GCJ02坐标系瓦片。
    该函数会检查缓存目录，如果瓦片已经存在，则直接从缓存中读取并返回。

    Args:
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.
        z (int): Zoom level.
        mapid (str): Map Id

    Returns:
        Image: Tile image.
    """
    url = amap_url[mapid]
    url = url.format(x=x, y=y, z=z)
    map_name = amap_name[mapid]
    # if in cache, return the cached tile
    tile_file_path = CACHE_DIR.joinpath(f"./{map_name}/gcj/{z}/{x}/{y}.png")
    if tile_file_path.exists():
        return Image.open(tile_file_path)

    r = requests.get(url)
    if r.status_code != 200:
        raise Exception(f"Failed to fetch tile from {url}")
    # save the tile image to cache
    file_path = CACHE_DIR.joinpath(f"./{map_name}/gcj/{z}/{x}/{y}.png")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(r.content)
    return Image.open(BytesIO(r.content))


async def get_tile_async(x: int, y: int, z: int, mapid: str) -> Image:
    """
    异步获取瓦片，支持高精度坐标转换
    """
    map_name = amap_name[mapid]
    # 小于 9 级时 没有明显的偏移 直接使用 GCJ02 坐标系的瓦片
    if z <= 9:
        return await get_tile_gcj_async(x, y, z, mapid)

    # 如果缓存中存在，直接返回缓存的瓦片
    tile_file_path = CACHE_DIR.joinpath(f"./{map_name}/wgs/{z}/{x}/{y}.png")
    if tile_file_path.exists():
        return Image.open(tile_file_path)

    wgs_bbox = xyz_to_bbox(x, y, z)
    gcj_bbox = wgsbbox_to_gcjbbox(wgs_bbox)
    left_upper, right_lower = gcj_bbox

    # 计算左上角和右下角的瓦片行列号
    x_min, y_min = lonlat_to_xyz(left_upper[0], left_upper[1], z)  # 左上角
    x_max, y_max = lonlat_to_xyz(right_lower[0], right_lower[1], z)  # 右下角

    # 创建任务列表，异步获取所有需要的瓦片
    tasks = []
    for ax in range(x_min, x_max + 1):
        for ay in range(y_min, y_max + 1):
            tasks.append(get_tile_gcj_async(ax, ay, z, mapid))

    # 并发执行所有瓦片下载任务
    tiles = await asyncio.gather(*tasks)

    # 拼合瓦片
    composite = Image.new(
        "RGBA", ((x_max - x_min + 1) * 256, (y_max - y_min + 1) * 256)
    )

    tile_index = 0
    for i, ax in enumerate(range(x_min, x_max + 1)):
        for j, ay in enumerate(range(y_min, y_max + 1)):
            tile = tiles[tile_index]
            if tile:
                composite.paste(tile, (i * 256, j * 256))
            tile_index += 1

    # 计算拼合后的瓦片范围
    megred_bbox = xyz_to_bbox(x_min, y_min, z)[0], xyz_to_bbox(x_max, y_max, z)[1]

    x_range = megred_bbox[1][0] - megred_bbox[0][0]
    y_range = megred_bbox[0][1] - megred_bbox[1][1]

    left_percent = (gcj_bbox[0][0] - megred_bbox[0][0]) / x_range
    top_percent = (megred_bbox[0][1] - gcj_bbox[0][1]) / y_range
    img_width, img_height = composite.size
    # 裁剪选区(left, top, right, bottom)
    crop_bbox = (
        int(left_percent * img_width),
        int(top_percent * img_height),
        int(left_percent * img_width) + 256,
        int(top_percent * img_height) + 256,
    )

    # 从拼合的瓦片中裁剪出对应的区域
    croped_image = composite.crop(crop_bbox)
    wgs_tile_path = CACHE_DIR.joinpath(f"./{map_name}/wgs/{z}/{x}/{y}.png")
    wgs_tile_path.parent.mkdir(parents=True, exist_ok=True)
    croped_image.save(wgs_tile_path)
    return croped_image
