# 文件：astrbot_plugin_meme_maker_api/api_client.py (最终性能优化版)

import aiohttp
import asyncio
import base64
from typing import Dict, Any, List, Optional

from astrbot.api import logger
from .models import MemeInfo
from .exceptions import APIError

class APIClient:
    def __init__(self, base_url: str, timeout: int):
        self.base_url = base_url
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("APIClient session 已成功关闭。")

    async def _download_image(self, url: str) -> Optional[bytes]:
        """独立的图片下载，因为它不使用 base_url (例如用于下载头像)"""
        try:
            session = await self._get_session()
            headers = {"User-Agent": "Mozilla/5.0"}
            async with session.get(url, headers=headers) as r:
                r.raise_for_status()
                return await r.read()
        except Exception as e:
            logger.error(f"图片下载失败: {url} - {e}")
            return None

    async def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        try:
            async with session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                if "image/" in response.headers.get("Content-Type", ""):
                    return await response.read()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"API 请求失败: {method.upper()} {url} - {e}")
            raise APIError(f"API 请求失败: {e}") from e

    async def get_meme_infos(self) -> List[MemeInfo]:
        data = await self._request("GET", "meme/infos")
        return [MemeInfo.parse_obj(i) for i in data]

    async def upload_image(self, image_bytes: bytes) -> str:
        payload = {"type": "data", "data": base64.b64encode(image_bytes).decode()}
        response_data = await self._request("POST", "image/upload", json=payload)
        return response_data["image_id"]

    async def generate_meme(self, key: str, payload: Dict) -> bytes:
        response_data = await self._request("POST", f"memes/{key}", json=payload)
        image_id = response_data["image_id"]
        image_bytes = await self._request("GET", f"image/{image_id}")
        if not image_bytes: raise APIError("无法从API下载生成的图片")
        return image_bytes

    async def get_meme_preview(self, key: str) -> bytes:
        response_data = await self._request("GET", f"memes/{key}/preview")
        image_id = response_data["image_id"]
        image_bytes = await self._request("GET", f"image/{image_id}")
        if not image_bytes: raise APIError("无法从API下载预览图")
        return image_bytes

    async def render_list_image(self, meme_properties: Dict[str, Dict[str, bool]]) -> bytes:
        payload = { "meme_properties": meme_properties, "sort_by": "keywords_pinyin" }
        response_data = await self._request("POST", "tools/render_list", json=payload)
        image_id = response_data["image_id"]
        image_bytes = await self._request("GET", f"image/{image_id}")
        if not image_bytes: raise APIError("无法从API下载列表图")
        return image_bytes

    async def search_memes(self, query: str, include_tags: bool = True) -> List[str]:
        params = {"query": query, "include_tags": str(include_tags).lower()}
        return await self._request("GET", "meme/search", params=params)

    async def inspect_image(self, image_id: str) -> Dict[str, Any]:
        """查看图片信息"""
        return await self._request(
            "POST",
            "tools/image_operations/inspect",
            json={"image_id": image_id}
        )

    async def _call_image_operation(self, operation: str, payload: Dict) -> bytes:
        response_data = await self._request("POST", f"tools/image_operations/{operation}", json=payload)
        image_id = response_data["image_id"]
        image_bytes = await self._request("GET", f"image/{image_id}")
        if not image_bytes: raise APIError(f"无法从API下载处理后的图片 (op: {operation})")
        return image_bytes
    
    async def flip_horizontal(self, image_id: str) -> bytes: return await self._call_image_operation("flip_horizontal", {"image_id": image_id})
    async def flip_vertical(self, image_id: str) -> bytes: return await self._call_image_operation("flip_vertical", {"image_id": image_id})
    async def grayscale(self, image_id: str) -> bytes: return await self._call_image_operation("grayscale", {"image_id": image_id})
    async def invert(self, image_id: str) -> bytes: return await self._call_image_operation("invert", {"image_id": image_id})
    async def rotate(self, image_id: str, degrees: float) -> bytes: return await self._call_image_operation("rotate", {"image_id": image_id, "degrees": degrees})
    async def resize(self, image_id: str, width: Optional[int], height: Optional[int]) -> bytes: return await self._call_image_operation("resize", {"image_id": image_id, "width": width, "height": height})
    async def crop(self, image_id: str, left: int, top: int, right: int, bottom: int) -> bytes: return await self._call_image_operation("crop", {"image_id": image_id, "left": left, "top": top, "right": right, "bottom": bottom})
    async def merge_horizontal(self, image_ids: List[str]) -> bytes: return await self._call_image_operation("merge_horizontal", {"image_ids": image_ids})
    async def merge_vertical(self, image_ids: List[str]) -> bytes: return await self._call_image_operation("merge_vertical", {"image_ids": image_ids})
    
    async def gif_split(self, image_id: str) -> List[bytes]:
        response_data = await self._request("POST", "tools/image_operations/gif_split", json={"image_id": image_id})
        tasks = [self._request("GET", f"image/{img_id}") for img_id in response_data["image_ids"]]
        return [img for img in await asyncio.gather(*tasks) if img]
        
    async def gif_merge(self, image_ids: List[str], duration: float) -> bytes: return await self._call_image_operation("gif_merge", {"image_ids": image_ids, "duration": duration})
    async def gif_reverse(self, image_id: str) -> bytes: return await self._call_image_operation("gif_reverse", {"image_id": image_id})
    async def gif_change_duration(self, image_id: str, duration: float) -> bytes: return await self._call_image_operation("gif_change_duration", {"image_id": image_id, "duration": duration})

    async def render_statistics(self, title: str, stats_type: str, data: List) -> bytes:
        payload = {"title": title, "statistics_type": stats_type, "data": data}
        response_data = await self._request("POST", "tools/render_statistics", json=payload)
        image_id = response_data["image_id"]
        image_bytes = await self._request("GET", f"image/{image_id}")
        if not image_bytes: raise APIError("无法从API下载统计图")
        return image_bytes