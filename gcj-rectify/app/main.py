from fastapi import FastAPI, Response, Request
from .rectify import get_tile_gcj_cached, get_tile_wgs_cached
from .utils import get_config, APP_DIR, set_cache_dir
from pathlib import Path

app = FastAPI()

cache_dir = get_config().get("cache_dir", "")
if cache_dir == "":
    cache_dir = APP_DIR.parent.parent.joinpath("cache")
    set_cache_dir(cache_dir)
cache_dir = Path(cache_dir)

print(f"Cache directory: {cache_dir}")
app.state.cache_dir = cache_dir


@app.get("/")
def index():
    return {"message": "Welcome to the GCJ Rectify Tile Service"}


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
    """
    state_cache_dir = request.app.state.cache_dir
    if z <= 9:
        # For zoom levels 9 and below, use GCJ02 tiles directly
        img_bytes = await get_tile_gcj_cached(x, y, z, map_id, state_cache_dir)
    else:
        img_bytes = await get_tile_wgs_cached(x, y, z, map_id, state_cache_dir)
    return Response(content=img_bytes, media_type="image/png")
