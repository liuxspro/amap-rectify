# amap-rectify
Rectify the map from GCJ-02 to WGS-84 coordinate system

see: https://garden.liuxs.pro/amap-rectify



Run server without qgis:

```bash
uv run uvicorn gcj-rectify.app.main:app --reload
```