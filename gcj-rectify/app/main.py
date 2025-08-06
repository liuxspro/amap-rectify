from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response, Request

from .fetch import reset_async_client
from .rectify import get_tile_gcj_cached, get_tile_wgs_cached
from .utils import get_config, APP_DIR, set_cache_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    # 在启动服务器前重置异步客户端，确保使用新的事件循环
    reset_async_client()
    yield
    # 关闭时执行
    from .fetch import close_async_client_async

    await close_async_client_async()


app = FastAPI(lifespan=lifespan)

cache_dir = get_config().get("cache_dir", "")
if cache_dir == "":
    cache_dir = APP_DIR.parent.parent.joinpath("cache")
    set_cache_dir(cache_dir)
cache_dir = Path(cache_dir)

# print(f"Cache directory: {cache_dir}")
app.state.cache_dir = cache_dir


@app.get("/")
def index():
    return {"message": "Server is Running"}


@app.get("/config")
def get_config(request: Request):
    return {"cache_dir": str(request.app.state.cache_dir)}


@app.get("/tiles/{map_id}/{z}/{x}/{y}")
async def tile(map_id: str, z: int, x: int, y: int, request: Request):
    """
    Get a tile image for the specified map ID, zoom level, and row/column numbers.

    Args:
        map_id (str): The ID of the map.
        z (int): Zoom level.
        x (int): Tile column number.
        y (int): Tile row number.
        request: Fastapi Request
    """
    state_cache_dir = request.app.state.cache_dir
    try:
        if z <= 9:
            # For zoom levels 9 and below, use GCJ02 tiles directly
            img_bytes = await get_tile_gcj_cached(x, y, z, map_id, state_cache_dir)
        else:
            img_bytes = await get_tile_wgs_cached(x, y, z, map_id, state_cache_dir)

        if img_bytes is None:
            # 如果获取瓦片失败，返回空图片或错误响应
            return Response(status_code=500, content="Failed to fetch tile")

        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        print(f"获取瓦片时发生错误: {e}")
        return Response(status_code=500, content="Internal server error")
