# 文件：astrbot_plugin_meme_maker_api/handlers/help.py

from datetime import datetime, timedelta, timezone
from typing import Dict

from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp
from astrbot.api import logger

class HelpHandlers:
    """一个 Mixin 类，只包含表情列表指令的处理器"""

    async def handle_meme_list(self, event: AstrMessageEvent, _=None):
        try:
            logger.info("开始生成动态表情包列表图...")
            # 1. 先发送“正在生成”的提示，这部分保持不变
            yield event.plain_result("正在生成动态列表，请稍候...")

            # 2. 生成列表图的逻辑保持不变
            # ... (这部分代码和你原来的一样) ...
            start_time = datetime.now(timezone.utc) - timedelta(days=self.label_hot_days)
            recent_meme_keys = await self.recorder.get_recent_meme_keys(start_time)
            meme_properties: Dict[str, Dict[str, bool]] = {}
            now_utc = datetime.now(timezone.utc)
            new_timedelta = timedelta(days=self.label_new_days)
            for meme in self.meme_manager.meme_infos.values():
                try:
                    is_new = (now_utc - meme.date_created) < new_timedelta
                except (ValueError, TypeError):
                    is_new = False
                is_hot = recent_meme_keys.count(meme.key) >= self.label_hot_threshold
                is_disabled = await self.recorder.is_meme_disabled(meme.key, event.get_group_id())
                properties = {"new": is_new, "hot": is_hot, "disabled": is_disabled}
                meme_properties[meme.key] = properties
            image_data = await self.api_client.render_list_image(meme_properties)

            # 3. 【核心修改】构建一个包含文字和图片的复合消息链
            A_text = "触发：“-关键词 [文] [@人] [--选项]”\n"
            B_text = "-表情详情 <关键词> | -表情搜索 <关键词>\n"
            
            # 将所有文本合并成一个字符串
            full_text = A_text + B_text
            
            # Message Components 的 Plain 用于文字，Image.fromBytes 用于图片数据
            message_chain = [
                Comp.Plain(full_text),  # 使用合并后的完整文本
                Comp.Image.fromBytes(image_data)
            ]

            # 4. 一次性发送整条消息链，而不是分开发送
            yield event.chain_result(message_chain)

        except Exception as e:
            logger.error(f"生成动态表情列表图失败: {e}", exc_info=True)
            yield event.plain_result("生成列表图失败了，呜呜...")
        finally:
            event.stop_event()