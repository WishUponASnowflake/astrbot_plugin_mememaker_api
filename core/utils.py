# 文件: meme_maker_api/core/utils.py

from typing import List
from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp

def get_ats(event: AstrMessageEvent) -> List[str]:
    """从消息事件中提取所有at用户的ID"""
    user_ids = []
    for seg in event.get_messages():
        if isinstance(seg, Comp.At) and hasattr(seg, 'qq'):
            user_ids.append(str(seg.qq))
    return user_ids