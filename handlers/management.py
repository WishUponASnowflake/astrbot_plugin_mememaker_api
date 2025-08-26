# 文件：astrbot_plugin_meme_maker_api/handlers/management.py

import asyncio
import random
from typing import Dict, List

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp

from ..models import MemeInfo, MemeParams
from ..exceptions import ArgParseError, APIError
from ..core.permission import perm_required, PermLevel

class ManagementHandlers:
    """一个 Mixin 类，包含所有管理相关的指令处理器。"""

    @perm_required()
    async def handle_group_admin_manager(self, event: AstrMessageEvent, arg_text: str):
        try:
            args = arg_text.split()
            if not args or args[0] not in ["添加", "删除", "查看"]:
                yield event.plain_result("用法: -群管理员 [添加/删除/查看] [@某人或QQ号] [群号(可选)]")
                return

            sub_command = args[0]
            
            if sub_command == "查看":
                target_group_id = args[1] if len(args) > 1 else event.get_group_id()
                if not target_group_id:
                    yield event.plain_result("请指定群号或在群内使用此指令。")
                    return
                admins = await self.recorder.list_group_admins(target_group_id)
                if not admins:
                    yield event.plain_result(f"群 {target_group_id} 尚无自定义插件管理员。")
                else:
                    yield event.plain_result(f"群 {target_group_id} 的插件管理员有：\n" + "\n".join(admins))
                return

            target_user_id = None
            for seg in event.get_messages():
                if isinstance(seg, Comp.At): target_user_id = str(seg.qq); break
            if not target_user_id:
                for arg in args[1:]:
                    if arg.isdigit(): target_user_id = arg; break
            if not target_user_id:
                yield event.plain_result("请 @要操作的用户 或提供其 QQ 号。"); return

            target_group_id = event.get_group_id()
            for arg in args[1:]:
                if arg.isdigit() and arg != target_user_id: target_group_id = arg; break
            if not target_group_id:
                yield event.plain_result("请在群内使用此指令，或在最后提供群号。"); return

            if sub_command == "添加":
                await self.recorder.add_group_admin(target_group_id, target_user_id)
                yield event.plain_result(f"✅ 已将用户 {target_user_id} 添加为群 {target_group_id} 的插件管理员。")
            elif sub_command == "删除":
                await self.recorder.remove_group_admin(target_group_id, target_user_id)
                yield event.plain_result(f"✅ 已移除用户 {target_user_id} 在群 {target_group_id} 的插件管理员身份。")

        except Exception as e:
            logger.error(f"管理插件管理员时出错: {e}", exc_info=True)
            yield event.plain_result("操作失败，请检查后台日志。")
        finally:
            event.stop_event()

    @perm_required()
    async def handle_refresh_memes(self, event: AstrMessageEvent, _=None):
        try:
            yield event.plain_result("正在强制刷新表情包列表...")
            success, meme_count, shortcut_count = await self.meme_manager.refresh_memes(self.api_client)
            if success:
                yield event.plain_result(f"表情包列表刷新成功！共加载 {meme_count} 个表情和 {shortcut_count} 个快捷指令。")
            else:
                yield event.plain_result("刷新失败，请查看后台日志。")
        finally:
            event.stop_event()

    @perm_required()
    async def handle_disable_meme(self, event: AstrMessageEvent, keyword: str):
        try:
            if not (group_id := event.get_group_id()):
                yield event.plain_result("❌ 此指令不能在私聊中使用，请使用 `-全局禁用表情`。"); return
            if not keyword: yield event.plain_result("请输入要禁用的表情关键词。"); return
            if not (meme_info := self.meme_manager.find_meme_by_keyword(keyword)):
                yield event.plain_result(f"找不到表情“{keyword}”。"); return
            
            await self.recorder.set_meme_mode(meme_info.key, 'group', group_id, 'black')
            yield event.plain_result(f"✅ 已在当前群禁用表情“{meme_info.key}”。")
        except Exception as e: logger.error(f"分群禁用失败: {e}", exc_info=True); yield event.plain_result("操作失败...")
        finally: event.stop_event()

    @perm_required()
    async def handle_enable_meme(self, event: AstrMessageEvent, keyword: str):
        try:
            if not (group_id := event.get_group_id()):
                yield event.plain_result("❌ 此指令不能在私聊中使用。"); return
            if not keyword: yield event.plain_result("请输入要启用的表情关键词。"); return
            
            meme_info = self.meme_manager.find_meme_by_keyword(keyword)
            key_to_enable = meme_info.key if meme_info else keyword

            is_white_mode = await self.recorder.is_meme_whitelisted(key_to_enable)
            if is_white_mode:
                await self.recorder.set_meme_mode(key_to_enable, 'group', group_id, 'white')
            else:
                await self.recorder.remove_meme_rule(key_to_enable, 'group', group_id)

            yield event.plain_result(f"✅ 已在当前群启用/解除限制表情“{key_to_enable}”。")
        except Exception as e: logger.error(f"分群启用失败: {e}", exc_info=True); yield event.plain_result("操作失败...")
        finally: event.stop_event()

    @perm_required()
    async def handle_manager_list(self, event: AstrMessageEvent, _=None):
        try:
            if not (group_id := event.get_group_id()):
                yield event.plain_result("请在群内使用此指令。"); return

            rules = await self.recorder.get_manager_list(group_id)
            if not rules: yield event.plain_result("当前没有任何全局或本群表情管理规则。"); return
            
            rule_texts = [f"• {key} ({'全局' if scope == 'global' else '本群'} { '白名单(默认禁用)' if mode == 'white' else '黑名单(禁用)'})" for key, scope, mode in rules]
            yield event.plain_result("--- 表情管理规则 ---\n" + "\n".join(rule_texts))
        except Exception as e: logger.error(f"查看管理列表失败: {e}", exc_info=True); yield event.plain_result("操作失败...")
        finally: event.stop_event()

    @perm_required()
    async def handle_global_disable_meme(self, event: AstrMessageEvent, arg_text: str):
        try:
            if not arg_text: yield event.plain_result("请输入要设为白名单模式的表情关键词。"); return
            if not (meme_info := self.meme_manager.find_meme_by_keyword(arg_text)):
                yield event.plain_result(f"找不到表情“{arg_text}”。"); return
            
            await self.recorder.set_meme_mode(meme_info.key, 'global', '*', 'white')
            yield event.plain_result(f"✅ 已将表情“{meme_info.key}”设为全局白名单模式（默认禁用）。")
        except Exception as e: logger.error(f"全局禁用失败: {e}", exc_info=True); yield event.plain_result("操作失败...")
        finally: event.stop_event()

    @perm_required()
    async def handle_global_enable_meme(self, event: AstrMessageEvent, arg_text: str):
        try:
            if not arg_text: yield event.plain_result("请输入要恢复为黑名单模式的表情关键词。"); return
            meme_info = self.meme_manager.find_meme_by_keyword(arg_text)
            key_to_manage = meme_info.key if meme_info else arg_text
            await self.recorder.remove_meme_rule(key_to_manage, 'global', '*')
            yield event.plain_result(f"✅ 已将表情“{key_to_manage}”恢复为全局黑名单模式（默认启用）。")
        except Exception as e: logger.error(f"全局启用失败: {e}", exc_info=True); yield event.plain_result("操作失败...")
        finally: event.stop_event()
