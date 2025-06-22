#!/usr/bin/env python3
"""
测试异步瓦片获取功能
"""

import asyncio
import time
from tile import get_tile_gcj_async, get_tile_gcj, close_async_client

async def test_async_tile_download():
    """测试异步瓦片下载"""
    print("开始测试异步瓦片下载...")
    
    # 测试参数
    x, y, z = 13523, 6531, 14
    mapid = "vec"
    
    start_time = time.time()
    
    try:
        # 异步下载瓦片
        image = await get_tile_gcj_async(x, y, z, mapid)
        async_time = time.time() - start_time
        print(f"异步下载完成，耗时: {async_time:.2f}秒")
        print(f"图像大小: {image.size}")
        
        # 测试同步下载作为对比
        start_time = time.time()
        image_sync = get_tile_gcj(x, y, z, mapid)
        sync_time = time.time() - start_time
        print(f"同步下载完成，耗时: {sync_time:.2f}秒")
        print(f"图像大小: {image_sync.size}")
        
        # 测试并发下载多个瓦片
        print("\n测试并发下载多个瓦片...")
        start_time = time.time()
        
        tasks = []
        for i in range(4):
            tasks.append(get_tile_gcj_async(x + i, y, z, mapid))
        
        images = await asyncio.gather(*tasks)
        concurrent_time = time.time() - start_time
        print(f"并发下载4个瓦片完成，耗时: {concurrent_time:.2f}秒")
        
        # 对比串行下载
        start_time = time.time()
        for i in range(4):
            get_tile_gcj(x + i, y, z, mapid)
        serial_time = time.time() - start_time
        print(f"串行下载4个瓦片完成，耗时: {serial_time:.2f}秒")
        
        print(f"\n性能提升: {serial_time/concurrent_time:.2f}x")
        
    except Exception as e:
        print(f"测试失败: {e}")
    finally:
        # 关闭异步客户端
        await close_async_client()

if __name__ == "__main__":
    asyncio.run(test_async_tile_download()) 