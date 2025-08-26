# 文件：astrbot_plugin_meme_maker_api/handlers/search.py

from typing import List

from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import session_waiter, SessionController
from astrbot.api import logger

class SearchHandlers:
    """一个 Mixin 类，只包含表情搜索指令的处理器"""

    async def handle_meme_search(self, event: AstrMessageEvent, query: str):
        if not query:
            yield event.plain_result("请输入搜索关键词，例如：-表情搜索 猫")
            return

        try:
            yield event.plain_result(f"正在搜索“{query}”...")
            searched_keys = await self.api_client.search_memes(query, include_tags=True)
            if not searched_keys:
                yield event.plain_result("没有找到相关表情！")
                return

            searched_memes = [self.meme_manager.meme_infos[key] for key in searched_keys if key in self.meme_manager.meme_infos]
            num_per_page = 8
            total_page = (len(searched_memes) - 1) // num_per_page + 1
            page_num = 0

            def format_page() -> str:
                start = page_num * num_per_page
                end = min(start + num_per_page, len(searched_memes))
                page_content = [
                    f"{start + i + 1}. {meme.key} ({'/'.join(meme.keywords)})" +
                    (f"\n    tags: {'、'.join(meme.tags)}" if meme.tags else "")
                    for i, meme in enumerate(searched_memes[start:end])
                ]
                msg = f"找到了与“{query}”相关的表情：\n" + "\n".join(page_content)
                if total_page > 1:
                    msg += f"\n\n--- 页码 {page_num + 1}/{total_page} ---\n发送 '<' 或 '>' 翻页，或直接发送页码。超时30秒后自动结束。"
                return msg

            if total_page <= 1:
                yield event.plain_result(format_page())
                return

            @session_waiter(timeout=30)
            async def pagination_waiter(controller: SessionController, next_event: AstrMessageEvent):
                nonlocal page_num
                resp = next_event.get_message_str().strip()
                if resp.isdigit() and 1 <= (page := int(resp)) <= total_page: page_num = page - 1
                elif resp in ["上一页", "上页", "上", "←", "<", "<-"]: page_num = (page_num - 1 + total_page) % total_page
                elif resp in ["下一页", "下页", "下", "→", ">", "->"]: page_num = (page_num + 1) % total_page
                else: await next_event.send(event.plain_result("搜索会话已结束。")); controller.stop(); return
                await next_event.send(event.plain_result(format_page()))
                controller.keep(timeout=30, reset_timeout=True)

            yield event.plain_result(format_page())
            await pagination_waiter(event)
        except TimeoutError:
            yield event.plain_result("搜索会话超时，已自动结束。")
        except Exception as e:
            logger.error(f"搜索表情时出错: {e}", exc_info=True)
            yield event.plain_result("搜索失败了，呜呜...")
        finally:
            event.stop_event()