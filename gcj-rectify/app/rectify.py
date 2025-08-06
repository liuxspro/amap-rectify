import asyncio
from io import BytesIO
from pathlib import Path

from PIL import Image

from .fetch import fetch_tile
from .utils import (
    xyz_to_bbox,
    wgsbbox_to_gcjbbox,
    lonlat_to_xyz,
    image_to_bytes,
    bytes_to_image,
    get_maps,
)

map_data = get_maps()


async def get_tile_gcj(x: int, y: int, z: int, mapid: str) -> bytes:
    """
    获取指定瓦片的图像，这里下载的是原始瓦片(GCJ02 坐标系)。
    Args:
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.
        z (int): Zoom level.
        mapid (str): Map Id
    Returns:
        bytes: Tile image bytes.
    """
    url = map_data[mapid]["url"]
    if "-y" in url:
        # 如果 URL 中包含 -y，认为是TMS格式，需要调整 Y 值
        url = url.replace("-y", "y")
        url = url.format(x=x, y=(2**z - 1 - y), z=z)
    else:
        url = url.format(x=x, y=y, z=z)

    # 使用异步HTTP客户端获取瓦片
    content = await fetch_tile(url)

    return content


async def get_tile_gcj_cached(
    x: int, y: int, z: int, mapid: str, cache_dir: Path = Path.cwd().joinpath("cache")
) -> Image:
    """
    获取指定瓦片的图像，使用缓存。
    Args:
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.
        z (int): Zoom level.
        mapid (str): Map Id
        cache_dir (str): 缓存目录
    Returns:
        Image: Tile image.
    """
    tile_file_path = cache_dir.joinpath(f"{mapid}/GCJ/{z}/{x}/{y}.png")
    if tile_file_path.exists():
        # print(f"从缓存中获取了瓦片: {tile_file_path}")
        image = Image.open(tile_file_path)
        return image_to_bytes(image)
    # 如果缓存不存在，则下载瓦片并保存到缓存
    tile_file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image_bytes = await get_tile_gcj(x, y, z, mapid)
        image = bytes_to_image(image_bytes)
        image.save(tile_file_path, "PNG")
    except Exception as e:
        print(f"获取瓦片失败: {e}")
        # 如果是事件循环错误，尝试重置客户端并重试
        if "Event loop is closed" in str(e) or "RuntimeError" in str(e):
            from .fetch import reset_async_client

            reset_async_client()
            try:
                image_bytes = await get_tile_gcj(x, y, z, mapid)
                image = bytes_to_image(image_bytes)
                image.save(tile_file_path, "PNG")
            except Exception as retry_e:
                print(f"重试获取瓦片失败: {retry_e}")
                return None
        else:
            return None

    return image_bytes


async def get_tile_wgs(x: int, y: int, z: int, mapid: str) -> Image:
    """
    获取瓦片(调整为 WGS84 坐标系)
    """
    if z <= 9:
        print("Z 小于 9 时 没有明显的偏移 直接使用 GCJ02 坐标系的瓦片")
        return

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
            tasks.append(get_tile_gcj_cached(ax, ay, z, mapid))

    # 并发执行所有瓦片下载任务
    tiles = await asyncio.gather(*tasks)
    tile_images = [Image.open(BytesIO(content)) for content in tiles]

    # 拼合瓦片
    composite = Image.new(
        "RGBA", ((x_max - x_min + 1) * 256, (y_max - y_min + 1) * 256)
    )

    tile_index = 0
    for i, ax in enumerate(range(x_min, x_max + 1)):
        for j, ay in enumerate(range(y_min, y_max + 1)):
            tile = tile_images[tile_index]
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
    return image_to_bytes(croped_image)


async def get_tile_wgs_cached(
    x: int, y: int, z: int, mapid: str, cache_dir: Path = Path.cwd().joinpath("cache")
) -> Image:
    """
    获取指定瓦片的图像，使用缓存。
    Args:
        x (int): Tile X coordinate.
        y (int): Tile Y coordinate.
        z (int): Zoom level.
        mapid (str): Map Id
        cache_dir (str): 缓存目录
    Returns:
        Image: Tile image.
    """
    tile_file_path = cache_dir.joinpath(f"{mapid}/WGS/{z}/{x}/{y}.png")
    if tile_file_path.exists():
        # print(f"从缓存中获取了瓦片: {tile_file_path}")
        image = Image.open(tile_file_path)
        return image_to_bytes(image)
    # 如果缓存不存在，则下载瓦片并保存到缓存
    tile_file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image_bytes = await get_tile_wgs(x, y, z, mapid)
        image = bytes_to_image(image_bytes)
        image.save(tile_file_path, "PNG")
    except Exception as e:
        print(f"获取WGS瓦片失败: {e}")
        # 如果是事件循环错误，尝试重置客户端并重试
        if "Event loop is closed" in str(e) or "RuntimeError" in str(e):
            from .fetch import reset_async_client

            reset_async_client()
            try:
                image_bytes = await get_tile_wgs(x, y, z, mapid)
                image = bytes_to_image(image_bytes)
                image.save(tile_file_path, "PNG")
            except Exception as retry_e:
                print(f"重试获取WGS瓦片失败: {retry_e}")
                return None
        else:
            return None

    return image_bytes


# 测试


# http://127.0.0.1:8000/tiles/amap-sat/11/1661/807
# https://wprd02.is.autonavi.com//appmaptile?lang=zh_cn&size=1&scale=1&style=6&x=1661&y=807&z=11
