from functools import wraps
import inspect
from typing import Awaitable, Callable, Any, AsyncGenerator, Dict, List, Optional, Union, cast
from enum import IntEnum
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot import logger
# 注意: 这个文件依赖 core/utils.py 中的 get_ats, 请确保它存在
from .utils import get_ats 

class PermLevel(IntEnum):
    """定义用户的权限等级。数字越小，权限越高。"""
    SUPERUSER = 0
    OWNER = 1
    ADMIN = 2
    MEMBER = 3
    UNKNOWN = 4

    def __str__(self):
        return {
            PermLevel.SUPERUSER: "超管",
            PermLevel.OWNER: "群主",
            PermLevel.ADMIN: "管理员",
            PermLevel.MEMBER: "成员",
        }.get(self, "未知")

    @classmethod
    def from_str(cls, perm_str: str):
        return {
            "超管": cls.SUPERUSER,
            "群主": cls.OWNER,
            "管理员": cls.ADMIN,
            "成员": cls.MEMBER,
        }.get(perm_str, cls.UNKNOWN)


class PermissionManager:
    _instance: Optional["PermissionManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        superusers: Optional[List[str]] = None,
        perms: Optional[Dict[str, str]] = None,
        recorder_instance=None, # 保留 recorder 用于插件管理员检查
    ):
        if self._initialized:
            return
        self.superusers = superusers or []
        if perms is None:
            raise ValueError("初始化必须传入 perms")
        self.perms: Dict[str, PermLevel] = {
            k: PermLevel.from_str(v) for k, v in perms.items()
        }
        self.recorder = recorder_instance
        self._initialized = True

    @classmethod
    def get_instance(
        cls,
        superusers: Optional[List[str]] = None,
        perms: Optional[Dict[str, str]] = None,
        recorder_instance=None,
    ) -> "PermissionManager":
        if cls._instance is None:
            cls._instance = cls(
                superusers=superusers,
                perms=perms,
                recorder_instance=recorder_instance,
            )
        return cls._instance

    async def get_perm_level(
        self, event: AiocqhttpMessageEvent, user_id: str | int
    ) -> PermLevel:
        user_id = str(user_id)
        group_id = event.get_group_id()
        if not group_id or not user_id:
            return PermLevel.MEMBER # 私聊或无效用户视为普通成员

        # 1. 检查是否为超级用户
        if user_id in self.superusers:
            return PermLevel.SUPERUSER

        # 2. 检查QQ原生权限（群主/管理员）
        try:
            info = await event.bot.get_group_member_info(
                group_id=int(group_id), user_id=int(user_id), no_cache=True
            )
            role = info.get("role", "unknown")
            if role == "owner":
                return PermLevel.OWNER
            if role == "admin":
                return PermLevel.ADMIN
        except Exception:
            logger.warning(f"无法获取用户 {user_id} 在群 {group_id} 的原生权限信息。")
            pass

        # 3. 检查是否为插件数据库中手动设置的管理员
        if self.recorder and await self.recorder.is_plugin_group_admin(
            group_id, user_id
        ):
            return PermLevel.ADMIN  # 插件管理员等同于QQ管理员

        # 4. 如果以上都不是，则为普通成员
        return PermLevel.MEMBER

    # 简化：perm_block 现在只检查用户权限，不再检查机器人自身或@对象
    async def perm_block(
        self, event: AiocqhttpMessageEvent, perm_key: str
    ) -> str | None:
        user_level = await self.get_perm_level(event, user_id=event.get_sender_id())
        required_level = self.perms.get(perm_key)

        if required_level is None:
            return None # 如果指令没有在perms中定义，则不进行权限控制

        if user_level > required_level:
            return f"❌ 您的权限（{user_level}）不足以使用此指令（需要：{required_level}）"

        return None


# 简化：装饰器不再需要 bot_perm 和 check_at 参数
def perm_required(perm_key: str | None = None):
    """权限检查装饰器。"""
    def decorator(
        func: Callable[..., Union[AsyncGenerator[Any, Any], Awaitable[Any]]],
    ) -> Callable[..., AsyncGenerator[Any, Any]]:
        actual_perm_key = perm_key or func.__name__
        @wraps(func)
        async def wrapper(
            plugin_instance: Any,
            event: AiocqhttpMessageEvent,
            *args: Any,
            **kwargs: Any,
        ) -> AsyncGenerator[Any, Any]:
            perm_manager = PermissionManager.get_instance()

            if not perm_manager._initialized:
                logger.error(f"PermissionManager 未初始化（尝试访问权限项：{perm_key}）")
                yield event.plain_result("内部错误：权限系统未正确加载")
                event.stop_event()
                return

            # 判断权限
            result = await perm_manager.perm_block(event, perm_key=actual_perm_key)
            if result:
                yield event.plain_result(result)
                event.stop_event()
                return

            # 执行原始方法
            if inspect.isasyncgenfunction(func):
                async for item in func(plugin_instance, event, *args, **kwargs):
                    yield item
            else:
                await cast(
                    Awaitable[Any], func(plugin_instance, event, *args, **kwargs)
                )

        return wrapper
    return decorator