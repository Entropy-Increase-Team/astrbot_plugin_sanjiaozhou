import asyncio
import datetime as dt
import os
import re
from typing import Any, AsyncGenerator, Dict, Iterable, List, Optional, Tuple

import yaml
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core import AstrBotConfig

try:
    import astrbot.api.message_components as Comp
except Exception:
    Comp = None

from .core.client import DeltaForceClient
from .core.calculator import DeltaCalculator
from .core.data import DeltaDataManager
from .core.render import DeltaRenderer
from .core.user import BindingManager


SOL_ALIASES = {"sol", "烽火", "烽火地带", "摸金"}
MP_ALIASES = {"mp", "tdm", "全面", "全面战场", "战场", "大战场"}
ESCAPE_REASONS = {"1": "撤离成功", "2": "被玩家击杀", "3": "被人机击杀", "10": "撤离失败"}
MP_RESULTS = {"1": "胜利", "2": "失败", "3": "中途退出"}


DELTA_COMMAND_SPECS = [
    ("帮助", {"菜单", "help", "三角洲帮助", "df帮助", "delta帮助"}),
    ("娱乐帮助", {"娱乐菜单"}),
    ("计算帮助", {"计算菜单"}),
    ("登录", {"登陆", "qq登录", "QQ登录", "微信登录", "wx登录", "WX登录", "wegame登录", "WEGAME登录", "wegame微信登录", "微信wegame登录", "qqsafe登录", "QQsafe登录", "安全中心登录", "qq安全中心登录"}),
    ("ck登录", {"ck登陆"}),
    ("qq授权登录", {"QQ授权登录", "qqauth登录", "QQauth登录", "qqoauth登录", "QQoauth登录"}),
    ("微信授权登录", {"wx授权登录", "WX授权登录", "微信auth登录", "wxauth登录", "微信oauth登录", "wxoauth登录"}),
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
    ("tts状态", set()),
    ("tts角色列表", {"tts预设列表", "tts角色", "tts预设"}),
    ("tts角色详情", set()),
    ("tts", set()),
    ("伤害计算", {"伤害", "dmg"}),
    ("战备计算", {"战备"}),
    ("维修计算", {"维修"}),
    ("修甲", {"修理"}),
    ("计算映射表", {"映射表"}),
    ("取消计算", {"取消"}),
    ("ws连接", {"WS连接", "websocket连接", "WebSocket连接", "ws启动", "WS启动", "websocket启动", "WebSocket启动", "ws开启", "WS开启", "websocket开启", "WebSocket开启", "ws断开", "WS断开", "websocket断开", "WebSocket断开", "ws关闭", "WS关闭", "websocket关闭", "WebSocket关闭", "ws停止", "WS停止", "websocket停止", "WebSocket停止", "ws状态", "WS状态", "websocket状态", "WebSocket状态", "wsstatus", "WSstatus", "websocketstatus", "WebSocketstatus"}),
    ("订阅 战绩", {"取消订阅 战绩", "订阅状态 战绩"}),
    ("开启本群订阅推送", {"关闭本群订阅推送", "开启私信订阅推送", "关闭私信订阅推送"}),
    ("广播开启", {"通知开启", "广播启用", "通知启用", "广播订阅", "通知订阅", "广播关闭", "通知关闭", "广播禁用", "通知禁用", "广播取消", "通知取消", "广播状态", "通知状态", "广播设置", "通知设置"}),
    ("开启日报推送", {"关闭日报推送", "开启周报推送", "关闭周报推送", "开启特勤处推送", "关闭特勤处推送", "开启每日密码推送", "关闭每日密码推送"}),
    ("房间列表", {"创建房间", "加入房间", "退出房间", "解散房间", "踢人", "房间信息", "房间地图列表", "房间标签列表"}),
    ("更新", {"强制更新", "插件更新", "更新日志", "update", "update_log"}),
]


@register(
    "sanjiaozhou",
    "bvzrays & Entropy-Increase-Team",
    "三角洲行动 AstrBot 插件",
    "0.4.0",
    "https://github.com/Entropy-Increase-Team/astrbot_plugin_sanjiaozhou",
)
class DeltaForcePlugin(Star):
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
        self.data_mgr = DeltaDataManager(self.plugin_path, data_dir)
        self.calculator = DeltaCalculator(self.data_mgr)
        self.renderer = DeltaRenderer(
            self.resources,
            render_timeout=int(self.config.get("render_timeout", 30000) or 30000),
        )
        self._static_task: Optional[asyncio.Task] = None

    async def initialize(self):
        self._static_task = asyncio.create_task(self.data_mgr.refresh_static(self.client))

    async def terminate(self):
        if self._static_task and not self._static_task.done():
            self._static_task.cancel()
        await self.client.close()
        await self.renderer.close()

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
    def _ok(res: Any) -> bool:
        return DeltaForceClient.ok(res)

    @staticmethod
    def _data(res: Any, default: Any = None) -> Any:
        data = DeltaForceClient.data(res, default)
        if isinstance(data, dict) and "data" in data and len(data) <= 3:
            return data.get("data")
        return data

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

    async def _dispatch(self, event: AstrMessageEvent, msg: str) -> AsyncGenerator[Any, None]:
        body = self._body(msg)
        lowered = body.lower()

        if body in {"帮助", "菜单", "help", "三角洲帮助", "df帮助", "delta帮助"}:
            async for r in self._help(event, "main"):
                yield r
            return
        if body in {"娱乐帮助", "娱乐菜单"}:
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
        if re.fullmatch(r"(网页|web|网站)(登陆|登录)", body):
            yield event.plain_result("三角洲网页授权登录：https://df.shallow.ink/oauth-login\n登录后复制 frameworkToken，再发送 绑定 <token>。")
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
            async for r in self._delete_account(event, int(m.group(1)), delete_remote=body.startswith("删除")):
                yield r
            return
        if re.fullmatch(r"(微信刷新|刷新微信|qq刷新|QQ刷新|刷新qq|刷新QQ)", body):
            async for r in self._refresh_account(event):
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

        if re.fullmatch(r"(每日密码|今日密码)", body):
            async for r in self._daily_keyword(event):
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
            async for r in self._ai_review(event, m.group(2).strip()):
                yield r
            return
        if m := re.fullmatch(r"(ai|AI)评价\s+(\S+)\s+(\S+)(?:\s+(\S+))?", body):
            async for r in self._ai_review(event, f"{m.group(2)} {m.group(3)} {m.group(4) or ''}".strip()):
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
        if re.fullmatch(r"(歌词|鼠鼠歌词|鼠鼠音乐歌词|鼠鼠语音)", body):
            async for r in self._music(event, ""):
                yield r
            return
        if m := re.fullmatch(r"鼠鼠音乐(列表|排行榜)\s*(\d*)", body):
            async for r in self._music_list(event, m.group(2) or "1"):
                yield r
            return
        if m := re.fullmatch(r"鼠鼠歌单\s*(.*)", body):
            async for r in self._music(event, m.group(1).strip()):
                yield r
            return
        if m := re.fullmatch(r"(点歌|听|听歌|播放)\s*(\d+)", body):
            async for r in self._music(event, m.group(2)):
                yield r
            return
        if m := re.fullmatch(r"鼠鼠音乐\s*(.*)", body):
            async for r in self._music(event, m.group(1).strip()):
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
        if m := re.fullmatch(r"tts\s+([\s\S]+)", body):
            async for r in self._tts(event, m.group(1).strip()):
                yield r
            return

        if re.fullmatch(r"(伤害计算|伤害|战备计算|战备|维修计算|维修)", body):
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
            yield event.plain_result("AstrBot 版计算器当前使用直接命令，无需取消会话。")
            return

        if re.fullmatch(r"(ws|WS|websocket|WebSocket)(连接|启动|开启|断开|关闭|停止|状态|status)", body):
            yield event.plain_result("AstrBot 版暂未启用云崽 WebSocket 服务层；REST 查询命令可直接使用。")
            return
        if re.fullmatch(r"(开启|关闭)(日报推送|周报推送|特勤处推送|每日密码推送)", body) or "订阅" in body or "广播" in body:
            yield event.plain_result("该命令在 AstrBot 版已保留入口，定时推送/订阅需要在 AstrBot 任务体系中单独配置。")
            return
        if body.startswith(("房间", "创建房间", "加入房间", "退出房间", "解散房间", "踢人")):
            yield event.plain_result("房间功能依赖云崽专用实时服务，AstrBot 版暂未接入。")
            return
        if body in {"更新", "强制更新", "插件更新", "更新日志", "update", "update_log"}:
            yield event.plain_result("AstrBot 插件请通过插件管理器或 Git 更新；当前版本 0.4.0。")
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
        token = data.get("frameworkToken") or data.get("framework_token") or data.get("token") or ""
        qr = data.get("qr_image") or data.get("qrImage") or data.get("qrcode") or data.get("qr") or data.get("url") or ""
        msg = f"请扫码登录 {platform}，有效期约 180 秒。"
        if qr:
            if Comp and str(qr).startswith(("http://", "https://")):
                yield event.chain_result([Comp.Plain(msg + "\n"), Comp.Image.fromURL(qr)])
            elif Comp and os.path.exists(str(qr)):
                yield event.chain_result([Comp.Plain(msg + "\n"), Comp.Image.fromFileSystem(str(qr))])
            elif str(qr).startswith(("http://", "https://")) or os.path.exists(str(qr)):
                yield event.image_result(qr)
            else:
                yield event.plain_result(msg + f"\n二维码/链接: {qr}")
        else:
            yield event.plain_result(msg + (f"\n临时 token: {token}" if token else ""))
        if not token:
            return
        timeout = int(self.config.get("login_poll_timeout", 180) or 180)
        interval = int(self.config.get("login_poll_interval", 5) or 5)
        end_at = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < end_at:
            await asyncio.sleep(interval)
            status = await self.client.login_status(platform, token)
            data = self._data(status, {}) or {}
            state = str(data.get("status") or data.get("state") or data.get("message") or "").lower()
            new_token = data.get("frameworkToken") or data.get("framework_token") or data.get("token") or token
            if self._ok(status) and any(x in state for x in ("success", "confirmed", "done", "ok", "已登录", "成功")):
                async for r in self._bind_token(event, new_token, login_type=platform, quiet=True):
                    yield r
                yield event.plain_result("登录成功，已绑定为当前账号。")
                return
        yield event.plain_result("登录轮询超时。如已获取 frameworkToken，可发送 绑定 <token> 手动绑定。")

    async def _cookie_login(self, event: AstrMessageEvent, cookie: str) -> AsyncGenerator[Any, None]:
        if not cookie:
            yield event.plain_result("用法：ck登录 <cookie>")
            return
        res = await self.client.login_cookie(cookie)
        if not self._ok(res):
            yield event.plain_result(f"Cookie 登录失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        token = data.get("frameworkToken") or data.get("framework_token") or data.get("token")
        if not token:
            yield event.plain_result("Cookie 登录成功但未返回 frameworkToken。")
            return
        async for r in self._bind_token(event, token, login_type="qq", quiet=True):
            yield r
        yield event.plain_result("Cookie 登录成功，已绑定账号。")

    async def _oauth_login(self, event: AstrMessageEvent, platform: str, extra: str) -> AsyncGenerator[Any, None]:
        pf = "wechat" if platform.lower() in {"微信", "wx"} else "qq"
        res = await self.client.oauth_url(pf, platform_id=self._user_identifier(event), bot_id=self._client_id(event))
        if not self._ok(res):
            yield event.plain_result(f"获取 OAuth 链接失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        url = data.get("auth_url") or data.get("url") or data.get("oauth_url") or str(data)
        yield event.plain_result(f"请打开链接完成 {pf} 授权登录：\n{url}\n完成后如页面返回 token，请发送 绑定 <token>。")

    async def _bind_token(self, event: AstrMessageEvent, token: str, login_type: str = "", quiet: bool = False) -> AsyncGenerator[Any, None]:
        user_identifier = self._user_identifier(event)
        client_id = self._client_id(event)
        api_binding = None
        res = await self.client.create_binding(token, user_identifier, client_id, "bot")
        if self._ok(res):
            data = self._data(res, {}) or {}
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
        await self._fill_binding_info(event, binding)
        if not quiet:
            name = binding.get("nickname") or binding.get("delta_uid") or token[:8]
            extra = "" if self._ok(res) else f"\n后端绑定接口未确认：{self._message_of(res)}\n已先保存到 AstrBot 本地绑定。"
            yield event.plain_result(f"绑定成功：{name}{extra}")

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
        token = token_arg or await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号，请先使用 登录 或 绑定 <token>。")
            return
        res = await self.client.bind_character(token)
        if not self._ok(res):
            yield event.plain_result(f"角色绑定失败: {self._message_of(res)}")
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
            name = item.get("nickname") or item.get("delta_uid") or item.get("framework_token", "")[:8]
            login_type = item.get("login_type") or item.get("token_type") or "unknown"
            uid = item.get("delta_uid") or "-"
            lines.append(f"{mark} {idx}. {name} [{login_type}] UID:{uid}")
        lines.append("\n账号切换 <序号> 切换，解绑 <序号> 删除本地绑定。")
        yield event.plain_result("\n".join(lines))

    async def _switch_account(self, event: AstrMessageEvent, index: int) -> AsyncGenerator[Any, None]:
        binding = await self.bindings.set_primary(event.get_sender_id(), index)
        if not binding:
            yield event.plain_result("序号无效，请发送 账号 查看列表。")
            return
        yield event.plain_result(f"已切换到：{binding.get('nickname') or binding.get('framework_token', '')[:8]}")

    async def _delete_account(self, event: AstrMessageEvent, index: int, delete_remote: bool = False) -> AsyncGenerator[Any, None]:
        binding = await self.bindings.delete_binding(event.get_sender_id(), index)
        if not binding:
            yield event.plain_result("序号无效，请发送 账号 查看列表。")
            return
        if delete_remote and binding.get("binding_id") and not str(binding["binding_id"]).startswith("local-"):
            await self.client.delete_binding(binding["binding_id"], self._user_identifier(event), self._client_id(event))
        yield event.plain_result("已删除该账号绑定。")

    async def _refresh_account(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        binding = await self.bindings.get_primary_binding(event.get_sender_id())
        if not binding:
            yield event.plain_result("您尚未绑定账号。")
            return
        if binding.get("binding_id") and not str(binding["binding_id"]).startswith("local-"):
            res = await self.client.refresh_binding(binding["binding_id"], self._user_identifier(event), self._client_id(event))
            data = self._data(res, {}) or {}
            token = data.get("framework_token") or data.get("frameworkToken")
            if self._ok(res) and token:
                await self.bindings.update_token(event.get_sender_id(), binding["binding_id"], token)
                yield event.plain_result("凭证刷新成功。")
                return
            yield event.plain_result(f"凭证刷新失败: {self._message_of(res)}")
            return
        yield event.plain_result("该账号是本地绑定，缺少后端 binding_id，无法刷新；请重新登录。")

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
        raw = self._data(res, {}) or {}
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
        raw = self._data(res, {}) or {}
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
        raw = self._data(res, {}) or {}
        details = self._extract_mode_details(raw, mode)
        if not details:
            yield event.plain_result("暂未查询到该账号的游戏数据。")
            return
        for mode_name, detail in details:
            render_data = self._build_personal_data(event, mode_name, detail, season)
            text = self._summary_dict(f"{'烽火' if mode_name == 'sol' else '全面'}个人数据", detail)
            async for r in self._render_or_text(event, "Template/personalData/personalData.html", render_data, text, {"viewport_width": 1200, "viewport_height": 1800}):
                yield r

    def _extract_mode_details(self, raw: Any, mode: Optional[str]) -> List[Tuple[str, Dict[str, Any]]]:
        if not isinstance(raw, dict):
            return []
        candidates = []
        if mode == "sol":
            candidates.append(("sol", raw.get("data", {}).get("data", {}).get("solDetail") if isinstance(raw.get("data"), dict) else raw.get("solDetail")))
        elif mode == "mp":
            candidates.append(("mp", raw.get("data", {}).get("data", {}).get("mpDetail") if isinstance(raw.get("data"), dict) else raw.get("mpDetail")))
        else:
            candidates.extend(
                [
                    ("sol", (((raw.get("sol") or {}).get("data") or {}).get("data") or {}).get("solDetail") or raw.get("solDetail")),
                    ("mp", (((raw.get("mp") or {}).get("data") or {}).get("data") or {}).get("mpDetail") or raw.get("mpDetail")),
                ]
            )
        return [(m, d) for m, d in candidates if isinstance(d, dict) and d]

    def _build_personal_data(self, event: AstrMessageEvent, mode: str, detail: Dict[str, Any], season: str) -> Dict[str, Any]:
        base = {
            "nickname": self._sender_name(event),
            "userName": self._sender_name(event),
            "userAvatar": "",
            "qqAvatarUrl": f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
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
            records = self._first_list(self._data(res, []), ("records", "list", "items", "data"))
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
                    "incomeClass": "income-positive" if float(r.get("flowCalGainedPrice") or 0) >= 0 else "income-negative",
                    "killsHtml": f"<span class=\"kill-item kill-player\">玩家 {r.get('KillCount') or 0}</span><span class=\"kill-separator\">/</span><span class=\"kill-item kill-ai\">AI {r.get('KillAICount') or 0}</span>",
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
                }
            )
        return item

    async def _daily(self, event: AstrMessageEvent, arg: str, yesterday: bool) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode, _, _ = self._parse_mode_page(arg)
        day = dt.datetime.now() - dt.timedelta(days=1 if yesterday else 0)
        date_api = day.strftime("%Y%m%d")
        res = await self.client.daily_record(token, mode or "")
        if not self._ok(res):
            yield event.plain_result(f"日报查询失败: {self._message_of(res)}")
            return
        raw = self._data(res, {}) or {}
        data = self._build_daily(event, raw, mode, day.strftime("%Y-%m-%d"), yesterday)
        text = self._summary_dict("昨日收益" if yesterday else "三角洲日报", raw)
        async for r in self._render_or_text(event, "Template/dailyReport/dailyReport.html", data, text, {"viewport_width": 1000, "viewport_height": 900}):
            yield r

    def _build_daily(self, event: AstrMessageEvent, raw: Dict[str, Any], mode: Optional[str], date_str: str, yesterday: bool) -> Dict[str, Any]:
        sol = (((raw.get("sol") or {}).get("data") or {}).get("data") or {}).get("solDetail") or (((raw.get("data") or {}).get("data") or {}).get("solDetail")) or raw.get("solDetail")
        mp = (((raw.get("mp") or {}).get("data") or {}).get("data") or {}).get("mpDetail") or (((raw.get("data") or {}).get("data") or {}).get("mpDetail")) or raw.get("mpDetail")
        data = {
            "type": "profit" if yesterday else "daily",
            "mode": mode or "",
            "userName": self._sender_name(event),
            "userAvatar": "",
            "qqAvatarUrl": f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
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
        raw = self._data(res, {}) or {}
        data = self._build_weekly(event, raw, mode, date or dt.datetime.now().strftime("%Y%m%d"))
        text = self._summary_dict("三角洲周报", raw)
        async for r in self._render_or_text(event, "Template/weeklyReport/weeklyReport.html", data, text, {"viewport_width": 1100, "viewport_height": 1800}):
            yield r

    def _build_weekly(self, event: AstrMessageEvent, raw: Dict[str, Any], mode: Optional[str], date: str) -> Dict[str, Any]:
        sol = (((raw.get("sol") or {}).get("data") or {}).get("data") or {}) or (raw.get("data") or {}).get("data") or raw
        mp = (((raw.get("mp") or {}).get("data") or {}).get("data") or {}) or (raw.get("data") or {}).get("data") or raw
        data = {
            "userName": self._sender_name(event),
            "userAvatar": "",
            "qqAvatarUrl": f"http://q.qlogo.cn/headimg_dl?dst_uin={event.get_sender_id()}&spec=640&img_type=jpg",
            "date": date,
        }
        if mode in (None, "", "sol") and isinstance(sol, dict):
            rank = self.data_mgr.get_rank_by_score(sol.get("Rank_Score") or 0, "sol")
            data["solData"] = {
                **sol,
                "rankName": rank,
                "rankImagePath": self.data_mgr.get_rank_image_path(rank, "sol"),
                "Gained_Price": self.data_mgr.fmt_num(sol.get("Gained_Price") or 0),
                "consume_Price": self.data_mgr.fmt_num(sol.get("consume_Price") or 0),
                "rise_Price": self.data_mgr.fmt_num(sol.get("rise_Price") or 0),
                "gameTime": self.data_mgr.fmt_duration(sol.get("total_Online_Time") or 0),
                "teammates": [],
                "maps": [],
                "operators": [],
                "highPriceItems": [],
            }
        if mode in (None, "", "mp") and isinstance(mp, dict):
            rank = self.data_mgr.get_rank_by_score(mp.get("Rank_Match_Score") or 0, "mp")
            data["mpData"] = {
                **mp,
                "rankName": rank,
                "rankImagePath": self.data_mgr.get_rank_image_path(rank, "mp"),
                "winRate": self._percent(mp.get("win_num"), mp.get("total_num")),
                "hitRate": self._percent(mp.get("Hit_Bullet_Num"), mp.get("Consume_Bullet_Num")),
                "total_score": self.data_mgr.fmt_num(mp.get("total_score") or 0),
                "teammates": [],
                "maps": [],
            }
        return data

    async def _map_stats(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode, _, rest = self._parse_mode_page(arg)
        season = next((x for x in arg.split() if x.isdigit()), "")
        res = await self.client.map_stats(token, mode or "", season, rest)
        if not self._ok(res):
            yield event.plain_result(f"地图统计查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        yield event.plain_result(self._summary_dict("地图统计", data))

    async def _money(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        res = await self.client.money(token)
        yield event.plain_result(self._summary_or_error("货币信息", res))

    async def _flows(self, event: AstrMessageEvent, flow_type: str, page: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        type_map = {"设备": "1", "道具": "2", "货币": "3", "all": ""}
        res = await self.client.flows(token, type_map.get(flow_type, flow_type), page)
        yield event.plain_result(self._summary_or_error("流水记录", res))

    async def _collection(self, event: AstrMessageEvent, kind: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        res = await self.client.collection(token, 2)
        if not self._ok(res):
            yield event.plain_result(f"藏品查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        text = self._summary_dict("藏品资产", data)
        async for r in self._render_or_text(event, "Template/collection/collection.html", {"data": data, "collectionData": data, "filterType": kind}, text, {"viewport_width": 1200, "viewport_height": 1600}):
            yield r

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
            yield event.plain_result(self._summary_dict("健康状态", raw))
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
        yield event.plain_result(self._summary_or_error("封号/违规记录", res))

    async def _place_status(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        res = await self.client.place_status(token)
        yield event.plain_result(self._summary_or_error("特勤处状态", res))

    async def _place_info(self, event: AstrMessageEvent, place: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        res = await self.client.place_info(token, place)
        if not self._ok(res):
            yield event.plain_result(f"特勤处信息查询失败: {self._message_of(res)}")
            return
        data = self._data(res, {}) or {}
        text = self._summary_dict("特勤处信息", data)
        async for r in self._render_or_text(event, "Template/placeInfo/placeInfo.html", {"placeData": data, "data": data}, text, {"viewport_width": 1200, "viewport_height": 1600}):
            yield r

    async def _server_status(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        health, object_health = await asyncio.gather(self.client.health(), self.client.object_health(), return_exceptions=True)
        lines = ["【三角洲 API 状态】"]
        for name, res in (("服务", health), ("游戏数据", object_health)):
            if isinstance(res, Exception):
                lines.append(f"{name}: {res}")
            elif self._ok(res):
                lines.append(f"{name}: 正常")
            else:
                lines.append(f"{name}: {self._message_of(res)}")
        yield event.plain_result("\n".join(lines))

    async def _operator_list(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.operators(detail=False)
        if not self._ok(res):
            yield event.plain_result(f"干员列表查询失败: {self._message_of(res)}")
            return
        rows = self._first_list(self._data(res, []), ("operators", "items", "list", "data"))
        lines = ["【三角洲干员列表】"]
        for item in rows[:50]:
            lines.append(f"{item.get('id') or item.get('operatorId') or '-'} - {item.get('name') or item.get('operatorName') or '-'}")
        yield event.plain_result("\n".join(lines) if rows else self._summary_dict("干员列表", self._data(res, {})))

    async def _operator_info(self, event: AstrMessageEvent, name: str) -> AsyncGenerator[Any, None]:
        res = await self.client.operators(detail=True)
        if not self._ok(res):
            yield event.plain_result(f"干员查询失败: {self._message_of(res)}")
            return
        rows = self._first_list(self._data(res, []), ("operators", "items", "list", "data"))
        target = None
        for item in rows:
            item_name = str(item.get("name") or item.get("operatorName") or "")
            if name == item_name or name in item_name:
                target = item
                break
        if not target:
            yield event.plain_result(f"未找到干员：{name}")
            return
        op_name = target.get("name") or target.get("operatorName") or name
        abilities = target.get("abilities") or target.get("abilityList") or target.get("skills") or []
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
        res = await self.client.object_list(parts[0] if parts else "", parts[1] if len(parts) > 1 else "")
        yield event.plain_result(self._summary_or_error("物品列表", res))

    async def _object_search(self, event: AstrMessageEvent, keyword: str) -> AsyncGenerator[Any, None]:
        res = await self.client.object_search(keyword)
        if self._ok(res):
            yield event.plain_result(self._summary_dict("物品搜索", self._data(res, {})))
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
        yield event.plain_result(self._summary_or_error("当前价格", res))

    async def _price_history(self, event: AstrMessageEvent, keyword: str) -> AsyncGenerator[Any, None]:
        item_id = await self._resolve_item_id(keyword)
        res = await self.client.price_history_v2(item_id)
        if not self._ok(res):
            res = await self.client.object_value_history(item_id)
        yield event.plain_result(self._summary_or_error("价格历史", res))

    async def _material_price(self, event: AstrMessageEvent, item_id: str) -> AsyncGenerator[Any, None]:
        res = await self.client.material_price(item_id)
        yield event.plain_result(self._summary_or_error("材料价格", res))

    async def _profit(self, event: AstrMessageEvent, command: str, arg: str) -> AsyncGenerator[Any, None]:
        params = self._parse_key_values(arg)
        if "历史" in command:
            res = await self.client.profit_history(params)
        elif "排行" in command or "利润榜" in command or "最高" in command:
            res = await self.client.profit_rank(params)
        else:
            res = await self.client.place_profit(params)
        yield event.plain_result(self._summary_or_error(command, res))

    async def _daily_keyword(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.daily_keyword()
        yield event.plain_result(self._summary_or_error("每日密码", res))

    async def _article_list(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.article_list()
        yield event.plain_result(self._summary_or_error("文章列表", res))

    async def _article_detail(self, event: AstrMessageEvent, thread_id: str) -> AsyncGenerator[Any, None]:
        res = await self.client.article_detail(thread_id)
        yield event.plain_result(self._summary_or_error("文章详情", res))

    async def _ai_presets(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.ai_presets()
        yield event.plain_result(self._summary_or_error("AI 预设", res))

    async def _ai_review(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        token = await self._need_token(event)
        if not token:
            yield event.plain_result("您尚未绑定账号。")
            return
        mode, _, rest = self._parse_mode_page(arg)
        res = await self.client.ai_review(token, mode or "sol", rest)
        yield event.plain_result(self._summary_or_error("AI 锐评", res))

    async def _voice_meta(self, event: AstrMessageEvent, command: str) -> AsyncGenerator[Any, None]:
        if command == "语音列表":
            res = await self.client.audio_characters()
        elif command == "标签列表":
            res = await self.client.audio_tags()
        elif command == "语音分类":
            res = await self.client.audio_categories()
        else:
            res = await self.client.audio_stats()
        yield event.plain_result(self._summary_or_error(command, res))

    async def _voice(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        params = self._parse_key_values(arg)
        if arg and not params:
            params = {"keyword": arg}
        res = await self.client.audio_random(params)
        data = self._data(res, {}) or {}
        url = data.get("url") or data.get("audioUrl") or data.get("audio_url")
        if self._ok(res) and url and Comp:
            yield event.chain_result([Comp.Plain("三角洲语音\n"), Comp.Record(file=url, url=url)])
        else:
            yield event.plain_result(self._summary_or_error("随机语音", res))

    async def _music(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        params = {"keyword": arg} if arg else {}
        res = await self.client.shushu_music(params)
        yield event.plain_result(self._summary_or_error("鼠鼠音乐", res))

    async def _music_list(self, event: AstrMessageEvent, page: str) -> AsyncGenerator[Any, None]:
        res = await self.client.shushu_music_list({"page": page})
        data = self._data(res, {}) or {}
        text = self._summary_dict("鼠鼠音乐列表", data)
        async for r in self._render_or_text(event, "Template/musicList/musicList.html", {"data": data, "musicList": self._first_list(data, ('items', 'list', 'songs'))}, text):
            yield r

    async def _tts_status(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.tts_health()
        yield event.plain_result(self._summary_or_error("TTS 状态", res))

    async def _tts_presets(self, event: AstrMessageEvent) -> AsyncGenerator[Any, None]:
        res = await self.client.tts_presets()
        yield event.plain_result(self._summary_or_error("TTS 预设", res))

    async def _tts_preset(self, event: AstrMessageEvent, character_id: str) -> AsyncGenerator[Any, None]:
        res = await self.client.tts_preset(character_id)
        yield event.plain_result(self._summary_or_error("TTS 角色详情", res))

    async def _tts(self, event: AstrMessageEvent, arg: str) -> AsyncGenerator[Any, None]:
        parts = arg.split(maxsplit=2)
        if len(parts) < 3:
            yield event.plain_result("用法：tts <角色/预设> <情感> <文本>")
            return
        preset, emotion, text = parts
        max_len = int(self.config.get("tts_max_length", 800) or 800)
        if len(text) > max_len:
            yield event.plain_result(f"TTS 文本过长，最多 {max_len} 字。")
            return
        res = await self.client.tts_synthesize({"characterId": preset, "emotion": emotion, "text": text})
        yield event.plain_result(self._summary_or_error("TTS 合成", res))

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
        yield event.plain_result("AstrBot 版暂未接入云崽交互式战备会话；当前可用：伤害 ...、修甲 ...、计算映射表。")

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
