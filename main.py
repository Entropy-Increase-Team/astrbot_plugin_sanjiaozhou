import ast
import asyncio
import base64
import binascii
import datetime as dt
import inspect
import json
import os
import re
from html import unescape
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

import yaml

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core import AstrBotConfig

try:
    import astrbot.api.message_components as Comp
except Exception:
    Comp = None

try:
    from astrbot.api.event import MessageChain
except Exception:
    MessageChain = None

Plain = getattr(Comp, "Plain", None) if Comp is not None else None

from .core.calculator import DeltaCalculator
from .core.client import DeltaForceClient
from .core.data import DeltaDataManager
from .core.media_cache import MusicCache
from .core.render import DeltaRenderer
from .core.subscription import SubscriptionStore
from .core.user import BindingManager
from .core.version import PLUGIN_VERSION

try:
    import websockets
except Exception:  # 可选依赖缺失时保留 REST 查询能力
    websockets = None


SOL_ALIASES = {"sol", "烽火", "烽火地带", "摸金", "4"}
MP_ALIASES = {"mp", "tdm", "全面", "全面战场", "战场", "大战场", "5"}
ESCAPE_REASONS = {"1": "撤离成功", "2": "被玩家击杀", "3": "被人机击杀", "10": "撤离失败"}
MP_RESULTS = {"1": "胜利", "2": "失败", "3": "中途退出"}


class _ScheduledEvent:
    """仅为复用现有日报、周报字段适配器提供最小事件信息。"""

    def __init__(self, user_id: str):
        self._user_id = str(user_id)
        self.sender = None

    def get_sender_id(self) -> str:
        return self._user_id


DELTA_COMMAND_SPECS = [
    ("帮助", {"菜单", "功能", "help", "三角洲帮助", "df帮助", "delta帮助"}),
    ("娱乐帮助", {"娱乐菜单", "娱乐功能"}),
    ("计算帮助", {"计算菜单"}),
    (
        "登录",
        {
            "登陆",
            "qq登录",
            "qq登陆",
            "QQ登录",
            "QQ登陆",
            "微信登录",
            "微信登陆",
            "wx登录",
            "wx登陆",
            "WX登录",
            "WX登陆",
            "wegame登录",
            "wegame登陆",
            "WEGAME登录",
            "WEGAME登陆",
            "wegame微信登录",
            "wegame微信登陆",
            "微信wegame登录",
            "微信wegame登陆",
            "qqsafe登录",
            "qqsafe登陆",
            "QQsafe登录",
            "QQsafe登陆",
            "安全中心登录",
            "安全中心登陆",
            "qq安全中心登录",
            "qq安全中心登陆",
        },
    ),
    ("ck登录", {"ck登陆"}),
    (
        "qq授权登录",
        {
            "qq授权登陆",
            "QQ授权登录",
            "QQ授权登陆",
            "qqauth登录",
            "qqauth登陆",
            "QQauth登录",
            "QQauth登陆",
            "qqoauth登录",
            "qqoauth登陆",
            "QQoauth登录",
            "QQoauth登陆",
        },
    ),
    (
        "微信授权登录",
        {
            "微信授权登陆",
            "wx授权登录",
            "wx授权登陆",
            "WX授权登录",
            "WX授权登陆",
            "微信auth登录",
            "微信auth登陆",
            "wxauth登录",
            "wxauth登陆",
            "WXauth登录",
            "WXauth登陆",
            "微信oauth登录",
            "微信oauth登陆",
            "wxoauth登录",
            "wxoauth登陆",
            "WXoauth登录",
            "WXoauth登陆",
        },
    ),
    ("网页登录", {"web登录", "网站登录", "网页登陆", "web登陆", "网站登陆"}),
    ("角色绑定", set()),
    ("绑定", set()),
    ("账号", {"账号列表"}),
    ("账号切换", {"切换账号"}),
    ("解绑", {"删除"}),
    ("微信刷新", {"刷新微信", "qq刷新", "QQ刷新", "刷新qq", "刷新QQ"}),
    ("信息", {"info"}),
    ("uid", {"UID"}),
    ("数据", {"data"}),
    ("战绩", set()),
    ("日报", {"daily"}),
    ("昨日收益", {"昨日物资"}),
    ("周报", {"weekly"}),
    ("地图统计", {"mapStats", "地图数据"}),
    ("货币", {"money", "余额"}),
    ("流水", {"flows"}),
    ("藏品", {"资产"}),
    ("出红记录", {"大红记录", "藏品记录", "大红收藏", "大红藏品", "大红海报", "藏品海报"}),
    ("封号记录", {"违规记录", "违规历史", "封号历史"}),
    ("特勤处状态", {"placestatus"}),
    ("特勤处信息", {"placeinfo"}),
    ("健康状态", set()),
    ("服务器状态", set()),
    ("用户统计", set()),
    ("干员列表", set()),
    ("干员", set()),
    ("物品列表", set()),
    ("物品搜索", set()),
    ("当前价格", {"最新价格", "价格"}),
    ("价格历史", {"历史价格"}),
    ("材料价格", {"制造材料"}),
    ("利润历史", {"历史利润", "利润排行", "利润榜", "最高利润", "利润排行v2", "利润榜v2", "特勤处利润", "特勤利润"}),
    ("上传改枪码", {"上传改枪方案"}),
    ("改枪码列表", {"改枪方案列表"}),
    ("改枪码详情", {"改枪方案详情"}),
    ("改枪码点赞", {"改枪方案点赞", "改枪码点踩", "改枪方案点踩"}),
    ("更新改枪码", {"更新改枪方案"}),
    ("删除改枪码", {"删除改枪方案"}),
    ("收藏改枪码", {"收藏改枪方案", "取消收藏改枪码", "取消收藏改枪方案"}),
    ("改枪码收藏列表", {"改枪方案收藏列表"}),
    ("每日密码", {"今日密码"}),
    ("文章列表", set()),
    ("文章详情", {"文章"}),
    ("ai预设列表", {"AI预设列表"}),
    ("ai锐评", {"AI锐评"}),
    ("ai评价", {"AI评价"}),
    ("语音列表", {"标签列表", "语音分类", "语音统计"}),
    ("语音", set()),
    ("歌词", {"鼠鼠歌词", "鼠鼠音乐歌词", "鼠鼠语音"}),
    ("鼠鼠音乐列表", {"鼠鼠音乐排行榜"}),
    ("鼠鼠歌单", set()),
    ("点歌", {"听", "听歌", "播放"}),
    ("鼠鼠音乐", set()),
    ("音乐缓存状态", {"音乐缓存统计"}),
    ("清理音乐缓存", set()),
    ("tts状态", set()),
    ("tts角色列表", {"tts预设列表", "tts角色", "tts预设"}),
    ("tts角色详情", set()),
    ("tts上传", {"tts下载"}),
    ("tts重播", {"tts语音"}),
    ("tts", set()),
    ("伤害计算", {"伤害", "dmg"}),
    ("战备计算", {"战备"}),
    ("维修计算", {"维修"}),
    ("修甲", {"修理"}),
    ("计算映射表", {"映射表"}),
    ("取消计算", {"取消"}),
    ("ws连接", {"WS连接", "websocket连接", "WebSocket连接", "ws启动", "WS启动", "websocket启动", "WebSocket启动", "ws开启", "WS开启", "websocket开启", "WebSocket开启", "ws断开", "WS断开", "websocket断开", "WebSocket断开", "ws关闭", "WS关闭", "websocket关闭", "WebSocket关闭", "ws停止", "WS停止", "websocket停止", "WebSocket停止", "ws状态", "WS状态", "websocket状态", "WebSocket状态", "wsstatus", "WSstatus", "websocketstatus", "WebSocketstatus"}),
    ("订阅", {"取消订阅", "订阅状态"}),
    ("开启本群订阅推送", {"关闭本群订阅推送", "开启私信订阅推送", "关闭私信订阅推送"}),
    ("广播开启", {"通知开启", "广播启用", "通知启用", "广播订阅", "通知订阅", "广播关闭", "通知关闭", "广播禁用", "通知禁用", "广播取消", "通知取消", "广播状态", "通知状态", "广播设置", "通知设置"}),
    ("开启日报推送", {"关闭日报推送", "开启周报推送", "关闭周报推送", "开启特勤处推送", "关闭特勤处推送", "开启每日密码推送", "关闭每日密码推送"}),
    ("房间列表", {"创建房间", "加入房间", "退出房间", "解散房间", "踢人", "房间信息", "房间地图列表", "房间标签列表"}),
    ("更新", {"强制更新", "插件更新", "插件强制更新", "更新日志", "插件更新日志", "update", "update_log"}),
    ("活动日历", {"活动", "活动列表"}),
    (
        "微信安全中心授权登录",
        {"gamesafe授权登录", "gamesafeoauth登录", "微信安全中心oauth登录"},
    ),
    ("微信安全中心绑定", {"gamesafe绑定", "微信安全中心账号"}),
    ("微信安全中心登录信息", {"gamesafe登录信息"}),
    ("微信安全中心封禁记录", {"gamesafe封禁记录", "微信安全中心处罚记录"}),
    ("微信安全中心冻结状态", {"gamesafe冻结状态"}),
    ("微信安全中心设备", {"gamesafe设备", "微信安全中心设备列表"}),
    ("微信安全中心在线状态", {"gamesafe在线状态"}),
    ("微信安全中心安全报告", {"gamesafe安全报告"}),
]


@register(
    "sanjiaozhou",
    "bvzrays & Entropy-Increase-Team",
    "三角洲行动 AstrBot 插件",
    PLUGIN_VERSION,
    "https://github.com/Entropy-Increase-Team/astrbot_plugin_sanjiaozhou",
)
class DeltaForcePlugin(Star):
    _BACKGROUND_REGISTRY_KEY = "_astrbot_sanjiaozhou_background_tasks"
    _TASK_STOP_TIMEOUT = 5.0
    _RESOURCE_CLOSE_TIMEOUT = 10.0

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.plugin_path = os.path.abspath(os.path.dirname(__file__))
        self.resources = os.path.join(self.plugin_path, "resources")
        self.client = DeltaForceClient(
            api_key=self.config.get("api_key", ""),
            api_mode=self.config.get("api_mode", "auto"),
            api_base_url=self.config.get("api_base_url", ""),
            timeout=float(self.config.get("request_timeout", 30) or 30),
        )
        data_dir = str(StarTools.get_data_dir())
        self.bindings = BindingManager(data_dir)
        self.subscriptions = SubscriptionStore(data_dir)
        self.data_mgr = DeltaDataManager(self.plugin_path, data_dir)
        self.music_cache = MusicCache(data_dir)
        self.music_cache.clean_expired()
        self.calculator = DeltaCalculator(self.data_mgr)
        self.renderer = DeltaRenderer(
            self.resources,
            render_timeout=int(self.config.get("render_timeout", 30000) or 30000),
        )
        self._static_task: Optional[asyncio.Task] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._push_task: Optional[asyncio.Task] = None
        self._ws_stop = asyncio.Event()
        self._ws_wakeup = asyncio.Event()
        self._ws_requested = False
        self._ws_connection = None
        self._seen_record_events: Dict[str, int] = {}
        self._oauth_sessions: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._music_lists: Dict[str, Dict[str, Any]] = {}
        self._music_last: Dict[str, Dict[str, Any]] = {}
        self._tts_last: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        self._terminated = False

    def _background_task_registry(self) -> Dict[str, asyncio.Task]:
        loop = asyncio.get_running_loop()
        registry = getattr(loop, self._BACKGROUND_REGISTRY_KEY, None)
        if not isinstance(registry, dict):
            registry = {}
            setattr(loop, self._BACKGROUND_REGISTRY_KEY, registry)
        return registry

    async def _cancel_background_tasks(self, tasks: Iterable[asyncio.Task]) -> None:
        unique_tasks = list(dict.fromkeys(task for task in tasks if isinstance(task, asyncio.Task)))
        if not unique_tasks:
            return
        for task in unique_tasks:
            if not task.done():
                task.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(*unique_tasks, return_exceptions=True),
                timeout=self._TASK_STOP_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("[三角洲生命周期] 后台任务未在限定时间内结束。")

    async def _cancel_stale_background_tasks(self) -> None:
        registry = self._background_task_registry()
        await self._cancel_background_tasks(registry.values())
        registry.clear()

    def _register_background_task(self, name: str, coroutine: Any) -> asyncio.Task:
        task = asyncio.create_task(
            coroutine,
            name=f"sanjiaozhou:{name}:{id(self):x}",
        )
        self._background_task_registry()[name] = task
        return task

    def _unregister_background_task(self, name: str, task: Optional[asyncio.Task]) -> None:
        registry = self._background_task_registry()
        if registry.get(name) is task:
            registry.pop(name, None)

    async def _close_resource(self, name: str, closer: Any) -> None:
        try:
            await asyncio.wait_for(closer(), timeout=self._RESOURCE_CLOSE_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning(f"[三角洲生命周期] {name} 关闭超时。")
        except Exception as exc:
            logger.warning(f"[三角洲生命周期] {name} 关闭失败：{type(exc).__name__}")

    async def initialize(self):
        if getattr(self, "_terminated", False):
            logger.warning("[三角洲生命周期] 已终止的插件实例不能再次初始化。")
            return
        await self._cancel_stale_background_tasks()
        self._ws_stop.clear()
        self._ws_requested = bool(self.subscriptions.enabled_targets())
        self._static_task = self._register_background_task(
            "static_refresh", self.data_mgr.refresh_static(self.client)
        )
        self._ws_task = self._register_background_task(
            "websocket", self._ws_supervisor()
        )
        self._push_task = self._register_background_task(
            "scheduled_push", self._scheduled_push_loop()
        )
        self._initialized = True

    async def terminate(self):
        if getattr(self, "_terminated", False):
            return
        self._terminated = True
        self._ws_stop.set()
        self._ws_wakeup.set()
        task_items = (
            ("static_refresh", self._static_task),
            ("websocket", self._ws_task),
            ("scheduled_push", self._push_task),
        )
        await self._cancel_background_tasks(task for _name, task in task_items if task)
        for name, task in task_items:
            self._unregister_background_task(name, task)
        self._static_task = None
        self._ws_task = None
        self._push_task = None

        connection = self._ws_connection
        self._ws_connection = None
        if connection is not None:
            await self._close_resource("WebSocket", connection.close)
        await self._close_resource("HTTP 客户端", self.client.close)
        await self._close_resource("渲染器", self.renderer.close)
        self._initialized = False

    async def _handle_astr_command(self, event: AstrMessageEvent):
        msg = self._message(event)
        async for result in self._dispatch(event, msg):
            yield result

    def _message(self, event: AstrMessageEvent) -> str:
        try:
            return event.get_message_str().strip()
        except Exception:
            return str(getattr(event, "message_str", "") or "").strip()

    def _body(self, msg: str) -> str:
        return msg.strip()

    def _client_id(self, event: AstrMessageEvent) -> str:
        cfg = str(self.config.get("client_id", "") or "").strip()
        if cfg:
            return cfg
        try:
            return str(event.get_self_id() or "astrbot")
        except Exception:
            return "astrbot"

    def _user_identifier(self, event: AstrMessageEvent) -> str:
        return f"qq_{event.get_sender_id()}"

    def _sender_name(self, event: AstrMessageEvent) -> str:
        try:
            sender = getattr(event, "sender", None)
            if sender:
                return getattr(sender, "card", None) or getattr(sender, "nickname", None) or str(event.get_sender_id())
        except Exception:
            pass
        return str(event.get_sender_id())

    @staticmethod
    def _image_base64(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        payload = ""
        if match := re.fullmatch(
            r"data:image/[a-zA-Z0-9.+-]+;base64,([A-Za-z0-9+/=\s]+)",
            text,
            flags=re.I,
        ):
            payload = match.group(1)
        elif text.lower().startswith("base64://"):
            payload = text[len("base64://") :]
        elif re.fullmatch(r"[A-Za-z0-9+/=\s]+", text):
            payload = text
        else:
            return None

        payload = re.sub(r"\s+", "", payload)
        try:
            raw = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("二维码 Base64 数据无效") from exc

        is_image = (
            raw.startswith(b"\x89PNG\r\n\x1a\n")
            or raw.startswith((b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM"))
            or (len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
        )
        if not is_image:
            raise ValueError("二维码数据不是受支持的图片")
        return payload

    @staticmethod
    def _oauth_callback_parts(callback_url: str) -> Tuple[str, str]:
        try:
            parsed = urlparse(callback_url.strip())
        except ValueError:
            return "", ""
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "", ""
        params = parse_qs(parsed.query)
        if (not params.get("code") or not params.get("state")) and parsed.fragment:
            fragment_query = parsed.fragment.split("?", 1)[-1]
            fragment_params = parse_qs(fragment_query)
            params.update({key: value for key, value in fragment_params.items() if key not in params})
        code = str((params.get("code") or [""])[0]).strip()
        state = str((params.get("state") or [""])[0]).strip()
        return code, state

    @staticmethod
    async def _recall_sensitive_message(
        event: AstrMessageEvent,
        source: str = "敏感凭证",
    ) -> bool:
        """在 aiocqhttp 中尽力撤回用户提交的敏感消息。"""
        try:
            get_platform_name = getattr(event, "get_platform_name", None)
            if not callable(get_platform_name) or get_platform_name() != "aiocqhttp":
                return False
            bot = getattr(event, "bot", None)
            message_obj = getattr(event, "message_obj", None)
            message_id = str(getattr(message_obj, "message_id", "") or "").strip()
            delete_msg = getattr(bot, "delete_msg", None)
            if not message_id or not callable(delete_msg):
                return False
            await delete_msg(
                message_id=int(message_id) if message_id.isdigit() else message_id
            )
            logger.info(f"[三角洲安全] 已撤回用户提交的{source}消息。")
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                f"[三角洲安全] {source}消息撤回失败：{type(exc).__name__}"
            )
            return False

    @classmethod
    async def _recall_oauth_callback(cls, event: AstrMessageEvent) -> bool:
        """保留 OAuth 专用入口，兼容既有调用与测试。"""
        return await cls._recall_sensitive_message(event, "OAuth 回调")

    @staticmethod
    def _privacy_notice(recalled: bool, credential_name: str) -> str:
        if recalled:
            return ""
        return (
            f"隐私提醒：当前平台无法自动撤回含{credential_name}的消息，"
            "请立即手动撤回。"
        )

    @staticmethod
    def _redact_secret(text: Any, *secrets: str) -> str:
        result = str(text or "")
        for secret in secrets:
            value = str(secret or "")
            if value:
                result = result.replace(value, "[已隐藏]")
        return result

    @staticmethod
    def _expiry_millis(value: Any) -> int:
        if isinstance(value, dt.datetime):
            parsed = value
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
            return int(parsed.timestamp() * 1000)
        text = str(value or "").strip()
        if not text:
            return 0
        try:
            timestamp = int(float(text))
        except (OverflowError, TypeError, ValueError):
            try:
                parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return 0
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
            return int(parsed.timestamp() * 1000)
        return timestamp * 1000 if 0 < timestamp < 100_000_000_000 else timestamp

    @classmethod
    def _remaining_login_seconds(
        cls,
        expiry: Any,
        fallback_seconds: int,
        now_millis: Optional[int] = None,
    ) -> int:
        expire_millis = cls._expiry_millis(expiry)
        if not expire_millis:
            return max(1, int(fallback_seconds))
        current_millis = (
            now_millis
            if now_millis is not None
            else int(dt.datetime.now().timestamp() * 1000)
        )
        remaining_millis = expire_millis - current_millis
        return max(0, (remaining_millis + 999) // 1000)

    @staticmethod
    def _ok(res: Any) -> bool:
        return DeltaForceClient.ok(res)

    @staticmethod
    def _data(res: Any, default: Any = None) -> Any:
        data = DeltaForceClient.data(res, default)
        if isinstance(data, dict) and "data" in data and len(data) <= 3:
            return data.get("data")
        return data

    @staticmethod
    def _payload(res: Any, default: Any = None) -> Any:
        """只移除 Go API 的统一响应信封，保留 AMS 业务层级。"""
        return DeltaForceClient.data(res, default)

    @staticmethod
    def _ams_inner(value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        first = value.get("data")
        if not isinstance(first, dict):
            return value
        second = first.get("data")
        return second if isinstance(second, dict) else first

    @staticmethod
    def _number(value: Any, default: float = 0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_compound_list(value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        text = str(value or "").strip()
        if not text or text.lower() == "null":
            return []

        parts = text.split("#") if "#" in text else [text]
        result: List[Dict[str, Any]] = []
        for part in parts:
            item: Any = None
            try:
                item = json.loads(part)
            except (json.JSONDecodeError, TypeError):
                try:
                    item = ast.literal_eval(part)
                except (ValueError, SyntaxError):
                    continue
            if isinstance(item, dict):
                result.append(item)
        return result

    @staticmethod
    def _last_sunday(value: Optional[dt.datetime] = None) -> str:
        now = value or dt.datetime.now()
        sunday = now - dt.timedelta(days=now.isoweekday())
        return sunday.strftime("%Y%m%d")

    async def _render_identity(self, event: AstrMessageEvent, token: str) -> Dict[str, str]:
        identity = {
            "userName": self._sender_name(event),
            "userAvatar": "",
            "qqAvatarUrl": f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
        }
        try:
            res = await self.client.personal_info(token)
            if not self._ok(res):
                return identity
            raw = self._payload(res, {}) or {}
            data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
            user_data = data.get("userData") or data.get("user_data") or {}
            role = raw.get("roleInfo") or data.get("roleInfo") or raw.get("role_info") or {}
            name = self.data_mgr.decode_text(user_data.get("charac_name") or role.get("charac_name") or role.get("nickname") or "")
            avatar = self.data_mgr.decode_text(user_data.get("picurl") or role.get("picurl") or "")
            if avatar and avatar.isdigit():
                avatar = f"https://wegame.gtimg.com/g.2001918-r.ea725/helper/df/skin/{avatar}.webp"
            if name:
                identity["userName"] = name
            if avatar:
                identity["userAvatar"] = avatar
        except Exception as exc:
            logger.debug(f"[三角洲] 获取渲染身份失败: {type(exc).__name__}")
        return identity

    @staticmethod
    def _message_of(res: Any) -> str:
        if not isinstance(res, dict):
            return "API 返回格式异常"
        return str(res.get("message") or res.get("msg") or res.get("error") or "请求失败")

    @staticmethod
    def _first_list(data: Any, keys: Iterable[str] = ()) -> List[Any]:
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
        for value in data.values():
            if isinstance(value, list):
                return value
        return []

    async def _token(self, event: AstrMessageEvent) -> str:
        binding = await self.bindings.get_primary_binding(event.get_sender_id())
        return str((binding or {}).get("framework_token") or "")

    async def _need_token(self, event: AstrMessageEvent) -> Optional[str]:
        token = await self._token(event)
        if not token:
            return None
        return token

    async def _token_for_type(
        self,
        event: AstrMessageEvent,
        token_type: str,
    ) -> Optional[str]:
        bindings = await self.bindings.get_user_bindings(event.get_sender_id())
        expected = str(token_type or "").strip().lower()
        candidates = [
            item
            for item in bindings
            if str(item.get("token_type") or item.get("login_type") or "").lower()
            == expected
            and item.get("is_valid", True)
            and item.get("framework_token")
        ]
        if not candidates:
            return None
        primary = next((item for item in candidates if item.get("is_primary")), None)
        return str((primary or candidates[0]).get("framework_token") or "") or None

    async def _render_or_text(
        self,
        event: AstrMessageEvent,
        template: str,
        data: Dict[str, Any],
        fallback: str,
        options: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Any, None]:
        if self.config.get("enable_image_render", True):
            img = await self.renderer.render_html(template, data, options or {})
            if img:
                yield event.image_result(img)
                return
        yield event.plain_result(fallback)

    @staticmethod
    def _subscription_list(res: Any) -> List[Dict[str, Any]]:
        payload = DeltaForceClient.data(res, {})
        if isinstance(payload, dict):
            payload = payload.get("list") or payload.get("subscriptions") or []
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    @staticmethod
    def _subscription_id(item: Dict[str, Any]) -> str:
        return str(item.get("id") or item.get("subscription_id") or "").strip()

    async def _subscription_binding(self, event: AstrMessageEvent) -> Optional[Dict[str, Any]]:
        binding = await self.bindings.get_primary_binding(event.get_sender_id())
        if not binding:
            return None
        binding_id = str(binding.get("binding_id") or "")
        if not binding_id or binding_id.startswith("local-"):
            return None
        return binding

    async def _record_subscription(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        """处理战绩订阅创建、取消和状态查询。"""
        action = "create"
        text = str(arg or "").strip()
        if text.startswith("取消订阅") or text.startswith("取消"):
            action = "delete"
        elif text.startswith("订阅状态") or text in {"状态", "查询"}:
            action = "status"

        binding = await self._subscription_binding(event)
        if not binding:
            if action == "status":
                yield event.plain_result("当前账号没有可用的后端绑定；本地绑定不能创建战绩订阅，请重新登录或刷新绑定。")
            else:
                yield event.plain_result("战绩订阅需要后端绑定 ID，请先完成登录和角色绑定。")
            return

        user_identifier = self._user_identifier(event)
        client_id = self._client_id(event)
        binding_id = str(binding.get("binding_id"))
        response = await self.client.list_record_subscriptions(user_identifier, client_id)
        if not self._ok(response):
            yield event.plain_result(f"获取战绩订阅失败：{self._message_of(response)}")
            return
        items = self._subscription_list(response)
        current = next((item for item in items if str(item.get("binding_id") or "") == binding_id), None)

        if action == "status":
            if not items:
                yield event.plain_result("当前账号没有战绩订阅。发送“订阅 战绩 sol/mp/both”创建。")
                return
            lines = ["【战绩订阅】"]
            for item in items:
                sub_type = str(item.get("subscription_type") or "both")
                state = "启用" if item.get("enabled", item.get("status") == "active") else "停用"
                lines.append(
                    f"{self._subscription_id(item) or '未知'}：{sub_type}，{state}，"
                    f"间隔 {item.get('poll_interval_sec') or 0} 秒，失败 {item.get('consecutive_failures') or 0} 次"
                )
            yield event.plain_result("\n".join(lines))
            return

        if action == "delete":
            if not current:
                yield event.plain_result("当前账号没有可取消的战绩订阅。")
                return
            sub_id = self._subscription_id(current)
            result = await self.client.delete_record_subscription(sub_id, user_identifier, client_id)
            if not self._ok(result):
                yield event.plain_result(f"取消战绩订阅失败：{self._message_of(result)}")
                return
            self.subscriptions.remove(event.get_sender_id(), binding_id)
            self._ws_wakeup.set()
            yield event.plain_result("战绩订阅已取消。")
            return

        parts = text.split()
        if len(parts) > 1 and parts[1].lower() in {"战绩", "record"}:
            type_token = parts[2] if len(parts) > 2 else "both"
        else:
            type_token = parts[1] if len(parts) > 1 else "both"
        sub_type = type_token.lower()
        sub_type = {"烽火": "sol", "烽火地带": "sol", "全面": "mp", "全面战场": "mp", "4": "sol", "5": "mp"}.get(sub_type, sub_type)
        if sub_type not in {"sol", "mp", "both"}:
            yield event.plain_result("订阅类型只能是 sol、mp 或 both，例如：订阅 战绩 both。")
            return
        if current:
            current_type = str(current.get("subscription_type") or "both")
            if current_type == sub_type:
                self.subscriptions.upsert(
                    event.get_sender_id(), binding_id,
                    {"subscription_id": self._subscription_id(current), "subscription_type": current_type},
                )
                self._ws_requested = True
                self._ws_wakeup.set()
                yield event.plain_result(f"当前已存在 {current_type} 战绩订阅，已恢复本地推送配置。")
                return
            old_id = self._subscription_id(current)
            deleted = await self.client.delete_record_subscription(old_id, user_identifier, client_id)
            if not self._ok(deleted):
                yield event.plain_result(f"切换订阅类型失败：无法删除旧订阅，{self._message_of(deleted)}")
                return
            self.subscriptions.remove(event.get_sender_id(), binding_id)

        created = await self.client.create_record_subscription(
            binding_id,
            subscription_type=sub_type,
            poll_interval_sec=int(self.config.get("record_poll_interval", 300) or 300),
            rank_detection_enabled=bool(self.config.get("record_rank_detection", False)),
            user_identifier=user_identifier,
            client_id=client_id,
        )
        if not self._ok(created):
            yield event.plain_result(f"创建战绩订阅失败：{self._message_of(created)}")
            return
        payload = DeltaForceClient.data(created, {})
        subscription = payload.get("subscription") if isinstance(payload, dict) else payload
        subscription = subscription if isinstance(subscription, dict) else {}
        sub_id = self._subscription_id(subscription)
        if not sub_id:
            yield event.plain_result("后端未返回订阅 ID，无法启动推送；请稍后查询订阅状态。")
            return
        self.subscriptions.upsert(
            event.get_sender_id(), binding_id,
            {
                "subscription_id": sub_id,
                "subscription_type": sub_type,
                "user_identifier": user_identifier,
                "client_id": client_id,
                "targets": {},
            },
        )
        self._ws_requested = True
        self._ws_wakeup.set()
        yield event.plain_result(f"已创建 {sub_type} 战绩订阅（{sub_id}）。请用“开启本群订阅推送”或“开启私信订阅推送”设置接收目标。")

    async def _subscription_target(self, event: AstrMessageEvent, kind: str, enabled: bool) -> AsyncGenerator[Any, None]:
        binding = await self._subscription_binding(event)
        if not binding:
            yield event.plain_result("请先完成后端登录和角色绑定，再设置订阅推送目标。")
            return
        group_id = str(event.get_group_id() or "").strip()
        if kind == "group" and not group_id:
            yield event.plain_result("该命令需要在群聊中使用。")
            return
        if kind == "private" and group_id:
            yield event.plain_result("私信推送目标请在私聊中设置。")
            return
        user_id = event.get_sender_id()
        user_identifier = self._user_identifier(event)
        result = await self.client.list_record_subscriptions(user_identifier, self._client_id(event))
        if not self._ok(result):
            yield event.plain_result(f"获取战绩订阅失败：{self._message_of(result)}")
            return
        current = next((item for item in self._subscription_list(result) if str(item.get("binding_id") or "") == str(binding.get("binding_id"))), None)
        if not current:
            yield event.plain_result("当前账号没有战绩订阅，请先发送“订阅 战绩 both”。")
            return
        sub_id = self._subscription_id(current)
        self.subscriptions.upsert(user_id, binding["binding_id"], {"subscription_id": sub_id})
        self.subscriptions.set_target(user_id, binding["binding_id"], event.unified_msg_origin, kind, enabled)
        self._ws_requested = True
        if not enabled and not self.subscriptions.enabled_targets():
            self._ws_requested = False
            if self._ws_connection is not None:
                try:
                    await self._ws_connection.close()
                except Exception:
                    pass
        self._ws_wakeup.set()
        status = "已开启" if enabled else "已关闭"
        yield event.plain_result(f"{status}{'本群' if kind == 'group' else '私信'}战绩订阅推送。")

    def _ws_client_id(self) -> str:
        configured = str(self.config.get("client_id") or "").strip()
        if configured:
            return configured
        for item in self.subscriptions.all():
            client_id = str(item.get("client_id") or "").strip()
            if client_id:
                return client_id
        return "astrbot"

    def _ws_uri(self) -> Tuple[str, str]:
        base = self.client._base_urls()[0]
        parsed = urlparse(str(base))
        scheme = "wss" if parsed.scheme == "https" else "ws"
        uri = urlunparse((scheme, parsed.netloc, "/ws", "", "", ""))
        origin = f"{parsed.scheme or 'https'}://{parsed.netloc}" if parsed.netloc else "https://delta-test-api.shallow.ink"
        return uri, origin

    @staticmethod
    def _ws_header_argument(connect: Any) -> str:
        try:
            parameters = inspect.signature(connect).parameters
        except (TypeError, ValueError):
            parameters = {}
        if "extra_headers" in parameters and "additional_headers" not in parameters:
            return "extra_headers"
        return "additional_headers"

    async def _ws_supervisor(self) -> None:
        if websockets is None:
            logger.warning("[三角洲订阅] 未安装 websockets，战绩实时推送不可用；REST 订阅仍可使用。")
            return
        backoff = 2
        while not self._ws_stop.is_set():
            if not self._ws_requested or not self.client.api_key:
                try:
                    await asyncio.wait_for(self._ws_wakeup.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
                self._ws_wakeup.clear()
                continue
            try:
                await self._ws_run_once()
                backoff = 2
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"[三角洲订阅] WebSocket 连接断开：{type(exc).__name__}，{backoff} 秒后重连")
                try:
                    await asyncio.wait_for(self._ws_stop.wait(), timeout=backoff)
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, 60)

    async def _ws_run_once(self) -> None:
        uri, origin = self._ws_uri()
        header_argument = self._ws_header_argument(websockets.connect)
        connect_options = {
            "origin": origin,
            "ping_interval": 20,
            "ping_timeout": 60,
            "close_timeout": 5,
            header_argument: {"X-API-Key": self.client.api_key},
        }
        try:
            async with websockets.connect(uri, **connect_options) as connection:
                self._ws_connection = connection
                request_id = f"astrbot-{int(dt.datetime.now().timestamp() * 1000)}"
                envelope = {
                    "id": request_id,
                    "type": "record.client.subscribe",
                    "kind": "request",
                    "data": {"client_id": self._ws_client_id()},
                    "ts": int(dt.datetime.now().timestamp() * 1000),
                }
                await connection.send(json.dumps(envelope, ensure_ascii=False))
                while True:
                    raw = await asyncio.wait_for(connection.recv(), timeout=10)
                    try:
                        message = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(message, dict):
                        continue
                    if message.get("kind") == "event" and message.get("type") == "record.new":
                        await self._push_record_event(message.get("data") or {})
                        continue
                    if message.get("id") != request_id or message.get("kind") not in {
                        "response",
                        "error",
                    }:
                        continue
                    if message.get("kind") == "error" or message.get("code", 0) not in {
                        0,
                        None,
                    }:
                        raise RuntimeError("战绩订阅请求被后端拒绝")
                    payload = message.get("data") if isinstance(message.get("data"), dict) else {}
                    if not payload.get("subscribed"):
                        raise RuntimeError("后端未确认战绩订阅频道")
                    break
                async for raw in connection:
                    if self._ws_stop.is_set():
                        break
                    try:
                        message = json.loads(raw)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(message, dict) and message.get("kind") == "event" and message.get("type") == "record.new":
                        await self._push_record_event(message.get("data") or {})
        finally:
            self._ws_connection = None

    async def _push_record_event(self, data: Dict[str, Any]) -> None:
        sub_id = str(data.get("subscription_id") or "")
        if not sub_id:
            return
        event_key = f"{sub_id}:{data.get('record_id') or ''}:{data.get('event_time') or ''}"
        if event_key in self._seen_record_events:
            return
        self._seen_record_events[event_key] = int(dt.datetime.now().timestamp())
        if len(self._seen_record_events) > 512:
            oldest = sorted(self._seen_record_events, key=self._seen_record_events.get)[:128]
            for key in oldest:
                self._seen_record_events.pop(key, None)

        subscriptions = [
            item
            for item in self.subscriptions.all()
            if str(item.get("subscription_id") or "") == sub_id
        ]
        targets: List[str] = []
        for item in subscriptions:
            item_targets = item.get("targets") if isinstance(item.get("targets"), dict) else {}
            for umo, flags in item_targets.items():
                if isinstance(flags, dict) and (flags.get("group") or flags.get("private")):
                    target = str(umo or "").strip()
                    if target and target not in targets:
                        targets.append(target)
        if not targets:
            return

        record = data.get("record") if isinstance(data.get("record"), dict) else {}
        if MessageChain is None or Plain is None:
            logger.warning("[三角洲订阅] 当前 AstrBot 版本缺少 MessageChain，无法发送主动推送。")
            return

        display_name = await self._record_push_display_name(subscriptions[0], data, record)
        template_data, text = self._record_push_data(data, record, display_name)
        image_path = None
        image_type = getattr(Comp, "Image", None) if Comp is not None else None
        if self.config.get("enable_image_render", True) and image_type is not None:
            try:
                image_path = await self.renderer.render_html(
                    "Template/recordPush/recordPush.html",
                    template_data,
                    {"viewport_width": 600, "viewport_height": 500},
                )
            except Exception as exc:
                logger.warning(f"[三角洲订阅] 战绩卡片渲染失败：{type(exc).__name__}")

        for umo in targets:
            try:
                components = [Plain(text)]
                if image_path:
                    try:
                        components.append(image_type.fromFileSystem(str(image_path)))
                    except Exception as exc:
                        image_path = None
                        logger.warning(f"[三角洲订阅] 创建战绩图片消息失败：{type(exc).__name__}")
                await self.context.send_message(umo, MessageChain(components))
            except Exception as exc:
                logger.warning(f"[三角洲订阅] 推送到 {umo} 失败：{type(exc).__name__}")

    async def _record_push_display_name(
        self,
        subscription: Dict[str, Any],
        data: Dict[str, Any],
        record: Dict[str, Any],
    ) -> str:
        manager = getattr(self, "bindings", None)
        if manager is not None and hasattr(manager, "get_user_bindings"):
            try:
                bindings = await manager.get_user_bindings(subscription.get("user_id"))
                binding_id = str(subscription.get("binding_id") or data.get("binding_id") or "")
                if binding_id:
                    binding = next(
                        (item for item in bindings if str(item.get("binding_id") or "") == binding_id),
                        {},
                    )
                else:
                    binding = bindings[0] if bindings else {}
                name = binding.get("nickname") or binding.get("delta_uid")
                if name:
                    return self.data_mgr.decode_text(name)
            except Exception as exc:
                logger.debug(f"[三角洲订阅] 读取本地角色名称失败：{type(exc).__name__}")

        name = (
            data.get("display_name")
            or data.get("displayName")
            or record.get("charac_name")
            or record.get("nickname")
            or "玩家"
        )
        return self.data_mgr.decode_text(name)

    def _record_push_data(
        self,
        data: Dict[str, Any],
        record: Dict[str, Any],
        display_name: str,
    ) -> Tuple[Dict[str, Any], str]:
        mode = str(data.get("record_type") or "").lower()
        mode_name = "烽火地带" if mode == "sol" else "全面战场" if mode == "mp" else "未知模式"
        map_name = self.data_mgr.decode_text(record.get("MapName") or record.get("mapName") or "")
        if not map_name:
            map_id = record.get("MapId") or record.get("MapID") or record.get("mapId") or record.get("mapID")
            map_name = self.data_mgr.get_map_name(map_id)
        operator_name = self.data_mgr.get_operator_name(
            record.get("ArmedForceId")
            or record.get("ArmedForceID")
            or record.get("DeployArmedForceType")
            or record.get("armedForceId")
        )
        time_text = str(record.get("dtEventTime") or record.get("eventTime") or data.get("event_time") or "-")
        template_data: Dict[str, Any] = {
            "isRecent": bool(data.get("is_recent") or data.get("isRecent")),
            "displayName": display_name or "玩家",
            "modeName": mode_name,
            "time": time_text,
            "map": map_name or "未知地图",
            "operator": operator_name or "未知干员",
            "mapBg": self.data_mgr.get_map_image_path(map_name, mode) or "",
            "operatorImg": self.data_mgr.get_operator_image_path(operator_name) or "",
        }

        title_prefix = "最近战绩｜" if template_data["isRecent"] else ""
        lines = [
            f"【三角洲战绩推送｜{title_prefix}{mode_name}】",
            f"玩家：{template_data['displayName']}",
            f"地图：{template_data['map']}",
            f"干员：{template_data['operator']}",
            f"时间：{time_text}",
        ]
        if mode == "sol":
            reason = str(record.get("EscapeFailReason") or "")
            income_raw = record.get("flowCalGainedPrice")
            if income_raw in (None, ""):
                income_raw = record.get("Gainedprice")
            if income_raw in (None, ""):
                income_raw = record.get("gainedPrice")
            has_income = income_raw not in (None, "")
            income = self.data_mgr.fmt_num(income_raw, "未知")
            kill_player = record.get("KillCount")
            if kill_player is None:
                kill_player = record.get("KillNum")
            kill_player = kill_player or 0
            kill_player_ai = record.get("KillPlayerAICount") or 0
            kill_ai = record.get("KillAICount") or 0
            template_data.update(
                {
                    "status": ESCAPE_REASONS.get(reason, "撤离失败"),
                    "statusClass": "success" if reason == "1" else "exit" if reason == "3" else "fail",
                    "duration": self.data_mgr.fmt_duration(record.get("DurationS") or 0),
                    "value": self.data_mgr.fmt_num(record.get("FinalPrice") or 0),
                    "income": income,
                    "incomeClass": (
                        "income-positive" if self._number(income_raw) >= 0 else "income-negative"
                    ) if has_income else "",
                    "killCount": kill_player,
                    "killAI": kill_ai,
                    "killPlayerAI": kill_player_ai,
                    "killsHtml": (
                        f'<span class="kill-item kill-player">玩家 {kill_player}</span>'
                        '<span class="kill-separator">/</span>'
                        f'<span class="kill-item kill-ai-player">AI玩家 {kill_player_ai}</span>'
                        '<span class="kill-separator">/</span>'
                        f'<span class="kill-item kill-ai">AI {kill_ai}</span>'
                    ),
                }
            )
            if self._number(record.get("Rescue")) > 0:
                template_data["rescue"] = record.get("Rescue")
            lines.extend(
                [
                    f"状态：{template_data['status']}",
                    f"存活：{template_data['duration']}",
                    f"带出价值：{template_data['value']}",
                    f"净收益：{template_data['income']}",
                    f"击杀：玩家({kill_player}) / AI玩家({kill_player_ai}) / AI({kill_ai})",
                ]
            )
        else:
            result = str(record.get("MatchResult") or record.get("Result") or "")
            template_data.update(
                {
                    "status": MP_RESULTS.get(result, "未知结果"),
                    "statusClass": "success" if result == "1" else "exit" if result == "3" else "fail",
                    "duration": self.data_mgr.fmt_duration(record.get("gametime") or record.get("DurationS") or 0),
                    "kda": f"{record.get('KillNum') or 0}/{record.get('Death') or 0}/{record.get('Assist') or 0}",
                    "score": self.data_mgr.fmt_num(record.get("TotalScore") or record.get("score") or 0),
                }
            )
            if self._number(record.get("RescueTeammateCount")) > 0:
                template_data["rescue"] = record.get("RescueTeammateCount")
            lines.extend(
                [
                    f"结果：{template_data['status']}",
                    f"K/D/A：{template_data['kda']}",
                    f"得分：{template_data['score']}",
                    f"时长：{template_data['duration']}",
                ]
            )

        if template_data.get("rescue"):
            lines.append(f"救援：{template_data['rescue']}次")
        lines.append(f"记录 ID：{data.get('record_id') or '未知'}")
        return template_data, "\n".join(lines)

    async def _toggle_scheduled_push(self, event: AstrMessageEvent, kind: str, enabled: bool) -> AsyncGenerator[Any, None]:
        """在当前群聊中开启或关闭一类定时推送。"""
        if not str(event.get_group_id() or "").strip():
            yield event.plain_result("该命令只能在群聊中使用。")
            return
        actor_user_id = str(event.get_sender_id())
        user_id = "" if kind == "keyword" else actor_user_id
        binding_id = ""
        if kind != "keyword":
            binding = await self.bindings.get_primary_binding(actor_user_id)
            if not binding or not binding.get("framework_token"):
                yield event.plain_result("您尚未绑定账号，请先完成登录。")
                return
            binding_id = str(binding.get("binding_id") or "")
        if kind == "keyword" and not event.is_admin():
            yield event.plain_result("只有群管理员可以设置每日密码推送。")
            return
        if kind == "place" and enabled:
            response = await self.client.place_status(str(binding.get("framework_token") or ""))
            if not self._ok(response):
                yield event.plain_result(f"当前账号无法查询特勤处状态：{self._message_of(response)}")
                return

        umo = event.unified_msg_origin
        if not enabled:
            changed = False
            for item in self.subscriptions.scheduled_pushes(kind, enabled_only=False):
                if str(item.get("user_id")) == user_id and str(item.get("umo")) == umo and item.get("enabled"):
                    self.subscriptions.update_scheduled_push(item["key"], {"enabled": False})
                    changed = True
            yield event.plain_result("已关闭本群推送。" if changed else "本群尚未开启该推送。")
            return

        self.subscriptions.set_scheduled_push(kind, user_id, binding_id, umo, True)
        names = {"daily": "日报", "weekly": "周报", "place": "特勤处生产完成", "keyword": "每日密码"}
        yield event.plain_result(f"已为本群开启{names[kind]}推送。")

    async def _scheduled_push_loop(self) -> None:
        interval = max(30, int(self.config.get("push_check_interval", 60) or 60))
        while True:
            try:
                await self._run_scheduled_pushes(dt.datetime.now())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(f"[三角洲定时推送] 本轮执行失败：{type(exc).__name__}")
            await asyncio.sleep(interval)

    async def _run_scheduled_pushes(self, now: dt.datetime) -> None:
        for item in self.subscriptions.scheduled_pushes():
            try:
                kind = str(item.get("kind") or "")
                if kind == "place":
                    await self._run_place_push(item, now)
                    continue
                run_key = self._scheduled_run_key(kind, now)
                if not run_key or item.get("last_run_key") == run_key:
                    continue
                success = await self._run_fixed_push(item, kind)
                if success:
                    self.subscriptions.update_scheduled_push(item["key"], {"last_run_key": run_key})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    f"[三角洲定时推送] 任务 {item.get('key') or '未知'} 执行失败：{type(exc).__name__}"
                )

    def _scheduled_run_key(self, kind: str, now: dt.datetime) -> str:
        hour = {
            "daily": self._config_int("daily_push_hour", 10),
            "weekly": self._config_int("weekly_push_hour", 10),
            "keyword": self._config_int("keyword_push_hour", 8),
        }.get(kind)
        if hour is None or now.hour < min(max(hour, 0), 23):
            return ""
        if kind == "weekly":
            weekday = min(max(self._config_int("weekly_push_weekday", 0), 0), 6)
            if now.weekday() != weekday:
                return ""
            return now.strftime("%G-W%V")
        return now.strftime("%Y-%m-%d")

    def _config_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    async def _binding_for_push(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rows = await self.bindings.get_user_bindings(item.get("user_id"))
        binding_id = str(item.get("binding_id") or "")
        return next((row for row in rows if str(row.get("binding_id") or "") == binding_id), None)

    async def _run_fixed_push(self, item: Dict[str, Any], kind: str) -> bool:
        if kind == "keyword":
            response = await self.client.daily_keyword()
            if not self._ok(response):
                return False
            data = self._data(response, {}) or {}
            rows = self._first_list(data, ("list", "items", "data"))
            if not rows:
                return True
            lines = ["【每日密码】"]
            for row in rows:
                if isinstance(row, dict):
                    lines.append(f"{row.get('mapName') or row.get('map') or '未知地图'}：{row.get('secret') or row.get('password') or '-'}")
            return await self._send_scheduled_message(item["umo"], "\n".join(lines))

        binding = await self._binding_for_push(item)
        token = str((binding or {}).get("framework_token") or "")
        if not token:
            logger.warning(f"[三角洲定时推送] 用户 {item.get('user_id')} 的绑定已失效")
            return False
        event = _ScheduledEvent(str(item.get("user_id") or ""))
        identity = await self._render_identity(event, token)
        if kind == "daily":
            response = await self.client.daily_record(token, "")
            if not self._ok(response):
                return False
            raw = self._payload(response, {}) or {}
            sol, mp = self._daily_details(raw, None)
            if not sol and not mp:
                return True
            data = self._build_daily(event, sol, mp, None, dt.datetime.now().strftime("%Y-%m-%d"), False, identity)
            image = await self.renderer.render_html(
                "Template/dailyReport/dailyReport.html", data, {"viewport_width": 1000, "viewport_height": 900}
            ) if self.config.get("enable_image_render", True) else None
            return await self._send_scheduled_message(item["umo"], self._summary_dict("三角洲日报", raw), image)
        if kind == "weekly":
            response = await self.client.weekly_record(token, "", "", True)
            if not self._ok(response):
                return False
            raw = self._payload(response, {}) or {}
            sol, mp, report_dm = self._weekly_details(raw, None)
            if not sol and not mp:
                return True
            data = self._build_weekly(event, sol, mp, report_dm, None, self._last_sunday(), identity)
            image = await self.renderer.render_html(
                "Template/weeklyReport/weeklyReport.html", data, {"viewport_width": 1100, "viewport_height": 1800}
            ) if self.config.get("enable_image_render", True) else None
            return await self._send_scheduled_message(item["umo"], self._summary_dict("三角洲周报", raw), image)
        return True

    async def _run_place_push(self, item: Dict[str, Any], now: dt.datetime) -> None:
        binding = await self._binding_for_push(item)
        token = str((binding or {}).get("framework_token") or "")
        if not token:
            return
        response = await self.client.place_status(token)
        if not self._ok(response):
            return
        data = self._data(response, {}) or {}
        places = self._first_list(data, ("places", "list", "items", "data"))
        old_jobs = item.get("place_jobs") if isinstance(item.get("place_jobs"), dict) else {}
        jobs = dict(old_jobs)
        now_ts = int(now.timestamp())
        active_ids = set()
        for place in places:
            if not isinstance(place, dict) or not isinstance(place.get("objectDetail"), dict):
                continue
            place_id = str(place.get("id") or place.get("placeId") or place.get("placeType") or "")
            if not place_id:
                continue
            finish_at = int(self._number(place.get("pushTime")))
            if finish_at > 10_000_000_000:
                finish_at //= 1000
            if finish_at <= 0:
                finish_at = now_ts + max(0, int(self._number(place.get("leftTime"))))
            job_id = f"{place_id}:{finish_at}:{place.get('objectId') or ''}"
            active_ids.add(job_id)
            if job_id not in jobs:
                detail = place["objectDetail"]
                jobs[job_id] = {
                    "finish_at": finish_at,
                    "place_name": place.get("placeName") or place.get("name") or place_id,
                    "object_name": detail.get("objectName") or detail.get("name") or "未知物品",
                    "notified": False,
                }
        due = [job for job in jobs.values() if not job.get("notified") and int(job.get("finish_at") or 0) <= now_ts]
        if due:
            lines = ["【特勤处生产完成】"]
            lines.extend(f"{job.get('place_name')}：{job.get('object_name')}" for job in due)
            if await self._send_scheduled_message(item["umo"], "\n".join(lines)):
                for job in due:
                    job["notified"] = True
        jobs = {
            key: value
            for key, value in jobs.items()
            if key in active_ids or not value.get("notified") or now_ts - int(value.get("finish_at") or 0) < 86400
        }
        self.subscriptions.update_scheduled_push(item["key"], {"place_jobs": jobs, "last_poll_at": now_ts})

    async def _send_scheduled_message(self, umo: str, text: str, image_path: Optional[str] = None) -> bool:
        if MessageChain is None or Plain is None:
            return False
        chain = MessageChain()
        if image_path and Comp is not None:
            chain.chain.append(Plain("三角洲定时推送\n"))
            chain.chain.append(Comp.Image.fromFileSystem(image_path))
        else:
            chain.chain.append(Plain(text))
        try:
            return bool(await self.context.send_message(umo, chain))
        except Exception as exc:
            logger.warning(f"[三角洲定时推送] 发送到 {umo} 失败：{type(exc).__name__}")
            return False

    async def _dispatch(self, event: AstrMessageEvent, msg: str) -> AsyncGenerator[Any, None]:
        body = self._body(msg)
        lowered = body.lower()

        if body in {"帮助", "菜单", "功能", "help", "三角洲帮助", "df帮助", "delta帮助"}:
            async for r in self._help(event, "main"):
                yield r
            return
        if body in {"娱乐帮助", "娱乐菜单", "娱乐功能"}:
            async for r in self._help(event, "entertainment"):
                yield r
            return
        if body in {"计算帮助", "计算菜单"}:
            async for r in self._help(event, "calculator"):
                yield r
            return

        if re.fullmatch(r"(qq|QQ|微信|wx|WX|wegame|WEGAME|wegame微信|微信wegame|qqsafe|QQsafe|安全中心|qq安全中心)?(登陆|登录)", body):
            async for r in self._login(event, body):
                yield r
            return
        if m := re.fullmatch(r"ck(?:登陆|登录)\s*(.*)", body, flags=re.S):
            async for r in self._cookie_login(event, m.group(1).strip()):
                yield r
            return
        if m := re.fullmatch(r"(qq|QQ|微信|wx|WX)(?:授权|auth|oauth)(?:登陆|登录)\s*(.*)", body, flags=re.S):
            async for r in self._oauth_login(event, m.group(1), m.group(2).strip()):
                yield r
            return
        if m := re.fullmatch(
            r"(?:微信安全中心授权登录|gamesafe授权登录|gamesafeoauth登录|微信安全中心oauth登录)\s*(.*)",
            body,
            flags=re.I | re.S,
        ):
            async for r in self._oauth_login(event, "gamesafe", m.group(1).strip()):
                yield r
            return
        if re.fullmatch(r"(网页|web|网站)(登陆|登录)", body):
            async for r in self._web_login(event):
                yield r
            return
        if m := re.fullmatch(r"角色绑定\s*([a-zA-Z0-9-]+)?", body):
            async for r in self._bind_character(event, m.group(1) or ""):
                yield r
            return
        if m := re.fullmatch(r"绑定\s*([a-zA-Z0-9-]+)", body):
            async for r in self._bind_token(event, m.group(1)):
                yield r
            return
        if re.fullmatch(r"账号(列表)?", body):
            async for r in self._account_list(event):
                yield r
            return
        if m := re.fullmatch(r"(?:账号切换|切换账号)\s*(\d+)", body):
            async for r in self._switch_account(event, int(m.group(1))):
                yield r
            return
        if m := re.fullmatch(r"(?:解绑|删除)\s*(\d+)", body):
            async for r in self._delete_account(event, int(m.group(1)), delete_login_data=body.startswith("删除")):
                yield r
            return
        if re.fullmatch(r"(微信刷新|刷新微信|qq刷新|QQ刷新|刷新qq|刷新QQ)", body):
            platform = "wechat" if "微信" in body else "qq"
            async for r in self._refresh_account(event, platform):
                yield r
            return

        if re.fullmatch(r"(信息|info)", body):
            async for r in self._user_info(event):
                yield r
            return
        if re.fullmatch(r"(uid|UID)", body):
            async for r in self._uid(event):
                yield r
            return
        if m := re.fullmatch(r"(数据|data)\s*(.*)", body):
            async for r in self._personal_data(event, m.group(2).strip()):
                yield r
            return
        if body.startswith("战绩"):
            async for r in self._record(event, body[2:].strip()):
                yield r
            return
        if m := re.fullmatch(r"(日报|daily)\s*(.*)", body):
            async for r in self._daily(event, m.group(2).strip(), yesterday=False):
                yield r
            return
        if m := re.fullmatch(r"(昨日收益|昨日物资)\s*(.*)", body):
            async for r in self._daily(event, m.group(2).strip(), yesterday=True):
                yield r
            return
        if m := re.fullmatch(r"(周报|weekly)\s*(.*)", body):
            async for r in self._weekly(event, m.group(2).strip()):
                yield r
            return
        if m := re.fullmatch(r"(地图统计|mapStats|地图数据)\s*(.*)", body):
            async for r in self._map_stats(event, m.group(2).strip()):
                yield r
            return
        if re.fullmatch(r"(货币|money|余额)", body):
            async for r in self._money(event):
                yield r
            return
        if m := re.fullmatch(r"(流水|flows)(?:\s+(设备|道具|货币|all))?(?:\s+(all|\d+))?", body):
            async for r in self._flows(event, m.group(2) or "", m.group(3) or "1"):
                yield r
            return
        if m := re.fullmatch(r"(藏品|资产)(?:\s+(.*))?", body):
            async for r in self._collection(event, (m.group(2) or "").strip()):
                yield r
            return
        if m := re.fullmatch(r"(出红记录|大红记录|藏品记录|大红收藏|大红藏品|大红海报|藏品海报)(?:\s+(.+))?", body):
            async for r in self._red_records(event, m.group(1), (m.group(2) or "").strip()):
                yield r
            return
        if re.fullmatch(r"(封号记录|违规记录|违规历史|封号历史)", body):
            async for r in self._ban_history(event):
                yield r
            return
        if re.fullmatch(r"(微信安全中心绑定|gamesafe绑定|微信安全中心账号)", body, flags=re.I):
            async for r in self._gamesafe_bindings(event):
                yield r
            return
        if re.fullmatch(r"(微信安全中心登录信息|gamesafe登录信息)", body, flags=re.I):
            async for r in self._gamesafe_query(event, "login"):
                yield r
            return
        if m := re.fullmatch(
            r"(?:微信安全中心封禁记录|gamesafe封禁记录|微信安全中心处罚记录)(?:\s+(\d{5,20}))?",
            body,
            flags=re.I,
        ):
            async for r in self._gamesafe_query(event, "punish", m.group(1) or ""):
                yield r
            return
        if m := re.fullmatch(
            r"(?:微信安全中心冻结状态|gamesafe冻结状态)(?:\s+(\d{5,20}))?",
            body,
            flags=re.I,
        ):
            async for r in self._gamesafe_query(event, "frozen", m.group(1) or ""):
                yield r
            return
        if m := re.fullmatch(
            r"(?:微信安全中心设备|gamesafe设备|微信安全中心设备列表)(?:\s+(\d{5,20}))?",
            body,
            flags=re.I,
        ):
            async for r in self._gamesafe_query(event, "devices", m.group(1) or ""):
                yield r
            return
        if re.fullmatch(r"(微信安全中心在线状态|gamesafe在线状态)", body, flags=re.I):
            async for r in self._gamesafe_query(event, "online"):
                yield r
            return
        if m := re.fullmatch(
            r"(?:微信安全中心安全报告|gamesafe安全报告)(?:\s+(\d{5,20}))?",
            body,
            flags=re.I,
        ):
            async for r in self._gamesafe_query(event, "report", m.group(1) or ""):
                yield r
            return
        if re.fullmatch(r"(特勤处状态|placestatus)", body):
            async for r in self._place_status(event):
                yield r
            return
        if m := re.fullmatch(r"(特勤处信息|placeinfo)\s*(.*)", body):
            async for r in self._place_info(event, m.group(2).strip()):
                yield r
            return
        if body == "健康状态":
            async for r in self._health_info(event):
                yield r
            return
        if body == "服务器状态":
            async for r in self._server_status(event):
                yield r
            return
        if body == "用户统计":
            async for r in self._user_stats(event):
                yield r
            return

        if body == "干员列表":
            async for r in self._operator_list(event):
                yield r
            return
        if m := re.fullmatch(r"干员\s+(.+)", body):
            async for r in self._operator_info(event, m.group(1).strip()):
                yield r
            return

        if m := re.fullmatch(r"物品列表\s*(.*)", body):
            async for r in self._object_list(event, m.group(1).strip()):
                yield r
            return
        if m := re.fullmatch(r"物品搜索\s+(.+)", body):
            async for r in self._object_search(event, m.group(1).strip()):
                yield r
            return
        if m := re.fullmatch(r"(当前价格|最新价格|价格)\s+(.+)", body):
            async for r in self._price_now(event, m.group(2).strip()):
                yield r
            return
        if m := re.fullmatch(r"(价格历史|历史价格)\s+(.+)", body):
            async for r in self._price_history(event, m.group(2).strip()):
                yield r
            return
        if m := re.fullmatch(r"(材料价格|制造材料)\s*(.*)", body):
            async for r in self._material_price(event, m.group(2).strip()):
                yield r
            return
        if m := re.fullmatch(r"(利润历史|历史利润|利润排行|利润榜|最高利润|利润排行v2|利润榜v2|特勤处利润|特勤利润)\s*(.*)", body):
            async for r in self._profit(event, m.group(1), m.group(2).strip()):
                yield r
            return
        if m := re.fullmatch(r"上传(改枪码|改枪方案)\s*(.*)", body, flags=re.S):
            async for r in self._solution_upload(event, m.group(2).strip()):
                yield r
            return
        if m := re.fullmatch(r"(改枪码|改枪方案)列表\s*(.*)", body):
            async for r in self._solution_list(event, m.group(2).strip(), favorites=False):
                yield r
            return
        if m := re.fullmatch(r"(改枪码|改枪方案)详情\s+(\S+)", body):
            async for r in self._solution_detail(event, m.group(2)):
                yield r
            return
        if m := re.fullmatch(r"(改枪码|改枪方案)(点赞|点踩)\s+(\S+)", body):
            async for r in self._solution_vote(event, m.group(3), 1 if m.group(2) == "点赞" else -1):
                yield r
            return
        if m := re.fullmatch(r"更新(改枪码|改枪方案)\s+(\S+)\s+(.+)", body, flags=re.S):
            async for r in self._solution_update(event, m.group(2), m.group(3).strip()):
                yield r
            return
        if m := re.fullmatch(r"删除(改枪码|改枪方案)\s+(\S+)", body):
            async for r in self._solution_delete(event, m.group(2)):
                yield r
            return
        if m := re.fullmatch(r"(收藏|取消收藏)(改枪码|改枪方案)\s+(\S+)", body):
            async for r in self._solution_favorite(event, m.group(3), m.group(1) == "收藏"):
                yield r
            return
        if re.fullmatch(r"(改枪码|改枪方案)收藏列表", body):
            async for r in self._solution_list(event, "", favorites=True):
                yield r
            return

        if re.fullmatch(r"(每日密码|今日密码)", body):
            async for r in self._daily_keyword(event):
                yield r
            return
        if re.fullmatch(r"(活动日历|活动列表|活动)", body):
            async for r in self._activities(event):
                yield r
            return
        if body == "文章列表":
            async for r in self._article_list(event):
                yield r
            return
        if m := re.fullmatch(r"(文章详情|文章)\s*(\d+)", body):
            async for r in self._article_detail(event, m.group(2)):
                yield r
            return

        if body == "ai预设列表" or lowered == "ai预设列表":
            async for r in self._ai_presets(event):
                yield r
            return
        if m := re.fullmatch(r"(ai|AI)锐评\s*(.*)", body):
            async for r in self._ai_review(event, m.group(2).strip(), preset_required=False):
                yield r
            return
        if m := re.fullmatch(r"(ai|AI)评价\s+(\S+)\s+(\S+)(?:\s+(\S+))?", body):
            async for r in self._ai_review(
                event,
                f"{m.group(2)} {m.group(3)} {m.group(4) or ''}".strip(),
                preset_required=True,
            ):
                yield r
            return

        if re.fullmatch(r"(语音列表|标签列表|语音分类|语音统计)", body):
            async for r in self._voice_meta(event, body):
                yield r
            return
        if m := re.fullmatch(r"语音\s*(.*)", body):
            async for r in self._voice(event, m.group(1).strip()):
                yield r
            return
        if re.fullmatch(r"(歌词|鼠鼠歌词|鼠鼠音乐歌词)", body):
            async for r in self._music_lyrics(event):
                yield r
            return
        if body == "鼠鼠语音":
            async for r in self._music_replay(event):
                yield r
            return
        if m := re.fullmatch(r"鼠鼠音乐(列表|排行榜)\s*(\d*)", body):
            async for r in self._music_list(event, m.group(2) or "1"):
                yield r
            return
        if m := re.fullmatch(r"鼠鼠歌单\s*(.*)", body):
            async for r in self._music_playlist(event, m.group(1).strip()):
                yield r
            return
        if m := re.fullmatch(r"(点歌|听|听歌|播放)\s*(\d+)", body):
            async for r in self._music_select(event, int(m.group(2))):
                yield r
            return
        if m := re.fullmatch(r"鼠鼠音乐\s*(.*)", body):
            async for r in self._music(event, m.group(1).strip()):
                yield r
            return
        if body in {"音乐缓存状态", "音乐缓存统计"}:
            yield event.plain_result(self._music_cache_status())
            return
        if body == "清理音乐缓存":
            async for r in self._music_cache_clear(event):
                yield r
            return
        if body == "tts状态":
            async for r in self._tts_status(event):
                yield r
            return
        if re.fullmatch(r"tts(角色|预设)(列表)?", body):
            async for r in self._tts_presets(event):
                yield r
            return
        if m := re.fullmatch(r"tts角色详情\s*(.+)", body):
            async for r in self._tts_preset(event, m.group(1).strip()):
                yield r
            return
        if body in {"tts上传", "tts下载"}:
            async for r in self._tts_recent(event, as_file=True):
                yield r
            return
        if body in {"tts重播", "tts语音"}:
            async for r in self._tts_recent(event, as_file=False):
                yield r
            return
        if m := re.fullmatch(r"tts\s+([\s\S]+)", body):
            async for r in self._tts(event, m.group(1).strip()):
                yield r
            return

        if body in {"战备计算", "战备"}:
            async for r in self._readiness_session(event):
                yield r
            return
        if re.fullmatch(r"(伤害计算|伤害|维修计算|维修)", body):
            async for r in self._calculator_help(event, body):
                yield r
            return
        if m := re.fullmatch(r"(修甲|修理)\s+(.+?)\s+(\d+(?:\.\d+)?)[/／](\d+(?:\.\d+)?)\s+(局内|局外|inside|outside)", body):
            async for r in self._quick_repair(event, m.group(2), m.group(3), m.group(4), m.group(5)):
                yield r
            return
        if m := re.fullmatch(r"(伤害|dmg)\s+(.+)", body):
            async for r in self._quick_damage(event, m.group(2).strip()):
                yield r
            return
        if body in {"计算映射表", "映射表"}:
            yield event.plain_result(self.calculator.mapping_text())
            return
        if body in {"取消计算", "取消"}:
            yield event.plain_result("当前没有进行中的计算会话。")
            return

        if re.fullmatch(r"(ws|WS|websocket|WebSocket)(连接|启动|开启|断开|关闭|停止|状态|status)", body):
            if body.endswith(("断开", "关闭", "停止")):
                self._ws_requested = False
                self._ws_wakeup.set()
                if self._ws_connection is not None:
                    try:
                        await self._ws_connection.close()
                    except Exception:
                        pass
                yield event.plain_result("已停止三角洲 WebSocket 战绩推送。")
            elif body.endswith(("状态", "status")):
                state = "已连接" if self._ws_connection is not None else "等待连接"
                if websockets is None:
                    state = "未安装 websockets"
                yield event.plain_result(f"WebSocket 状态：{state}。")
            else:
                self._ws_requested = True
                self._ws_wakeup.set()
                yield event.plain_result("已请求连接三角洲 WebSocket，连接成功后会自动订阅当前客户端战绩。")
            return
        if body.startswith(("订阅", "取消订阅", "订阅状态")):
            async for result in self._record_subscription(event, body):
                yield result
            return
        if body in {"开启本群订阅推送", "关闭本群订阅推送"}:
            async for result in self._subscription_target(event, "group", body.startswith("开启")):
                yield result
            return
        if body in {"开启私信订阅推送", "关闭私信订阅推送"}:
            async for result in self._subscription_target(event, "private", body.startswith("开启")):
                yield result
            return
        if "广播" in body or "通知" in body:
            yield event.plain_result("最新版后端未提供通用通知广播协议，该功能当前无法接入；战绩实时推送不受影响。")
            return
        if match := re.fullmatch(r"(开启|关闭)(日报推送|周报推送|特勤处推送|每日密码推送)", body):
            kind = {
                "日报推送": "daily",
                "周报推送": "weekly",
                "特勤处推送": "place",
                "每日密码推送": "keyword",
            }[match.group(2)]
            async for result in self._toggle_scheduled_push(event, kind, match.group(1) == "开启"):
                yield result
            return
        if body.startswith("房间信息"):
            parts = body.split()
            if len(parts) != 3:
                yield event.plain_result("用法：房间信息 <烽火/全面> <对局房间ID>，例如：房间信息 烽火 123456。")
                return
            async for result in self._battle_room_info(event, parts[1], parts[2]):
                yield result
            return
        if body.startswith(("房间", "创建房间", "加入房间", "退出房间", "解散房间", "踢人")):
            yield event.plain_result("最新版后端仅提供战绩房间详情查询，没有创建、加入、退出、踢人等房间管理路由，因此当前无法等价移植。")
            return
        if body in {"更新日志", "插件更新日志", "update_log"}:
            async for result in self._update_log(event):
                yield result
            return
        if body in {"更新", "强制更新", "插件更新", "插件强制更新", "update"}:
            async for result in self._update_plugin(event, force=body in {"强制更新", "插件强制更新"}):
                yield result
            return

        yield event.plain_result("未识别的三角洲命令。发送 帮助 查看菜单。")

    async def _help(self, event: AstrMessageEvent, kind: str) -> AsyncGenerator[Any, None]:
        file_map = {
            "main": "main_default.yaml",
            "entertainment": "entertainment_default.yaml",
            "calculator": "calculator_help_default.yaml",
        }
        path = os.path.join(self.plugin_path, "config", "help", file_map[kind])
        try:
            cfg = yaml.safe_load(open(path, "r", encoding="utf-8")) or {}
        except Exception as exc:
            yield event.plain_result(f"读取帮助配置失败: {exc}")
            return
        cfg_prefix = {"main": "", "entertainment": "entertainment", "calculator": "calculator"}[kind]
        help_cfg = cfg.get("helpCfg") or cfg.get(f"{cfg_prefix}HelpCfg") or {}
        help_list = cfg.get("helpList") or cfg.get(f"{cfg_prefix}HelpList") or {}
        groups = []
        if isinstance(help_list, list):
            help_list = {"left": help_list}
        for area in ("fullWidth", "left", "right"):
            for group in (help_list.get(area, []) if isinstance(help_list, dict) else []) or []:
                if group.get("masterOnly") and not event.is_admin():
                    continue
                groups.append(dict(group, area=area))
        data = {
            "helpCfg": help_cfg,
            "helpGroup": groups,
            "topFullWidthGroups": [g for g in groups if g["area"] == "fullWidth"],
            "leftGroups": [g for g in groups if g["area"] == "left"],
            "rightGroups": [g for g in groups if g["area"] == "right"],
            "bottomFullWidthGroups": [],
            "colCount": int(help_cfg.get("colCount", 2) or 2),
            "bgType": 0,
            "style": "",
            "copyright": "AstrBot DeltaForce Plugin",
        }
        text = "三角洲帮助\n" + "\n".join(
            f"{item.get('title', '')} - {item.get('desc', '')}"
            for g in groups
            for item in (g.get("list") or [])
        )[:3500]
        async for r in self._render_or_text(event, "help/index.html", data, text, {"viewport_width": 1300, "viewport_height": 1600}):
            yield r

    @staticmethod
    def _parse_changelog(content: str, limit: int = 2) -> List[Dict[str, Any]]:
        releases: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        section: Optional[Dict[str, Any]] = None

        for line in str(content or "").splitlines():
            text = line.strip()
            version_match = re.fullmatch(r"##\s+\[([^\]]+)\]\s*-\s*(.+)", text)
            if version_match:
                if current and current["sections"]:
                    releases.append(current)
                    if len(releases) >= max(1, limit):
                        break
                current = {
                    "version": version_match.group(1).strip(),
                    "date": version_match.group(2).strip(),
                    "sections": [],
                }
                section = None
                continue
            if not current:
                continue
            section_match = re.fullmatch(r"###\s+(.+)", text)
            if section_match:
                section = {"title": section_match.group(1).strip(), "items": []}
                current["sections"].append(section)
                continue
            item_match = re.fullmatch(r"-\s+(.+)", text)
            if item_match and section is not None:
                section["items"].append(item_match.group(1).strip())

        if current and current["sections"] and len(releases) < max(1, limit):
            releases.append(current)
        for release in releases:
            release["sections"] = [item for item in release["sections"] if item["items"]]
        return [release for release in releases if release["sections"]][: max(1, limit)]

    async def _update_log(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        path = Path(self.plugin_path) / "CHANGELOG.md"
        try:
            with open(path, "r", encoding="utf-8") as file:
                content = file.read().strip()
        except FileNotFoundError:
            yield event.plain_result("当前安装包未包含更新日志。")
            return
        except Exception as exc:
            yield event.plain_result(f"读取更新日志失败: {type(exc).__name__}")
            return
        if not content:
            yield event.plain_result("更新日志暂无内容。")
            return
        suffix = "\n\n内容较长，已截取前 3500 字。" if len(content) > 3500 else ""
        fallback = content[:3500] + suffix
        changelogs = self._parse_changelog(content)
        if not changelogs:
            yield event.plain_result(fallback)
            return
        data = {
            "name": "三角洲行动",
            "currentVersion": PLUGIN_VERSION,
            "changelogs": changelogs,
        }
        async for result in self._render_or_text(
            event,
            "help/version-info.html",
            data,
            fallback,
            {"viewport_width": 760, "viewport_height": 1200},
        ):
            yield result

    async def _update_plugin(self, event: AstrMessageEvent, force: bool = False) -> AsyncGenerator[Any, None]:
        if not event.is_admin():
            yield event.plain_result("只有管理员可以更新三角洲行动插件。")
            return
        manager = getattr(self.context, "_star_manager", None)
        if manager is None or not hasattr(manager, "update_plugin"):
            yield event.plain_result("当前 AstrBot 环境未提供插件更新管理器，请在 WebUI 插件管理页更新。")
            return
        action = "强制更新" if force else "更新"
        yield event.plain_result(f"正在通过 AstrBot 插件管理器{action}三角洲行动插件，请稍候。")
        try:
            await manager.update_plugin("sanjiaozhou")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield event.plain_result(f"插件{action}失败: {str(exc) or type(exc).__name__}")
            return
        yield event.plain_result("插件更新并重载成功。")

    async def _login(self, event: AstrMessageEvent, body: str) -> AsyncGenerator[Any, None]:
        platform_raw = re.sub(r"(登陆|登录)$", "", body).strip().lower()
        platform = {
            "": "qq",
            "qq": "qq",
            "微信": "wechat",
            "wx": "wechat",
            "wegame": "wegame",
            "wegame微信": "wegame/wechat",
            "微信wegame": "wegame/wechat",
            "qqsafe": "qqsafe",
            "安全中心": "qqsafe",
            "qq安全中心": "qqsafe",
        }.get(platform_raw, platform_raw or "qq")
        res = await self.client.login_qr(platform)
        if not self._ok(res):
            yield event.plain_result(f"获取登录二维码失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        if not isinstance(data, dict):
            yield event.plain_result("登录接口返回格式异常，请稍后重试。")
            return
        token = data.get("frameworkToken") or data.get("framework_token") or data.get("token") or ""
        qr = data.get("qr_image") or data.get("qrImage") or data.get("qrcode") or data.get("qr") or data.get("url") or ""
        configured_timeout = max(
            1, int(self.config.get("login_poll_timeout", 180) or 180)
        )
        expiry = data.get("expire") or data.get("expires_at") or data.get("expiresAt")
        remaining_seconds = self._remaining_login_seconds(expiry, configured_timeout)
        if self._expiry_millis(expiry) and remaining_seconds <= 0:
            yield event.plain_result("登录二维码生成后已过期，请重新发起登录。")
            return
        msg = f"请扫码登录 {platform}，有效期约 {remaining_seconds} 秒。"
        if qr:
            try:
                qr_text = str(qr).strip()
                image_base64 = self._image_base64(qr_text)
                if Comp and image_base64:
                    yield event.chain_result([Comp.Plain(msg + "\n"), Comp.Image.fromBase64(image_base64)])
                elif Comp and qr_text.startswith(("http://", "https://")):
                    yield event.chain_result([Comp.Plain(msg + "\n"), Comp.Image.fromURL(qr_text)])
                elif Comp and os.path.isfile(qr_text):
                    yield event.chain_result([Comp.Plain(msg + "\n"), Comp.Image.fromFileSystem(qr_text)])
                elif qr_text.startswith(("http://", "https://")) or os.path.isfile(qr_text):
                    yield event.image_result(qr_text)
                elif image_base64:
                    yield event.plain_result("当前消息适配器无法发送二维码图片，请改用 OAuth 授权登录。")
                    return
                else:
                    yield event.plain_result("登录接口返回了不支持的二维码格式，请稍后重试。")
                    return
            except ValueError as exc:
                yield event.plain_result(f"登录二维码解析失败: {exc}")
                return
        else:
            yield event.plain_result("登录接口未返回可用二维码，请稍后重试。")
            return
        if not token:
            yield event.plain_result("登录接口未返回临时会话标识，无法继续轮询。")
            return
        timeout = min(configured_timeout, remaining_seconds)
        interval = int(self.config.get("login_poll_interval", 5) or 5)
        end_at = asyncio.get_running_loop().time() + timeout
        notified_scanned = False
        while asyncio.get_running_loop().time() < end_at:
            await asyncio.sleep(interval)
            status_res = await self.client.login_status(platform, token)
            status_data = self._data(status_res, {}) or {}
            if not isinstance(status_data, dict):
                status_data = {}
            root_code = status_res.get("code") if isinstance(status_res, dict) else None
            if "code" not in status_data and root_code in {-2, -3, -4, "-2", "-3", "-4"}:
                status_data = status_res
            if not self._ok(status_res) and not status_data.get("code") in {-2, -3, -4, "-2", "-3", "-4"}:
                yield event.plain_result(f"登录状态查询失败: {self._message_of(status_res)}")
                return
            state = str(status_data.get("status") or status_data.get("state") or "").strip().lower()
            status_code_raw = status_data.get("code")
            try:
                status_code = int(status_code_raw)
            except (TypeError, ValueError):
                status_code = {"pending": 1, "scanned": 2, "authed": 0, "done": 0, "expired": -2, "risk_control": -3}.get(state, -4)
            new_token = status_data.get("frameworkToken") or status_data.get("framework_token") or status_data.get("token") or token

            if status_code == 0:
                message = await self._finish_login(event, new_token, platform, "扫码登录")
                yield event.plain_result(message)
                return
            if status_code == 2:
                if not notified_scanned:
                    notified_scanned = True
                    yield event.plain_result("二维码已扫码，请在手机上确认登录。")
                continue
            if status_code == 1:
                continue
            if status_code == -2:
                yield event.plain_result("登录二维码已过期，请重新发起登录。")
                return
            if status_code == -3:
                yield event.plain_result("登录被安全风控拦截，请在手机上确认或改用 OAuth 授权登录。")
                return
            status_message = status_data.get("msg") or status_data.get("message") or "未知状态"
            yield event.plain_result(f"登录状态异常: {status_message}")
            return
        yield event.plain_result("登录轮询超时。如已获取 frameworkToken，可发送 绑定 <token> 手动绑定。")

    async def _cookie_login(self, event: AstrMessageEvent, cookie: str) -> AsyncGenerator[Any, None]:
        if not cookie:
            yield event.plain_result("用法：ck登录 <cookie>")
            return
        recalled = await self._recall_sensitive_message(event, "Cookie 凭证")
        privacy_notice = self._privacy_notice(recalled, "Cookie 凭证")
        if privacy_notice:
            yield event.plain_result(privacy_notice)
        res = await self.client.login_cookie(cookie)
        if not self._ok(res):
            message = self._redact_secret(self._message_of(res), cookie)
            yield event.plain_result(f"Cookie 登录失败: {message}")
            return
        data = self._data(res, {}) or {}
        token = data.get("frameworkToken") or data.get("framework_token") or data.get("token")
        if not token:
            yield event.plain_result("Cookie 登录成功但未返回 frameworkToken。")
            return
        message = await self._finish_login(event, str(token), "qq", "Cookie 登录")
        yield event.plain_result(message)

    async def _oauth_login(self, event: AstrMessageEvent, platform: str, extra: str) -> AsyncGenerator[Any, None]:
        platform_key = platform.lower()
        if platform_key in {"微信", "wx", "wechat"}:
            pf = "wechat"
        elif platform_key == "gamesafe":
            pf = "gamesafe"
        else:
            pf = "qq"
        session_key = (str(event.get_sender_id()), pf)
        command_name = {
            "wechat": "微信授权登录",
            "gamesafe": "微信安全中心授权登录",
        }.get(pf, "qq授权登录")

        if not extra:
            res = await self.client.oauth_url(pf, platform_id=self._user_identifier(event), bot_id=self._client_id(event))
            if not self._ok(res):
                yield event.plain_result(f"获取 OAuth 链接失败: {self._message_of(res)}")
                return
            data = self._data(res, {}) or {}
            if not isinstance(data, dict):
                yield event.plain_result("OAuth 接口返回格式异常，请稍后重试。")
                return
            url = data.get("loginUrl") or data.get("login_url") or data.get("auth_url") or data.get("oauth_url") or data.get("url") or ""
            framework_token = data.get("frameworkToken") or data.get("framework_token") or ""
            state = str(data.get("state") or framework_token).strip()
            expire = self._expiry_millis(
                data.get("expire") or data.get("expires_at") or data.get("expiresAt")
            )
            if not url or not framework_token or not state:
                yield event.plain_result("OAuth 接口响应缺少授权链接或会话标识，请稍后重试。")
                return
            self._oauth_sessions[session_key] = {
                "framework_token": str(framework_token),
                "state": state,
                "expire": expire,
            }
            yield event.plain_result(
                f"请在对应客户端中打开以下链接完成授权：\n{url}\n\n"
                f"授权后复制浏览器最终停留的完整回调 URL，并发送：\n"
                f"{command_name} <完整回调URL>\n\n"
                "回调 URL 含敏感授权信息，请勿转发给他人。"
            )
            return

        recalled = await self._recall_oauth_callback(event)
        notice = self._privacy_notice(recalled, "授权信息")
        privacy_notice = f"\n{notice}" if notice else ""
        code, state = self._oauth_callback_parts(extra)
        if not code or not state:
            yield event.plain_result(
                "回调 URL 无效，必须是包含 code 和 state 的完整 http(s) 地址。"
                + privacy_notice
            )
            return

        session = self._oauth_sessions.get(session_key)
        now_ms = int(dt.datetime.now().timestamp() * 1000)
        if session and session.get("expire") and now_ms >= int(session["expire"]):
            self._oauth_sessions.pop(session_key, None)
            yield event.plain_result(
                "OAuth 授权会话已过期，请重新获取授权链接。" + privacy_notice
            )
            return
        if session and state != session.get("state"):
            yield event.plain_result(
                "OAuth 回调的 state 与当前会话不匹配，请重新获取授权链接。"
                + privacy_notice
            )
            return

        framework_token = str((session or {}).get("framework_token") or state)
        res = await self.client.oauth_submit(
            pf,
            {
                "callbackUrl": extra.strip(),
                "frameworkToken": framework_token,
            },
        )
        if not self._ok(res):
            yield event.plain_result(
                f"OAuth 授权提交失败: {self._message_of(res)}{privacy_notice}"
            )
            return
        data = self._data(res, {}) or {}
        if not isinstance(data, dict):
            yield event.plain_result(
                "OAuth 提交响应格式异常，未保存任何凭证。" + privacy_notice
            )
            return
        final_token = data.get("frameworkToken") or data.get("framework_token") or data.get("token") or framework_token
        if not final_token:
            yield event.plain_result(
                "OAuth 授权成功，但接口未返回 frameworkToken。" + privacy_notice
            )
            return

        self._oauth_sessions.pop(session_key, None)
        message = await self._finish_login(event, str(final_token), pf, "OAuth 登录")
        yield event.plain_result(message + privacy_notice)

    async def _web_login(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        client_id = self._client_id(event)
        res = await self.client.create_authorization_request(
            client_id,
            "AstrBot 三角洲行动",
            self._user_identifier(event),
        )
        if not self._ok(res):
            yield event.plain_result(f"创建网页登录授权请求失败：{self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        if not isinstance(data, dict):
            yield event.plain_result("网页登录授权接口返回格式异常，请稍后重试。")
            return
        request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
        auth_url = self.client.resolve_url(data.get("auth_url") or data.get("authUrl") or "")
        if not re.fullmatch(r"req_[A-Za-z0-9]+", request_id) or not auth_url.startswith(
            ("http://", "https://")
        ):
            yield event.plain_result("网页登录授权接口未返回有效的请求标识或授权链接。")
            return

        configured_timeout = max(
            1, int(self.config.get("login_poll_timeout", 180) or 180)
        )
        expiry = data.get("expires_at") or data.get("expiresAt") or data.get("expire")
        remaining_seconds = self._remaining_login_seconds(expiry, configured_timeout)
        if self._expiry_millis(expiry) and remaining_seconds <= 0:
            yield event.plain_result("网页登录授权请求生成后已过期，请重新发起。")
            return
        wait_seconds = min(configured_timeout, remaining_seconds)
        yield event.plain_result(
            "请在浏览器打开以下链接，登录三角洲 API 平台后选择账号并批准授权：\n"
            f"{auth_url}\n\n"
            f"插件将在约 {wait_seconds} 秒内自动等待结果，无需复制 frameworkToken。"
        )

        interval = max(1, int(self.config.get("login_poll_interval", 5) or 5))
        end_at = asyncio.get_running_loop().time() + wait_seconds
        consecutive_errors = 0
        while asyncio.get_running_loop().time() < end_at:
            await asyncio.sleep(interval)
            status_res = await self.client.authorization_request_status(request_id)
            if not self._ok(status_res):
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    yield event.plain_result(
                        f"查询网页登录授权状态失败：{self._message_of(status_res)}"
                    )
                    return
                continue
            consecutive_errors = 0
            status_data = self._data(status_res, {}) or {}
            if not isinstance(status_data, dict):
                yield event.plain_result("网页登录授权状态返回格式异常，请重新发起。")
                return
            status = str(status_data.get("status") or "").strip().lower()
            final_token = str(
                status_data.get("framework_token")
                or status_data.get("frameworkToken")
                or ""
            ).strip()
            if status in {"approved", "used"} and final_token:
                binding_info = status_data.get("binding_info") or status_data.get(
                    "bindingInfo"
                )
                login_type = (
                    str(binding_info.get("token_type") or binding_info.get("tokenType") or "")
                    if isinstance(binding_info, dict)
                    else ""
                ).lower()
                message = await self._finish_login(
                    event,
                    final_token,
                    login_type,
                    "网页登录",
                )
                yield event.plain_result(message)
                return
            if status == "pending" or status == "approved":
                continue
            if status == "rejected":
                yield event.plain_result("你已拒绝本次网页登录授权，未保存任何凭证。")
                return
            if status == "expired":
                yield event.plain_result("网页登录授权请求已过期，请重新发起。")
                return
            if status == "used":
                yield event.plain_result(
                    "网页登录授权结果已被领取，但接口未返回凭证，请重新发起授权。"
                )
                return
            yield event.plain_result(f"网页登录授权状态异常：{status or '未知状态'}。")
            return
        yield event.plain_result("网页登录等待超时，请重新发起授权。")

    async def _save_binding(
        self,
        event: AstrMessageEvent,
        token: str,
        login_type: str = "",
    ) -> Tuple[Dict[str, Any], bool, str]:
        user_identifier = self._user_identifier(event)
        client_id = self._client_id(event)
        res = await self.client.create_binding(token, user_identifier, client_id, "bot")
        remote_ok = self._ok(res)
        data = (self._data(res, {}) or {}) if remote_ok else {}
        api_binding = data.get("binding") if isinstance(data, dict) else None
        binding = await self.bindings.upsert_binding(
            event.get_sender_id(),
            api_binding
            or {
                "framework_token": token,
                "login_type": login_type,
                "nickname": "",
                "is_primary": True,
            },
        )
        binding_type = str(
            binding.get("token_type") or binding.get("login_type") or login_type
        ).lower()
        if binding_type != "gamesafe":
            await self._fill_binding_info(event, binding)
        return binding, remote_ok, "" if remote_ok else self._message_of(res)

    async def _finish_login(
        self,
        event: AstrMessageEvent,
        token: str,
        login_type: str,
        source: str,
    ) -> str:
        _binding, remote_ok, remote_message = await self._save_binding(event, token, login_type)
        safe_remote_message = self._redact_secret(remote_message, token)
        role_res = None
        if login_type in {"qq", "wechat"}:
            role_res = await self.client.bind_character(token)

        if remote_ok and (role_res is None or self._ok(role_res)):
            suffix = "账号和游戏角色均已绑定。" if role_res is not None else "已绑定为当前账号。"
            return f"{source}成功，{suffix}"
        if remote_ok:
            role_message = self._redact_secret(self._message_of(role_res), token)
            return (
                f"{source}成功，账号已绑定；自动绑定游戏角色失败：{role_message}。"
                "可稍后发送 角色绑定 重试。"
            )

        local_notice = f"后端账号绑定未确认：{safe_remote_message}；凭证已保存到 AstrBot 本地。"
        if role_res is None:
            return f"{source}成功，但{local_notice}"
        if self._ok(role_res):
            return f"{source}成功，游戏角色绑定已完成，但{local_notice}"
        role_message = self._redact_secret(self._message_of(role_res), token)
        return (
            f"{source}成功，但{local_notice}\n"
            f"自动绑定游戏角色也失败：{role_message}。可稍后发送 角色绑定 重试。"
        )

    async def _bind_token(self, event: AstrMessageEvent, token: str, login_type: str = "", quiet: bool = False) -> AsyncGenerator[Any, None]:
        if not quiet:
            recalled = await self._recall_sensitive_message(event, "frameworkToken 凭证")
            privacy_notice = self._privacy_notice(recalled, "frameworkToken 凭证")
            if privacy_notice:
                yield event.plain_result(privacy_notice)
        binding, remote_ok, remote_message = await self._save_binding(event, token, login_type)
        if not quiet:
            name = binding.get("nickname") or binding.get("delta_uid") or "未命名账号"
            safe_remote_message = self._redact_secret(remote_message, token)
            if remote_ok:
                yield event.plain_result(f"绑定成功：{name}")
            else:
                yield event.plain_result(
                    f"后端绑定接口未确认：{safe_remote_message}\n"
                    f"已先保存到 AstrBot 本地绑定：{name}。"
                )

    async def _fill_binding_info(self, event: AstrMessageEvent, binding: Dict[str, Any]):
        token = binding.get("framework_token", "")
        if not token:
            return
        try:
            res = await self.client.personal_info(token)
            data = self._data(res, {}) or {}
            role = data.get("roleInfo") or (data.get("data") or {}).get("roleInfo") or data.get("role_info") or {}
            user_data = (data.get("data") or {}).get("userData") or data.get("userData") or {}
            name = self.data_mgr.decode_text(user_data.get("charac_name") or role.get("charac_name") or role.get("nickname") or "")
            avatar = self.data_mgr.decode_text(user_data.get("picurl") or role.get("picurl") or "")
            if avatar and avatar.isdigit():
                avatar = f"https://wegame.gtimg.com/g.2001918-r.ea725/helper/df/skin/{avatar}.webp"
            await self.bindings.upsert_binding(
                event.get_sender_id(),
                {
                    **binding,
                    "nickname": name or binding.get("nickname", ""),
                    "avatar": avatar or binding.get("avatar", ""),
                    "delta_uid": role.get("uid") or binding.get("delta_uid", ""),
                },
            )
        except Exception:
            pass

    async def _bind_character(self, event: AstrMessageEvent, token_arg: str) -> AsyncGenerator[Any, None]:
        if token_arg:
            recalled = await self._recall_sensitive_message(event, "frameworkToken 凭证")
            privacy_notice = self._privacy_notice(recalled, "frameworkToken 凭证")
            if privacy_notice:
                yield event.plain_result(privacy_notice)
        token = token_arg or await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号，请先使用 登录 或 绑定 <token>。")
            return
        res = await self.client.bind_character(token)
        if not self._ok(res):
            message = self._redact_secret(self._message_of(res), token)
            yield event.plain_result(f"角色绑定失败: {message}")
            return
        yield event.plain_result("角色绑定请求已完成。")

    async def _account_list(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        bindings = await self.bindings.get_user_bindings(event.get_sender_id())
        if not bindings:
            yield event.plain_result("您尚未绑定任何账号，请使用 登录 或 绑定 <token>。")
            return
        lines = ["【三角洲账号列表】"]
        for idx, item in enumerate(bindings, 1):
            mark = "★" if item.get("is_primary") else " "
            name = item.get("nickname") or item.get("delta_uid") or "未命名账号"
            login_type = item.get("login_type") or item.get("token_type") or "unknown"
            uid = item.get("delta_uid") or "-"
            lines.append(f"{mark} {idx}. {name} [{login_type}] UID:{uid}")
        lines.append("\n账号切换 <序号> 切换，解绑 <序号> 删除本地绑定。")
        yield event.plain_result("\n".join(lines))

    async def _switch_account(self, event: AstrMessageEvent, index: int) -> AsyncGenerator[Any, None]:
        bindings = await self.bindings.get_user_bindings(event.get_sender_id())
        if index < 1 or index > len(bindings):
            yield event.plain_result("序号无效，请发送 账号 查看列表。")
            return
        target = bindings[index - 1]
        if not target.get("is_valid", True):
            yield event.plain_result("该账号凭证已失效，无法切换，请重新登录。")
            return
        binding_id = str(target.get("binding_id") or "")
        if binding_id and not binding_id.startswith("local-"):
            res = await self.client.set_primary_binding(
                binding_id,
                self._user_identifier(event),
                self._client_id(event),
            )
            if not self._ok(res):
                yield event.plain_result(f"账号切换失败: {self._message_of(res)}")
                return
        binding = await self.bindings.set_primary(event.get_sender_id(), index)
        if not binding:
            yield event.plain_result("序号无效，请发送 账号 查看列表。")
            return
        name = binding.get("nickname") or binding.get("delta_uid") or "未命名账号"
        yield event.plain_result(f"已切换到：{name}")

    async def _delete_account(self, event: AstrMessageEvent, index: int, delete_login_data: bool = False) -> AsyncGenerator[Any, None]:
        bindings = await self.bindings.get_user_bindings(event.get_sender_id())
        if index < 1 or index > len(bindings):
            yield event.plain_result("序号无效，请发送 账号 查看列表。")
            return
        target = bindings[index - 1]
        token = str(target.get("framework_token") or "")
        login_type = str(target.get("login_type") or target.get("token_type") or "").lower()
        binding_id = str(target.get("binding_id") or "")
        login_deleted = False

        if delete_login_data:
            if login_type not in {"qq", "wechat", "gamesafe"}:
                yield event.plain_result(
                    f"该账号类型（{login_type or '未知'}）不支持删除登录数据；"
                    "删除功能仅支持 QQ、微信和微信安全中心账号。"
                )
                return
            if not token:
                yield event.plain_result("该账号缺少 frameworkToken，无法删除登录数据。")
                return
            delete_res = await self.client.login_delete(login_type, token)
            if not self._ok(delete_res):
                yield event.plain_result(f"登录数据删除失败: {self._message_of(delete_res)}")
                return
            login_deleted = True

        if not login_deleted and binding_id and not binding_id.startswith("local-"):
            unbind_res = await self.client.delete_binding(
                binding_id,
                self._user_identifier(event),
                self._client_id(event),
            )
            if not self._ok(unbind_res):
                yield event.plain_result(f"账号解绑失败: {self._message_of(unbind_res)}")
                return

        binding = await self.bindings.delete_binding(event.get_sender_id(), index)
        if not binding:
            yield event.plain_result("本地账号状态已变化，请发送 账号 重新查看列表。")
            return
        if login_deleted:
            yield event.plain_result("登录数据已删除，账号绑定已自动解除。")
        elif binding_id.startswith("local-") or not binding_id:
            yield event.plain_result("已删除 AstrBot 本地账号绑定。")
        else:
            yield event.plain_result("账号解绑成功。")

    async def _refresh_account(self, event: AstrMessageEvent, platform: str) -> AsyncGenerator[Any, None]:
        binding = await self.bindings.get_primary_binding(event.get_sender_id())
        if not binding:
            yield event.plain_result("您尚未绑定账号。")
            return
        login_type = str(binding.get("login_type") or binding.get("token_type") or "").lower()
        if login_type != platform:
            platform_name = "微信" if platform == "wechat" else "QQ"
            yield event.plain_result(
                f"当前主账号类型为 {login_type or '未知'}，无法执行{platform_name}刷新；"
                "请先切换到对应账号。"
            )
            return
        token = str(binding.get("framework_token") or "")
        if not token:
            yield event.plain_result("当前账号缺少 frameworkToken，请重新登录。")
            return
        res = await self.client.login_refresh(platform, token)
        if not self._ok(res):
            yield event.plain_result(f"登录凭证刷新失败: {self._message_of(res)}")
            return
        platform_name = "微信" if platform == "wechat" else "QQ"
        yield event.plain_result(f"{platform_name}登录凭证刷新成功。")

    def _parse_mode_page(self, arg: str) -> Tuple[Optional[str], int, str]:
        mode = None
        page = 1
        rest = []
        for part in arg.split():
            low = part.lower()
            if part in SOL_ALIASES or low in SOL_ALIASES:
                mode = "sol"
            elif part in MP_ALIASES or low in MP_ALIASES:
                mode = "mp"
            elif part.isdigit():
                page = max(1, int(part))
            else:
                rest.append(part)
        return mode, page, " ".join(rest)

    async def _user_info(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号，请先使用 登录 或 绑定 <token>。")
            return
        res = await self.client.personal_info(token)
        if not self._ok(res):
            yield event.plain_result(f"查询失败: {self._message_of(res)}")
            return
        raw = self._payload(res, {}) or {}
        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        user_data = data.get("userData") or data.get("user_data") or {}
        career = data.get("careerData") or data.get("career_data") or {}
        role = raw.get("roleInfo") or data.get("roleInfo") or raw.get("role_info") or {}
        name = self.data_mgr.decode_text(user_data.get("charac_name") or role.get("charac_name") or role.get("nickname") or self._sender_name(event))
        avatar = self.data_mgr.decode_text(user_data.get("picurl") or role.get("picurl") or "")
        if avatar and avatar.isdigit():
            avatar = f"https://wegame.gtimg.com/g.2001918-r.ea725/helper/df/skin/{avatar}.webp"
        sol_rank = self.data_mgr.get_rank_by_score(career.get("rankpoint") or career.get("rankPoint") or 0, "sol")
        mp_rank = self.data_mgr.get_rank_by_score(career.get("tdmrankpoint") or career.get("tdmRankPoint") or 0, "mp")
        render_data = {
            "backgroundImage": self.data_mgr.get_random_background(),
            "userName": name,
            "userAvatar": avatar,
            "qqAvatarUrl": f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
            "registerTime": self._fmt_time(role.get("register_time") or role.get("registerTime")),
            "lastLoginTime": self._fmt_time(role.get("lastlogintime") or role.get("lastLoginTime")),
            "accountStatus": f"账号封禁: {'封禁' if str(role.get('isbanuser')) == '1' else '正常'} | 禁言: {'禁言' if str(role.get('isbanspeak')) == '1' else '正常'}",
            "solLevel": role.get("level") or "-",
            "solRankName": re.sub(r"\s*\(\d+\)", "", sol_rank),
            "solRankImage": self.data_mgr.get_rank_image_path(sol_rank, "sol"),
            "solTotalFight": career.get("soltotalfght") or career.get("solTotalFight") or "-",
            "solTotalEscape": career.get("solttotalescape") or career.get("solTotalEscape") or "-",
            "solEscapeRatio": career.get("solescaperatio") or career.get("solEscapeRatio") or "-",
            "solTotalKill": career.get("soltotalkill") or career.get("solTotalKill") or "-",
            "solDuration": self.data_mgr.fmt_duration(career.get("solduration") or 0),
            "tdmLevel": role.get("tdmlevel") or role.get("tdmLevel") or "-",
            "tdmRankName": re.sub(r"\s*\(\d+\)", "", mp_rank),
            "tdmRankImage": self.data_mgr.get_rank_image_path(mp_rank, "mp"),
            "tdmTotalFight": career.get("tdmtotalfight") or career.get("tdmTotalFight") or "-",
            "tdmTotalWin": career.get("totalwin") or career.get("totalWin") or "-",
            "tdmWinRatio": career.get("tdmsuccessratio") or career.get("tdmSuccessRatio") or "-",
            "tdmTotalKill": career.get("tdmtotalkill") or career.get("tdmTotalKill") or "-",
            "tdmDuration": self.data_mgr.fmt_duration(career.get("tdmduration") or 0, "minutes"),
            "hafCoin": self.data_mgr.fmt_num(role.get("hafcoinnum") or role.get("hafCoinNum") or 0),
            "totalAssets": self.data_mgr.fmt_price(float(role.get("propcapital") or 0) + float(role.get("hafcoinnum") or 0)),
        }
        text = f"【三角洲信息】\n昵称: {name}\nUID: {role.get('uid', '-')}\n烽火: {sol_rank}\n全面: {mp_rank}"
        async for r in self._render_or_text(event, "Template/userInfo/userInfo.html", render_data, text, {"viewport_width": 1365, "viewport_height": 700}):
            yield r

    async def _uid(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        res = await self.client.personal_info(token)
        if not self._ok(res):
            yield event.plain_result(f"查询 UID 失败: {self._message_of(res)}")
            return
        raw = self._payload(res, {}) or {}
        data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        role = raw.get("roleInfo") or data.get("roleInfo") or raw.get("role_info") or {}
        yield event.plain_result(f"昵称: {self.data_mgr.decode_text(role.get('charac_name') or '-')}\nUID: {role.get('uid') or '未获取到'}")

    async def _personal_data(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode, _, rest = self._parse_mode_page(arg)
        season = "7"
        for part in arg.split():
            if part.isdigit() or part.lower() == "all":
                season = part
        res = await self.client.personal_data(token, mode or "", season)
        if not self._ok(res):
            yield event.plain_result(f"查询数据失败: {self._message_of(res)}")
            return
        raw = self._payload(res, {}) or {}
        details = self._extract_mode_details(raw, mode)
        if not details:
            yield event.plain_result("暂未查询到该账号的游戏数据。")
            return
        identity = await self._render_identity(event, token)
        for mode_name, detail in details:
            render_data = self._build_personal_data(event, mode_name, detail, season, identity)
            text = self._summary_dict(f"{'烽火' if mode_name == 'sol' else '全面'}个人数据", detail)
            async for r in self._render_or_text(event, "Template/personalData/personalData.html", render_data, text, {"viewport_width": 1200, "viewport_height": 1800}):
                yield r

    def _extract_mode_details(self, raw: Any, mode: Optional[str]) -> List[Tuple[str, Dict[str, Any]]]:
        if not isinstance(raw, dict):
            return []
        candidates: List[Tuple[str, Any]] = []
        if mode == "sol":
            candidates.append(("sol", self._ams_inner(raw).get("solDetail")))
        elif mode == "mp":
            candidates.append(("mp", self._ams_inner(raw).get("mpDetail")))
        else:
            candidates.extend(
                [
                    ("sol", self._ams_inner(raw.get("sol") or {}).get("solDetail") or raw.get("solDetail")),
                    ("mp", self._ams_inner(raw.get("mp") or {}).get("mpDetail") or raw.get("mpDetail")),
                ]
            )
        return [(m, d) for m, d in candidates if isinstance(d, dict) and d]

    def _build_personal_data(
        self,
        event: AstrMessageEvent,
        mode: str,
        detail: Dict[str, Any],
        season: str,
        identity: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        identity = identity or {}
        base = {
            "nickname": identity.get("userName") or self._sender_name(event),
            "userName": identity.get("userName") or self._sender_name(event),
            "userAvatar": identity.get("userAvatar") or "",
            "qqAvatarUrl": identity.get("qqAvatarUrl") or f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
            "currentDate": dt.datetime.now().strftime("%Y-%m-%d"),
            "season": "全部" if season == "all" else season,
        }
        if mode == "sol":
            rank = self.data_mgr.get_rank_by_score(detail.get("levelScore") or 0, "sol")
            maps = []
            for item in detail.get("mapList") or []:
                name = self.data_mgr.get_map_name(item.get("mapID") or item.get("mapId"))
                maps.append({**item, "mapName": name, "mapImage": self.data_mgr.get_map_image_path(name, "sol")})
            base["solDetail"] = {
                **detail,
                "totalGameTime": self.data_mgr.fmt_duration(detail.get("totalGameTime") or 0),
                "totalGainedPriceFormatted": self.data_mgr.fmt_price(detail.get("totalGainedPrice")),
                "redTotalMoneyFormatted": self.data_mgr.fmt_price(detail.get("redTotalMoney")),
                "profitLossRatioFormatted": self.data_mgr.fmt_price(detail.get("profitLossRatio")),
                "lowKD": self._ratio(detail.get("lowKillDeathRatio"), 100),
                "medKD": self._ratio(detail.get("medKillDeathRatio"), 100),
                "highKD": self._ratio(detail.get("highKillDeathRatio"), 100),
                "mapList": [{"baseMapName": "地图统计", "maps": maps[:10]}],
                "redCollectionList": [
                    {
                        **x,
                        "objectName": x.get("objectName") or f"物品({x.get('objectID')})",
                        "imageUrl": f"https://playerhub.df.qq.com/playerhub/60004/object/{x.get('objectID')}.png",
                        "priceFormatted": self.data_mgr.fmt_price(x.get("price")),
                    }
                    for x in (detail.get("redCollectionDetail") or [])[:10]
                ],
                "gunPlayList": [
                    {
                        **x,
                        "weaponName": x.get("objectName") or f"武器({x.get('objectID')})",
                        "imageUrl": f"https://playerhub.df.qq.com/playerhub/60004/object/{x.get('objectID')}.png",
                        "totalPriceFormatted": self.data_mgr.fmt_price(x.get("totalPrice")),
                    }
                    for x in (detail.get("gunPlayList") or [])[:10]
                ],
            }
            base["solRank"] = rank
            base["solRankImage"] = self.data_mgr.get_rank_image_path(rank, "sol")
            base["mpDetail"] = None
        else:
            rank = self.data_mgr.get_rank_by_score(detail.get("levelScore") or 0, "mp")
            maps = []
            for item in detail.get("mapList") or []:
                name = self.data_mgr.get_map_name(item.get("mapID") or item.get("mapId"))
                maps.append({**item, "mapName": name, "mapImage": self.data_mgr.get_map_image_path(name, "mp")})
            base["mpDetail"] = {
                **detail,
                "totalGameTime": self.data_mgr.fmt_duration(detail.get("totalGameTime") or 0, "minutes"),
                "winRatioFormatted": f"{detail.get('winRatio')}%" if detail.get("winRatio") not in (None, "") else "-",
                "totalScoreFormatted": self.data_mgr.fmt_num(detail.get("totalScore") or 0),
                "avgKillPerMinuteFormatted": self._ratio(detail.get("avgKillPerMinute"), 100),
                "avgScorePerMinuteFormatted": self._ratio(detail.get("avgScorePerMinute"), 100),
                "mapList": maps[:10],
            }
            base["mpRank"] = rank
            base["mpRankImage"] = self.data_mgr.get_rank_image_path(rank, "mp")
            base["solDetail"] = None
        return base

    async def _record(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode, page, _ = self._parse_mode_page(arg)
        modes = [mode] if mode else ["sol", "mp"]
        for item_mode in modes:
            type_id = "4" if item_mode == "sol" else "5"
            res = await self.client.record(token, type_id, str(page))
            if not self._ok(res):
                yield event.plain_result(f"{'烽火' if item_mode == 'sol' else '全面'}战绩查询失败: {self._message_of(res)}")
                continue
            records = self._first_list(self._payload(res, []), ("records", "list", "items", "data"))
            if not records:
                yield event.plain_result(f"{'烽火' if item_mode == 'sol' else '全面'}第 {page} 页暂无战绩。")
                continue
            render_records = [self._record_item(x, item_mode, (page - 1) * 5 + i + 1) for i, x in enumerate(records[:5])]
            data = {"modeName": "烽火地带" if item_mode == "sol" else "全面战场", "page": page, "records": render_records}
            text = "\n".join([f"【{data['modeName']}战绩 第{page}页】"] + [f"{x['recordNum']}. {x['map']} {x['status']} {x.get('value') or x.get('score') or ''}" for x in render_records])
            async for r in self._render_or_text(event, "Template/record/record.html", data, text, {"viewport_width": 1200, "viewport_height": 1600}):
                yield r

    def _record_item(self, r: Dict[str, Any], mode: str, num: int) -> Dict[str, Any]:
        map_id = r.get("MapId") or r.get("MapID") or r.get("mapID") or r.get("mapId")
        map_name = self.data_mgr.get_map_name(map_id)
        op_name = self.data_mgr.get_operator_name(r.get("ArmedForceId") or r.get("DeployArmedForceType") or r.get("armedForceId"))
        item = {
            "recordNum": num,
            "time": r.get("dtEventTime") or r.get("eventTime") or "-",
            "map": map_name,
            "operator": op_name,
            "mapBg": (self.renderer.res_path.as_uri() + "/" + self.data_mgr.get_map_image_path(map_name, mode)) if self.data_mgr.get_map_image_path(map_name, mode) else "",
            "operatorImg": self.data_mgr.get_operator_image_path(op_name),
            "duration": self.data_mgr.fmt_duration(r.get("DurationS") or r.get("gametime") or 0),
        }
        if mode == "sol":
            reason = str(r.get("EscapeFailReason") or "")
            item.update(
                {
                    "status": ESCAPE_REASONS.get(reason, "撤离失败"),
                    "statusClass": "success" if reason == "1" else "exit" if reason == "3" else "fail",
                    "value": self.data_mgr.fmt_num(r.get("FinalPrice") or 0),
                    "income": self.data_mgr.fmt_num(r.get("flowCalGainedPrice") or 0),
                    "incomeClass": "income-positive" if self._number(r.get("flowCalGainedPrice")) >= 0 else "income-negative",
                    "killsHtml": f"<span class=\"kill-item kill-player\">玩家 {r.get('KillCount') or 0}</span><span class=\"kill-separator\">/</span><span class=\"kill-item kill-ai-player\">AI玩家 {r.get('KillPlayerAICount') or 0}</span><span class=\"kill-separator\">/</span><span class=\"kill-item kill-ai\">AI {r.get('KillAICount') or 0}</span>",
                    "teammates": [self._record_teammate(x) for x in (r.get("teammateArr") or []) if isinstance(x, dict)],
                }
            )
        else:
            result = str(r.get("MatchResult") or "")
            item.update(
                {
                    "status": MP_RESULTS.get(result, "未知结果"),
                    "statusClass": "success" if result == "1" else "exit" if result == "3" else "fail",
                    "kda": f"{r.get('KillNum') or 0}/{r.get('Death') or 0}/{r.get('Assist') or 0}",
                    "score": self.data_mgr.fmt_num(r.get("TotalScore") or r.get("score") or 0),
                    "rescue": r.get("RescueTeammateCount") or 0,
                }
            )
        return item

    def _record_teammate(self, teammate: Dict[str, Any]) -> Dict[str, Any]:
        reason = str(teammate.get("EscapeFailReason") or "")
        operator = self.data_mgr.get_operator_name(teammate.get("ArmedForceId"))
        kills = sum(
            int(self._number(teammate.get(key)))
            for key in ("KillCount", "KillPlayerAICount", "KillAICount")
        )
        return {
            "operator": operator,
            "operatorImg": self.data_mgr.get_operator_image_path(operator),
            "status": ESCAPE_REASONS.get(reason, "撤离失败"),
            "statusClass": "success" if reason == "1" else "exit" if reason == "3" else "fail",
            "value": self.data_mgr.fmt_num(teammate.get("FinalPrice") or 0),
            "duration": self.data_mgr.fmt_duration(teammate.get("DurationS") or 0),
            "kills": kills,
            "rescue": teammate.get("Rescue") or 0,
        }

    @staticmethod
    def _room_player_data(item: Dict[str, Any]) -> Dict[str, Any]:
        """合并全面战场响应中可能嵌套的玩家详情。"""
        result = dict(item)
        for _ in range(2):
            changed = False
            for key in ("userDetail", "playerDetail", "userInfo", "playerInfo"):
                detail = result.get(key)
                if isinstance(detail, dict):
                    result.update(detail)
                    changed = True
            if not changed:
                break
        return result

    def _room_players(self, raw: Any) -> List[Dict[str, Any]]:
        if isinstance(raw, list):
            candidates = raw
        else:
            candidates = []
            for key in (
                "players",
                "playerList",
                "userList",
                "memberList",
                "members",
                "roomUsers",
                "needUserDetail",
                "list",
                "data",
            ):
                candidates = self._find_nested_list(raw, key)
                if candidates:
                    break
        return [self._room_player_data(item) for item in candidates if isinstance(item, dict)]

    @staticmethod
    def _room_value(item: Dict[str, Any], *keys: str, default: Any = "") -> Any:
        for key in keys:
            value = item.get(key)
            if value is not None and value != "":
                return value
        return default

    async def _battle_room_info(
        self,
        event: AstrMessageEvent,
        mode_token: str,
        room_id: str,
    ) -> AsyncGenerator[Any, None]:
        mode_text = str(mode_token or "").strip().lower()
        if mode_text in SOL_ALIASES:
            mode, type_id, mode_name = "sol", "4", "烽火地带"
        elif mode_text in MP_ALIASES:
            mode, type_id, mode_name = "mp", "5", "全面战场"
        else:
            yield event.plain_result("模式仅支持烽火（sol/4）或全面（mp/5）。")
            return

        room_id = str(room_id or "").strip()
        if not room_id or len(room_id) > 128:
            yield event.plain_result("对局房间 ID 无效。用法：房间信息 <烽火/全面> <对局房间ID>。")
            return
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return

        response = await self.client.room_info(token, room_id, type_id)
        if not self._ok(response):
            yield event.plain_result(f"{mode_name}房间详情查询失败：{self._message_of(response)}")
            return
        players = self._room_players(self._payload(response, []))
        if not players:
            yield event.plain_result(f"未查询到{mode_name}对局房间 {room_id} 的成员详情。")
            return

        first = players[0]
        map_id = self._room_value(first, "MapId", "MapID", "mapId", "mapID")
        event_time = self._room_value(first, "dtEventTime", "eventTime", "matchTime", default="未知")
        map_name = self.data_mgr.get_map_name(map_id)
        lines = [
            "【战绩对局房间详情】",
            f"模式：{mode_name}",
            f"房间 ID：{room_id}",
            f"地图：{map_name}",
            f"时间：{event_time}",
            f"玩家：{len(players)} 人",
        ]
        for index, player in enumerate(players[:20], 1):
            nickname = self.data_mgr.decode_text(
                self._room_value(
                    player,
                    "nickName",
                    "NickName",
                    "nickname",
                    "userName",
                    "UserName",
                    "roleName",
                    "charac_name",
                    default="未知玩家",
                )
            )
            team_id = self._room_value(player, "TeamId", "TeamID", "teamId", "teamID", "team", default="-")
            operator_id = self._room_value(
                player,
                "ArmedForceId",
                "armedForceId",
                "DeployArmedForceType",
                "deployArmedForceType",
                "operatorId",
            )
            operator = self.data_mgr.get_operator_name(operator_id)
            lines.append(f"{index}. {nickname}｜队伍 {team_id}｜{operator}")
            if mode == "sol":
                reason = str(self._room_value(player, "EscapeFailReason", "escapeFailReason"))
                status = ESCAPE_REASONS.get(reason, "撤离结果未知")
                player_kills = self._room_value(player, "KillCount", "killCount", default=0)
                ai_player_kills = self._room_value(player, "KillPlayerAICount", "killPlayerAICount", default=0)
                ai_kills = self._room_value(player, "KillAICount", "killAICount", default=0)
                value = self._room_value(
                    player,
                    "FinalPrice",
                    "finalPrice",
                    "KeyChainCarryOutPrice",
                    "keyChainCarryOutPrice",
                    default=0,
                )
                rescue = self._room_value(player, "Rescue", "rescue", default=0)
                revive = self._room_value(player, "Revive", "revive", default=0)
                duration = self.data_mgr.fmt_duration(
                    self._room_value(player, "DurationS", "durationS", "gameTime", "gametime", default=0)
                )
                lines.append(
                    f"   {status}｜击杀 玩家 {player_kills} / AI玩家 {ai_player_kills} / AI {ai_kills}｜"
                    f"带出 {self.data_mgr.fmt_num(value)}｜救援 {rescue} / 复活 {revive}｜{duration}"
                )
            else:
                kills = self._room_value(player, "KillNum", "killNum", "KillCount", "killCount", default=0)
                deaths = self._room_value(player, "Death", "death", "DeathNum", "deathNum", default=0)
                assists = self._room_value(player, "Assist", "assist", "AssistNum", "assistNum", default=0)
                score = self._room_value(player, "TotalScore", "totalScore", "Score", "score", default=0)
                rescue = self._room_value(
                    player,
                    "RescueTeammateCount",
                    "rescueTeammateCount",
                    "Rescue",
                    "rescue",
                    default=0,
                )
                lines.append(
                    f"   K/D/A {kills}/{deaths}/{assists}｜得分 {self.data_mgr.fmt_num(score)}｜救援 {rescue}"
                )
        if len(players) > 20:
            lines.append(f"仅显示前 20 名玩家，另有 {len(players) - 20} 人未展开。")
        yield event.plain_result("\n".join(lines))

    async def _daily(self, event: AstrMessageEvent, arg: str, yesterday: bool) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode, _, _ = self._parse_mode_page(arg)
        day = dt.datetime.now() - dt.timedelta(days=1 if yesterday else 0)
        request_mode = "sol" if yesterday else (mode or "")
        res = await self.client.daily_record(token, request_mode)
        if not self._ok(res):
            yield event.plain_result(f"日报查询失败: {self._message_of(res)}")
            return
        raw = self._payload(res, {}) or {}
        sol, mp = self._daily_details(raw, request_mode or None)
        if yesterday:
            gain_date = str((sol or {}).get("recentGainDate") or "")
            if not sol or re.sub(r"\D", "", gain_date)[:8] != day.strftime("%Y%m%d"):
                yield event.plain_result("暂无昨日收益数据，快去摸金吧！")
                return
        elif not mode and not sol and not mp:
            yield event.plain_result("暂无日报数据，不打两把吗？")
            return
        identity = await self._render_identity(event, token)
        data = self._build_daily(event, sol, mp, mode, day.strftime("%Y-%m-%d"), yesterday, identity)
        text = self._summary_dict("昨日收益" if yesterday else "三角洲日报", raw)
        async for r in self._render_or_text(event, "Template/dailyReport/dailyReport.html", data, text, {"viewport_width": 1000, "viewport_height": 900}):
            yield r

    def _daily_details(self, raw: Dict[str, Any], mode: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if mode:
            inner = self._ams_inner(raw)
            return (
                inner.get("solDetail") if mode == "sol" and isinstance(inner.get("solDetail"), dict) else None,
                inner.get("mpDetail") if mode == "mp" and isinstance(inner.get("mpDetail"), dict) else None,
            )
        sol = self._ams_inner(raw.get("sol") or {}).get("solDetail")
        mp = self._ams_inner(raw.get("mp") or {}).get("mpDetail")
        return (
            sol if isinstance(sol, dict) and sol else None,
            mp if isinstance(mp, dict) and mp else None,
        )

    def _build_daily(
        self,
        event: AstrMessageEvent,
        sol: Optional[Dict[str, Any]],
        mp: Optional[Dict[str, Any]],
        mode: Optional[str],
        date_str: str,
        yesterday: bool,
        identity: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        identity = identity or {}
        data = {
            "type": "profit" if yesterday else "daily",
            "mode": mode or "",
            "userName": identity.get("userName") or self._sender_name(event),
            "userAvatar": identity.get("userAvatar") or "",
            "qqAvatarUrl": identity.get("qqAvatarUrl") or f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
            "currentDate": date_str,
        }
        if yesterday and isinstance(sol, dict):
            items = ((sol.get("userCollectionTop") or {}).get("list") or [])[:3]
            data["profitData"] = {
                "gainDate": sol.get("recentGainDate") or "昨日",
                "recentGain": self.data_mgr.fmt_num(sol.get("recentGain") or 0),
                "topItems": [self._item_image(x) for x in items],
            }
            return data
        if mode in (None, "", "sol"):
            data["solDetail"] = self._daily_sol(sol)
        if mode in (None, "", "mp"):
            data["mpDetail"] = self._daily_mp(mp)
        return data

    def _daily_sol(self, sol: Any) -> Dict[str, Any]:
        if not isinstance(sol, dict) or not sol.get("recentGainDate"):
            return {"isEmpty": True}
        items = ((sol.get("userCollectionTop") or {}).get("list") or [])[:5]
        return {
            "recentGainDate": sol.get("recentGainDate") or "-",
            "recentGain": self.data_mgr.fmt_num(sol.get("recentGain") or 0),
            "topItems": [self._item_image(x) for x in items],
        }

    def _daily_mp(self, mp: Any) -> Dict[str, Any]:
        if not isinstance(mp, dict) or not mp.get("recentDate"):
            return {"isEmpty": True}
        op = self.data_mgr.get_operator_name(mp.get("mostUseForceType"))
        best = mp.get("bestMatch") or {}
        map_name = self.data_mgr.get_map_name(best.get("mapID"))
        return {
            "recentDate": mp.get("recentDate") or "-",
            "totalFightNum": mp.get("totalFightNum") or 0,
            "totalWinNum": mp.get("totalWinNum") or 0,
            "totalKillNum": mp.get("totalKillNum") or 0,
            "totalScore": self.data_mgr.fmt_num(mp.get("totalScore") or 0),
            "mostUsedOperator": op,
            "operatorImage": self.data_mgr.get_operator_image_path(op),
            "bestMatch": {
                "mapID": best.get("mapID"),
                "mapName": map_name,
                "mapImage": self.data_mgr.get_map_image_path(map_name, "mp"),
                "dtEventTime": best.get("dtEventTime") or "-",
                "isWinner": best.get("isWinner") or False,
                "killNum": best.get("killNum") or 0,
                "death": best.get("death") or 0,
                "assist": best.get("assist") or 0,
                "score": self.data_mgr.fmt_num(best.get("score") or 0),
            },
        }

    async def _weekly(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode, _, _ = self._parse_mode_page(arg)
        date = next((x for x in arg.split() if re.fullmatch(r"\d{8}", x)), "")
        show_extra = any(x.lower() in {"详细", "detail", "extra"} for x in arg.split())
        res = await self.client.weekly_record(token, mode or "", date, show_extra)
        if not self._ok(res):
            yield event.plain_result(f"周报查询失败: {self._message_of(res)}")
            return
        raw = self._payload(res, {}) or {}
        sol, mp, report_dm = self._weekly_details(raw, mode)
        has_sol = bool(sol and self._number(sol.get("total_sol_num")) > 0)
        has_mp = bool(mp and self._number(mp.get("total_num")) > 0)
        if mode == "sol" and not has_sol:
            yield event.plain_result("暂无烽火地带周报数据，不打两把吗？")
            return
        if mode == "mp" and not has_mp:
            yield event.plain_result("暂无全面战场周报数据，不打两把吗？")
            return
        if not mode and not has_sol and not has_mp:
            yield event.plain_result("暂无周报数据，不打两把吗？")
            return
        identity = await self._render_identity(event, token)
        display_date = date or self._last_sunday()
        data = self._build_weekly(event, sol, mp, report_dm, mode, display_date, identity)
        text = self._summary_dict("三角洲周报", raw)
        async for r in self._render_or_text(event, "Template/weeklyReport/weeklyReport.html", data, text, {"viewport_width": 1100, "viewport_height": 1800}):
            yield r

    def _weekly_details(
        self,
        raw: Dict[str, Any],
        mode: Optional[str],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, Any]]:
        if mode:
            inner = self._ams_inner(raw)
            report_dm = inner.get("reportDm") if isinstance(inner.get("reportDm"), dict) else {}
            return (inner if mode == "sol" else None, inner if mode == "mp" else None, report_dm)
        sol = self._ams_inner(raw.get("sol") or {})
        mp = self._ams_inner(raw.get("mp") or {})
        report_dm = raw.get("reportDm") if isinstance(raw.get("reportDm"), dict) else {}
        return (sol or None, mp or None, report_dm)

    def _build_weekly(
        self,
        event: AstrMessageEvent,
        sol: Optional[Dict[str, Any]],
        mp: Optional[Dict[str, Any]],
        report_dm: Dict[str, Any],
        mode: Optional[str],
        date: str,
        identity: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        identity = identity or {}
        data = {
            "userName": identity.get("userName") or self._sender_name(event),
            "userAvatar": identity.get("userAvatar") or "",
            "qqAvatarUrl": identity.get("qqAvatarUrl") or f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
            "date": date,
            "dateDisplay": f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date,
        }
        if mode in (None, "", "sol"):
            data["solData"] = self._build_weekly_sol(sol)
        if mode in (None, "", "mp"):
            data["mpData"] = self._build_weekly_mp(mp)
        if isinstance(report_dm, dict):
            for key in ("report1", "report2", "report3", "report4", "wbn", "fk", "bk"):
                value = report_dm.get(key)
                if isinstance(value, dict):
                    data[key] = value
            data["topFriends"] = self._weekly_top_friends(report_dm.get("wbn"))
        return data

    def _build_weekly_sol(self, sol: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not sol or self._number(sol.get("total_sol_num")) <= 0:
            return {"isEmpty": True}
        rank = self.data_mgr.get_rank_by_score(sol.get("Rank_Score") or 0, "sol")
        maps = self._weekly_usage_items(sol.get("total_mapid_num"), "sol", "map")
        operators = self._weekly_usage_items(sol.get("total_ArmedForceId_num"), "sol", "operator")
        gained = self._number(sol.get("Gained_Price"))
        consumed = self._number(sol.get("consume_Price"))
        profit_ratio = "∞" if gained > 0 and consumed == 0 else f"{gained / consumed:.2f}" if consumed > 0 else "0"
        teammates = []
        for item in sol.get("friends") or sol.get("teammates") or []:
            if not isinstance(item, dict) or self._number(item.get("Friend_total_sol_num")) <= 0:
                continue
            openid = str(item.get("friend_openid") or "")
            teammates.append(
                {
                    "name": f"...{openid[-6:]}" if openid else "匿名队友",
                    "avatar": "",
                    "total_sol_num": item.get("Friend_total_sol_num") or 0,
                    "escape1": item.get("Friend_is_Escape1_num") or 0,
                }
            )
        high_price_items = []
        for item in sorted(
            self._parse_compound_list(sol.get("CarryOut_highprice_list")),
            key=lambda x: self._number(x.get("iPrice")),
            reverse=True,
        )[:5]:
            high_price_items.append(
                {
                    "name": item.get("auctontype") or item.get("objectName") or "物品",
                    "price": self.data_mgr.fmt_num(item.get("iPrice") or 0),
                }
            )
        most_map = maps[0]["name"] if maps else "无"
        most_operator = operators[0]["name"] if operators else "无"
        return {
            **sol,
            "rankName": rank,
            "rankImagePath": self.data_mgr.get_rank_image_path(rank, "sol"),
            "rise_Price": self.data_mgr.fmt_num(sol.get("rise_Price") or 0),
            "Gained_Price": self.data_mgr.fmt_num(sol.get("Gained_Price") or 0),
            "consume_Price": self.data_mgr.fmt_num(sol.get("consume_Price") or 0),
            "profitRatio": profit_ratio,
            "assetTrend": self._weekly_asset_trend(sol.get("Total_Price")),
            "mileage": f"{self._number(sol.get('Total_Mileage')) / 100000:.2f}",
            "gameTime": self.data_mgr.fmt_duration(sol.get("total_Online_Time") or 0),
            "mostUsedMap": most_map,
            "mostUsedMapImagePath": self.data_mgr.get_map_image_path(most_map, "sol") if maps else "",
            "mostUsedOperator": most_operator,
            "mostUsedOperatorImagePath": self.data_mgr.get_operator_image_path(most_operator) if operators else "",
            "maps": maps,
            "operators": operators,
            "highPriceItems": high_price_items,
            "teammates": teammates,
        }

    def _build_weekly_mp(self, mp: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not mp or self._number(mp.get("total_num")) <= 0:
            return {"isEmpty": True}
        rank = self.data_mgr.get_rank_by_score(mp.get("Rank_Match_Score") or 0, "mp")
        maps = self._weekly_usage_items(mp.get("max_inum_mapid"), "mp", "map")
        operator_id = mp.get("max_inum_DeployArmedForceType")
        operator_name = self.data_mgr.get_operator_name(operator_id) if operator_id not in (None, "") else "无"
        teammates = []
        for item in mp.get("friends") or mp.get("teammates") or []:
            if not isinstance(item, dict):
                continue
            total = self._number(item.get("Friend_mp_total_num"))
            wins = self._number(item.get("Friend_mp_win_num"))
            kills = self._number(item.get("Friend_mp_KillNum"))
            if total <= 0 and wins <= 0 and kills <= 0:
                continue
            deaths = self._number(item.get("Friend_mp_Death"))
            assists = self._number(item.get("Friend_mp_Assist"))
            openid = str(item.get("friend_openid") or "")
            teammates.append(
                {
                    "name": f"...{openid[-6:]}" if openid else "匿名队友",
                    "avatar": "",
                    "total_num": int(total),
                    "win_num": int(wins),
                    "winRate": self._percent(wins, total),
                    "kda": f"{int(kills)}/{int(deaths)}/{int(assists)}",
                    "sumScore": self.data_mgr.fmt_num(item.get("Friend_mp_SumScore") or 0),
                    "maxScore": self.data_mgr.fmt_num(item.get("Friend_mp_MaxScore") or 0),
                }
            )
        most_map = maps[0]["name"] if maps else "无"
        return {
            **mp,
            "rankName": rank,
            "rankImagePath": self.data_mgr.get_rank_image_path(rank, "mp"),
            "winRate": self._percent(mp.get("win_num"), mp.get("total_num")),
            "hitRate": self._percent(mp.get("Hit_Bullet_Num"), mp.get("Consume_Bullet_Num")),
            "total_score": self.data_mgr.fmt_num(mp.get("total_score") or 0),
            "mostUsedMap": most_map,
            "mostUsedMapImagePath": self.data_mgr.get_map_image_path(most_map, "mp") if maps else "",
            "mostUsedOperator": operator_name,
            "mostUsedOperatorImagePath": self.data_mgr.get_operator_image_path(operator_name) if operator_name != "无" else "",
            "maps": maps,
            "teammates": teammates,
        }

    def _weekly_usage_items(self, value: Any, mode: str, kind: str) -> List[Dict[str, Any]]:
        result = []
        for item in self._parse_compound_list(value):
            count = int(self._number(item.get("inum") or item.get("count")))
            if kind == "map":
                item_id = item.get("MapId") or item.get("mapID") or item.get("mapId")
                name = self.data_mgr.get_map_name(item_id)
                image_path = self.data_mgr.get_map_image_path(name, mode)
            else:
                item_id = item.get("ArmedForceId") or item.get("armedForceId")
                name = self.data_mgr.get_operator_name(item_id)
                image_path = self.data_mgr.get_operator_image_path(name)
            result.append({"id": item_id, "count": count, "name": name, "imagePath": image_path})
        return sorted(result, key=lambda x: x["count"], reverse=True)

    def _weekly_asset_trend(self, value: Any) -> Optional[Dict[str, Any]]:
        day_names = {
            "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三", "Thursday": "周四",
            "Friday": "周五", "Saturday": "周六", "Sunday": "周日",
        }
        prices: Dict[str, float] = {}
        for part in str(value or "").split(","):
            fields = part.split("-")
            if len(fields) >= 2 and fields[0] in day_names:
                prices[fields[0]] = self._number(fields[-1], float("nan"))
        ordered = [(day, prices[day]) for day in day_names if day in prices and prices[day] == prices[day]]
        if (
            "Monday" not in prices
            or "Sunday" not in prices
            or prices["Monday"] != prices["Monday"]
            or prices["Sunday"] != prices["Sunday"]
            or len(ordered) < 2
        ):
            return None
        width, height = 2000, 200
        minimum = min(price for _, price in ordered)
        maximum = max(price for _, price in ordered)
        spread = maximum - minimum
        points = []
        for index, (day, price) in enumerate(ordered):
            x = 160 + index / max(1, len(ordered) - 1) * 1680
            y = 95 if spread == 0 else 20 + 150 - (price - minimum) / spread * 150
            points.append(
                {
                    "dayName": day_names[day],
                    "price": self.data_mgr.fmt_num(price),
                    "rawPrice": price,
                    "x": f"{x:.1f}",
                    "y": f"{y:.1f}",
                    "xPercent": f"{x / width * 100:.2f}",
                    "yPercent": f"{y / height * 100:.2f}",
                }
            )
        path = " ".join(("M" if index == 0 else "L") + f" {point['x']},{point['y']}" for index, point in enumerate(points))
        return {
            "startPrice": self.data_mgr.fmt_num(prices["Monday"]),
            "endPrice": self.data_mgr.fmt_num(prices["Sunday"]),
            "maxPrice": self.data_mgr.fmt_num(maximum),
            "minPrice": self.data_mgr.fmt_num(minimum),
            "chartWidth": width,
            "chartHeight": height,
            "pathData": path,
            "allDays": points,
        }

    def _weekly_top_friends(self, wbn: Any) -> List[Dict[str, Any]]:
        if not isinstance(wbn, dict):
            return []
        friends = wbn.get("friends") if isinstance(wbn.get("friends"), list) else []
        ranked = sorted(friends, key=lambda x: self._number(x.get("total_gained_price")) if isinstance(x, dict) else 0, reverse=True)
        result = []
        for index, friend in enumerate(ranked[:10], 1):
            if not isinstance(friend, dict):
                continue
            openid = str(friend.get("Friendopenid") or "")
            result.append(
                {
                    **friend,
                    "rank": index,
                    "name": f"...{openid[-6:]}" if openid else "匿名好友",
                    "avatar": "",
                    "intimacy": friend.get("FriendIntimacy") or 0,
                    "total_gained_price": self.data_mgr.fmt_num(friend.get("total_gained_price") or 0),
                    "total_GainedPrice": self.data_mgr.fmt_num(friend.get("total_GainedPrice") or 0),
                    "max_GainedPrice": self.data_mgr.fmt_num(friend.get("max_GainedPrice") or 0),
                    "items": [],
                }
            )
        return result

    async def _map_stats(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode: Optional[str] = None
        season = "all"
        season_explicit = False
        keyword_parts = []
        for part in arg.split():
            low = part.lower()
            if part in SOL_ALIASES or low in SOL_ALIASES:
                mode = "sol"
            elif part in MP_ALIASES or low in MP_ALIASES:
                mode = "mp"
            elif low in {"all", "全部"}:
                season = "all"
                season_explicit = True
            elif re.fullmatch(r"\d+(?:,\d+)*", part):
                season = part
                season_explicit = True
            else:
                keyword_parts.append(part)
        keyword = " ".join(keyword_parts).strip()
        if season_explicit and not mode and not keyword:
            yield event.plain_result("指定赛季时请同时指定游戏模式，例如：地图统计 烽火 7。")
            return

        identity = await self._render_identity(event, token)
        rendered = 0
        failures = []
        for item_mode in ([mode] if mode else ["sol", "mp"]):
            res = await self.client.map_stats(token, item_mode, season)
            if not self._ok(res):
                failures.append(f"{'烽火地带' if item_mode == 'sol' else '全面战场'}: {self._message_of(res)}")
                continue
            payload = self._payload(res, {}) or {}
            rows = self._first_list(payload, ("list", "items", "data"))
            if keyword:
                rows = [
                    item for item in rows
                    if isinstance(item, dict)
                    and keyword in str(item.get("mapName") or self.data_mgr.get_map_name(item.get("mapId")))
                ]
            rows = [item for item in rows if isinstance(item, dict) and isinstance(item.get("data"), dict)]
            if not rows:
                continue
            data = self._build_map_stats(item_mode, season, rows, identity)
            title = "烽火地带" if item_mode == "sol" else "全面战场"
            text_lines = [f"【{title}地图统计】"]
            for item in data["mapStatsList"]:
                detail = item.get(item_mode) or {}
                text_lines.append(
                    f"{item['mapName']}: "
                    + (f"{detail.get('totalGames')}局，撤离率 {detail.get('escapeRate')}" if item_mode == "sol" else f"{detail.get('totalGames')}局，胜率 {detail.get('winRate')}")
                )
            async for result in self._render_or_text(
                event,
                "Template/mapStats/mapStats.html",
                data,
                "\n".join(text_lines),
                {"viewport_width": 1100, "viewport_height": 1500},
            ):
                yield result
            rendered += 1
        if rendered:
            for failure in failures:
                yield event.plain_result(f"部分地图统计查询失败: {failure}")
            return
        if failures:
            yield event.plain_result("地图统计查询失败: " + "；".join(failures))
        elif keyword:
            yield event.plain_result(f"未找到包含“{keyword}”的地图数据。")
        else:
            yield event.plain_result("暂未查询到地图统计数据。")

    def _build_map_stats(
        self,
        mode: str,
        season: str,
        rows: List[Dict[str, Any]],
        identity: Dict[str, str],
    ) -> Dict[str, Any]:
        stats = [self._map_stats_item(item, mode) for item in rows]
        return {
            "backgroundImage": self.data_mgr.get_random_background(),
            "userName": identity.get("userName") or "",
            "userAvatar": identity.get("userAvatar") or "",
            "qqAvatarUrl": identity.get("qqAvatarUrl") or "",
            "currentDate": dt.datetime.now().strftime("%Y-%m-%d"),
            "type": mode,
            "typeName": "烽火地带" if mode == "sol" else "全面战场",
            "seasonid": "全部赛季" if season == "all" else f"第{season}赛季",
            "totalMaps": len(stats),
            "mapStatsList": stats,
        }

    def _map_stats_item(self, item: Dict[str, Any], mode: str) -> Dict[str, Any]:
        detail = item.get("data") if isinstance(item.get("data"), dict) else {}
        map_name = str(item.get("mapName") or self.data_mgr.get_map_name(item.get("mapId")))
        base = {
            "baseName": re.sub(r"[-（(].*$", "", map_name).strip(),
            "mapName": map_name,
            "mapId": item.get("mapId"),
            "mapImage": self.data_mgr.get_map_image_path(map_name, mode),
            "sol": None,
            "mp": None,
        }
        if mode == "sol":
            games = detail.get("zdj") or detail.get("cs") or 0
            base["sol"] = {
                "profit": self._format_profit(detail.get("a1")),
                "totalGames": self.data_mgr.fmt_num(games),
                "escaped": self.data_mgr.fmt_num(detail.get("isescapednum") or 0),
                "escapeRate": self._percent(detail.get("isescapednum"), games),
                "kill": self.data_mgr.fmt_num(detail.get("killnum") or 0),
                "failed": self.data_mgr.fmt_num(detail.get("nums") or 0),
            }
        else:
            games = detail.get("zdjnum") or 0
            kills = self._number(detail.get("killnum"))
            assists = self._number(detail.get("assist"))
            deaths = self._number(detail.get("death"))
            base["mp"] = {
                "win": self.data_mgr.fmt_num(detail.get("winnum") or 0),
                "totalGames": self.data_mgr.fmt_num(games),
                "winRate": self._percent(detail.get("winnum"), games),
                "score": self.data_mgr.fmt_num(detail.get("score") or 0),
                "gameTime": self.data_mgr.fmt_duration(detail.get("gametime") or 0),
                "kill": self.data_mgr.fmt_num(kills),
                "assist": self.data_mgr.fmt_num(assists),
                "death": self.data_mgr.fmt_num(deaths),
                "kda": f"{kills:.2f}" if deaths == 0 else f"{(kills + assists) / deaths:.2f}",
            }
        return base

    def _format_profit(self, value: Any) -> str:
        number = self._number(value)
        absolute = abs(number)
        if absolute >= 1_000_000_000:
            text = f"{absolute / 1_000_000_000:.2f}".rstrip("0").rstrip(".") + "B"
        elif absolute >= 1_000_000:
            text = f"{absolute / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
        elif absolute >= 1_000:
            text = f"{absolute / 1_000:.2f}".rstrip("0").rstrip(".") + "K"
        else:
            text = self.data_mgr.fmt_num(absolute)
        return ("+" if number >= 0 else "-") + text

    async def _money(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        res = await self.client.money(token)
        if not self._ok(res):
            yield event.plain_result(f"货币信息查询失败: {self._message_of(res)}")
            return
        rows = self._first_list(self._data(res, {}), ("list", "items", "data"))
        if not rows:
            yield event.plain_result("未查询到任何货币信息。")
            return
        lines = ["【三角洲行动 - 货币信息】"]
        for item in rows:
            name = item.get("name") or item.get("item") or "未知货币"
            amount = self.data_mgr.fmt_num(item.get("totalMoney") or item.get("amount") or 0)
            lines.append(f"{name}: {amount}")
        yield event.plain_result("\n".join(lines))

    async def _flows(self, event: AstrMessageEvent, flow_type: str, page: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        type_map = {"设备": "1", "道具": "2", "货币": "3"}
        targets = [(flow_type, type_map[flow_type])] if flow_type in type_map else list(type_map.items())
        results = await asyncio.gather(
            *(self._fetch_flows(token, type_id, page) for _name, type_id in targets),
            return_exceptions=True,
        )
        for (type_name, type_id), res in zip(targets, results):
            if isinstance(res, Exception):
                yield event.plain_result(f"{type_name}流水查询失败: {res}")
                continue
            if not self._ok(res):
                yield event.plain_result(f"{type_name}流水查询失败: {self._message_of(res)}")
                continue
            data = self._adapt_flows(res, int(type_id), type_name, page)
            record_count = sum(len(column) for key, value in data.items() if key.endswith("Columns") for column in value)
            if record_count == 0:
                yield event.plain_result(f"【{type_name}流水】第 {data['page']} 页暂无记录。")
                continue
            text = self._flows_text(data)
            trend_data = data.get("moneyTrendChart") if type_id == "3" else None
            if trend_data and self.config.get("enable_image_render", True):
                try:
                    trend_image = await self.renderer.render_html(
                        "Template/flows/moneyTrendChart.html",
                        {"moneyTrendChart": trend_data},
                        {"viewport_width": 1000, "viewport_height": 500},
                    )
                    if trend_image:
                        yield event.image_result(trend_image)
                except Exception as exc:
                    logger.warning(f"[三角洲流水] 金额趋势图渲染失败：{type(exc).__name__}")
            async for result in self._render_or_text(
                event,
                "Template/flows/flows.html",
                data,
                text,
                {"viewport_width": 2200, "viewport_height": 1200},
            ):
                yield result

    async def _fetch_flows(self, token: str, type_id: str, page: str) -> Dict[str, Any]:
        if page != "all":
            return await self.client.flows(token, type_id, page)
        merged: List[Any] = []
        for current_page in range(1, 51):
            res = await self.client.flows(token, type_id, str(current_page))
            if not self._ok(res):
                return res if not merged else {"code": 0, "data": {"list": merged}}
            rows = self._first_list(self._data(res, {}), ("list", "items", "data"))
            if not rows or self._flow_record_count(rows, int(type_id)) == 0:
                break
            merged.extend(rows)
        return {"code": 0, "data": {"list": merged}}

    @staticmethod
    def _flow_record_count(rows: List[Any], type_id: int) -> int:
        key = {1: "LoginArr", 2: "itemArr", 3: "iMoneyArr"}[type_id]
        return sum(len(row.get(key) or []) for row in rows if isinstance(row, dict))

    def _adapt_flows(self, res: Dict[str, Any], type_id: int, type_name: str, page: str) -> Dict[str, Any]:
        rows = self._first_list(self._data(res, {}), ("list", "items", "data"))
        source = next((row for row in rows if isinstance(row, dict)), {})
        result: Dict[str, Any] = {"typeName": type_name, "typeValue": type_id, "page": "全部" if page == "all" else page}
        if type_id == 1:
            records = [item for row in rows if isinstance(row, dict) for item in (row.get("LoginArr") or []) if isinstance(item, dict)]
            formatted = [
                {
                    "index": index,
                    "indtEventTime": item.get("indtEventTime") or "-",
                    "outdtEventTime": item.get("outdtEventTime") or "-",
                    "vClientIP": item.get("vClientIP") or "未知",
                    "SystemHardware": item.get("SystemHardware") or "未知",
                }
                for index, item in enumerate(records, 1)
            ]
            device_stats: Dict[str, int] = {}
            ip_stats: Dict[str, int] = {}
            for item in formatted:
                device_stats[item["SystemHardware"]] = device_stats.get(item["SystemHardware"], 0) + 1
                ip_stats[item["vClientIP"]] = ip_stats.get(item["vClientIP"], 0) + 1
            result.update(
                {
                    "playerInfo": {
                        "vRoleName": source.get("vRoleName") or "未知",
                        "Level": source.get("Level") or "未知",
                        "loginDay": source.get("loginDay") or "未知",
                    },
                    "totalCount": len(formatted),
                    "deviceStats": [{"name": key, "count": value} for key, value in sorted(device_stats.items(), key=lambda item: item[1], reverse=True)],
                    "ipStats": [{"ip": key, "count": value} for key, value in sorted(ip_stats.items(), key=lambda item: item[1], reverse=True)],
                    "loginColumns": self._flow_columns(formatted),
                }
            )
        elif type_id == 2:
            records = [item for row in rows if isinstance(row, dict) for item in (row.get("itemArr") or []) if isinstance(item, dict)]
            formatted = [
                {
                    "index": index,
                    "dtEventTime": item.get("dtEventTime") or "-",
                    "Name": item.get("Name") or "未知物品",
                    "AddOrReduce": str(item.get("AddOrReduce") or "0"),
                    "Reason": self._decode_reason(item.get("Reason")),
                    "changeType": "positive" if str(item.get("AddOrReduce") or "").startswith("+") else "negative",
                }
                for index, item in enumerate(records, 1)
            ]
            result["itemColumns"] = self._flow_columns(formatted)
        else:
            records = [item for row in rows if isinstance(row, dict) for item in (row.get("iMoneyArr") or []) if isinstance(item, dict)]
            formatted = [
                {
                    "index": index,
                    "dtEventTime": item.get("dtEventTime") or "-",
                    "AddOrReduce": str(item.get("AddOrReduce") or "0"),
                    "leftMoney": self.data_mgr.fmt_num(item.get("leftMoney") or 0),
                    "Reason": self._decode_reason(item.get("Reason")),
                    "changeType": "positive" if str(item.get("AddOrReduce") or "").startswith("+") else "negative",
                }
                for index, item in enumerate(records, 1)
            ]
            result["moneyColumns"] = self._flow_columns(formatted)
            trend_chart = self._money_trend_chart(records)
            if trend_chart:
                result["moneyTrendChart"] = trend_chart
        return result

    def _money_trend_chart(self, records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        date_map: Dict[str, List[Dict[str, Any]]] = {}
        for record in records:
            time_text = str(record.get("dtEventTime") or "").strip()
            if not time_text:
                continue
            date_text = time_text.replace("/", "-").split(" ", 1)[0].split("T", 1)[0]
            if date_text:
                date_map.setdefault(date_text, []).append(record)

        daily_data: List[Dict[str, Any]] = []
        for date_text in sorted(date_map):
            day_records = sorted(date_map[date_text], key=lambda item: str(item.get("dtEventTime") or ""))
            balances: List[float] = []
            total_change = 0.0
            for record in day_records:
                total_change += self._flow_number(record.get("AddOrReduce"))
                raw_balance = record.get("leftMoney")
                if raw_balance in (None, "", "未知"):
                    continue
                balance_text = str(raw_balance).replace(",", "").strip()
                balance = self._flow_number(balance_text)
                if balance >= 0:
                    balances.append(balance)
            if balances:
                daily_data.append(
                    {
                        "date": date_text,
                        "startBalance": balances[0],
                        "endBalance": balances[-1],
                        "totalChange": total_change,
                        "recordCount": len(day_records),
                    }
                )
        if not daily_data:
            return None

        end_balances = [item["endBalance"] for item in daily_data]
        maximum = max(end_balances)
        minimum = min(end_balances)
        balance_range = maximum - minimum or 1
        chart_width = 800
        chart_height = 120
        padding = {"top": 20, "right": 10, "bottom": 30, "left": 10}
        plot_width = chart_width - padding["left"] - padding["right"]
        plot_height = chart_height - padding["top"] - padding["bottom"]
        points = []
        for index, item in enumerate(daily_data):
            x = (
                padding["left"] + plot_width / 2
                if len(daily_data) == 1
                else padding["left"] + index / (len(daily_data) - 1) * plot_width
            )
            y = padding["top"] + plot_height - (item["endBalance"] - minimum) / balance_range * plot_height
            date_parts = item["date"].split("-")
            points.append(
                {
                    "date": "-".join(date_parts[-2:]) if len(date_parts) >= 3 else item["date"],
                    "fullDate": item["date"],
                    "balance": self.data_mgr.fmt_num(item["endBalance"]),
                    "totalChange": self.data_mgr.fmt_num(item["totalChange"]),
                    "startBalance": self.data_mgr.fmt_num(item["startBalance"]),
                    "recordCount": item["recordCount"],
                    "x": f"{x:.1f}",
                    "y": f"{y:.1f}",
                    "xPercent": f"{x / chart_width * 100:.2f}",
                }
            )
        if len(points) == 1:
            path_data = f"M {points[0]['x']},{points[0]['y']} L {float(points[0]['x']) + 10:.1f},{points[0]['y']}"
        else:
            path_data = " ".join(
                ("M" if index == 0 else "L") + f" {point['x']},{point['y']}"
                for index, point in enumerate(points)
            )

        first_day = daily_data[0]
        last_day = daily_data[-1]
        return {
            "startBalance": self.data_mgr.fmt_num(first_day["startBalance"]),
            "endBalance": self.data_mgr.fmt_num(last_day["endBalance"]),
            "maxBalance": self.data_mgr.fmt_num(maximum),
            "minBalance": self.data_mgr.fmt_num(minimum),
            "totalChange": self.data_mgr.fmt_num(sum(item["totalChange"] for item in daily_data)),
            "chartWidth": chart_width,
            "chartHeight": chart_height,
            "pathData": path_data,
            "points": points,
            "dateRange": f"{first_day['date']} ~ {last_day['date']}",
        }

    @staticmethod
    def _flow_number(value: Any) -> float:
        try:
            return float(str(value or 0).replace(",", "").strip())
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _flow_columns(records: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        columns = [[] for _ in range(min(5, max(1, len(records))))]
        for index, record in enumerate(records):
            columns[index % len(columns)].append(record)
        return columns if records else []

    @staticmethod
    def _decode_reason(value: Any) -> str:
        try:
            return unquote(str(value or "")) or "未知原因"
        except Exception:
            return str(value or "未知原因")

    @staticmethod
    def _flows_text(data: Dict[str, Any]) -> str:
        key = {1: "loginColumns", 2: "itemColumns", 3: "moneyColumns"}[data["typeValue"]]
        rows = [item for column in data.get(key, []) for item in column]
        lines = [f"【{data['typeName']}流水】第 {data['page']} 页，共 {len(rows)} 条"]
        for item in sorted(rows, key=lambda value: value.get("index", 0))[:20]:
            if data["typeValue"] == 1:
                lines.append(f"{item['index']}. {item['indtEventTime']} {item['SystemHardware']} {item['vClientIP']}")
            elif data["typeValue"] == 2:
                lines.append(f"{item['index']}. {item['dtEventTime']} {item['Name']} {item['AddOrReduce']} {item['Reason']}")
            else:
                lines.append(f"{item['index']}. {item['dtEventTime']} {item['AddOrReduce']} 余额 {item['leftMoney']} {item['Reason']}")
        return "\n".join(lines)

    async def _collection(self, event: AstrMessageEvent, kind: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        collection_res, map_res = await asyncio.gather(
            self.client.collection(token, 2),
            self.client.object_collection_map(),
            return_exceptions=True,
        )
        if isinstance(collection_res, Exception) or not self._ok(collection_res):
            message = str(collection_res) if isinstance(collection_res, Exception) else self._message_of(collection_res)
            yield event.plain_result(f"藏品查询失败: {message}")
            return
        if isinstance(map_res, Exception) or not self._ok(map_res):
            message = str(map_res) if isinstance(map_res, Exception) else self._message_of(map_res)
            yield event.plain_result(f"藏品基础信息查询失败: {message}")
            return
        raw = self._payload(collection_res, {}) or {}
        user_items = self._find_nested_list(raw, "userData")
        weapon_items = self._find_nested_list(raw, "weponData") or self._find_nested_list(raw, "weaponData")
        owned = [item for item in user_items + weapon_items if isinstance(item, dict)]
        if not owned:
            yield event.plain_result("您的藏品库为空。")
            return
        mapping_rows = self._first_list(self._data(map_res, {}), ("list", "items", "data"))
        mapping = {str(item.get("id") or item.get("objectID") or ""): item for item in mapping_rows if isinstance(item, dict)}
        render_data = self._adapt_collection(owned, mapping, kind)
        if not render_data["categories"]:
            suffix = f"类型“{kind}”" if kind else ""
            yield event.plain_result(f"未找到{suffix}的藏品。")
            return
        text = "\n".join(
            [f"【{render_data['typeName']}】共 {render_data['totalCount']} 件"]
            + [f"{category['name']}: {category['count']} 件" for category in render_data["categories"]]
        )
        async for r in self._render_or_text(event, "Template/collection/collection.html", render_data, text, {"viewport_width": 1200, "viewport_height": 1600}):
            yield r

    def _adapt_collection(self, owned: List[Dict[str, Any]], mapping: Dict[str, Dict[str, Any]], kind: str) -> Dict[str, Any]:
        quality = {"橙": ("传说", 5), "紫": ("史诗", 4), "蓝": ("稀有", 3), "绿": ("普通", 2)}
        background = {
            "干员皮肤": "operator-skin",
            "喷漆": "property-gx-li3.webp",
            "挂饰": "property-gx-li2.webp",
            "典藏枪皮": "property-jz-bg.webp",
            "枪皮": "property-jz-bg.webp",
            "载具": "property-qx-bg2.webp",
            "头像": "property-gx-li3.webp",
            "军牌": "property-jz-bg.webp",
        }
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        quality_counts: Dict[int, int] = {}
        for item in owned:
            item_id = str(item.get("ItemId") or item.get("itemId") or item.get("objectID") or item.get("id") or "")
            info = mapping.get(item_id)
            if not info:
                continue
            category = str(info.get("type") or "其他资产")
            if kind and kind not in category and category not in kind:
                continue
            _quality_name, level = quality.get(str(info.get("rare") or ""), ("其他", 1))
            quality_counts[level] = quality_counts.get(level, 0) + 1
            grouped.setdefault(category, []).append(
                {
                    "name": info.get("name") or info.get("objectName") or f"物品 {item_id}",
                    "id": item_id,
                    "imageUrl": info.get("pic") or f"https://playerhub.df.qq.com/playerhub/60004/object/{item_id}.png",
                    "qualityLevel": level,
                    "category": category,
                }
            )
        categories = [
            {
                "name": name,
                "items": sorted(items, key=lambda item: (-item["qualityLevel"], item["name"])),
                "count": len(items),
                "bgImage": background.get(name, "property-gx-li3.webp"),
            }
            for name, items in sorted(grouped.items())
        ]
        return {
            "typeName": kind or "所有藏品",
            "totalCount": sum(category["count"] for category in categories),
            "qualityStats": [{"level": level, "count": quality_counts[level]} for level in sorted(quality_counts, reverse=True)],
            "categories": categories,
        }

    async def _red_records(self, event: AstrMessageEvent, command: str, arg: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        if command in {"出红记录", "大红记录", "藏品记录"} and arg and not arg.isdigit():
            async for r in self._red_one(event, token, arg):
                yield r
            return
        if command in {"大红收藏", "大红藏品", "大红海报", "藏品海报"}:
            async for r in self._red_collection(event, token, arg if arg.isdigit() else "all"):
                yield r
            return
        async for r in self._red_list(event, token):
            yield r

    async def _red_list(self, event: AstrMessageEvent, token: str) -> AsyncGenerator[Any, None]:
        profile_res, red_res = await asyncio.gather(self.client.personal_info(token), self.client.red_list(token), return_exceptions=True)
        if isinstance(red_res, Exception):
            yield event.plain_result(f"出红记录查询失败: {red_res}")
            return
        if not self._ok(red_res):
            yield event.plain_result(f"出红记录查询失败: {self._message_of(red_res)}")
            return
        raw = self._data(red_res, {}) or {}
        records_wrap = raw.get("records") if isinstance(raw, dict) else raw
        records = self._first_list(records_wrap or raw, ("list", "records", "items", "data"))
        if not records:
            yield event.plain_result("您还没有任何藏品解锁记录。")
            return

        stats: Dict[str, Dict[str, Any]] = {}
        for record in records:
            item_id = str(record.get("itemId") or record.get("objectID") or record.get("objectId") or record.get("id") or "")
            if not item_id:
                continue
            count = self._num(record.get("num") or record.get("count") or 1)
            item = stats.setdefault(item_id, {"id": item_id, "count": 0, "records": []})
            item["count"] += int(count or 1)
            item["records"].append(record)
        if not stats:
            yield event.plain_result("出红记录返回数据缺少物品 ID。")
            return

        info_map = await self._object_info_map(list(stats.keys())[:30])
        rendered_records = []
        total_value = 0.0
        for item_id, item in stats.items():
            info = info_map.get(item_id, {})
            name = info.get("objectName") or info.get("name") or f"未知物品({item_id})"
            price = self._num(info.get("avgPrice") or info.get("price") or info.get("marketPrice") or info.get("latestPrice") or 0)
            value = price * item["count"]
            total_value += value
            rendered_records.append(
                {
                    "name": name,
                    "count": item["count"],
                    "value": self.data_mgr.fmt_price(value),
                    "imageUrl": f"https://playerhub.df.qq.com/playerhub/60004/object/{item_id}.png",
                    "_sort": value,
                }
            )
        rendered_records.sort(key=lambda x: x["_sort"], reverse=True)
        uncollected_count = await self._uncollected_red_count(set(stats.keys()))
        profile = self._profile_template(event, profile_res if not isinstance(profile_res, Exception) else {})
        render_data = {
            **profile,
            "statistics": {
                "redGodCount": str(len(stats)),
                "redTotalCount": str(sum(x["count"] for x in stats.values())),
                "redTotalValue": self.data_mgr.fmt_price(total_value),
                "unlockedCount": str(uncollected_count) if uncollected_count else "",
            },
            "records": rendered_records[:6],
            "totalRecords": len(rendered_records),
        }
        text = "\n".join(
            ["【出红记录统计】", f"收藏种类: {len(stats)}", f"总出红次数: {sum(x['count'] for x in stats.values())}", f"总价值: {self.data_mgr.fmt_price(total_value)}"]
            + [f"{idx}. {item['name']} x{item['count']} {item['value']}" for idx, item in enumerate(rendered_records[:6], 1)]
        )
        height = max(620, 580 + len(render_data["records"]) * 95)
        async for r in self._render_or_text(event, "Template/redRecordList/redRecordList.html", render_data, text, {"viewport_width": 650, "viewport_height": height}):
            yield r

    async def _red_one(self, event: AstrMessageEvent, token: str, keyword: str) -> AsyncGenerator[Any, None]:
        item = await self._object_info(keyword)
        if not item:
            yield event.plain_result(f"未找到名为“{keyword}”的物品。")
            return
        object_id = str(item.get("objectID") or item.get("objectId") or item.get("id") or "")
        if not object_id:
            yield event.plain_result("已找到物品，但返回数据缺少 objectID。")
            return
        profile_res, red_res = await asyncio.gather(self.client.personal_info(token), self.client.red_one(token, object_id), return_exceptions=True)
        if isinstance(red_res, Exception):
            yield event.plain_result(f"单藏品记录查询失败: {red_res}")
            return
        if not self._ok(red_res):
            yield event.plain_result(f"单藏品记录查询失败: {self._message_of(red_res)}")
            return
        raw = self._data(red_res, {}) or {}
        item_data = raw.get("itemData") if isinstance(raw, dict) else raw
        records = self._first_list(item_data or raw, ("list", "records", "items", "data"))
        if not records:
            yield event.plain_result(f"物品“{item.get('objectName') or item.get('name') or keyword}”暂无解锁记录。")
            return
        sorted_records = sorted(records, key=lambda x: str(x.get("time") or x.get("dtEventTime") or ""))
        first = sorted_records[0]
        first_map = self.data_mgr.get_map_name(first.get("mapid") or first.get("mapID") or first.get("mapId"))
        latest = list(reversed(sorted_records[-20:]))
        profile = self._profile_template(event, profile_res if not isinstance(profile_res, Exception) else {})
        render_data = {
            **profile,
            "itemName": item.get("objectName") or item.get("name") or keyword,
            "itemType": item.get("objectType") or (f"GRADE {item.get('grade')}" if item.get("grade") else ""),
            "itemImageUrl": f"https://playerhub.df.qq.com/playerhub/60004/object/{object_id}.png",
            "firstUnlockTime": first.get("time") or first.get("dtEventTime") or "-",
            "firstUnlockMap": first_map,
            "firstUnlockMapBg": self.data_mgr.get_map_image_path(first_map, "sol"),
            "records": [
                {
                    "time": x.get("time") or x.get("dtEventTime") or "-",
                    "map": self.data_mgr.get_map_name(x.get("mapid") or x.get("mapID") or x.get("mapId")),
                    "count": x.get("num") or x.get("count") or 1,
                }
                for x in latest
            ],
            "recordCount": (item_data or {}).get("total") if isinstance(item_data, dict) else len(records),
        }
        text = "\n".join(
            [f"【{render_data['itemName']} 出红记录】", f"首次解锁: {render_data['firstUnlockTime']} {render_data['firstUnlockMap']}"]
            + [f"{idx}. {x['time']} {x['map']} x{x['count']}" for idx, x in enumerate(render_data["records"][:10], 1)]
        )
        async for r in self._render_or_text(event, "Template/redRecord/redRecord.html", render_data, text, {"viewport_width": 650, "viewport_height": 5000}):
            yield r

    async def _red_collection(self, event: AstrMessageEvent, token: str, season_id: str) -> AsyncGenerator[Any, None]:
        profile_res, data_res, title_res = await asyncio.gather(
            self.client.personal_info(token),
            self.client.personal_data(token, "", season_id),
            self.client.title(token),
            return_exceptions=True,
        )
        if isinstance(data_res, Exception):
            yield event.plain_result(f"大红收藏查询失败: {data_res}")
            return
        if not self._ok(data_res):
            yield event.plain_result(f"大红收藏查询失败: {self._message_of(data_res)}")
            return
        raw = self._data(data_res, {}) or {}
        sol_detail = self._find_nested_dict(raw, "solDetail")
        if not sol_detail:
            yield event.plain_result("没有找到烽火地带游戏数据，请确认账号已绑定角色并有烽火地带对局数据。")
            return
        red_items = sol_detail.get("redCollectionDetail") or []
        if not red_items:
            yield event.plain_result("您还没有任何大红收藏品。")
            return
        object_ids = [str(x.get("objectID") or x.get("objectId") or x.get("itemId") or "") for x in red_items if isinstance(x, dict)]
        info_map = await self._object_info_map([x for x in object_ids if x][:30])
        sorted_items = sorted([x for x in red_items if isinstance(x, dict)], key=lambda x: self._num(x.get("price")), reverse=True)
        top_collections = []
        for idx, item in enumerate(sorted_items[:6], 1):
            object_id = str(item.get("objectID") or item.get("objectId") or item.get("itemId") or "")
            info = info_map.get(object_id, {})
            top_collections.append(
                {
                    "rank": idx,
                    "name": info.get("objectName") or info.get("name") or f"物品{object_id}",
                    "count": item.get("count") or item.get("num") or 1,
                    "value": self.data_mgr.fmt_price(item.get("price") or 0),
                    "imageUrl": f"https://playerhub.df.qq.com/playerhub/60004/object/{object_id}.png",
                }
            )
        uncollected = await self._uncollected_red_items(set(object_ids), 3)
        title_data = self._data(title_res, {}) if isinstance(title_res, dict) and self._ok(title_res) else {}
        profile = self._profile_template(event, profile_res if not isinstance(profile_res, Exception) else {})
        render_data = {
            **profile,
            "title": title_data.get("title") or "血色会计",
            "subtitle": title_data.get("subtitle") or "能把肾上腺素换算成子弹汇率的鬼才",
            "unlockDesc": title_data.get("unlockDesc") or "总价值突破 800 万且持有医疗/能源类大红收藏品",
            "seasonDisplay": "所有赛季" if season_id in {"", "all"} else f"S{season_id}赛季",
            "statistics": {
                "redGodCount": str(len(set(object_ids))),
                "redTotalCount": str(int(self._num(sol_detail.get("redTotalCount") or len(red_items)))),
                "redTotalValue": self.data_mgr.fmt_price(sol_detail.get("redTotalMoney") or sum(self._num(x.get("price")) for x in red_items if isinstance(x, dict))),
                "unlockedCount": str(len(uncollected)) if uncollected else "",
            },
            "topCollections": top_collections,
            "unlockedCollections": uncollected,
        }
        text = "\n".join(["【大红收藏馆】", f"称号: {render_data['title']}", f"总价值: {render_data['statistics']['redTotalValue']}"] + [f"{x['rank']}. {x['name']} x{x['count']} {x['value']}" for x in top_collections])
        async for r in self._render_or_text(event, "Template/redCollection/redCollection.html", render_data, text, {"viewport_width": 1220, "viewport_height": 2340}):
            yield r

    async def _health_info(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.object_health()
        if not self._ok(res):
            yield event.plain_result(f"健康状态查询失败: {self._message_of(res)}")
            return
        raw = self._data(res, {}) or {}
        rows = self._first_list(raw, ("list", "items", "data"))
        health = rows[0] if rows else raw if isinstance(raw, dict) else {}
        detail = (health.get("healthyDetail") or health.get("healthy_detail") or {}) if isinstance(health, dict) else {}
        if not detail:
            yield event.plain_result("未查询到健康状态详细信息。")
            return
        debuffs = []
        for group in detail.get("deBuffList") or detail.get("debuffList") or []:
            area = group.get("area") or "未知部位"
            statuses = group.get("list") or []
            for idx in range(0, len(statuses), 2):
                part = statuses[idx : idx + 2]
                debuffs.append({"area": area, "list": part, "isMerged": len(part) == 2})
        data = {"deBuffList": debuffs, "buffList": detail.get("buffList") or []}
        text = self._summary_dict("健康状态", detail)
        async for r in self._render_or_text(event, "Template/healthInfo/healthInfo.html", data, text, {"viewport_width": 760, "viewport_height": 1200}):
            yield r

    async def _user_stats(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        if not event.is_admin():
            yield event.plain_result("抱歉，只有管理员可以查看本地用户统计。")
            return
        all_bindings = getattr(self.bindings, "_data", {}) or {}
        total_users = len(all_bindings)
        total_accounts = sum(len(v) for v in all_bindings.values() if isinstance(v, list))
        valid_accounts = 0
        login_types: Dict[str, int] = {}
        for rows in all_bindings.values():
            if not isinstance(rows, list):
                continue
            for item in rows:
                if item.get("is_valid", True):
                    valid_accounts += 1
                login_type = item.get("login_type") or item.get("token_type") or "unknown"
                login_types[login_type] = login_types.get(login_type, 0) + 1
        lines = [
            "【三角洲行动 - AstrBot 本地用户统计】",
            f"绑定用户数: {total_users}",
            f"绑定账号数: {total_accounts}",
            f"有效账号数: {valid_accounts}",
            "登录方式:",
        ]
        lines.extend(f"- {key}: {value}" for key, value in sorted(login_types.items()))
        lines.append("说明: 该统计来自 AstrBot 本地绑定文件，不读取云崽配置或数据库。")
        yield event.plain_result("\n".join(lines))

    async def _ban_history(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        res = await self.client.ban_history(token)
        if not self._ok(res):
            yield event.plain_result(f"封号/违规记录查询失败: {self._message_of(res)}")
            return

        raw = self._data(res, [])
        if isinstance(raw, list):
            records = [item for item in raw if isinstance(item, dict)]
        elif isinstance(raw, dict):
            records = self._first_list(raw, ("list", "records", "items", "data"))
        else:
            yield event.plain_result("封号/违规记录返回数据格式异常。")
            return
        if not records:
            yield event.plain_result("该账号暂无违规记录。")
            return

        lines = [f"【封号/违规记录】共 {len(records)} 条"]
        for index, record in enumerate(records, 1):
            game_name = str(record.get("game_name") or "未知游戏")
            zone = str(record.get("zone") or "").strip()
            lines.extend(
                [
                    f"\n--- 违规记录 {index} ---",
                    f"游戏: {game_name}{f'（{zone}）' if zone else ''}",
                    f"类型: {record.get('type') or '未知'}",
                    f"原因: {record.get('reason') or '未知'}",
                    f"分类: {record.get('strategy_desc') or '未知'}",
                    f"开始时间: {self._fmt_time(record.get('start_stmp'))}",
                    f"持续时间: {self._fmt_ban_duration(record.get('duration'))}",
                ]
            )
            if record.get("cheat_date"):
                lines.append(f"作弊时间: {self._fmt_time(record.get('cheat_date'))}")
        yield event.plain_result("\n".join(lines))

    @staticmethod
    def _gamesafe_records(data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("records", "list", "items", "data", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data] if data else []

    @staticmethod
    def _gamesafe_record_lines(record: Dict[str, Any]) -> List[str]:
        labels = {
            "uin": "账号",
            "user_id": "账号",
            "nickname": "昵称",
            "game_id": "游戏 ID",
            "gameid": "游戏 ID",
            "game_name": "游戏",
            "status": "状态",
            "online": "在线",
            "frozen": "冻结",
            "is_frozen": "冻结",
            "punish_type": "处罚类型",
            "reason": "原因",
            "start_time": "开始时间",
            "end_time": "结束时间",
            "device_name": "设备",
            "device_type": "设备类型",
            "last_login_time": "最近登录",
            "login_time": "登录时间",
            "login_ip": "登录 IP",
            "location": "地点",
            "is_trusted": "信任设备",
        }
        sensitive_parts = (
            "token",
            "cookie",
            "openid",
            "open_id",
            "credential",
            "secret",
            "auth",
            "callback",
            "state",
        )
        lines: List[str] = []
        for key, value in record.items():
            normalized = str(key).strip().lower()
            if any(part in normalized for part in sensitive_parts):
                continue
            if value in (None, "", [], {}):
                continue
            if isinstance(value, bool):
                display = "是" if value else "否"
            elif isinstance(value, list) and all(
                not isinstance(item, (dict, list)) for item in value
            ):
                display = "、".join(str(item) for item in value[:10])
            elif isinstance(value, (dict, list)):
                continue
            else:
                display = str(value)
            if len(display) > 240:
                display = display[:240].rstrip() + "..."
            label = labels.get(normalized, str(key))
            lines.append(f"{label}: {display}")
            if len(lines) >= 10:
                break
        return lines

    async def _gamesafe_token(self, event: AstrMessageEvent) -> Optional[str]:
        return await self._token_for_type(event, "gamesafe")

    async def _gamesafe_bindings(
        self,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[Any, None]:
        token = await self._gamesafe_token(event)
        if not token:
            yield event.plain_result(
                "尚未绑定微信安全中心账号，请先发送 微信安全中心授权登录。"
            )
            return
        res = await self.client.gamesafe_bindings(token)
        if not self._ok(res):
            yield event.plain_result(f"微信安全中心绑定列表查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        if not isinstance(data, dict):
            yield event.plain_result("微信安全中心绑定列表返回格式异常。")
            return
        accounts = [
            str(item).strip()
            for item in data.get("list") or []
            if re.fullmatch(r"\d{5,20}", str(item).strip())
        ]
        default = str(data.get("default") or "").strip()
        if not accounts:
            yield event.plain_result("微信安全中心当前没有可用的绑定账号。")
            return
        lines = [f"【微信安全中心绑定】共 {len(accounts)} 个账号"]
        for index, account in enumerate(accounts, 1):
            lines.append(f"{'★' if account == default else ' '} {index}. {account}")
        yield event.plain_result("\n".join(lines))

    async def _gamesafe_query(
        self,
        event: AstrMessageEvent,
        kind: str,
        account: str = "",
    ) -> AsyncGenerator[Any, None]:
        token = await self._gamesafe_token(event)
        if not token:
            yield event.plain_result(
                "尚未绑定微信安全中心账号，请先发送 微信安全中心授权登录。"
            )
            return

        requests = {
            "login": ("登录信息", lambda: self.client.gamesafe_login_info(token)),
            "punish": (
                "封禁记录",
                lambda: self.client.gamesafe_punishments(token, account, 10),
            ),
            "frozen": (
                "冻结状态",
                lambda: self.client.gamesafe_frozen(token, account),
            ),
            "devices": (
                "设备列表",
                lambda: self.client.gamesafe_devices(token, account),
            ),
            "online": ("在线状态", lambda: self.client.gamesafe_online(token)),
            "report": (
                "安全报告",
                lambda: self.client.gamesafe_report(token, account),
            ),
        }
        if kind not in requests:
            yield event.plain_result("不支持的微信安全中心查询类型。")
            return
        title, request = requests[kind]
        res = await request()
        if not self._ok(res):
            yield event.plain_result(f"微信安全中心{title}查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {})
        records = self._gamesafe_records(data)
        if not records:
            yield event.plain_result(f"微信安全中心当前没有可显示的{title}。")
            return

        lines = [f"【微信安全中心{title}】"]
        if account:
            lines.append(f"查询账号: {account}")
        shown = 0
        for index, record in enumerate(records[:20], 1):
            details = self._gamesafe_record_lines(record)
            if not details:
                continue
            shown += 1
            if len(records) > 1:
                lines.append(f"\n--- 第 {index} 项 ---")
            lines.extend(details)
        if shown == 0:
            yield event.plain_result(f"微信安全中心{title}响应中没有可安全展示的字段。")
            return
        if len(records) > 20:
            lines.append(f"\n结果较多，仅展示前 20 项，共 {len(records)} 项。")
        text = "\n".join(lines)
        if len(text) > 3500:
            text = text[:3500].rstrip() + "\n\n结果较长，已截断显示。"
        yield event.plain_result(text)

    async def _place_status(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        res = await self.client.place_status(token)
        if not self._ok(res):
            yield event.plain_result(f"特勤处状态查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        places = [item for item in self._first_list(data, ("places", "list", "items", "data")) if isinstance(item, dict)]
        if not places:
            yield event.plain_result("当前没有可显示的特勤处设施状态。")
            return
        stats = data.get("stats") if isinstance(data, dict) and isinstance(data.get("stats"), dict) else {}
        lines = [
            "【特勤处状态】",
            f"设施 {stats.get('total', len(places))} 个｜生产中 {stats.get('producing', 0)} 个｜闲置 {stats.get('idle', 0)} 个",
        ]
        for place in places:
            name = place.get("placeName") or place.get("name") or place.get("placeType") or "未知设施"
            status = place.get("status") or "未知状态"
            level = int(self._number(place.get("level"), 0))
            detail = place.get("objectDetail") if isinstance(place.get("objectDetail"), dict) else {}
            item_name = detail.get("objectName") or detail.get("name") or ""
            left_time = int(self._number(place.get("leftTime"), 0))
            suffix = f"，生产 {item_name}" if item_name else ""
            if left_time > 0:
                suffix += f"，剩余 {self._fmt_duration(left_time)}"
            lines.append(f"{name} Lv.{level}：{status}{suffix}")
        yield event.plain_result("\n".join(lines))

    async def _place_info(self, event: AstrMessageEvent, place: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        type_names = {
            "storage": "仓库",
            "control": "指挥中心",
            "workbench": "工作台",
            "tech": "技术中心",
            "shoot": "靶场",
            "training": "训练中心",
            "pharmacy": "制药台",
            "armory": "防具台",
            "diving": "潜水中心",
        }
        type_aliases = {**{key: key for key in type_names}, **{value: key for key, value in type_names.items()}}
        args = place.split()
        requested = args[0] if args and args[0].lower() not in {"all", "全部"} else ""
        place_type = type_aliases.get(requested, "") if requested else ""
        if requested and not place_type:
            yield event.plain_result("未知特勤处类型。支持：" + "、".join(type_names.values()))
            return
        level = next((int(value) for value in args[1:] if value.isdigit()), 0)
        res = await self.client.place_info(token, place_type)
        if not self._ok(res):
            yield event.plain_result(f"特勤处信息查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        places = self._first_list(data, ("places", "list", "items", "data"))
        relate_map = data.get("relateMap") if isinstance(data, dict) and isinstance(data.get("relateMap"), dict) else {}
        processed = self._adapt_places(places, relate_map, type_names)
        if level:
            exact = [item for item in processed if int(self._num(item.get("level"))) == level]
            if exact:
                processed = exact
            elif processed:
                highest = max(int(self._num(item.get("level"))) for item in processed)
                processed = [item for item in processed if int(self._num(item.get("level"))) == highest]
                yield event.plain_result(f"未找到等级 {level}，已展示当前可用最高等级 {highest}。")
        if not processed:
            yield event.plain_result("未查询到符合条件的特勤处设施。")
            return
        text = "\n".join(
            ["【特勤处信息】"]
            + [f"{item['displayName']} Lv.{item['level']}，升级材料 {len(item['upgradeRequired'])} 种" for item in processed]
        )
        async for r in self._render_or_text(event, "Template/placeInfo/placeInfo.html", {"places": processed}, text, {"viewport_width": 1200, "viewport_height": 1600}):
            yield r

    def _adapt_places(
        self,
        places: List[Any],
        relate_map: Dict[str, Any],
        type_names: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        type_images = {
            "storage": "仓库.png",
            "control": "指挥中心.png",
            "workbench": "工作台.png",
            "tech": "技术中心.png",
            "shoot": "靶场.png",
            "training": "训练中心.png",
            "pharmacy": "制药台.png",
            "armory": "防具台.png",
            "diving": "潜水中心.png",
        }
        result = []
        for place in places:
            if not isinstance(place, dict):
                continue
            place_type = str(place.get("placeType") or "")
            upgrade = place.get("upgradeInfo") if isinstance(place.get("upgradeInfo"), dict) else {}
            condition_text = str(upgrade.get("condition") or "")
            conditions = [value.strip() for value in re.split(r"[;；]", condition_text) if value.strip()]
            level_condition = next((value for value in conditions if re.search(r"解锁等级|等级\s*\d+", value)), "")
            other_conditions = [value for value in conditions if value != level_condition]
            required = []
            for item in place.get("upgradeRequired") or []:
                if not isinstance(item, dict):
                    continue
                object_id = str(item.get("objectID") or item.get("objectId") or item.get("id") or "")
                info = relate_map.get(object_id) if isinstance(relate_map.get(object_id), dict) else {}
                required.append(
                    {
                        "objectName": info.get("objectName") or info.get("name") or f"物品 {object_id}",
                        "count": item.get("count") or item.get("perCount") or 1,
                        "imageUrl": info.get("pic") or (f"https://playerhub.df.qq.com/playerhub/60004/object/{object_id}.png" if object_id else ""),
                    }
                )
            unlock = place.get("unlockInfo") if isinstance(place.get("unlockInfo"), dict) else {}
            properties_raw = unlock.get("properties") or []
            if isinstance(properties_raw, dict):
                properties_raw = properties_raw.get("list") or []
            properties = []
            for item in properties_raw if isinstance(properties_raw, list) else []:
                if isinstance(item, dict):
                    properties.append(str(item.get("name") or item.get("objectName") or item.get("desc") or "未知效果"))
                else:
                    properties.append(str(item))
            unlocked_props = []
            for item in unlock.get("props") or []:
                if not isinstance(item, dict):
                    unlocked_props.append({"objectName": str(item), "imageUrl": "", "count": ""})
                    continue
                object_id = str(item.get("objectID") or item.get("objectId") or item.get("id") or "")
                info = item.get("itemInfo") if isinstance(item.get("itemInfo"), dict) else {}
                if not info and object_id and isinstance(relate_map.get(object_id), dict):
                    info = relate_map[object_id]
                unlocked_props.append(
                    {
                        "objectName": info.get("objectName") or info.get("name") or item.get("name") or f"物品 {object_id}",
                        "imageUrl": info.get("pic") or (f"https://playerhub.df.qq.com/playerhub/60004/object/{object_id}.png" if object_id else ""),
                        "count": item.get("count") or item.get("perCount") or "",
                    }
                )
            haf_count = self._number(upgrade.get("hafCount"))
            result.append(
                {
                    "displayName": place.get("placeName") or type_names.get(place_type) or "未知设施",
                    "level": int(self._num(place.get("level"))),
                    "imageUrl": f"imgs/place/{type_images[place_type]}" if place_type in type_images else "",
                    "upgradeInfo": {
                        "condition": condition_text,
                        "conditions": other_conditions,
                        "levelCondition": level_condition,
                        "hafCount": haf_count,
                        "hafCountFormatted": self.data_mgr.fmt_num(haf_count),
                    } if upgrade else None,
                    "upgradeRequired": required,
                    "unlockInfo": {"properties": properties, "props": unlocked_props} if properties or unlocked_props else None,
                    "detail": place.get("detail") or "",
                }
            )
        return sorted(result, key=lambda item: (item["displayName"], item["level"]))

    async def _server_status(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        try:
            res = await self.client.health()
        except Exception as exc:
            yield event.plain_result(f"服务器状态查询失败: {exc}")
            return
        if not self._ok(res):
            yield event.plain_result(f"服务器状态查询失败: {self._message_of(res)}")
            return

        data = self._data(res, None)
        if not isinstance(data, dict) or not data:
            yield event.plain_result("服务器状态返回数据格式异常。")
            return
        status = str(data.get("status") or "unknown").lower()
        status_names = {"healthy": "正常", "degraded": "降级", "unhealthy": "异常"}
        dependencies = data.get("dependencies") if isinstance(data.get("dependencies"), dict) else {}
        mongodb = dependencies.get("mongodb") if isinstance(dependencies.get("mongodb"), dict) else {}
        redis = dependencies.get("redis") if isinstance(dependencies.get("redis"), dict) else {}
        system = data.get("system") if isinstance(data.get("system"), dict) else {}
        memory = system.get("memory") if isinstance(system.get("memory"), dict) else {}

        mongo_text = "已连接" if mongodb.get("status") == "connected" else "未连接"
        if mongodb.get("latencyMs") is not None:
            mongo_text += f"（延迟 {mongodb.get('latencyMs')} ms）"
        redis_text = "已连接" if redis.get("status") == "connected" else "未连接"
        runtime = " / ".join(
            str(value)
            for value in (system.get("goVersion"), system.get("platform"), system.get("arch"))
            if value
        )
        lines = [
            "【三角洲 API 服务器状态】",
            f"服务状态: {status_names.get(status, status or '未知')}",
            f"运行时间: {self.data_mgr.fmt_duration(data.get('uptime') or 0)}",
            f"检查时间: {data.get('timestamp') or '未知'}",
            f"MongoDB: {mongo_text}",
            f"Redis: {redis_text}",
        ]
        if runtime:
            lines.append(f"运行环境: {runtime}")
        if memory:
            lines.append(
                "内存: "
                f"堆 {memory.get('heapUsedMB', 0)}/{memory.get('heapTotalMB', 0)} MB，"
                f"系统 {memory.get('sysMB', 0)} MB"
            )
        if system.get("goroutines") is not None:
            lines.append(f"协程数: {system.get('goroutines')}")
        yield event.plain_result("\n".join(lines))

    async def _operator_list(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.operators(detail=False)
        if not self._ok(res):
            yield event.plain_result(f"干员列表查询失败: {self._message_of(res)}")
            return
        rows = self._first_list(self._data(res, []), ("operators", "items", "list", "data"))
        if not rows:
            yield event.plain_result("未查询到任何干员信息。")
            return
        groups: Dict[str, List[str]] = {"突击": [], "工程": [], "支援": [], "侦察": [], "未知": []}
        for item in rows:
            if not isinstance(item, dict):
                continue
            operator_id = int(self._num(item.get("id") or item.get("operatorId")))
            army_type = str(item.get("armyType") or "")
            if not army_type:
                army_type = next(
                    (name for lower, upper, name in ((10000, 20000, "突击"), (20000, 30000, "支援"), (30000, 40000, "工程"), (40000, 50000, "侦察")) if lower <= operator_id < upper),
                    "未知",
                )
            name = item.get("name") or item.get("operator") or item.get("operatorName") or item.get("fullName") or "未知干员"
            groups.setdefault(army_type, []).append(str(name))
        lines = [f"【三角洲干员列表】共 {sum(len(values) for values in groups.values())} 名"]
        for army_type in ("突击", "工程", "支援", "侦察", "未知"):
            if groups.get(army_type):
                lines.append(f"\n【{army_type}】({len(groups[army_type])} 人)")
                lines.extend(f"- {name}" for name in groups[army_type])
        yield event.plain_result("\n".join(lines))

    async def _operator_info(self, event: AstrMessageEvent, name: str) -> AsyncGenerator[Any, None]:
        res = await self.client.operators(detail=True)
        if not self._ok(res):
            yield event.plain_result(f"干员查询失败: {self._message_of(res)}")
            return
        rows = self._first_list(self._data(res, []), ("operators", "items", "list", "data"))
        target = None
        for item in rows:
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("operator") or item.get("name") or item.get("operatorName") or "")
            full_name = str(item.get("fullName") or "")
            if name in {item_name, full_name} or name in item_name or name in full_name:
                target = item
                break
        if not target:
            yield event.plain_result(f"未找到干员：{name}")
            return
        op_name = target.get("operator") or target.get("name") or target.get("operatorName") or name
        abilities = target.get("abilitiesList") or target.get("abilities") or target.get("abilityList") or target.get("skills") or []
        render_data = {
            "operatorName": op_name,
            "fullName": target.get("fullName") or target.get("englishName") or "",
            "operatorPic": target.get("pic") or target.get("operatorPic") or (self.renderer.res_path.as_uri() + f"/imgs/operator/{op_name}.jpg"),
            "armyType": target.get("armyType") or target.get("type") or "",
            "armyTypeDesc": target.get("armyTypeDesc") or "",
            "abilitiesList": abilities,
        }
        text = self._summary_dict(f"干员 {op_name}", target)
        async for r in self._render_or_text(event, "Template/operator/operator.html", render_data, text, {"viewport_width": 1100, "viewport_height": 1200}):
            yield r

    async def _object_list(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        parts = arg.split()
        page = next((part for part in parts if part.isdigit()), "1")
        categories = [part for part in parts if not part.isdigit()]
        primary = categories[0] if categories else "props"
        second = categories[1] if len(categories) > 1 else ("collection" if not categories else "")
        res = await self.client.object_list(primary, second, page, "20")
        if not self._ok(res):
            yield event.plain_result(f"物品列表查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        rows = [item for item in self._first_list(data, ("list", "items", "data")) if isinstance(item, dict)]
        if not rows:
            yield event.plain_result("未找到符合条件的物品。")
            return
        total = int(self._number(data.get("total") if isinstance(data, dict) else len(rows), len(rows)))
        current_page = int(self._number(data.get("page") if isinstance(data, dict) else page, 1))
        lines = [f"【物品列表】{primary}/{second or '全部'}，第 {current_page} 页，共 {total} 件"]
        for index, item in enumerate(rows, 1):
            item_id = item.get("objectID") or item.get("id") or "-"
            item_name = item.get("objectName") or item.get("gameName") or "未知物品"
            category_parts = [
                str(item.get("primaryClass") or ""),
                str(item.get("secondClassCN") or item.get("secondClass") or ""),
            ]
            category = "/".join(value for value in category_parts if value)
            price = self.data_mgr.fmt_num(item.get("price") or item.get("avgPrice") or 0)
            lines.append(f"{index}. {item_name}（{item_id}） {category or '未分类'}，价格 {price}")
        yield event.plain_result("\n".join(lines))

    async def _object_search(self, event: AstrMessageEvent, keyword: str) -> AsyncGenerator[Any, None]:
        res = await self.client.object_search(keyword)
        if self._ok(res):
            data = self._data(res, {}) or {}
            rows = [item for item in self._first_list(data, ("list", "items", "data")) if isinstance(item, dict)]
            if not rows:
                yield event.plain_result(f"未搜索到与“{keyword}”相关的物品。")
                return
            lines = [f"【物品搜索：{keyword}】共 {data.get('total', len(rows)) if isinstance(data, dict) else len(rows)} 条"]
            for index, item in enumerate(rows, 1):
                item_id = item.get("objectID") or item.get("id") or "-"
                name = item.get("objectName") or item.get("gameName") or "未知物品"
                category = item.get("secondClassCN") or item.get("secondClass") or item.get("primaryClass") or "未分类"
                lines.append(f"{index}. {name}（{item_id}） {category}")
            yield event.plain_result("\n".join(lines))
            return
        local = self.data_mgr.search_local_items(keyword)
        if local:
            yield event.plain_result("【本地物品搜索】\n" + "\n".join(f"{x['id']} {x['name']} ({x['source']})" for x in local))
        else:
            yield event.plain_result(f"物品搜索失败: {self._message_of(res)}")

    async def _resolve_item_id(self, keyword: str) -> str:
        if keyword.isdigit():
            return keyword
        res = await self.client.object_search(keyword, limit="1")
        rows = self._first_list(self._data(res, {}), ("items", "list", "data", "objects"))
        if rows:
            return str(rows[0].get("objectID") or rows[0].get("objectId") or rows[0].get("id") or keyword)
        value = await self.client.object_value_search(keyword)
        rows = self._first_list(self._data(value, {}), ("items", "list", "data", "keywords"))
        if rows:
            return str(rows[0].get("id") or rows[0].get("objectID") or rows[0].get("objectId") or keyword)
        return keyword

    async def _price_now(self, event: AstrMessageEvent, keyword: str) -> AsyncGenerator[Any, None]:
        item_id = await self._resolve_item_id(keyword)
        res = await self.client.current_price(item_id)
        if not self._ok(res):
            res = await self.client.object_value_search(keyword)
        if not self._ok(res):
            yield event.plain_result(f"当前价格查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        rows = [item for item in self._first_list(data, ("items", "list", "data")) if isinstance(item, dict)]
        if not rows and isinstance(data, dict) and data.get("avgPrice") is not None:
            rows = [data]
        if not rows:
            yield event.plain_result(f"未查询到“{keyword}”的当前价格。")
            return
        lines = [f"【当前价格：{keyword}】"]
        for item in rows:
            item_id = item.get("objectID") or item.get("id") or item_id
            lines.append(f"物品 {item_id}: {self.data_mgr.fmt_num(item.get('avgPrice') or item.get('price') or 0)}")
        yield event.plain_result("\n".join(lines))

    async def _price_history(self, event: AstrMessageEvent, keyword: str) -> AsyncGenerator[Any, None]:
        item_id = await self._resolve_item_id(keyword)
        res = await self.client.price_history_v2(item_id)
        if not self._ok(res):
            res = await self.client.object_value_history(item_id)
        if not self._ok(res):
            yield event.plain_result(f"价格历史查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        item = data
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            item = data["items"][0] if data["items"] else {}
        if not isinstance(item, dict) or not item:
            yield event.plain_result(f"未查询到“{keyword}”的价格历史。")
            return
        stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
        lines = [f"【价格历史：{item.get('objectName') or keyword}】", f"物品 ID: {item.get('objectID') or item_id}"]
        if stats:
            lines.extend(
                [
                    f"最新: {self.data_mgr.fmt_num(stats.get('latestPrice') or 0)}",
                    f"平均: {self.data_mgr.fmt_num(stats.get('avgPrice') or 0)}",
                    f"最低/最高: {self.data_mgr.fmt_num(stats.get('minPrice') or 0)} / {self.data_mgr.fmt_num(stats.get('maxPrice') or 0)}",
                    f"变化: {self._format_profit(stats.get('priceChange') or 0)}（{self._number(stats.get('priceChangePercent')):.2f}%）",
                ]
            )
        else:
            history = self._first_list(item, ("history", "list", "data"))
            lines.extend(f"{point.get('hour') or point.get('timestamp')}: {self.data_mgr.fmt_num(point.get('price') or point.get('avgPrice') or 0)}" for point in history[:10] if isinstance(point, dict))
        yield event.plain_result("\n".join(lines))

    async def _material_price(self, event: AstrMessageEvent, item_id: str) -> AsyncGenerator[Any, None]:
        res = await self.client.material_price(item_id)
        if not self._ok(res):
            yield event.plain_result(f"材料价格查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        rows = [item for item in self._first_list(data, ("materials", "items", "list", "data")) if isinstance(item, dict)]
        if not rows:
            yield event.plain_result("未查询到符合条件的制造材料。")
            return
        pagination = data.get("pagination") if isinstance(data, dict) and isinstance(data.get("pagination"), dict) else {}
        lines = [f"【材料价格】第 {pagination.get('page', 1)} 页，共 {pagination.get('total', len(rows))} 种"]
        for index, item in enumerate(rows, 1):
            name = item.get("objectName") or "未知材料"
            item_id = item.get("objectID") or "-"
            price = "暂无" if item.get("price") is None else self.data_mgr.fmt_num(item.get("price"))
            lines.append(f"{index}. {name}（{item_id}） {price}")
        yield event.plain_result("\n".join(lines))

    async def _profit(self, event: AstrMessageEvent, command: str, arg: str) -> AsyncGenerator[Any, None]:
        place_aliases = {
            "工作台": "workbench",
            "技术中心": "tech",
            "制药台": "pharmacy",
            "防具台": "armory",
            "workbench": "workbench",
            "tech": "tech",
            "pharmacy": "pharmacy",
            "armory": "armory",
        }
        params = self._parse_key_values(arg)
        parts = [part for part in arg.split() if "=" not in part]
        if "历史" in command:
            days = str(params.get("days") or "")
            query_parts = []
            for part in parts:
                match = re.fullmatch(r"(\d+)天", part)
                if match:
                    days = match.group(1)
                else:
                    query_parts.append(part)
            query = str(params.get("objectID") or params.get("objectId") or " ".join(query_parts)).strip()
            if not query:
                yield event.plain_result("用法：利润历史 <物品名称/ID> [天数]")
                return
            object_id = await self._resolve_item_id(query)
            if not object_id.isdigit():
                yield event.plain_result(f"未找到物品：{query}")
                return
            params = {"objectID": object_id}
            if days:
                params["days"] = days
            res = await self.client.profit_history(params)
        elif "排行" in command or "利润榜" in command or "最高" in command:
            params = self._profit_query_params(parts, params, place_aliases, default_limit="10")
            res = await self.client.profit_rank(params)
        else:
            params = self._profit_query_params(parts, params, place_aliases)
            res = await self.client.place_profit(params)
        if not self._ok(res):
            yield event.plain_result(f"{command}查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        if "历史" in command:
            info = data.get("objectInfo") if isinstance(data, dict) and isinstance(data.get("objectInfo"), dict) else {}
            history = self._first_list(data, ("history", "items", "list", "data"))
            if not history:
                yield event.plain_result("暂无该物品的利润历史数据。")
                return
            lines = [f"【{info.get('objectName') or '物品'}利润历史】{data.get('days', params.get('days', 7))} 天"]
            lines.append(f"{info.get('placeName') or info.get('placeType') or '未知场所'} Lv.{info.get('level') or '-'}，周期 {info.get('period') or '-'} 小时")
            for item in history[:20]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"{item.get('timestamp') or '-'} 售价 {self.data_mgr.fmt_num(item.get('salePrice') or 0)}，"
                    f"总利润 {self._format_profit(item.get('totalProfit') or 0)}，时均 {self._format_profit(item.get('hourProfit') or 0)}"
                )
            yield event.plain_result("\n".join(lines))
            return
        if "排行" in command or "利润榜" in command or "最高" in command:
            rows = [item for item in self._first_list(data, ("items", "list", "data")) if isinstance(item, dict)]
            if not rows:
                yield event.plain_result("当前查询条件下没有利润排行数据。")
                return
            sort_name = "时均利润" if str(data.get("sortType") or params.get("type")) == "hour" else "总利润"
            lines = [f"【利润排行 · {sort_name}】"]
            for index, item in enumerate(rows, 1):
                value = item.get("hourProfit") if sort_name == "时均利润" else item.get("totalProfit")
                lines.append(
                    f"{item.get('rank') or index}. {item.get('objectName') or item.get('objectID') or '未知物品'} "
                    f"({item.get('placeName') or item.get('placeType') or '未知场所'} Lv.{item.get('level') or '-'}) {self._format_profit(value or 0)}"
                )
            yield event.plain_result("\n".join(lines))
            return
        places = [item for item in self._first_list(data, ("manufacturingPlaces", "places", "list", "data")) if isinstance(item, dict)]
        if not places:
            yield event.plain_result("当前查询条件下没有特勤处利润数据。")
            return
        lines = [f"【特勤处利润 · {'时均' if str(data.get('sortType') or params.get('type')) == 'hour' else '总利润'}】"]
        for place in places:
            lines.append(f"\n【{place.get('placeName') or place.get('placeType') or '未知场所'} Lv.{place.get('level') or '-'}】")
            items = [item for item in place.get("manufacturingItems") or [] if isinstance(item, dict)]
            for index, item in enumerate(items[:10], 1):
                value = item.get("hourProfit") if str(data.get("sortType") or params.get("type")) == "hour" else item.get("totalProfit")
                lines.append(f"{index}. {item.get('objectName') or item.get('objectID') or '未知物品'} {self._format_profit(value or 0)}")
        yield event.plain_result("\n".join(lines))

    @staticmethod
    def _profit_query_params(
        parts: List[str],
        initial: Dict[str, Any],
        place_aliases: Dict[str, str],
        default_limit: str = "",
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for key, value in initial.items():
            normalized = {"objectId": "objectID", "sort": "type"}.get(key, key)
            params[normalized] = value
        if default_limit and "limit" not in params:
            params["limit"] = default_limit
        for part in parts:
            lowered = part.lower()
            if lowered in place_aliases:
                params["place"] = place_aliases[lowered]
            elif lowered in {"hour", "hourprofit", "小时", "时均"}:
                params["type"] = "hour"
            elif lowered in {"total", "totalprofit", "profit", "总利润"}:
                params["type"] = "total"
            elif match := re.fullmatch(r"(?:lv|等级)(\d+)", lowered):
                params["level"] = match.group(1)
            elif part.isdigit():
                params["limit"] = part
        params["type"] = "hour" if str(params.get("type") or "hour").lower() in {"hour", "hourprofit"} else "total"
        return params

    def _solution_items(self, response: Any) -> List[Dict[str, Any]]:
        data = self._data(response, {}) or {}
        rows = self._first_list(data, ("items", "list", "solutions", "data"))
        return [item for item in rows if isinstance(item, dict)]

    @staticmethod
    def _valid_solution_id(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9-]{1,80}", str(value or "")))

    def _solution_list_text(self, title: str, rows: List[Dict[str, Any]], total: Any = None) -> str:
        lines = [f"【{title}】" + (f" 共 {total} 条" if total not in (None, "") else "")]
        for index, item in enumerate(rows, 1):
            solution_id = item.get("solutionId") or item.get("id") or "未知"
            lines.append(
                f"{index}. {item.get('weaponName') or '未知武器'}｜{item.get('type') or 'sol'}｜"
                f"{self.data_mgr.fmt_price(item.get('totalPrice') or 0)}\n"
                f"ID: {solution_id}\n"
                f"改枪码: {item.get('solutionCode') or '-'}\n"
                f"作者: {item.get('authorNickname') or '匿名'}｜赞 {item.get('likes') or 0}｜收藏 {item.get('favoriteCount') or 0}"
            )
        return "\n\n".join(lines)

    async def _solution_list(self, event: AstrMessageEvent, arg: str, favorites: bool) -> AsyncGenerator[Any, None]:
        params: Dict[str, Any] = {"page": 1, "pageSize": 20}
        keywords = []
        for part in str(arg or "").split():
            low = part.lower()
            if low in SOL_ALIASES:
                params["type"] = "sol"
            elif low in MP_ALIASES:
                params["type"] = "mp"
            elif match := re.fullmatch(r"(?:page|页)(\d+)", low):
                params["page"] = max(1, int(match.group(1)))
            elif match := re.fullmatch(r"(?:weapon|武器)(?:id)?[=:]?(\d+)", low):
                params["weaponId"] = int(match.group(1))
            else:
                keywords.append(part)
        if keywords:
            params["keyword"] = " ".join(keywords)
        if favorites:
            response = await self.client.my_community_favorites(
                self._user_identifier(event), int(params["page"]), int(params["pageSize"])
            )
            title = "我的改枪码收藏"
        else:
            response = await self.client.community_solutions(params)
            title = "改枪码社区"
        if not self._ok(response):
            yield event.plain_result(f"查询{title}失败：{self._message_of(response)}")
            return
        rows = self._solution_items(response)
        if not rows:
            yield event.plain_result("未找到符合条件的改枪方案。")
            return
        data = self._data(response, {}) or {}
        yield event.plain_result(self._solution_list_text(title, rows, data.get("total") if isinstance(data, dict) else None))

    async def _solution_detail(self, event: AstrMessageEvent, solution_id: str) -> AsyncGenerator[Any, None]:
        if not self._valid_solution_id(solution_id):
            yield event.plain_result("改枪方案 ID 格式无效。")
            return
        response = await self.client.community_solution_detail(solution_id)
        if not self._ok(response):
            yield event.plain_result(f"查询改枪方案失败：{self._message_of(response)}")
            return
        data = self._data(response, {}) or {}
        item = data.get("solution") if isinstance(data, dict) and isinstance(data.get("solution"), dict) else data
        if not isinstance(item, dict) or not item:
            yield event.plain_result("改枪方案不存在或暂不可见。")
            return
        attachments = [part for part in item.get("attachments") or [] if isinstance(part, dict)]
        lines = [
            "【改枪方案详情】",
            f"ID: {item.get('solutionId') or item.get('id') or solution_id}",
            f"武器: {item.get('weaponName') or '未知'} ({item.get('weaponId') or '-'})",
            f"模式: {item.get('type') or 'sol'}",
            f"改枪码: {item.get('solutionCode') or '-'}",
            f"总价: {self.data_mgr.fmt_price(item.get('totalPrice') or 0)}",
            f"作者: {item.get('authorNickname') or '匿名'}",
            f"状态: {item.get('reviewStatus') or item.get('status') or '未知'}",
            f"互动: 赞 {item.get('likes') or 0} / 踩 {item.get('dislikes') or 0} / 收藏 {item.get('favoriteCount') or 0}",
        ]
        if item.get("description"):
            lines.append(f"描述: {item['description']}")
        if attachments:
            lines.append("配件:")
            lines.extend(
                f"- {part.get('slotId') or '未知槽位'}: {part.get('objectName') or part.get('objectId') or '未知配件'}"
                for part in attachments
            )
        yield event.plain_result("\n".join(lines))

    async def _solution_upload(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        help_text = (
            "格式：上传改枪码 <改枪码> <武器ID> [sol/mp] [描述] <配件JSON>\n"
            "配件示例：[ {\"slotId\":\"scope\",\"objectId\":12345} ]"
        )
        if not arg:
            yield event.plain_result(help_text)
            return
        match = re.search(r"(\[[\s\S]*\])\s*$", arg)
        if not match:
            yield event.plain_result("缺少配件 JSON。" + help_text)
            return
        try:
            attachments = json.loads(match.group(1))
        except json.JSONDecodeError:
            yield event.plain_result("配件 JSON 格式错误。")
            return
        if not isinstance(attachments, list) or not attachments:
            yield event.plain_result("配件 JSON 必须是非空数组。")
            return
        normalized = []
        for part in attachments:
            if not isinstance(part, dict):
                yield event.plain_result("每个配件必须是 JSON 对象。")
                return
            slot_id = str(part.get("slotId") or part.get("slot_id") or "").strip()
            object_id = part.get("objectId") or part.get("object_id")
            if not slot_id or not str(object_id or "").isdigit():
                yield event.plain_result("每个配件都必须包含 slotId 和数字 objectId。")
                return
            normalized.append(
                {"slotId": slot_id, "objectId": int(object_id), "objectName": str(part.get("objectName") or "")}
            )
        parts = arg[: match.start()].strip().split()
        if len(parts) < 2 or not parts[1].isdigit():
            yield event.plain_result(help_text)
            return
        solution_code = parts[0]
        weapon_id = int(parts[1])
        mode = "sol"
        description_parts = parts[2:]
        if description_parts and description_parts[0].lower() in SOL_ALIASES | MP_ALIASES:
            token = description_parts.pop(0).lower()
            mode = "sol" if token in SOL_ALIASES else "mp"
        payload = {
            "solutionCode": solution_code,
            "description": " ".join(description_parts),
            "type": mode,
            "weaponId": weapon_id,
            "attachments": normalized,
        }
        response = await self.client.create_community_solution(payload, self._user_identifier(event))
        if not self._ok(response):
            yield event.plain_result(f"上传改枪方案失败：{self._message_of(response)}")
            return
        data = self._data(response, {}) or {}
        item = data.get("solution") if isinstance(data, dict) and isinstance(data.get("solution"), dict) else data
        solution_id = item.get("solutionId") or item.get("id") if isinstance(item, dict) else ""
        yield event.plain_result(f"改枪方案已提交，ID：{solution_id or '后端未返回'}。方案需通过审核后才会公开显示。")

    async def _solution_update(self, event: AstrMessageEvent, solution_id: str, arg: str) -> AsyncGenerator[Any, None]:
        if not self._valid_solution_id(solution_id):
            yield event.plain_result("改枪方案 ID 格式无效。")
            return
        parts = arg.split()
        payload: Dict[str, Any] = {}
        visibility = next((part for part in reversed(parts) if part.lower() in {"公开", "私有", "public", "private"}), "")
        if visibility:
            payload["isPublic"] = visibility.lower() in {"公开", "public"}
            parts.remove(visibility)
        description = " ".join(parts).strip()
        if description:
            payload["description"] = description
        if not payload:
            yield event.plain_result("请提供新描述和/或公开、私有设置。")
            return
        response = await self.client.update_community_solution(solution_id, payload, self._user_identifier(event))
        yield event.plain_result("改枪方案已更新。" if self._ok(response) else f"更新失败：{self._message_of(response)}")

    async def _solution_delete(self, event: AstrMessageEvent, solution_id: str) -> AsyncGenerator[Any, None]:
        if not self._valid_solution_id(solution_id):
            yield event.plain_result("改枪方案 ID 格式无效。")
            return
        response = await self.client.delete_community_solution(solution_id, self._user_identifier(event))
        yield event.plain_result("改枪方案已删除。" if self._ok(response) else f"删除失败：{self._message_of(response)}")

    async def _solution_vote(self, event: AstrMessageEvent, solution_id: str, vote: int) -> AsyncGenerator[Any, None]:
        if not self._valid_solution_id(solution_id):
            yield event.plain_result("改枪方案 ID 格式无效。")
            return
        response = await self.client.vote_community_solution(solution_id, vote, self._user_identifier(event))
        action = "点赞" if vote > 0 else "点踩"
        yield event.plain_result(f"已{action}该方案。" if self._ok(response) else f"{action}失败：{self._message_of(response)}")

    async def _solution_favorite(self, event: AstrMessageEvent, solution_id: str, enabled: bool) -> AsyncGenerator[Any, None]:
        if not self._valid_solution_id(solution_id):
            yield event.plain_result("改枪方案 ID 格式无效。")
            return
        response = await self.client.favorite_community_solution(solution_id, enabled, self._user_identifier(event))
        action = "收藏" if enabled else "取消收藏"
        yield event.plain_result(f"已{action}该方案。" if self._ok(response) else f"{action}失败：{self._message_of(response)}")

    async def _daily_keyword(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.daily_keyword()
        if not self._ok(res):
            yield event.plain_result(f"每日密码查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        if isinstance(data, dict) and data.get("available") is False:
            yield event.plain_result(str(data.get("message") or "暂无可用的公共登录凭证。"))
            return
        rows = self._first_list(data, ("list", "items", "data"))
        if not rows:
            yield event.plain_result("今日暂无可用密码数据。")
            return
        lines = ["【每日密码】"]
        for item in rows:
            if not isinstance(item, dict):
                continue
            map_name = item.get("mapName") or item.get("map_name") or item.get("name") or "未知地图"
            secret = item.get("secret") or item.get("password") or "暂无"
            lines.append(f"【{map_name}】: {secret}")
        yield event.plain_result("\n".join(lines))

    @staticmethod
    def _activity_datetime(value: Any) -> Optional[dt.datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return dt.datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    @classmethod
    def _activity_status(
        cls,
        start_time: Any,
        end_time: Any,
        current_time: Any,
    ) -> Tuple[str, str]:
        now = cls._activity_datetime(current_time) or dt.datetime.now()
        start = cls._activity_datetime(start_time)
        end = cls._activity_datetime(end_time)
        if start and now < start:
            return "即将开始", "upcoming"
        if end and now > end:
            return "已结束", "ended"
        if start or end:
            return "进行中", "active"
        return "时间待定", "unknown"

    def _activity_groups(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        resolver = getattr(self.client, "resolve_url", None)

        def media_url(value: Any) -> str:
            raw = str(value or "").strip()
            if not raw or not callable(resolver):
                return raw
            return str(resolver(raw) or raw)

        current_time = data.get("currentTime") or data.get("current_time") or ""

        def normalize_card(card: Any) -> Optional[Dict[str, Any]]:
            if not isinstance(card, dict):
                return None
            title = str(card.get("eventTitle") or card.get("title") or "未命名活动").strip()
            start_time = str(card.get("startTime") or card.get("start_time") or "").strip()
            end_time = str(card.get("endTime") or card.get("end_time") or "").strip()
            status_text, status_class = self._activity_status(
                start_time,
                end_time,
                current_time,
            )
            illustrations = card.get("illustration") or []
            reward_images = [
                media_url(item.get("rewardImage") or item.get("image"))
                for item in illustrations
                if isinstance(item, dict) and (item.get("rewardImage") or item.get("image"))
            ]
            if start_time and end_time:
                time_text = f"{start_time} 至 {end_time}"
            elif start_time:
                time_text = f"{start_time} 起"
            elif end_time:
                time_text = f"截至 {end_time}"
            else:
                time_text = "活动时间待公布"
            return {
                "id": str(card.get("id") or ""),
                "title": title,
                "label": str(card.get("labelCopy") or card.get("label") or "活动").strip(),
                "timeText": time_text,
                "statusText": status_text,
                "statusClass": status_class,
                "backgroundImage": media_url(
                    card.get("backgroundImage") or card.get("background_image")
                ),
                "rewardImages": reward_images[:4],
                "associationTab": str(card.get("associationTab") or ""),
            }

        groups: List[Dict[str, Any]] = []
        raw_groups = data.get("groups") or []
        if isinstance(raw_groups, list):
            for group in raw_groups:
                if not isinstance(group, dict):
                    continue
                raw_rows = group.get("cardRows") or group.get("cards") or []
                raw_cards: List[Any] = []
                for row in raw_rows if isinstance(raw_rows, list) else []:
                    if isinstance(row, list):
                        raw_cards.extend(row)
                    elif isinstance(row, dict):
                        raw_cards.append(row)
                cards = [item for item in (normalize_card(card) for card in raw_cards) if item]
                groups.append(
                    {
                        "id": str(group.get("id") or ""),
                        "name": str(group.get("tabName") or group.get("name") or "活动").strip(),
                        "icon": media_url(group.get("imgUrl") or group.get("image")),
                        "cards": cards,
                    }
                )

        if any(group["cards"] for group in groups):
            return groups

        groups = []
        raw_cards = data.get("cards") or []
        cards = [
            item
            for item in (
                normalize_card(card) for card in raw_cards if isinstance(raw_cards, list)
            )
            if item
        ]
        tabs = data.get("tabs") or []
        if isinstance(tabs, list):
            for tab in tabs:
                if not isinstance(tab, dict):
                    continue
                tab_id = str(tab.get("id") or "")
                groups.append(
                    {
                        "id": tab_id,
                        "name": str(tab.get("tabName") or tab.get("name") or "活动").strip(),
                        "icon": media_url(tab.get("imgUrl") or tab.get("image")),
                        "cards": [card for card in cards if card["associationTab"] == tab_id],
                    }
                )
        if not groups and cards:
            groups.append({"id": "all", "name": "全部活动", "icon": "", "cards": cards})
        return groups

    async def _activities(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.activities()
        if not self._ok(res):
            yield event.plain_result(f"活动日历查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        if not isinstance(data, dict):
            yield event.plain_result("活动日历响应格式异常。")
            return
        groups = self._activity_groups(data)
        total_cards = sum(len(group["cards"]) for group in groups)
        if total_cards == 0:
            yield event.plain_result("当前暂无活动日历数据。")
            return

        current_time = str(data.get("currentTime") or data.get("current_time") or "未知")
        lines = [
            "【三角洲活动日历】",
            f"更新时间: {current_time}",
            f"共 {len(groups)} 个分类、{total_cards} 个活动",
        ]
        for group in groups:
            if not group["cards"]:
                continue
            lines.append(f"\n【{group['name']}】")
            for index, card in enumerate(group["cards"], 1):
                lines.append(f"{index}. {card['title']} [{card['statusText']}]")
                lines.append(f"   {card['timeText']} | {card['label']}")
        text = "\n".join(lines)
        if len(text) > 3500:
            text = text[:3500].rstrip() + "\n\n活动较多，文本结果已截断。"
        render_data = {
            "currentTime": current_time,
            "totalGroups": len(groups),
            "totalCards": total_cards,
            "groups": groups,
        }
        async for result in self._render_or_text(
            event,
            "Template/activities/activities.html",
            render_data,
            text,
            {
                "viewport_width": 1200,
                "viewport_height": 2000,
                "selector": ".calendar-shell",
            },
        ):
            yield result

    async def _article_list(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.article_list()
        if not self._ok(res):
            yield event.plain_result(f"文章列表查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        articles = data.get("articles") if isinstance(data, dict) else data
        category_list = articles.get("list") if isinstance(articles, dict) else articles
        rows = []
        if isinstance(category_list, list):
            rows = [item for item in category_list if isinstance(item, dict)]
        elif isinstance(category_list, dict):
            for category in category_list.values():
                if isinstance(category, list):
                    rows.extend(item for item in category if isinstance(item, dict))
        rows.sort(key=lambda item: str(item.get("createdAt") or item.get("created_at") or ""), reverse=True)
        if not rows:
            yield event.plain_result("暂无文章数据。")
            return
        lines = ["【三角洲行动 - 最新文章列表】"]
        for index, article in enumerate(rows[:20], 1):
            author = article.get("author") or "未知作者"
            if isinstance(author, dict):
                author = author.get("nickname") or author.get("name") or "未知作者"
            thread_id = article.get("threadID") or article.get("threadId") or article.get("id") or "-"
            summary = str(article.get("summary") or "").strip()
            lines.extend(
                [
                    f"\n{index}. 【{article.get('title') or '无标题'}】",
                    f"作者: {author} | ID: {thread_id}",
                    f"发布时间: {article.get('createdAt') or article.get('created_at') or '未知'}",
                    f"浏览: {article.get('viewCount') or 0} | 点赞: {article.get('likedCount') or 0}",
                ]
            )
            if summary:
                lines.append(summary[:100] + ("..." if len(summary) > 100 else ""))
        lines.append("\n发送 文章详情 <ID> 查看具体内容。")
        yield event.plain_result("\n".join(lines))

    async def _article_detail(self, event: AstrMessageEvent, thread_id: str) -> AsyncGenerator[Any, None]:
        res = await self.client.article_detail(thread_id)
        if not self._ok(res):
            yield event.plain_result(f"文章详情查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        article = data.get("article") if isinstance(data, dict) else None
        if not isinstance(article, dict):
            yield event.plain_result("文章不存在或已删除。")
            return
        author = article.get("author") or "未知作者"
        if isinstance(author, dict):
            author = author.get("nickname") or author.get("name") or "未知作者"
        content = article.get("content") or ""
        if isinstance(content, dict):
            content = content.get("text") or content.get("content") or ""
        text_content = re.sub(
            r"\s+",
            " ",
            unescape(re.sub(r"<[^>]+>", "", str(content))),
        ).strip()
        tags = article.get("ext", {}).get("gicpTags", []) if isinstance(article.get("ext"), dict) else []
        lines = [
            f"【{article.get('title') or '无标题'}】",
            f"作者: {author}",
            f"发布时间: {article.get('createdAt') or article.get('created_at') or '未知'}",
            f"浏览: {article.get('viewCount') or 0} | 点赞: {article.get('likedCount') or 0}",
            f"ID: {article.get('id') or article.get('threadID') or thread_id}",
        ]
        if tags:
            lines.append("标签: " + ", ".join(str(tag) for tag in tags))
        if text_content:
            lines.extend(["", text_content[:3500]])
        yield event.plain_result("\n".join(lines))

    async def _ai_presets(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.ai_presets()
        if not self._ok(res):
            yield event.plain_result(f"AI 预设查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        presets = self._first_list(data, ("presets", "items", "list", "data"))
        if not presets:
            yield event.plain_result("暂无可用的 AI 预设。")
            return
        lines = ["【AI 评价预设列表】"]
        for index, item in enumerate(presets, 1):
            if isinstance(item, dict):
                code = item.get("code") or item.get("id") or "-"
                name = item.get("name") or item.get("displayName") or code
                default = "（默认）" if item.get("isDefault") or item.get("default") else ""
                lines.append(f"{index}. {name} - {code}{default}")
            else:
                lines.append(f"{index}. {item}")
        yield event.plain_result("\n".join(lines))

    async def _ai_review(
        self,
        event: AstrMessageEvent,
        arg: str,
        preset_required: bool = False,
    ) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode, _, rest = self._parse_mode_page(arg)
        if arg and not mode:
            yield event.plain_result("无法识别游戏模式，请使用 sol/烽火/4 或 mp/战场/5。")
            return
        options = rest.split()
        if preset_required and not options:
            yield event.plain_result("用法：ai评价 <模式> <预设> [音色]")
            return
        preset = options[0] if options else ""
        voice = options[1] if len(options) > 1 else ""
        res = await self.client.ai_review(token, mode or "sol", preset)
        if not self._ok(res):
            yield event.plain_result(f"AI 评价失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        content = str(data.get("content") or "").strip() if isinstance(data, dict) else ""
        if not content:
            yield event.plain_result("AI 评价完成，但后端未返回正文。")
            return
        mode_name = "烽火地带" if (mode or "sol") == "sol" else "全面战场"
        preset_name = str(data.get("presetName") or preset or "锐评") if isinstance(data, dict) else (preset or "锐评")
        yield event.plain_result(f"【{mode_name} AI{preset_name}】\n{content}")
        if voice:
            async for result in self._tts(event, f"{voice} {content}"):
                yield result

    async def _voice_meta(self, event: AstrMessageEvent, command: str) -> AsyncGenerator[Any, None]:
        if command == "语音列表":
            res = await self.client.audio_characters()
        elif command == "标签列表":
            res = await self.client.audio_tags()
        elif command == "语音分类":
            res = await self.client.audio_categories()
        else:
            res = await self.client.audio_stats()
        if not self._ok(res):
            yield event.plain_result(f"{command}查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        if command == "语音列表":
            rows = self._first_list(data, ("characters", "items", "list", "data"))
            if not rows:
                yield event.plain_result("暂无语音角色数据。")
                return
            lines = [f"【语音角色列表】共 {len(rows)} 名"]
            for index, item in enumerate(rows, 1):
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or "未知角色"
                voice_id = item.get("voiceId") or item.get("voiceID") or "-"
                profession = item.get("profession") or "未知职业"
                skins = item.get("skins") if isinstance(item.get("skins"), list) else []
                lines.append(f"{index}. {name}（{profession}）ID: {voice_id}，皮肤音色 {len(skins)} 个")
            yield event.plain_result("\n".join(lines))
            return
        if command == "标签列表":
            rows = self._first_list(data, ("tags", "items", "list", "data"))
            if not rows:
                yield event.plain_result("暂无语音标签数据。")
                return
            lines = [f"【语音标签列表】共 {len(rows)} 个"]
            for index, item in enumerate(rows, 1):
                if isinstance(item, dict):
                    tag = item.get("tag") or item.get("name") or "未知标签"
                    description = item.get("description") or ""
                    lines.append(f"{index}. {tag}" + (f"：{description}" if description else ""))
            yield event.plain_result("\n".join(lines))
            return
        categories = self._first_list(data, ("categories", "items", "list", "data"))
        if command == "语音分类":
            if not categories:
                yield event.plain_result("暂无语音分类数据。")
                return
            lines = [f"【语音分类】共 {len(categories)} 类"]
            for index, item in enumerate(categories, 1):
                if isinstance(item, dict):
                    name = item.get("category") or item.get("name") or "未分类"
                    lines.append(f"{index}. {name}：{int(self._number(item.get('count'), 0))} 条")
            yield event.plain_result("\n".join(lines))
            return
        total = int(self._number(data.get("totalFiles") if isinstance(data, dict) else 0, 0))
        if not total and not categories:
            yield event.plain_result("暂无音频统计数据。")
            return
        lines = [f"【语音统计】总文件数：{total}"]
        for item in categories:
            if isinstance(item, dict):
                name = item.get("category") or item.get("name") or "未分类"
                count = int(self._number(item.get("fileCount") or item.get("count"), 0))
                lines.append(f"{name}：{count} 条")
        yield event.plain_result("\n".join(lines))

    async def _voice(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        params = self._parse_key_values(arg)
        if arg and not params:
            params = {"character": arg}
        res = await self.client.audio_random(params)
        if not self._ok(res):
            yield event.plain_result(f"随机语音查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        audios = self._first_list(data, ("audios", "items", "list", "data"))
        if not audios:
            yield event.plain_result("没有找到符合条件的语音。")
            return
        audio = audios[0]
        download = audio.get("download") if isinstance(audio.get("download"), dict) else {}
        url = download.get("url") or audio.get("url") or audio.get("audioUrl") or audio.get("audio_url")
        url = self.client.resolve_url(url)
        if not url or not Comp or not hasattr(Comp, "Record"):
            yield event.plain_result("语音数据缺少可播放地址。")
            return
        character = audio.get("character") if isinstance(audio.get("character"), dict) else {}
        title = character.get("name") or audio.get("fileName") or "三角洲语音"
        yield event.chain_result([Comp.Plain(f"{title}\n"), Comp.Record.fromURL(url)])

    async def _music(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        if arg:
            res = await self.client.shushu_music_list({"keyword": arg, "page": "1", "limit": "1"})
        else:
            res = await self.client.shushu_music({"count": "1"})
        if not self._ok(res):
            yield event.plain_result(f"鼠鼠音乐查询失败: {self._message_of(res)}")
            return
        songs = self._first_list(self._data(res, {}), ("songs", "musics", "items", "list", "data"))
        if not songs:
            suffix = f"：{arg}" if arg else ""
            yield event.plain_result(f"未找到鼠鼠音乐{suffix}")
            return
        yield await self._music_result(event, songs[0])

    async def _music_list(self, event: AstrMessageEvent, page: str) -> AsyncGenerator[Any, None]:
        async for result in self._music_list_query(event, {"page": page, "limit": "20"}, "鼠鼠音乐排行榜"):
            yield result

    async def _music_playlist(self, event: AstrMessageEvent, keyword: str) -> AsyncGenerator[Any, None]:
        keyword = keyword.strip()
        if not keyword:
            yield event.plain_result("请指定歌单名称、ID 或艺术家。")
            return
        params = {"page": "1", "limit": "20"}
        if keyword.isdigit():
            params["playlistId"] = keyword
            async for result in self._music_list_query(event, params, f"鼠鼠歌单 {keyword}"):
                yield result
            return

        all_res = await self.client.shushu_music_list({"page": "1", "limit": "2000"})
        if not self._ok(all_res):
            yield event.plain_result(f"鼠鼠歌单 {keyword}查询失败: {self._message_of(all_res)}")
            return
        all_songs = [
            song
            for song in self._first_list(self._data(all_res, {}), ("songs", "musics", "items", "list", "data"))
            if isinstance(song, dict)
        ]
        exact = [song for song in all_songs if str(song.get("playlistName") or "").casefold() == keyword.casefold()]
        matched = exact or [
            song for song in all_songs if keyword.casefold() in str(song.get("playlistName") or "").casefold()
        ]
        if matched:
            page_songs = matched[:20]
            response = {
                "code": 0,
                "data": {"songs": page_songs, "total": len(matched), "page": 1, "limit": 20},
            }
            title = str(page_songs[0].get("playlistName") or f"鼠鼠歌单 {keyword}")
            async for result in self._music_list_query(event, params, title, response=response):
                yield result
            return

        params["artist"] = keyword
        async for result in self._music_list_query(event, params, f"{keyword} 的歌曲"):
            yield result

    async def _music_list_query(
        self,
        event: AstrMessageEvent,
        params: Dict[str, Any],
        title: str,
        response: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Any, None]:
        res = response if response is not None else await self.client.shushu_music_list(params)
        if not self._ok(res):
            yield event.plain_result(f"{title}查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        songs = [
            song
            for song in self._first_list(data, ("songs", "musics", "items", "list", "data"))
            if isinstance(song, dict)
        ]
        if not songs:
            yield event.plain_result(f"{title}暂无歌曲。")
            return
        user_key = self._user_identifier(event)
        self._music_lists[user_key] = {"created_at": dt.datetime.now().timestamp(), "songs": songs}
        music_list = []
        for index, song in enumerate(songs, 1):
            metadata = song.get("metadata") if isinstance(song.get("metadata"), dict) else {}
            music_list.append({
                "index": index,
                "name": song.get("title") or song.get("fileName") or "未知歌曲",
                "artist": song.get("artist") or "未知艺术家",
                "cover": song.get("cover") or metadata.get("cover", ""),
                "playlist": song.get("playlistName") or song.get("playlist") or "",
                "hot": song.get("hot") or metadata.get("hot") or "",
            })
        total = int(self._num(data.get("total") or len(songs)))
        page = str(data.get("page") or params.get("page") or "1")
        render_data = {
            "listTitle": title,
            "subtitle": f"第 {page} 页",
            "totalCount": total,
            "musicList": music_list,
        }
        text = "\n".join(
            [f"【{title}】第 {page} 页，共 {total} 首"]
            + [f"{item['index']}. {item['name']} - {item['artist']}" for item in music_list]
            + ["发送 点歌 <序号> 播放本页歌曲。"]
        )
        async for r in self._render_or_text(event, "Template/musicList/musicList.html", render_data, text):
            yield r

    async def _music_select(self, event: AstrMessageEvent, index: int) -> AsyncGenerator[Any, None]:
        memory = self._music_lists.get(self._user_identifier(event))
        if not memory or dt.datetime.now().timestamp() - self._num(memory.get("created_at")) > 600:
            yield event.plain_result("音乐列表已失效，请先发送 鼠鼠音乐列表。")
            return
        songs = memory.get("songs") or []
        if index < 1 or index > len(songs):
            yield event.plain_result(f"序号超出范围，请输入 1-{len(songs)}。")
            return
        yield await self._music_result(event, songs[index - 1])

    async def _music_replay(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        memory = self._music_last.get(self._user_identifier(event))
        if memory and dt.datetime.now().timestamp() - self._num(memory.get("created_at")) <= 600:
            yield await self._music_result(event, memory.get("song") or {})
            return
        async for result in self._music(event, ""):
            yield result

    async def _music_lyrics(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        memory = self._music_last.get(self._user_identifier(event))
        if not memory or dt.datetime.now().timestamp() - self._num(memory.get("created_at")) > 600:
            yield event.plain_result("暂无最近播放的歌曲，请先发送 鼠鼠音乐。")
            return
        song = memory.get("song") or {}
        if not isinstance(song, dict):
            yield event.plain_result("最近播放的歌曲数据异常，请重新播放。")
            return
        metadata = song.get("metadata") if isinstance(song.get("metadata"), dict) else {}
        lyrics = str(song.get("lrc") or metadata.get("lrc") or "").strip()
        title = song.get("title") or song.get("fileName") or "当前歌曲"
        if not lyrics:
            yield event.plain_result(f"歌曲“{title}”暂无歌词。")
            return
        if lyrics.startswith(("http://", "https://", "/")):
            lyrics = await self.client.fetch_text(lyrics)
            if not lyrics:
                yield event.plain_result(f"歌曲“{title}”歌词下载失败，请稍后重试。")
                return
        parsed = self._parse_lrc(lyrics)
        if not parsed:
            yield event.plain_result(f"歌曲“{title}”暂无可显示的歌词。")
            return
        yield event.plain_result(f"【{title} 歌词】\n{parsed}")

    @staticmethod
    def _parse_lrc(content: str) -> str:
        lyrics: List[str] = []
        for raw_line in str(content or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.fullmatch(r"\[(?:ti|ar|al|by|offset):.*\]", line, flags=re.IGNORECASE):
                continue
            text = re.sub(r"(?:\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\])+", "", line).strip()
            if text and not text.startswith("["):
                lyrics.append(text)
        return "\n".join(lyrics)

    async def _music_result(self, event: AstrMessageEvent, song: Dict[str, Any]) -> Any:
        if not isinstance(song, dict):
            return event.plain_result("歌曲数据异常，请重新查询。")
        download = song.get("download") if isinstance(song.get("download"), dict) else {}
        url = song.get("url") or download.get("url") or song.get("audioUrl") or song.get("audio_url")
        url = self.client.resolve_url(url)
        title = song.get("title") or song.get("fileName") or "未知歌曲"
        artist = song.get("artist") or "未知艺术家"
        if not url or not Comp or not hasattr(Comp, "Record"):
            return event.plain_result(f"歌曲“{title}”缺少可播放地址。")
        self._music_last[self._user_identifier(event)] = {
            "created_at": dt.datetime.now().timestamp(),
            "song": song,
        }
        cached_path = await self.music_cache.get_or_download(song, self.client)
        record = Comp.Record.fromFileSystem(cached_path) if cached_path else Comp.Record.fromURL(url)
        return event.chain_result([Comp.Plain(f"{title} - {artist}\n"), record])

    def _music_cache_status(self) -> str:
        stats = self.music_cache.stats()
        return (
            "【鼠鼠音乐缓存统计】\n"
            f"缓存文件数：{stats['total_files']}\n"
            f"总缓存大小：{stats['total_size_mb']:.2f} MB\n"
            f"元数据记录：{stats['metadata_count']}\n"
            "发送 清理音乐缓存 可清空所有缓存。"
        )

    async def _music_cache_clear(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        if not event.is_admin():
            yield event.plain_result("只有管理员可以清理音乐缓存。")
            return
        stats = self.music_cache.clear()
        yield event.plain_result(
            "音乐缓存已清空。\n"
            f"清理文件：{stats['removed_files']} 个\n"
            f"释放空间：{stats['total_size_mb']:.2f} MB"
        )

    async def _tts_status(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.tts_health()
        if not self._ok(res):
            yield event.plain_result(f"TTS 状态查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        status = str(data.get("tts_service") or "").lower() if isinstance(data, dict) else ""
        if not status:
            yield event.plain_result("TTS 状态查询成功，但后端未返回服务状态。")
            return
        status_text = "可用" if status == "available" else "不可用" if status == "unavailable" else status
        lines = ["【TTS 服务状态】", f"服务：{status_text}"]
        if isinstance(data, dict) and data.get("error"):
            lines.append(f"原因：{data['error']}")
        yield event.plain_result("\n".join(lines))

    async def _tts_presets(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.tts_presets()
        if not self._ok(res):
            yield event.plain_result(f"TTS 角色列表查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        presets = data.get("presets") if isinstance(data, dict) else None
        if not isinstance(presets, dict) or not presets:
            yield event.plain_result("暂无可用的 TTS 角色预设。")
            return
        lines = [f"【TTS 角色列表】共 {len(presets)} 名"]
        for index, (character_id, value) in enumerate(presets.items(), 1):
            item = value if isinstance(value, dict) else {}
            name = item.get("name") or character_id
            emotions = item.get("emotions") if isinstance(item.get("emotions"), dict) else {}
            lines.append(f"{index}. {name}（{character_id}），情感 {len(emotions)} 种")
        lines.append("发送 tts角色详情 <角色ID> 查看详情。")
        yield event.plain_result("\n".join(lines))

    async def _tts_preset(self, event: AstrMessageEvent, character_id: str) -> AsyncGenerator[Any, None]:
        res = await self.client.tts_preset(character_id)
        if not self._ok(res):
            yield event.plain_result(f"TTS 角色详情查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        if not isinstance(data, dict) or not data:
            yield event.plain_result(f"未找到 TTS 角色：{character_id}。")
            return
        name = data.get("name") or character_id
        emotions = data.get("emotions") if isinstance(data.get("emotions"), dict) else {}
        lines = [f"【TTS 角色：{name}】", f"角色 ID：{character_id}"]
        if emotions:
            lines.append("可用情感：")
            for emotion_id, value in emotions.items():
                item = value if isinstance(value, dict) else {}
                lines.append(f"- {item.get('name') or emotion_id}（{emotion_id}）")
        else:
            lines.append("可用情感：默认")
        yield event.plain_result("\n".join(lines))

    async def _tts(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        parts = arg.split()
        if len(parts) < 2:
            yield event.plain_result("用法：tts <角色/预设> [情感] <文本>")
            return
        presets_res = await self.client.tts_presets()
        if not self._ok(presets_res):
            yield event.plain_result(f"TTS 角色列表查询失败: {self._message_of(presets_res)}")
            return
        presets_data = self._data(presets_res, {}) or {}
        presets = presets_data.get("presets") if isinstance(presets_data, dict) else {}
        if not isinstance(presets, dict) or not presets:
            yield event.plain_result("TTS 角色预设为空。")
            return
        preset_text = parts[0]
        character_id = ""
        preset_data: Dict[str, Any] = {}
        for key, value in presets.items():
            item = value if isinstance(value, dict) else {}
            if preset_text in {str(key), str(item.get("name") or "")}:
                character_id = str(key)
                preset_data = item
                break
        if not character_id:
            yield event.plain_result(f"未找到 TTS 角色：{preset_text}。发送 tts角色列表 查看可用角色。")
            return
        emotion = ""
        text_start = 1
        emotions = preset_data.get("emotions") or {}
        if len(parts) >= 3:
            candidates = emotions.items() if isinstance(emotions, dict) else []
            for key, value in candidates:
                item = value if isinstance(value, dict) else {}
                if parts[1] in {str(key), str(item.get("name") or "")}:
                    emotion = str(key)
                    text_start = 2
                    break
        text = " ".join(parts[text_start:]).strip()
        if not text:
            yield event.plain_result("请输入需要合成的文本。")
            return
        max_len = int(self.config.get("tts_max_length", 800) or 800)
        if len(text) > max_len:
            yield event.plain_result(f"TTS 文本过长，最多 {max_len} 字。")
            return
        payload = {"character": character_id, "text": text}
        if emotion:
            payload["emotion"] = emotion
        res = await self.client.tts_synthesize(payload)
        if not self._ok(res):
            yield event.plain_result(f"TTS 合成任务提交失败: {self._message_of(res)}")
            return
        task_data = self._data(res, {}) or {}
        task_id = str(task_data.get("taskId") or "")
        if not task_id:
            yield event.plain_result("TTS 合成任务提交成功，但后端未返回 taskId。")
            return
        position = task_data.get("position")
        queue_text = f"，当前队列位置 {position}" if position else ""
        yield event.plain_result(f"TTS 合成任务已提交{queue_text}，正在处理。")

        timeout = max(5.0, float(self.config.get("tts_poll_timeout", 450) or 450))
        interval = max(0.5, float(self.config.get("tts_poll_interval", 5) or 5))
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            status_res = await self.client.tts_task(task_id)
            if not self._ok(status_res):
                yield event.plain_result(f"TTS 任务状态查询失败: {self._message_of(status_res)}")
                return
            status_data = self._data(status_res, {}) or {}
            status = str(status_data.get("status") or "").lower()
            if status == "completed":
                result = status_data.get("result") if isinstance(status_data.get("result"), dict) else {}
                audio_url = self.client.resolve_url(result.get("audio_url") or result.get("audioUrl") or result.get("url") or "")
                if not audio_url or not Comp or not hasattr(Comp, "Record"):
                    yield event.plain_result("TTS 已完成，但后端未返回可播放的音频地址。")
                    return
                filename = str(result.get("filename") or f"{task_id}.wav")
                self._tts_last[self._user_identifier(event)] = {
                    "created_at": dt.datetime.now().timestamp(),
                    "audio_url": audio_url,
                    "filename": os.path.basename(filename) or f"{task_id}.wav",
                    "text": text,
                    "character": str(preset_data.get("name") or character_id),
                }
                yield event.chain_result([Comp.Plain(f"TTS 合成完成：{preset_data.get('name') or character_id}\n"), Comp.Record.fromURL(audio_url, text=text)])
                return
            if status == "failed":
                yield event.plain_result(f"TTS 合成失败: {status_data.get('error') or '未知错误'}")
                return
            if status not in {"queued", "processing"}:
                yield event.plain_result(f"TTS 返回了未知任务状态：{status or '空'}")
                return
            await asyncio.sleep(interval)
        yield event.plain_result("TTS 合成超时，任务可能仍在后端处理中，请稍后重试。")

    async def _tts_recent(self, event: AstrMessageEvent, as_file: bool) -> AsyncGenerator[Any, None]:
        recent = self._tts_last.get(self._user_identifier(event))
        if not recent:
            yield event.plain_result("暂无最近合成的 TTS 语音，请先发送 tts 命令。")
            return
        if dt.datetime.now().timestamp() - self._num(recent.get("created_at")) > 300:
            self._tts_last.pop(self._user_identifier(event), None)
            yield event.plain_result("最近合成的 TTS 语音已过期，请重新合成。")
            return
        audio_url = str(recent.get("audio_url") or "")
        if not audio_url or not Comp:
            yield event.plain_result("最近的 TTS 记录缺少可用音频地址。")
            return
        if as_file:
            if not hasattr(Comp, "File"):
                yield event.plain_result("当前 AstrBot 版本不支持文件消息。")
                return
            filename = str(recent.get("filename") or "tts.wav")
            yield event.chain_result([Comp.Plain("最近合成的 TTS 文件：\n"), Comp.File(name=filename, url=audio_url)])
            return
        if not hasattr(Comp, "Record"):
            yield event.plain_result("当前 AstrBot 版本不支持语音消息。")
            return
        yield event.chain_result([
            Comp.Plain(f"TTS 重播：{recent.get('character') or '未知角色'}\n"),
            Comp.Record.fromURL(audio_url, text=str(recent.get("text") or "")),
        ])

    async def _calculator_help(self, event: AstrMessageEvent, command: str) -> AsyncGenerator[Any, None]:
        if command in {"伤害计算", "伤害"}:
            yield event.plain_result(
                "【伤害计算器】\n"
                "用法：伤害 <模式> <武器名> <子弹名> <护甲/头盔:护甲> <距离> <射击次数> <部位分配>\n"
                "示例：伤害 烽火 腾龙 dvc12 41:37 50 6 1:2,2:4\n"
                "发送 计算映射表 查看常用别名。"
            )
            return
        if command in {"维修计算", "维修"}:
            yield event.plain_result("【维修计算器】\n用法：修甲 <装备名> <剩余耐久>/<当前上限> <局内|局外>\n示例：修甲 fs 0/100 局内")
            return
        yield event.plain_result("发送 战备 开始交互式战备计算；发送 取消 可随时退出。")

    async def _readiness_session(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        from astrbot.api.util import SessionController, session_waiter

        state: Dict[str, Any] = {"step": "target"}
        yield event.plain_result("【战备计算器】\n请输入目标战备值（正整数），发送 取消 可退出：")

        @session_waiter(timeout=300, record_history_chains=False)
        async def waiter(controller: SessionController, waiter_event: AstrMessageEvent):
            text = self._message(waiter_event).strip()
            command = text.lstrip("/#^").strip()
            if command in {"取消", "取消计算"}:
                await waiter_event.send(waiter_event.plain_result("已取消战备计算。"))
                controller.stop()
                return

            step = state["step"]
            if step == "target":
                try:
                    target = int(command)
                except ValueError:
                    target = 0
                if target <= 0:
                    await waiter_event.send(waiter_event.plain_result("请输入有效的目标战备值（正整数）。"))
                    controller.keep(timeout=300, reset_timeout=True)
                    return
                state["target"] = target
                state["step"] = "chest_option"
                await waiter_event.send(waiter_event.plain_result(
                    f"目标战备值：{target:,}\n是否指定胸挂？\n1. 指定胸挂\n2. 自动选择"
                ))
                controller.keep(timeout=300, reset_timeout=True)
                return

            if step == "chest_option":
                if command == "1":
                    items = self.calculator.readiness_equipment("chest")
                    if not items:
                        await waiter_event.send(waiter_event.plain_result("胸挂数据为空，将自动选择。"))
                        state["step"] = "backpack_option"
                        await waiter_event.send(waiter_event.plain_result("是否指定背包？\n1. 指定背包\n2. 自动选择"))
                    else:
                        state["chest_items"] = items
                        state["step"] = "chest_selection"
                        lines = ["请选择胸挂序号："] + [
                            f"{index}. {item.get('name')}（战备 {int(self._num(item.get('readinessValue'))):,}）"
                            for index, item in enumerate(items, 1)
                        ]
                        await waiter_event.send(waiter_event.plain_result("\n".join(lines)))
                elif command == "2":
                    state["step"] = "backpack_option"
                    await waiter_event.send(waiter_event.plain_result("已选择自动胸挂。\n是否指定背包？\n1. 指定背包\n2. 自动选择"))
                else:
                    await waiter_event.send(waiter_event.plain_result("请输入 1 或 2。"))
                controller.keep(timeout=300, reset_timeout=True)
                return

            if step == "chest_selection":
                items = state.get("chest_items") or []
                try:
                    index = int(command) - 1
                except ValueError:
                    index = -1
                if index < 0 or index >= len(items):
                    await waiter_event.send(waiter_event.plain_result(f"请输入 1-{len(items)} 之间的序号。"))
                    controller.keep(timeout=300, reset_timeout=True)
                    return
                state["chest"] = items[index]
                state["step"] = "backpack_option"
                await waiter_event.send(waiter_event.plain_result(
                    f"已选择胸挂：{items[index].get('name')}\n是否指定背包？\n1. 指定背包\n2. 自动选择"
                ))
                controller.keep(timeout=300, reset_timeout=True)
                return

            if step == "backpack_option":
                if command == "1":
                    items = self.calculator.readiness_equipment("backpack")
                    if not items:
                        state["step"] = "max_price"
                        await waiter_event.send(waiter_event.plain_result("背包数据为空，将自动选择。\n请输入最高单件价格，发送 0 表示不限制："))
                    else:
                        state["backpack_items"] = items
                        state["step"] = "backpack_selection"
                        lines = ["请选择背包序号："] + [
                            f"{index}. {item.get('name')}（战备 {int(self._num(item.get('readinessValue'))):,}）"
                            for index, item in enumerate(items, 1)
                        ]
                        await waiter_event.send(waiter_event.plain_result("\n".join(lines)))
                elif command == "2":
                    state["step"] = "max_price"
                    await waiter_event.send(waiter_event.plain_result("已选择自动背包。\n请输入最高单件价格，发送 0 表示不限制："))
                else:
                    await waiter_event.send(waiter_event.plain_result("请输入 1 或 2。"))
                controller.keep(timeout=300, reset_timeout=True)
                return

            if step == "backpack_selection":
                items = state.get("backpack_items") or []
                try:
                    index = int(command) - 1
                except ValueError:
                    index = -1
                if index < 0 or index >= len(items):
                    await waiter_event.send(waiter_event.plain_result(f"请输入 1-{len(items)} 之间的序号。"))
                    controller.keep(timeout=300, reset_timeout=True)
                    return
                state["backpack"] = items[index]
                state["step"] = "max_price"
                await waiter_event.send(waiter_event.plain_result(
                    f"已选择背包：{items[index].get('name')}\n请输入最高单件价格，发送 0 表示不限制："
                ))
                controller.keep(timeout=300, reset_timeout=True)
                return

            try:
                max_price = int(command)
            except ValueError:
                max_price = -1
            if max_price < 0:
                await waiter_event.send(waiter_event.plain_result("请输入大于等于 0 的价格。"))
                controller.keep(timeout=300, reset_timeout=True)
                return
            await waiter_event.send(waiter_event.plain_result("正在计算最低成本配装，请稍候……"))
            result = await asyncio.to_thread(
                self.calculator.calculate_readiness,
                int(state["target"]),
                state.get("chest"),
                state.get("backpack"),
                max_price or None,
            )
            await waiter_event.send(waiter_event.plain_result(self._readiness_result_text(result)))
            controller.stop()

        try:
            await waiter(event)
        except TimeoutError:
            yield event.plain_result("战备计算会话已超时，请重新发送 战备。")

    @staticmethod
    def _readiness_result_text(result: Dict[str, Any]) -> str:
        if not result.get("success"):
            return f"战备计算失败：{result.get('error') or '未知错误'}"
        combinations = result.get("topCombinations") or []
        if not combinations:
            return "未找到满足条件的装备组合，请降低目标战备值或放宽价格限制。"
        slot_names = {
            "weapon1": "主武器",
            "pistol": "手枪",
            "helmet": "头盔",
            "armor": "护甲",
            "chest": "胸挂",
            "backpack": "背包",
        }
        lines = [
            "【战备计算结果】",
            f"目标战备值：{int(result.get('targetReadiness') or 0):,}",
            f"符合条件组合：{int(result.get('totalCombinations') or 0):,} 个",
        ]
        for index, combination in enumerate(combinations, 1):
            lines.extend([
                "",
                f"方案 {index}：成本 {int(combination.get('totalCost') or 0):,}，战备 {int(combination.get('totalReadiness') or 0):,}",
            ])
            equipment = combination.get("equipment") or {}
            for slot, name in slot_names.items():
                item = equipment.get(slot) or {}
                lines.append(
                    f"{name}：{item.get('name') or '无'}（{int(item.get('marketPrice') or 0):,}/{int(item.get('readinessValue') or 0):,}）"
                )
        return "\n".join(lines)

    async def _quick_repair(self, event: AstrMessageEvent, equipment_name: str, remaining_text: str, current_text: str, mode_text: str) -> AsyncGenerator[Any, None]:
        try:
            remaining = float(remaining_text)
            current = float(current_text)
        except Exception:
            yield event.plain_result("耐久度参数无效，请输入数字。")
            return
        if current <= 0:
            yield event.plain_result("当前上限必须大于 0。")
            return
        equipment = self.calculator.find_equipment(equipment_name)
        if not equipment:
            yield event.plain_result(f"未找到装备：{equipment_name}")
            return
        mode = "inside" if mode_text in {"局内", "inside"} else "outside"
        result = self.calculator.calculate_repair(equipment, current, remaining, mode)
        if not result.get("success"):
            yield event.plain_result(f"维修计算失败: {result.get('error')}")
            return
        lines = ["【维修计算结果】", f"维修模式: {result['mode']}", f"护甲: {result['armor']}"]
        if mode == "inside":
            lines.extend(
                [
                    f"当前上限: {result['currentMax']}",
                    f"剩余耐久: {result['remainingDurability']}",
                    f"维修后上限: {result['repairedMax']}",
                    f"维修损耗: {result['repairLoss']}",
                    "消耗维修点数:",
                ]
            )
            lines.extend(f"- {pkg['name']}: {pkg['consumption']}" for pkg in result.get("repairPackages", []))
        else:
            lines.extend(
                [
                    f"维修等级: {result['repairLevel']}",
                    f"初始上限: {result['initialMax']}",
                    f"当前上限: {result['currentDurability']}",
                    f"剩余耐久: {result['remainingDurability']}",
                    f"维修后上限: {result['finalUpper']}",
                    f"维修损耗: {result['repairLoss']}",
                    f"维修花费: {result['repairCost']}",
                    f"磨损程度: {result['wearPercentage']}%",
                    f"能否出售: {result['marketStatus']}",
                ]
            )
        yield event.plain_result("\n".join(lines))

    async def _quick_damage(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        parts = arg.split()
        if len(parts) < 7:
            yield event.plain_result(
                "指令格式错误。\n"
                "格式：伤害 <模式> <武器名> <子弹名> <护甲/头盔:护甲> <距离> <次数> <部位分配>\n"
                "示例：伤害 烽火 腾龙 dvc12 41:37 50 6 1:2,2:4"
            )
            return
        mode_text, weapon_name, bullet_name, armor_text, distance_text, shots_text, hit_parts_text = parts[:7]
        mode = self.calculator.mode(mode_text)
        if not mode:
            yield event.plain_result("游戏模式错误：烽火支持 sol/烽火/摸金；全面支持 mp/战场/全面。")
            return
        try:
            distance = float(distance_text)
            shots = int(shots_text)
        except Exception:
            yield event.plain_result("距离或射击次数无效。")
            return
        if distance < 0 or shots < 1 or shots > 20:
            yield event.plain_result("距离需为非负数，射击次数需在 1-20 之间。")
            return
        weapon = self.calculator.find_weapon(weapon_name, mode)
        if not weapon:
            yield event.plain_result(f"未找到武器：{weapon_name}")
            return
        bullet = self.calculator.find_bullet(bullet_name, str(weapon.get("caliber") or ""))
        if not bullet:
            yield event.plain_result(f"未找到子弹：{bullet_name}（武器口径 {weapon.get('caliber') or '-'}）")
            return
        helmet, armor, armor_error = self.calculator.parse_armor(armor_text)
        if armor_error:
            yield event.plain_result(armor_error)
            return
        hit_parts, hit_error = self.calculator.parse_hit_parts(hit_parts_text, shots)
        if hit_error:
            yield event.plain_result(hit_error)
            return
        result = self.calculator.calculate_damage(weapon, bullet, helmet, armor, distance, hit_parts or [])
        if not result.get("success"):
            yield event.plain_result(f"伤害计算失败: {result.get('error')}")
            return
        protection = "无护甲"
        if result.get("helmet") != "无" and result.get("armor") != "无":
            protection = f"{result['helmet']} + {result['armor']}"
        elif result.get("helmet") != "无":
            protection = result["helmet"]
        elif result.get("armor") != "无":
            protection = result["armor"]
        lines = [
            "【击杀模拟结果】",
            f"游戏模式: {'烽火地带' if mode == 'sol' else '全面战场'}",
            f"武器: {result['weapon']}",
            f"防护: {protection}",
            f"子弹: {result['bullet']} (穿透等级{result['penetrationLevel']})",
            f"距离: {result['distance']}m",
            f"基础伤害: {result['baseDamage']}",
            f"距离衰减: {result['weaponDecayMultiplier']}",
            "",
            "━━━ 击杀情况 ━━━",
            f"击杀所需: {result['shotsToKill']}发 / {shots}发",
            f"总伤害: {result['totalDamage']}",
            f"护甲伤害: {result['totalArmorDamage']}",
            f"最终生命: {result['finalPlayerHealth']}/100",
            f"最终护甲: {result['finalArmorDurability']}/{result['maxArmorDurability']}" if result["maxArmorDurability"] else "最终护甲: 无",
            f"最终头盔: {result['finalHelmetDurability']}/{result['maxHelmetDurability']}" if result["maxHelmetDurability"] else "最终头盔: 无",
            f"击杀状态: {'已击杀' if result['isKilled'] else '未击杀'}",
            "",
            "━━━ 逐发详情 ━━━",
        ]
        for shot in result.get("shotResults", []):
            protector = ""
            if shot.get("isProtected"):
                name = "头盔" if shot.get("protectorType") == "helmet" else "护甲"
                protector = f"({name}{'击碎' if shot.get('protectorDestroyed') else '保护'})"
            lines.append(f"第{shot['shotNumber']}发: {shot['hitPart']} {shot['damage']} {protector}")
            lines.append(f"  生命: {shot['playerHealthAfter']}/100, 护甲: {shot['armorDurabilityAfter']}, 头盔: {shot['helmetDurabilityAfter']}")
        yield event.plain_result("\n".join(lines))

    async def _object_info(self, keyword: str) -> Optional[Dict[str, Any]]:
        res = await self.client.object_search(keyword, limit="1")
        if self._ok(res):
            rows = self._first_list(self._data(res, {}), ("keywords", "items", "list", "data", "objects"))
            if rows:
                return rows[0]
        local = self.data_mgr.search_local_items(keyword, 1)
        if local:
            return {"objectID": local[0].get("id"), "objectName": local[0].get("name")}
        return None

    async def _object_info_map(self, object_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for object_id in dict.fromkeys(str(x) for x in object_ids if x):
            try:
                res = await self.client.object_search(object_id, limit="1")
                rows = self._first_list(self._data(res, {}), ("keywords", "items", "list", "data", "objects")) if self._ok(res) else []
                if rows:
                    result[object_id] = rows[0]
            except Exception:
                continue
        return result

    async def _uncollected_red_count(self, collected: set) -> int:
        items = await self._uncollected_red_items(collected, 1000)
        return len(items)

    async def _uncollected_red_items(self, collected: set, limit: int) -> List[Dict[str, Any]]:
        try:
            res = await self.client.object_list("props", "collection")
            if not self._ok(res):
                return []
            rows = self._first_list(self._data(res, {}), ("keywords", "items", "list", "data", "objects"))
            missing = []
            for item in rows:
                object_id = str(item.get("objectID") or item.get("objectId") or item.get("id") or "")
                if str(item.get("grade") or "") != "6" or object_id in collected:
                    continue
                missing.append(
                    {
                        "name": item.get("objectName") or item.get("name") or f"物品{object_id}",
                        "objectID": object_id,
                        "price": self.data_mgr.fmt_price(item.get("avgPrice") or item.get("price") or 0),
                        "imageUrl": f"https://playerhub.df.qq.com/playerhub/60004/object/{object_id}.png",
                    }
                )
                if len(missing) >= limit:
                    break
            return missing
        except Exception:
            return []

    def _profile_template(self, event: AstrMessageEvent, personal_info_res: Any) -> Dict[str, Any]:
        raw = self._data(personal_info_res, {}) if isinstance(personal_info_res, dict) else {}
        data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw if isinstance(raw, dict) else {}
        user_data = data.get("userData") or data.get("user_data") or {}
        career = data.get("careerData") or data.get("career_data") or {}
        role = raw.get("roleInfo") or data.get("roleInfo") or raw.get("role_info") or {}
        name = self.data_mgr.decode_text(user_data.get("charac_name") or role.get("charac_name") or role.get("nickname") or self._sender_name(event))
        avatar = self.data_mgr.decode_text(user_data.get("picurl") or role.get("picurl") or "")
        if avatar and avatar.isdigit():
            avatar = f"https://wegame.gtimg.com/g.2001918-r.ea725/helper/df/skin/{avatar}.webp"
        rank = self.data_mgr.get_rank_by_score(career.get("rankpoint") or career.get("rankPoint") or 0, "sol")
        clean_rank = re.sub(r"\s*\(\d+\)", "", rank)
        return {
            "userName": name,
            "userAvatar": avatar,
            "userRank": clean_rank,
            "userRankImage": self.data_mgr.get_rank_image_path(clean_rank, "sol"),
            "userId": event.get_sender_id(),
            "qqAvatarUrl": f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
        }

    @staticmethod
    def _find_nested_dict(data: Any, key: str) -> Dict[str, Any]:
        if isinstance(data, dict):
            value = data.get(key)
            if isinstance(value, dict):
                return value
            for child in data.values():
                found = DeltaForcePlugin._find_nested_dict(child, key)
                if found:
                    return found
        elif isinstance(data, list):
            for child in data:
                found = DeltaForcePlugin._find_nested_dict(child, key)
                if found:
                    return found
        return {}

    @staticmethod
    def _find_nested_list(data: Any, key: str) -> List[Any]:
        if isinstance(data, dict):
            value = data.get(key)
            if isinstance(value, list):
                return value
            for child in data.values():
                found = DeltaForcePlugin._find_nested_list(child, key)
                if found:
                    return found
        elif isinstance(data, list):
            for child in data:
                found = DeltaForcePlugin._find_nested_list(child, key)
                if found:
                    return found
        return []

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _parse_key_values(arg: str) -> Dict[str, Any]:
        params = {}
        for part in str(arg or "").split():
            if "=" in part:
                k, v = part.split("=", 1)
                params[k] = v
            elif ":" in part:
                k, v = part.split(":", 1)
                params[k] = v
        return params

    @staticmethod
    def _ratio(value: Any, divisor: float = 1) -> str:
        try:
            return f"{float(value) / divisor:.2f}"
        except Exception:
            return "-"

    @staticmethod
    def _percent(a: Any, b: Any) -> str:
        try:
            total = float(b or 0)
            if total <= 0:
                return "0%"
            return f"{float(a or 0) / total * 100:.1f}%"
        except Exception:
            return "0%"

    @staticmethod
    def _fmt_time(value: Any) -> str:
        if not value:
            return "未知"
        try:
            ts = int(float(value))
            if ts > 10_000_000_000:
                ts = ts // 1000
            return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(value)

    @staticmethod
    def _fmt_ban_duration(value: Any) -> str:
        try:
            seconds = int(float(value))
        except (TypeError, ValueError):
            return "未知"
        if seconds < 0:
            return "未知"
        if seconds > 365 * 9 * 24 * 3600:
            return "永久"
        return DeltaForcePlugin._fmt_duration(seconds)

    @staticmethod
    def _fmt_duration(value: Any) -> str:
        try:
            seconds = int(float(value))
        except (TypeError, ValueError):
            return "未知"
        if seconds < 0:
            return "未知"
        days, remainder = divmod(seconds, 24 * 3600)
        hours, remainder = divmod(remainder, 3600)
        minutes = remainder // 60
        parts = []
        if days:
            parts.append(f"{days}天")
        if hours:
            parts.append(f"{hours}小时")
        if minutes or not parts:
            parts.append(f"{minutes}分钟")
        return "".join(parts)

    @staticmethod
    def _item_image(item: Dict[str, Any]) -> Dict[str, Any]:
        object_id = item.get("objectID") or item.get("objectId") or item.get("itemId")
        return {
            **item,
            "objectName": item.get("objectName") or item.get("name") or "未知物品",
            "price": f"{float(item.get('price') or 0):,.0f}",
            "imageUrl": item.get("pic") or (f"https://playerhub.df.qq.com/playerhub/60004/object/{object_id}.png" if object_id else ""),
        }

    def _summary_or_error(self, title: str, res: Any) -> str:
        if not self._ok(res):
            return f"{title}失败: {self._message_of(res)}"
        return self._summary_dict(title, self._data(res, {}))

    def _summary_dict(self, title: str, data: Any, limit: int = 24) -> str:
        lines = [f"【{title}】"]
        self._flatten(data, lines, "", limit)
        return "\n".join(lines[: limit + 1])

    def _flatten(self, data: Any, lines: List[str], prefix: str, limit: int):
        if len(lines) > limit:
            return
        if isinstance(data, dict):
            for key, value in data.items():
                if len(lines) > limit:
                    break
                name = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(value, (dict, list)):
                    if prefix:
                        lines.append(f"{name}:")
                    self._flatten(value, lines, name if not prefix else "", limit)
                else:
                    lines.append(f"{name}: {value}")
        elif isinstance(data, list):
            for idx, value in enumerate(data[:10], 1):
                if isinstance(value, dict):
                    label = value.get("name") or value.get("title") or value.get("objectName") or value.get("id") or idx
                    lines.append(f"{idx}. {label}")
                    self._flatten(value, lines, "", limit)
                else:
                    lines.append(f"{idx}. {value}")
        else:
            lines.append(str(data))


def _make_delta_command_handler(command_name: str, index: int):
    async def handler(self: DeltaForcePlugin, event: AstrMessageEvent):
        async for result in self._handle_astr_command(event):
            yield result

    handler.__name__ = f"delta_cmd_{index:02d}"
    handler.__qualname__ = f"DeltaForcePlugin.{handler.__name__}"
    handler.__doc__ = f"三角洲行动命令：{command_name}"
    return handler


def _install_delta_command_handlers():
    for index, (command_name, aliases) in enumerate(DELTA_COMMAND_SPECS, 1):
        method = _make_delta_command_handler(command_name, index)
        decorated = filter.command(command_name, alias=set(aliases) if aliases else None)(method)
        setattr(DeltaForcePlugin, method.__name__, decorated)


_install_delta_command_handlers()
