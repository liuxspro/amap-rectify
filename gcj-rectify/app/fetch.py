from typing import Optional

from httpx import AsyncClient

# 全局异步HTTP客户端
_async_client: Optional[AsyncClient] = None


def get_async_client() -> AsyncClient:
    """获取或创建异步HTTP客户端"""
    global _async_client
    if _async_client is None:
        _async_client = AsyncClient(timeout=30.0)
    return _async_client


def close_async_client():
    """关闭异步HTTP客户端（同步版本）"""
    global _async_client
    if _async_client is not None:
        # 强制设置为 None，让下次调用时重新创建
        _async_client = None


async def close_async_client_async():
    """关闭异步HTTP客户端（异步版本）"""
    global _async_client
    if _async_client is not None:
        await _async_client.aclose()
        _async_client = None


def reset_async_client():
    """重置异步HTTP客户端，强制重新创建"""
    global _async_client
    if _async_client is not None:
        _async_client = None


async def fetch_tile(url: str) -> bytes:
    """
    Fetch a tile image from the specified URL using an asynchronous HTTP client.

    Args:
        url (str): The URL to fetch the tile from.

    Returns:
        bytes: The content of the url and its content type.
    Raises:
        Exception: If the request fails or the response status is not 200.
    """
    try:
        client = get_async_client()
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise Exception(f"Failed to fetch tile from {url}")
            content = await response.aread()
            return content
    except Exception as e:
        # 如果出现事件循环相关错误，重置客户端并重试一次
        if "Event loop is closed" in str(e) or "RuntimeError" in str(e):
            reset_async_client()
            client = get_async_client()
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise Exception(f"Failed to fetch tile from {url}")
                content = await response.aread()
                return content
        else:
            raise e
