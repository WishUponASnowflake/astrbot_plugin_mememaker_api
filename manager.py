# 文件：astrbot_plugin_meme_maker_api/manager.py (性能优化版)

import re
from typing import Dict, Any, List, Optional, Set, Tuple

from astrbot.api import logger

from .api_client import APIClient
from .models import MemeInfo

class MemeManager:
    """负责管理内存中的表情包数据"""

    def __init__(self):
        self.meme_infos: Dict[str, MemeInfo] = {}
        # 【优化】新增 keyword_map，作为关键词到 MemeInfo 的直接映射，实现O(1)查找
        self.keyword_map: Dict[str, MemeInfo] = {}
        self.shortcuts: List[Dict] = []

    async def refresh_memes(self, api_client: APIClient) -> Tuple[bool, int, int]:
        """从 API 刷新表情包数据和快捷指令"""
        logger.info("MemeManager: 正在刷新表情包数据...")
        try:
            infos = await api_client.get_meme_infos()
            
            # 使用临时变量，刷新成功后再一次性替换，保证刷新过程中的线程安全
            meme_infos_temp: Dict[str, MemeInfo] = {info.key: info for info in infos}
            keyword_map_temp: Dict[str, MemeInfo] = {}
            shortcuts_temp: List[Dict] = []

            for info in infos:
                # 建立 keyword_map 索引
                keyword_map_temp[info.key] = info
                for keyword in info.keywords:
                    keyword_map_temp[keyword] = info
                
                # 处理快捷指令
                for sc in info.shortcuts:
                    try:
                        shortcuts_temp.append({
                            "pattern": re.compile(sc["pattern"]), "meme": info, "shortcut": sc
                        })
                    except re.error:
                        logger.warning(f"快捷指令 \"{sc['pattern']}\" 正则表达式无效，已跳过")

            # 一次性更新实例属性
            self.meme_infos = meme_infos_temp
            self.keyword_map = keyword_map_temp
            self.shortcuts = shortcuts_temp
            
            meme_count = len(self.meme_infos)
            shortcut_count = len(self.shortcuts)
            logger.info(f"成功缓存 {meme_count} 个表情和 {shortcut_count} 个快捷指令。")
            return True, meme_count, shortcut_count

        except Exception as e:
            logger.error(f"MemeManager: 刷新表情列表失败: {e}")
            return False, 0, 0

    def find_keyword_in_text(self, text: str, fuzzy_match: bool) -> Optional[str]:
        """在文本中寻找第一个匹配的表情包关键词"""
        first_word = text.split(" ", 1)[0]
        if first_word in self.keyword_map:
            return first_word
        if fuzzy_match:
            # 优化：只对关键词列表进行一次排序
            sorted_keywords = sorted(self.keyword_map.keys(), key=len, reverse=True)
            for keyword in sorted_keywords:
                if text.startswith(keyword):
                    return keyword
        return None

    def find_meme_by_keyword(self, keyword: str) -> Optional[MemeInfo]:
        """【优化】通过关键词精确查找单个表情，现在是O(1)操作"""
        return self.keyword_map.get(keyword)

    def find_memes_by_keyword(self, keyword: str) -> List[MemeInfo]:
        """【优化】根据关键词寻找所有匹配的表情（此函数使用场景少，暂不优化）"""
        # 注意：这个函数的逻辑保持原样，因为它可能需要找到多个同关键词的表情（尽管当前设计是一个关键词只对应一个表情）
        # 如果未来需要优化，可以修改 keyword_map 的值为 List[MemeInfo]
        return [meme for meme in self.meme_infos.values() if keyword in meme.keywords or keyword == meme.key]