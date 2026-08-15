import base64
import datetime as dt
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


class _Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


class _Plain:
    def __init__(self, text: str):
        self.text = text


class _Image:
    def __init__(self, file: str):
        self.file = file

    @staticmethod
    def fromBase64(value: str):
        return _Image(f"base64://{value}")

    @staticmethod
    def fromURL(value: str):
        return _Image(value)

    @staticmethod
    def fromFileSystem(value: str):
        return _Image(f"file:///{value}")


class _Record:
    def __init__(self, file: str, **kwargs):
        self.file = file
        self.text = kwargs.get("text")

    @staticmethod
    def fromURL(value: str, **kwargs):
        return _Record(value, **kwargs)

    @staticmethod
    def fromFileSystem(value: str, **kwargs):
        return _Record(f"file:///{value}", **kwargs)


class _File:
    def __init__(self, name: str, file: str = "", url: str = ""):
        self.name = name
        self.file = file
        self.url = url


class _Filter:
    @staticmethod
    def command(_name, alias=None):
        del alias

        def decorator(handler):
            return handler

        return decorator


class _Star:
    def __init__(self, context=None):
        self.context = context


class _StarTools:
    @staticmethod
    def get_data_dir():
        return Path.cwd()


def _register(*_args, **_kwargs):
    return lambda cls: cls


def _install_astrbot_stubs():
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    event = types.ModuleType("astrbot.api.event")
    star = types.ModuleType("astrbot.api.star")
    core = types.ModuleType("astrbot.core")
    components = types.ModuleType("astrbot.api.message_components")
    util = types.ModuleType("astrbot.api.util")

    api.logger = _Logger()
    event.AstrMessageEvent = object
    event.filter = _Filter
    star.Context = object
    star.Star = _Star
    star.StarTools = _StarTools
    star.register = _register
    core.AstrBotConfig = dict
    components.Plain = _Plain
    components.Image = _Image
    components.Record = _Record
    components.File = _File
    util.SessionController = object
    util.session_waiter = lambda *_args, **_kwargs: lambda handler: handler

    astrbot.api = api
    astrbot.core = core
    sys.modules.update(
        {
            "astrbot": astrbot,
            "astrbot.api": api,
            "astrbot.api.event": event,
            "astrbot.api.star": star,
            "astrbot.api.message_components": components,
            "astrbot.api.util": util,
            "astrbot.core": core,
        }
    )


PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR.parent))
_install_astrbot_stubs()

from astrbot_plugin_sanjiaozhou.core.client import DeltaForceClient  # noqa: E402
from astrbot_plugin_sanjiaozhou.core.media_cache import MusicCache  # noqa: E402
from astrbot_plugin_sanjiaozhou.main import (  # noqa: E402
    DELTA_COMMAND_SPECS,
    DeltaForcePlugin,
)

PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _Event:
    def get_sender_id(self):
        return "mock-user"

    def get_self_id(self):
        return "mock-bot"

    def is_admin(self):
        return True

    def plain_result(self, text):
        return {"type": "plain", "text": text}

    def chain_result(self, chain):
        return {"type": "chain", "chain": chain}

    def image_result(self, value):
        return {"type": "image", "value": value}


class _RecallEvent(_Event):
    def __init__(self, delete_error=None):
        self.bot = SimpleNamespace(
            delete_msg=AsyncMock(side_effect=delete_error)
        )
        self.message_obj = SimpleNamespace(message_id="12345")

    def get_platform_name(self):
        return "aiocqhttp"


async def _collect(generator):
    return [item async for item in generator]


class _QrClient:
    def __init__(self):
        self.statuses = [
            {"code": 0, "data": {"code": 2, "status": "scanned", "msg": "已扫码"}},
            {"code": 0, "data": {"code": 0, "status": "done", "msg": "登录成功"}},
        ]

    async def login_qr(self, _platform):
        return {
            "code": 0,
            "data": {
                "frameworkToken": "mock-session-token",
                "qr_image": f"data:image/png;base64,{PNG_BASE64}",
                "expire": int(dt.datetime.now().timestamp() * 1000) + 120_000,
            },
        }

    async def login_status(self, _platform, _token):
        return self.statuses.pop(0)

    async def bind_character(self, _token):
        return {"code": 0, "data": {"success": True}}


class _OAuthClient:
    def __init__(self):
        self.submit_payload = None

    async def oauth_url(self, _platform, platform_id="", bot_id=""):
        del platform_id, bot_id
        return {
            "code": 0,
            "data": {
                "frameworkToken": "mock-state",
                "loginUrl": "https://example.invalid/authorize?state=mock-state",
                "state": "mock-state",
                "expire": 4_102_444_800_000,
            },
        }

    async def oauth_submit(self, _platform, payload):
        self.submit_payload = payload
        return {"code": 0, "data": {"frameworkToken": "mock-final-token"}}

    async def bind_character(self, _token):
        return {"code": 0, "data": {"success": True}}


class _WebAuthorizationClient:
    def __init__(self, final_status=None):
        self.created_payload = None
        self.statuses = [
            {"code": 0, "data": {"status": "pending"}},
            final_status
            or {
                "code": 0,
                "data": {
                    "status": "used",
                    "framework_token": "mock-web-token",
                    "binding_info": {"token_type": "qq"},
                },
            },
        ]

    async def create_authorization_request(self, client_id, client_name, platform_id):
        self.created_payload = (client_id, client_name, platform_id)
        return {
            "code": 0,
            "data": {
                "request_id": "req_0123456789abcdef",
                "auth_url": "/authorize?request_id=req_0123456789abcdef",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        }

    async def authorization_request_status(self, _request_id):
        return self.statuses.pop(0)

    @staticmethod
    def resolve_url(value):
        return f"https://api.example.invalid{value}"

    async def bind_character(self, _token):
        return {"code": 0, "data": {"success": True}}


class _Response:
    status_code = 503
    reason_phrase = "Service Unavailable"
    text = ""

    @staticmethod
    def json():
        return {"code": 503, "message": "服务暂不可用", "data": None}


class _RequestClient:
    def __init__(self):
        self.calls = 0

    async def request(self, *_args, **_kwargs):
        self.calls += 1
        return _Response()


class _EntertainmentClient:
    def __init__(self):
        self.tts_payload = None
        self.tts_statuses = [
            {"code": 0, "data": {"status": "queued"}},
            {
                "code": 0,
                "data": {
                    "status": "completed",
                    "result": {"audio_url": "/api/v1/df/tts/audio/mock.wav?token=mock"},
                },
            },
        ]
        self.songs = [
            {
                "songId": 101,
                "title": "测试歌曲",
                "artist": "测试歌手",
                "url": "https://media.example.invalid/song.mp3",
                "lrc": "第一句\n第二句",
                "playlistName": "测试歌单",
                "hot": "99",
            }
        ]
        self.fetched_urls = []

    @staticmethod
    def resolve_url(value):
        if str(value).startswith("/"):
            return f"https://api.example.invalid{value}"
        return value

    async def audio_random(self, params):
        self.audio_params = params
        return {
            "code": 0,
            "data": {
                "audios": [
                    {
                        "fileName": "mock.wav",
                        "character": {"name": "麦晓雯"},
                        "download": {"url": "https://media.example.invalid/voice.wav"},
                    }
                ]
            },
        }

    async def shushu_music(self, params):
        self.music_params = params
        return {"code": 0, "data": {"songs": self.songs, "count": 1}}

    async def shushu_music_list(self, params):
        self.music_list_params = params
        return {"code": 0, "data": {"songs": self.songs, "total": 1, "page": 1, "limit": 20}}

    async def fetch_text(self, url):
        self.fetched_urls.append(url)
        return "[ti:测试歌曲]\n[00:01.20]远程第一句\n[00:02.30]远程第二句"

    async def tts_presets(self):
        return {
            "code": 0,
            "data": {
                "presets": {
                    "mai": {
                        "name": "麦晓雯",
                        "emotions": {"happy": {"name": "开心"}},
                    }
                }
            },
        }

    async def tts_synthesize(self, payload):
        self.tts_payload = payload
        return {"code": 0, "data": {"taskId": "mock-task", "position": 1}}

    async def tts_task(self, task_id):
        self.tts_task_id = task_id
        return self.tts_statuses.pop(0)


class _NoopMusicCache:
    async def get_or_download(self, _song, _client):
        return None

    def stats(self):
        return {"total_files": 2, "total_size": 3 * 1024 * 1024, "total_size_mb": 3.0, "metadata_count": 2}

    def clear(self):
        return {"total_files": 2, "total_size": 3 * 1024 * 1024, "total_size_mb": 3.0, "metadata_count": 2, "removed_files": 2}


class _BinaryClient:
    def resolve_url(self, value):
        return str(value)

    async def fetch_binary(self, _url, max_bytes):
        return b"ID3" + b"fixture" * min(max_bytes, 10)


class _WaiterEvent(_Event):
    def __init__(self, message, sent):
        self.message_str = message
        self.sent = sent

    def get_message_str(self):
        return self.message_str

    async def send(self, result):
        self.sent.append(result)


class _SessionController:
    def __init__(self):
        self.stopped = False

    def keep(self, timeout=0, reset_timeout=False):
        del timeout, reset_timeout

    def stop(self):
        self.stopped = True


class LoginFlowTests(unittest.IsolatedAsyncioTestCase):
    def _plugin(self, client):
        plugin = object.__new__(DeltaForcePlugin)
        plugin.client = client
        plugin.config = {
            "enable_image_render": False,
            "login_poll_timeout": 30,
            "login_poll_interval": 1,
            "tts_poll_timeout": 30,
            "tts_poll_interval": 1,
        }
        plugin._oauth_sessions = {}
        plugin._music_lists = {}
        plugin._music_last = {}
        plugin._tts_last = {}
        plugin.music_cache = _NoopMusicCache()

        plugin._save_binding = AsyncMock(
            return_value=(
                {"framework_token": "fixture-token", "nickname": "测试账号"},
                True,
                "",
            )
        )
        return plugin

    def test_image_base64_supports_three_backend_formats(self):
        self.assertEqual(
            DeltaForcePlugin._image_base64(f"data:image/png;base64,{PNG_BASE64}"),
            PNG_BASE64,
        )
        self.assertEqual(
            DeltaForcePlugin._image_base64(f"base64://{PNG_BASE64}"),
            PNG_BASE64,
        )
        self.assertEqual(DeltaForcePlugin._image_base64(PNG_BASE64), PNG_BASE64)

    def test_image_base64_rejects_invalid_image(self):
        invalid = base64.b64encode(b"not an image").decode() * 20
        with self.assertRaisesRegex(ValueError, "图片"):
            DeltaForcePlugin._image_base64(invalid)

    def test_login_expiry_supports_iso_seconds_and_milliseconds(self):
        expected = 1_700_000_000_000
        self.assertEqual(DeltaForcePlugin._expiry_millis(1_700_000_000), expected)
        self.assertEqual(DeltaForcePlugin._expiry_millis(expected), expected)
        self.assertEqual(
            DeltaForcePlugin._expiry_millis("2023-11-14T22:13:20Z"), expected
        )

    def test_login_remaining_seconds_handles_future_expired_and_fallback_values(self):
        now_millis = 1_700_000_000_000
        self.assertEqual(
            DeltaForcePlugin._remaining_login_seconds(
                now_millis + 120_001, 180, now_millis
            ),
            121,
        )
        self.assertEqual(
            DeltaForcePlugin._remaining_login_seconds(now_millis - 1, 180, now_millis),
            0,
        )
        self.assertEqual(
            DeltaForcePlugin._remaining_login_seconds(None, 45, now_millis), 45
        )
        self.assertEqual(
            DeltaForcePlugin._remaining_login_seconds("非法时间", 45, now_millis), 45
        )

    def test_command_names_do_not_contain_spaces(self):
        names = [name for name, _aliases in DELTA_COMMAND_SPECS]
        aliases = [alias for _name, values in DELTA_COMMAND_SPECS for alias in values]
        self.assertFalse([value for value in names + aliases if " " in value])
        all_commands = names + aliases
        duplicates = {value for value in all_commands if all_commands.count(value) > 1}
        self.assertFalse(duplicates)
        self.assertIn(("订阅", {"取消订阅", "订阅状态"}), DELTA_COMMAND_SPECS)
        self.assertIn(("活动日历", {"活动", "活动列表"}), DELTA_COMMAND_SPECS)
        self.assertIn(("我的改枪码", {"我的改枪方案"}), DELTA_COMMAND_SPECS)
        self.assertIn(("改枪码评论", {"改枪方案评论"}), DELTA_COMMAND_SPECS)
        self.assertIn(("评论改枪码", {"评论改枪方案"}), DELTA_COMMAND_SPECS)
        self.assertIn(
            ("编辑改枪评论", {"编辑改枪方案评论"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(
            ("删除改枪评论", {"删除改枪方案评论"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(("复制改枪码", {"复制改枪方案"}), DELTA_COMMAND_SPECS)
        self.assertIn(
            ("改枪收藏夹列表", {"改枪方案收藏夹列表"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(
            ("改枪收藏夹详情", {"改枪方案收藏夹详情"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(
            ("我的改枪收藏夹", {"我的改枪方案收藏夹"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(
            ("创建改枪收藏夹", {"创建改枪方案收藏夹"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(
            ("更新改枪收藏夹", {"更新改枪方案收藏夹"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(
            ("删除改枪收藏夹", {"删除改枪方案收藏夹"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(
            ("添加改枪收藏夹", {"添加改枪方案收藏夹"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(
            ("移除改枪收藏夹", {"移除改枪方案收藏夹"}),
            DELTA_COMMAND_SPECS,
        )
        self.assertIn(("改枪方案复审", {"改枪码复审"}), DELTA_COMMAND_SPECS)
        self.assertIn(
            (
                "微信安全中心授权登录",
                {"gamesafe授权登录", "gamesafeoauth登录", "微信安全中心oauth登录"},
            ),
            DELTA_COMMAND_SPECS,
        )

    def test_yunzai_literal_command_aliases_are_registered(self):
        command_aliases = {
            name: {name, *aliases} for name, aliases in DELTA_COMMAND_SPECS
        }
        expected = {
            "帮助": {"帮助", "菜单", "功能"},
            "娱乐帮助": {"娱乐帮助", "娱乐菜单", "娱乐功能"},
            "登录": {
                f"{prefix}{suffix}"
                for prefix in (
                    "",
                    "qq",
                    "QQ",
                    "微信",
                    "wx",
                    "WX",
                    "wegame",
                    "WEGAME",
                    "wegame微信",
                    "微信wegame",
                    "qqsafe",
                    "QQsafe",
                    "安全中心",
                    "qq安全中心",
                )
                for suffix in ("登陆", "登录")
            },
            "qq授权登录": {
                f"{prefix}{method}{suffix}"
                for prefix in ("qq", "QQ")
                for method in ("授权", "auth", "oauth")
                for suffix in ("登陆", "登录")
            },
            "微信授权登录": {
                f"{prefix}{method}{suffix}"
                for prefix in ("微信", "wx", "WX")
                for method in ("授权", "auth", "oauth")
                for suffix in ("登陆", "登录")
            },
            "微信安全中心授权登录": {
                "微信安全中心授权登录",
                "gamesafe授权登录",
                "gamesafeoauth登录",
                "微信安全中心oauth登录",
            },
            "更新": {
                "更新",
                "强制更新",
                "插件更新",
                "插件强制更新",
                "更新日志",
                "插件更新日志",
                "update",
            },
        }

        for command_name, aliases in expected.items():
            self.assertTrue(aliases <= command_aliases[command_name])

    async def test_yunzai_literal_aliases_dispatch_to_expected_handlers(self):
        plugin = object.__new__(DeltaForcePlugin)
        calls = []

        async def help_stub(_event, kind):
            calls.append(("help", kind))
            yield kind

        async def login_stub(_event, command):
            calls.append(("login", command))
            yield command

        async def oauth_stub(_event, platform, callback):
            calls.append(("oauth", platform, callback))
            yield platform

        async def update_log_stub(_event):
            calls.append(("update_log",))
            yield "update_log"

        async def update_stub(_event, force=False):
            calls.append(("update", force))
            yield "update"

        plugin._help = help_stub
        plugin._login = login_stub
        plugin._oauth_login = oauth_stub
        plugin._update_log = update_log_stub
        plugin._update_plugin = update_stub

        cases = (
            ("功能", ("help", "main")),
            ("娱乐功能", ("help", "entertainment")),
            ("qq登陆", ("login", "qq登陆")),
            ("WXoauth登陆 callback", ("oauth", "WX", "callback")),
            ("gamesafeoauth登录 callback", ("oauth", "gamesafe", "callback")),
            ("插件更新日志", ("update_log",)),
            ("插件强制更新", ("update", True)),
        )
        for command, expected_call in cases:
            await _collect(plugin._dispatch(_Event(), command))
            self.assertEqual(calls[-1], expected_call)

    async def test_qr_login_sends_image_and_handles_numeric_status(self):
        plugin = self._plugin(_QrClient())
        with patch("astrbot_plugin_sanjiaozhou.main.asyncio.sleep", new=AsyncMock()):
            results = await _collect(plugin._login(_Event(), "登录"))

        self.assertEqual(results[0]["type"], "chain")
        image = next(item for item in results[0]["chain"] if hasattr(item, "file"))
        self.assertTrue(image.file.startswith("base64://"))
        self.assertNotIn("data:image", results[0]["chain"][0].text)
        self.assertIn("有效期约 120 秒", results[0]["chain"][0].text)
        self.assertIn("已扫码", results[1]["text"])
        self.assertIn("账号和游戏角色均已绑定", results[2]["text"])

    async def test_qr_login_rejects_already_expired_image(self):
        client = SimpleNamespace(
            login_qr=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "frameworkToken": "fixture-token",
                        "qr_image": f"data:image/png;base64,{PNG_BASE64}",
                        "expire": 1,
                    },
                }
            ),
            login_status=AsyncMock(),
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._login(_Event(), "登录"))

        self.assertIn("生成后已过期", results[0]["text"])
        client.login_status.assert_not_awaited()

    async def test_oauth_gets_login_url_and_stores_session(self):
        plugin = self._plugin(_OAuthClient())
        results = await _collect(plugin._oauth_login(_Event(), "qq", ""))

        self.assertIn("https://example.invalid/authorize", results[0]["text"])
        self.assertNotIn("frameworkToken", results[0]["text"])
        self.assertEqual(plugin._oauth_sessions[("mock-user", "qq")]["state"], "mock-state")

    async def test_oauth_submits_callback_url_and_binds(self):
        client = _OAuthClient()
        plugin = self._plugin(client)
        await _collect(plugin._oauth_login(_Event(), "qq", ""))
        callback = "https://example.invalid/qccallback.html?code=mock-code&state=mock-state"

        results = await _collect(plugin._oauth_login(_Event(), "qq", callback))

        self.assertEqual(client.submit_payload["callbackUrl"], callback)
        self.assertEqual(client.submit_payload["frameworkToken"], "mock-state")
        self.assertIn("账号和游戏角色均已绑定", results[-1]["text"])
        self.assertIn("手动撤回", results[-1]["text"])
        self.assertNotIn(("mock-user", "qq"), plugin._oauth_sessions)

    async def test_gamesafe_oauth_uses_dedicated_session_and_skips_character_binding(self):
        client = _OAuthClient()
        plugin = self._plugin(client)
        started = await _collect(plugin._oauth_login(_Event(), "gamesafe", ""))
        callback = "https://wx.gamesafe.qq.com/do_offlin?code=mock-code&state=mock-state"

        completed = await _collect(plugin._oauth_login(_Event(), "gamesafe", callback))

        self.assertIn("微信安全中心授权登录", started[0]["text"])
        self.assertEqual(client.submit_payload["callbackUrl"], callback)
        self.assertIn("已绑定为当前账号", completed[-1]["text"])
        self.assertNotIn("游戏角色", completed[-1]["text"])
        self.assertEqual(
            plugin._save_binding.await_args.args[1:],
            ("mock-final-token", "gamesafe"),
        )
        self.assertNotIn(("mock-user", "gamesafe"), plugin._oauth_sessions)

    async def test_oauth_recalls_sensitive_callback_on_aiocqhttp(self):
        client = _OAuthClient()
        plugin = self._plugin(client)
        event = _RecallEvent()
        await _collect(plugin._oauth_login(event, "qq", ""))
        callback = "https://example.invalid/qccallback.html?code=mock-code&state=mock-state"

        results = await _collect(plugin._oauth_login(event, "qq", callback))

        event.bot.delete_msg.assert_awaited_once_with(message_id=12345)
        self.assertNotIn("手动撤回", results[-1]["text"])
        self.assertIn("账号和游戏角色均已绑定", results[-1]["text"])

    async def test_oauth_recall_failure_does_not_block_binding(self):
        client = _OAuthClient()
        plugin = self._plugin(client)
        event = _RecallEvent(RuntimeError("协议端拒绝撤回"))
        await _collect(plugin._oauth_login(event, "微信", ""))
        callback = "https://example.invalid/callback?code=mock-code&state=mock-state"

        results = await _collect(plugin._oauth_login(event, "微信", callback))

        event.bot.delete_msg.assert_awaited_once_with(message_id=12345)
        self.assertIn("账号和游戏角色均已绑定", results[-1]["text"])
        self.assertIn("手动撤回", results[-1]["text"])

    async def test_oauth_recalls_malformed_callback_before_rejecting_it(self):
        plugin = self._plugin(_OAuthClient())
        event = _RecallEvent()

        results = await _collect(
            plugin._oauth_login(
                event,
                "qq",
                "https://example.invalid/qccallback.html?code=incomplete",
            )
        )

        event.bot.delete_msg.assert_awaited_once_with(message_id=12345)
        self.assertIn("回调 URL 无效", results[0]["text"])
        self.assertNotIn("incomplete", results[0]["text"])

    async def test_cookie_login_recalls_sensitive_message_before_request(self):
        cookie = "fixture-cookie-secret"
        client = SimpleNamespace(
            login_cookie=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {"frameworkToken": "fixture-final-token"},
                }
            ),
            bind_character=AsyncMock(return_value={"code": 0, "data": {}}),
        )
        plugin = self._plugin(client)
        event = _RecallEvent()

        results = await _collect(plugin._cookie_login(event, cookie))

        event.bot.delete_msg.assert_awaited_once_with(message_id=12345)
        client.login_cookie.assert_awaited_once_with(cookie)
        self.assertIn("账号和游戏角色均已绑定", results[-1]["text"])
        self.assertNotIn("手动撤回", results[-1]["text"])
        self.assertNotIn(cookie, str(results))

    async def test_cookie_login_recall_failure_warns_and_redacts_response(self):
        cookie = "fixture-cookie-secret"
        client = SimpleNamespace(
            login_cookie=AsyncMock(
                return_value={
                    "code": 401,
                    "message": f"Cookie {cookie} 已失效",
                    "data": None,
                }
            )
        )
        plugin = self._plugin(client)
        event = _RecallEvent(RuntimeError("协议端拒绝撤回"))

        with patch("astrbot_plugin_sanjiaozhou.main.logger") as mocked_logger:
            results = await _collect(plugin._cookie_login(event, cookie))

        self.assertIn("请立即手动撤回", results[0]["text"])
        self.assertIn("[已隐藏]", results[-1]["text"])
        self.assertNotIn(cookie, str(results))
        self.assertNotIn(cookie, str(mocked_logger.mock_calls))
        client.login_cookie.assert_awaited_once_with(cookie)

    async def test_manual_binding_recalls_sensitive_message(self):
        token = "fixture-framework-token-secret"
        plugin = self._plugin(SimpleNamespace())
        event = _RecallEvent()

        results = await _collect(plugin._bind_token(event, token))

        event.bot.delete_msg.assert_awaited_once_with(message_id=12345)
        plugin._save_binding.assert_awaited_once_with(event, token, "")
        self.assertEqual(results[-1]["text"], "绑定成功：测试账号")
        self.assertNotIn(token, str(results))

    async def test_manual_binding_non_aiocqhttp_warns_and_redacts_response(self):
        token = "fixture-framework-token-secret"
        plugin = self._plugin(SimpleNamespace())
        plugin._save_binding = AsyncMock(
            return_value=(
                {"framework_token": token, "nickname": "", "delta_uid": ""},
                False,
                f"远端拒绝凭证 {token}",
            )
        )

        results = await _collect(plugin._bind_token(_Event(), token))

        self.assertIn("请立即手动撤回", results[0]["text"])
        self.assertIn("[已隐藏]", results[-1]["text"])
        self.assertIn("未命名账号", results[-1]["text"])
        self.assertNotIn(token, str(results))

    async def test_oauth_rejects_mismatched_state(self):
        client = _OAuthClient()
        plugin = self._plugin(client)
        await _collect(plugin._oauth_login(_Event(), "qq", ""))
        callback = "https://example.invalid/qccallback.html?code=mock-code&state=other-state"

        results = await _collect(plugin._oauth_login(_Event(), "qq", callback))

        self.assertIn("state 与当前会话不匹配", results[0]["text"])
        self.assertIsNone(client.submit_payload)

    async def test_web_login_creates_authorization_and_binds_approved_account(self):
        client = _WebAuthorizationClient()
        plugin = self._plugin(client)
        with patch("astrbot_plugin_sanjiaozhou.main.asyncio.sleep", new=AsyncMock()):
            results = await _collect(plugin._web_login(_Event()))

        self.assertEqual(
            client.created_payload,
            ("mock-bot", "AstrBot 三角洲行动", "qq_mock-user"),
        )
        self.assertIn(
            "https://api.example.invalid/authorize?request_id=req_0123456789abcdef",
            results[0]["text"],
        )
        self.assertNotIn("mock-web-token", results[0]["text"])
        self.assertIn("账号和游戏角色均已绑定", results[-1]["text"])
        plugin._save_binding.assert_awaited_once()
        self.assertEqual(
            plugin._save_binding.await_args.args[1:], ("mock-web-token", "qq")
        )

    async def test_web_login_handles_rejected_expired_and_consumed_results(self):
        cases = [
            ({"code": 0, "data": {"status": "rejected"}}, "已拒绝"),
            ({"code": 0, "data": {"status": "expired"}}, "已过期"),
            ({"code": 0, "data": {"status": "used"}}, "未返回凭证"),
        ]
        for final_status, expected in cases:
            with self.subTest(status=final_status["data"]["status"]):
                plugin = self._plugin(_WebAuthorizationClient(final_status))
                with patch(
                    "astrbot_plugin_sanjiaozhou.main.asyncio.sleep", new=AsyncMock()
                ):
                    results = await _collect(plugin._web_login(_Event()))
                self.assertIn(expected, results[-1]["text"])
                plugin._save_binding.assert_not_awaited()

    async def test_web_login_handles_create_and_status_errors(self):
        client = _WebAuthorizationClient()
        client.create_authorization_request = AsyncMock(
            return_value={"code": 403, "message": "授权功能不可用"}
        )
        plugin = self._plugin(client)
        create_failed = await _collect(plugin._web_login(_Event()))
        self.assertIn("授权功能不可用", create_failed[0]["text"])

        client = _WebAuthorizationClient()
        client.statuses = [
            {"code": 503, "message": "状态服务异常"},
            {"code": 503, "message": "状态服务异常"},
            {"code": 503, "message": "状态服务异常"},
        ]
        plugin = self._plugin(client)
        with patch("astrbot_plugin_sanjiaozhou.main.asyncio.sleep", new=AsyncMock()):
            status_failed = await _collect(plugin._web_login(_Event()))
        self.assertIn("状态服务异常", status_failed[-1]["text"])

    async def test_client_uses_authoritative_web_authorization_routes(self):
        client = object.__new__(DeltaForceClient)
        client.post = AsyncMock(return_value={"code": 0})
        client.get = AsyncMock(return_value={"code": 0})

        await client.create_authorization_request(
            "mock-bot", "AstrBot 三角洲行动", "qq_mock-user"
        )
        await client.authorization_request_status("req_mock/path")

        client.post.assert_awaited_once_with(
            "/api/v1/authorization/requests",
            json_data={
                "client_id": "mock-bot",
                "client_name": "AstrBot 三角洲行动",
                "client_type": "bot",
                "platform_id": "qq_mock-user",
                "scopes": ["user_info", "binding_info", "game_data"],
            },
        )
        client.get.assert_awaited_once_with(
            "/api/v1/authorization/requests/req_mock%2Fpath/status"
        )

    async def test_login_completion_reports_remote_and_role_binding_failures(self):
        client = SimpleNamespace(
            bind_character=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"success": True}},
                    {"code": 400, "message": "角色尚未创建 fixture-token"},
                ]
            )
        )
        plugin = self._plugin(client)
        plugin._save_binding.side_effect = [
            ({"framework_token": "fixture-token"}, False, "绑定服务暂不可用 fixture-token"),
            ({"framework_token": "fixture-token"}, True, ""),
        ]

        remote_failed = await plugin._finish_login(_Event(), "fixture-token", "qq", "扫码登录")
        role_failed = await plugin._finish_login(_Event(), "fixture-token", "qq", "扫码登录")

        self.assertIn("后端账号绑定未确认", remote_failed)
        self.assertIn("凭证已保存到 AstrBot 本地", remote_failed)
        self.assertNotIn("账号已绑定", remote_failed)
        self.assertIn("自动绑定游戏角色失败", role_failed)
        self.assertIn("角色尚未创建", role_failed)
        self.assertNotIn("fixture-token", remote_failed)
        self.assertNotIn("fixture-token", role_failed)

    async def test_non_idempotent_post_does_not_retry(self):
        client = object.__new__(DeltaForceClient)
        client.api_key = "test-api-key"
        client.client = _RequestClient()
        client._base_urls = lambda: ["https://first.invalid", "https://second.invalid"]

        result = await client.request("POST", "/api/v1/login/qq/oauth", json_data={})

        self.assertEqual(result["code"], 503)
        self.assertEqual(client.client.calls, 1)

    def test_auto_mode_deduplicates_same_api_address(self):
        client = object.__new__(DeltaForceClient)
        client.api_mode = "auto"
        client.api_base_url = ""
        self.assertEqual(client._base_urls(), ["https://delta-test-api.shallow.ink"])

    def test_client_resolves_relative_resource_and_uses_current_tts_parameter(self):
        client = object.__new__(DeltaForceClient)
        client.api_mode = "custom"
        client.api_base_url = "https://api.example.invalid/base"
        self.assertEqual(
            client.resolve_url("/api/v1/df/tts/audio/mock.wav"),
            "https://api.example.invalid/api/v1/df/tts/audio/mock.wav",
        )

    async def test_tts_preset_uses_character_query_parameter(self):
        client = object.__new__(DeltaForceClient)
        client.get = AsyncMock(return_value={"code": 0})

        await client.tts_preset("mai")

        client.get.assert_awaited_once_with(
            "/api/v1/df/tts/preset",
            params={"character": "mai"},
            require_key=False,
        )

    async def test_client_uses_authoritative_voice_metadata_and_tts_routes(self):
        client = object.__new__(DeltaForceClient)
        client.get = AsyncMock(return_value={"code": 0})

        await client.audio_categories()
        await client.audio_characters()
        await client.audio_stats()
        await client.audio_tags()
        await client.tts_health()
        await client.tts_presets()

        self.assertEqual(
            [item.args[0] for item in client.get.await_args_list],
            [
                "/api/v1/df/audio/categories",
                "/api/v1/df/audio/characters",
                "/api/v1/df/audio/stats",
                "/api/v1/df/audio/tags",
                "/api/v1/df/tts/health",
                "/api/v1/df/tts/presets",
            ],
        )
        self.assertTrue(all(item.kwargs["require_key"] is False for item in client.get.await_args_list))

    async def test_client_uses_authoritative_account_and_role_routes(self):
        client = object.__new__(DeltaForceClient)
        client.get = AsyncMock(return_value={"code": 0})
        client.delete = AsyncMock(return_value={"code": 0})
        client.post = AsyncMock(return_value={"code": 0})

        await client.bind_character("fixture-token")
        self.assertEqual(client.get.await_args.args[0], "/api/v1/df/person/bind")
        self.assertEqual(client.get.await_args.kwargs["params"], {"method": "bind"})
        self.assertEqual(client.get.await_args.kwargs["framework_token"], "fixture-token")

        await client.login_refresh("qq", "fixture-token")
        self.assertEqual(client.get.await_args.args[0], "/api/v1/login/qq/refresh")
        self.assertEqual(client.get.await_args.kwargs["framework_token"], "fixture-token")

        await client.login_delete("wechat", "fixture-token")
        self.assertEqual(client.delete.await_args.args[0], "/api/v1/login/wechat/token")
        self.assertEqual(client.delete.await_args.kwargs["framework_token"], "fixture-token")

        await client.set_primary_binding("fixture-binding", "qq_mock-user", "mock-bot")
        self.assertEqual(
            client.post.await_args.args[0],
            "/api/v1/user/bindings/fixture-binding/primary",
        )

    async def test_account_switch_syncs_remote_before_local_and_rejects_failure(self):
        class Bindings:
            def __init__(self):
                self.items = [
                    {
                        "binding_id": "fixture-binding",
                        "framework_token": "fixture-token",
                        "nickname": "测试账号",
                        "is_valid": True,
                    }
                ]
                self.primary_calls = []

            async def get_user_bindings(self, _user_id):
                return [dict(item) for item in self.items]

            async def set_primary(self, _user_id, index):
                self.primary_calls.append(index)
                return dict(self.items[index - 1])

        client = SimpleNamespace(
            set_primary_binding=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"message": "主绑定已更新"}},
                    {"code": 500, "message": "后端切换失败", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)
        plugin.config["client_id"] = "mock-bot"
        plugin.bindings = Bindings()

        success = await _collect(plugin._switch_account(_Event(), 1))
        failed = await _collect(plugin._switch_account(_Event(), 1))

        self.assertIn("已切换到：测试账号", success[0]["text"])
        self.assertIn("后端切换失败", failed[0]["text"])
        self.assertEqual(plugin.bindings.primary_calls, [1])
        self.assertEqual(
            client.set_primary_binding.await_args_list[0].args,
            ("fixture-binding", "qq_mock-user", "mock-bot"),
        )

    async def test_account_unbind_and_login_delete_keep_remote_and_local_consistent(self):
        class Bindings:
            def __init__(self, item):
                self.items = [dict(item)]
                self.deleted = 0

            async def get_user_bindings(self, _user_id):
                return [dict(item) for item in self.items]

            async def delete_binding(self, _user_id, index):
                self.deleted += 1
                return self.items.pop(index - 1) if self.items else None

        base = {
            "binding_id": "fixture-binding",
            "framework_token": "fixture-token",
            "login_type": "qq",
        }

        unbind_client = SimpleNamespace(
            delete_binding=AsyncMock(return_value={"code": 0, "data": {}}),
            login_delete=AsyncMock(),
        )
        unbind_plugin = self._plugin(unbind_client)
        unbind_plugin.config["client_id"] = "mock-bot"
        unbind_plugin.bindings = Bindings(base)
        unbound = await _collect(unbind_plugin._delete_account(_Event(), 1, False))

        self.assertIn("账号解绑成功", unbound[0]["text"])
        unbind_client.delete_binding.assert_awaited_once_with(
            "fixture-binding", "qq_mock-user", "mock-bot"
        )
        unbind_client.login_delete.assert_not_awaited()
        self.assertEqual(unbind_plugin.bindings.deleted, 1)

        delete_client = SimpleNamespace(
            login_delete=AsyncMock(return_value={"code": 0, "data": {"success": True}}),
            delete_binding=AsyncMock(return_value={"code": 0, "data": {}}),
        )
        delete_plugin = self._plugin(delete_client)
        delete_plugin.config["client_id"] = "mock-bot"
        delete_plugin.bindings = Bindings(base)
        deleted = await _collect(delete_plugin._delete_account(_Event(), 1, True))

        self.assertIn("登录数据已删除，账号绑定已自动解除", deleted[0]["text"])
        delete_client.login_delete.assert_awaited_once_with("qq", "fixture-token")
        delete_client.delete_binding.assert_not_awaited()
        self.assertEqual(delete_plugin.bindings.deleted, 1)

    async def test_account_remote_failure_does_not_remove_local_binding(self):
        class Bindings:
            def __init__(self):
                self.deleted = 0

            async def get_user_bindings(self, _user_id):
                return [
                    {
                        "binding_id": "fixture-binding",
                        "framework_token": "fixture-token",
                        "login_type": "qq",
                    }
                ]

            async def delete_binding(self, _user_id, _index):
                self.deleted += 1
                return {}

        client = SimpleNamespace(
            delete_binding=AsyncMock(
                return_value={"code": 500, "message": "后端解绑失败", "data": None}
            ),
            login_delete=AsyncMock(),
        )
        plugin = self._plugin(client)
        plugin.config["client_id"] = "mock-bot"
        plugin.bindings = Bindings()

        result = await _collect(plugin._delete_account(_Event(), 1, False))

        self.assertIn("后端解绑失败", result[0]["text"])
        self.assertEqual(plugin.bindings.deleted, 0)

    async def test_account_login_delete_rejects_unsupported_type(self):
        class Bindings:
            async def get_user_bindings(self, _user_id):
                return [
                    {
                        "binding_id": "local-fixture",
                        "framework_token": "fixture-token",
                        "login_type": "wegame",
                    }
                ]

            async def delete_binding(self, _user_id, _index):
                raise AssertionError("不应删除本地绑定")

        client = SimpleNamespace(login_delete=AsyncMock(), delete_binding=AsyncMock())
        plugin = self._plugin(client)
        plugin.bindings = Bindings()

        result = await _collect(plugin._delete_account(_Event(), 1, True))

        self.assertIn("仅支持 QQ、微信和微信安全中心账号", result[0]["text"])
        client.login_delete.assert_not_awaited()

    async def test_account_login_delete_supports_gamesafe(self):
        class Bindings:
            def __init__(self):
                self.deleted = 0

            async def get_user_bindings(self, _user_id):
                return [
                    {
                        "binding_id": "fixture-gamesafe-binding",
                        "framework_token": "fixture-gamesafe-token",
                        "login_type": "gamesafe",
                    }
                ]

            async def delete_binding(self, _user_id, _index):
                self.deleted += 1
                return {"framework_token": "fixture-gamesafe-token"}

        client = SimpleNamespace(
            login_delete=AsyncMock(return_value={"code": 0, "data": {"success": True}}),
            delete_binding=AsyncMock(),
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()

        result = await _collect(plugin._delete_account(_Event(), 1, True))

        self.assertIn("登录数据已删除", result[0]["text"])
        client.login_delete.assert_awaited_once_with(
            "gamesafe", "fixture-gamesafe-token"
        )
        self.assertEqual(plugin.bindings.deleted, 1)

    async def test_gamesafe_token_selection_ignores_primary_game_account(self):
        plugin = self._plugin(SimpleNamespace())
        plugin.bindings = SimpleNamespace(
            get_user_bindings=AsyncMock(
                return_value=[
                    {
                        "framework_token": "fixture-qq-token",
                        "token_type": "qq",
                        "is_primary": True,
                        "is_valid": True,
                    },
                    {
                        "framework_token": "fixture-expired-gamesafe",
                        "token_type": "gamesafe",
                        "is_valid": False,
                    },
                    {
                        "framework_token": "fixture-gamesafe-token",
                        "login_type": "gamesafe",
                        "is_valid": True,
                    },
                ]
            )
        )

        token = await plugin._token_for_type(_Event(), "gamesafe")

        self.assertEqual(token, "fixture-gamesafe-token")

    async def test_gamesafe_binding_skips_game_character_lookup(self):
        client = SimpleNamespace(
            create_binding=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "binding": {
                            "id": "fixture-gamesafe-binding",
                            "framework_token": "fixture-gamesafe-token",
                            "token_type": "gamesafe",
                            "login_type": "gamesafe",
                        }
                    },
                }
            )
        )
        plugin = self._plugin(client)
        del plugin._save_binding
        plugin.config["client_id"] = "mock-bot"
        plugin.bindings = SimpleNamespace(
            upsert_binding=AsyncMock(
                return_value={
                    "binding_id": "fixture-gamesafe-binding",
                    "framework_token": "fixture-gamesafe-token",
                    "token_type": "gamesafe",
                    "login_type": "gamesafe",
                }
            )
        )
        plugin._fill_binding_info = AsyncMock()

        binding, remote_ok, message = await plugin._save_binding(
            _Event(), "fixture-gamesafe-token", "gamesafe"
        )

        self.assertTrue(remote_ok)
        self.assertEqual(message, "")
        self.assertEqual(binding["token_type"], "gamesafe")
        plugin._fill_binding_info.assert_not_awaited()

    async def test_account_refresh_uses_login_route_and_checks_account_type(self):
        class Bindings:
            def __init__(self, login_type="qq"):
                self.login_type = login_type

            async def get_primary_binding(self, _user_id):
                return {
                    "binding_id": "fixture-binding",
                    "framework_token": "fixture-token",
                    "login_type": self.login_type,
                }

        client = SimpleNamespace(
            login_refresh=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"success": True}},
                    {"code": 400, "message": "Cookie 已失效", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()

        success = await _collect(plugin._refresh_account(_Event(), "qq"))
        failed = await _collect(plugin._refresh_account(_Event(), "qq"))
        mismatch = await _collect(plugin._refresh_account(_Event(), "wechat"))

        self.assertIn("QQ登录凭证刷新成功", success[0]["text"])
        self.assertIn("Cookie 已失效", failed[0]["text"])
        self.assertIn("当前主账号类型为 qq", mismatch[0]["text"])
        self.assertEqual(client.login_refresh.await_count, 2)

    async def test_character_binding_success_error_and_missing_account(self):
        client = SimpleNamespace(
            bind_character=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"bindarea": "36"}},
                    {"code": 401, "message": "登录凭证已失效", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)
        plugin._need_token = AsyncMock(return_value=None)

        recall_event = _RecallEvent()
        success = await _collect(plugin._bind_character(recall_event, "fixture-token"))
        error = await _collect(plugin._bind_character(_Event(), "fixture-token"))
        missing = await _collect(plugin._bind_character(_Event(), ""))

        recall_event.bot.delete_msg.assert_awaited_once_with(message_id=12345)
        self.assertIn("角色绑定请求已完成", success[-1]["text"])
        self.assertIn("请立即手动撤回", error[0]["text"])
        self.assertIn("登录凭证已失效", error[-1]["text"])
        self.assertIn("尚未绑定账号", missing[0]["text"])

    async def test_manual_binding_keeps_explicit_local_fallback_on_remote_error(self):
        bindings = SimpleNamespace(
            upsert_binding=AsyncMock(
                side_effect=[
                    {
                        "binding_id": "fixture-binding",
                        "framework_token": "fixture-token",
                        "nickname": "测试账号",
                    },
                    {
                        "binding_id": "local-fixture",
                        "framework_token": "local-token",
                        "nickname": "",
                    },
                ]
            )
        )
        client = SimpleNamespace(
            create_binding=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {
                            "binding": {
                                "id": "fixture-binding",
                                "framework_token": "fixture-token",
                            }
                        },
                    },
                    {"code": 503, "message": "绑定服务暂不可用", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)
        del plugin._save_binding
        plugin.config["client_id"] = "mock-bot"
        plugin.bindings = bindings
        plugin._fill_binding_info = AsyncMock()

        success = await _collect(plugin._bind_token(_Event(), "fixture-token"))
        fallback = await _collect(plugin._bind_token(_Event(), "local-token"))

        self.assertIn("绑定成功：测试账号", success[-1]["text"])
        self.assertIn("已先保存到 AstrBot 本地绑定", fallback[-1]["text"])
        self.assertIn("绑定服务暂不可用", fallback[-1]["text"])
        self.assertEqual(bindings.upsert_binding.await_count, 2)

    async def test_account_list_success_and_empty(self):
        bindings = SimpleNamespace(
            get_user_bindings=AsyncMock(
                side_effect=[
                    [
                        {
                            "framework_token": "fixture-token",
                            "nickname": "测试账号",
                            "login_type": "qq",
                            "delta_uid": "123456",
                            "is_primary": True,
                        }
                    ],
                    [],
                ]
            )
        )
        plugin = self._plugin(SimpleNamespace())
        plugin.bindings = bindings

        success = await _collect(plugin._account_list(_Event()))
        empty = await _collect(plugin._account_list(_Event()))

        self.assertIn("★ 1. 测试账号 [qq] UID:123456", success[0]["text"])
        self.assertIn("尚未绑定任何账号", empty[0]["text"])

    async def test_account_list_does_not_use_token_as_display_name(self):
        token = "fixture-framework-token-secret"
        plugin = self._plugin(SimpleNamespace())
        plugin.bindings = SimpleNamespace(
            get_user_bindings=AsyncMock(
                return_value=[
                    {
                        "framework_token": token,
                        "nickname": "",
                        "delta_uid": "",
                        "login_type": "qq",
                        "is_primary": True,
                    }
                ]
            )
        )

        result = await _collect(plugin._account_list(_Event()))

        self.assertIn("未命名账号", result[0]["text"])
        self.assertNotIn(token, result[0]["text"])
        self.assertNotIn(token[:8], result[0]["text"])

    async def test_qr_login_handles_missing_image_and_api_error(self):
        client = SimpleNamespace(
            login_qr=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"frameworkToken": "fixture-token"}},
                    {"code": 503, "message": "登录服务暂不可用", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        missing = await _collect(plugin._login(_Event(), "登录"))
        error = await _collect(plugin._login(_Event(), "登录"))

        self.assertIn("未返回可用二维码", missing[0]["text"])
        self.assertIn("登录服务暂不可用", error[0]["text"])

    async def test_random_voice_reads_nested_download_url(self):
        client = _EntertainmentClient()
        plugin = self._plugin(client)

        results = await _collect(plugin._voice(_Event(), "麦晓雯"))

        self.assertEqual(client.audio_params, {"character": "麦晓雯"})
        self.assertEqual(results[0]["type"], "chain")
        self.assertEqual(results[0]["chain"][-1].file, "https://media.example.invalid/voice.wav")

    async def test_random_voice_handles_empty_and_error_responses(self):
        client = _EntertainmentClient()
        client.audio_random = AsyncMock(
            side_effect=[
                {"code": 0, "data": {"audios": []}},
                {"code": 500, "message": "语音服务异常"},
            ]
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._voice(_Event(), ""))
        error = await _collect(plugin._voice(_Event(), ""))

        self.assertIn("没有找到", empty[0]["text"])
        self.assertIn("语音服务异常", error[0]["text"])

    async def test_voice_metadata_formats_authoritative_fields(self):
        client = SimpleNamespace(
            audio_characters=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "characters": [
                            {
                                "name": "麦晓雯",
                                "profession": "侦察",
                                "voiceId": "mai",
                                "skins": [{"voiceId": "mai-a", "name": "麦晓雯A"}],
                            }
                        ],
                        "totalCount": 1,
                    },
                }
            ),
            audio_tags=AsyncMock(
                return_value={"code": 0, "data": {"tags": [{"tag": "鼓励", "description": "鼓励队友"}]}}
            ),
            audio_categories=AsyncMock(
                return_value={"code": 0, "data": {"categories": [{"category": "干员语音", "count": 12}]}}
            ),
            audio_stats=AsyncMock(
                return_value={"code": 0, "data": {"totalFiles": 12, "categories": [{"category": "干员语音", "fileCount": 12}]}}
            ),
        )
        plugin = self._plugin(client)

        characters = await _collect(plugin._voice_meta(_Event(), "语音列表"))
        tags = await _collect(plugin._voice_meta(_Event(), "标签列表"))
        categories = await _collect(plugin._voice_meta(_Event(), "语音分类"))
        stats = await _collect(plugin._voice_meta(_Event(), "语音统计"))

        self.assertIn("麦晓雯（侦察）ID: mai", characters[0]["text"])
        self.assertIn("鼓励：鼓励队友", tags[0]["text"])
        self.assertIn("干员语音：12 条", categories[0]["text"])
        self.assertIn("总文件数：12", stats[0]["text"])

    async def test_voice_metadata_handles_empty_and_error_responses(self):
        client = SimpleNamespace(
            audio_characters=AsyncMock(side_effect=[{"code": 0, "data": {"characters": []}}, {"code": 500, "message": "角色服务异常"}]),
            audio_tags=AsyncMock(side_effect=[{"code": 0, "data": {"tags": []}}, {"code": 500, "message": "标签服务异常"}]),
            audio_categories=AsyncMock(side_effect=[{"code": 0, "data": {"categories": []}}, {"code": 500, "message": "分类服务异常"}]),
            audio_stats=AsyncMock(side_effect=[{"code": 0, "data": {"totalFiles": 0, "categories": []}}, {"code": 500, "message": "统计服务异常"}]),
        )
        plugin = self._plugin(client)

        for command, empty_text, error_text in (
            ("语音列表", "暂无语音角色数据", "角色服务异常"),
            ("标签列表", "暂无语音标签数据", "标签服务异常"),
            ("语音分类", "暂无语音分类数据", "分类服务异常"),
            ("语音统计", "暂无音频统计数据", "统计服务异常"),
        ):
            empty = await _collect(plugin._voice_meta(_Event(), command))
            error = await _collect(plugin._voice_meta(_Event(), command))
            self.assertIn(empty_text, empty[0]["text"])
            self.assertIn(error_text, error[0]["text"])

    async def test_music_list_selection_and_lyrics_form_a_closed_loop(self):
        client = _EntertainmentClient()
        plugin = self._plugin(client)

        listing = await _collect(plugin._music_list(_Event(), "1"))
        selected = await _collect(plugin._music_select(_Event(), 1))
        lyrics = await _collect(plugin._music_lyrics(_Event()))

        self.assertIn("测试歌曲", listing[0]["text"])
        self.assertEqual(selected[0]["chain"][-1].file, "https://media.example.invalid/song.mp3")
        self.assertIn("第一句", lyrics[0]["text"])

    async def test_music_playlist_supports_name_and_artist_fallback(self):
        client = _EntertainmentClient()
        plugin = self._plugin(client)

        by_name = await _collect(plugin._music_playlist(_Event(), "测试歌单"))
        self.assertEqual(client.music_list_params, {"page": "1", "limit": "2000"})
        self.assertIn("测试歌曲", by_name[0]["text"])

        by_artist = await _collect(plugin._music_playlist(_Event(), "测试歌手"))
        self.assertEqual(client.music_list_params["artist"], "测试歌手")
        self.assertIn("测试歌曲", by_artist[0]["text"])

    async def test_music_lyrics_downloads_and_parses_lrc_url(self):
        client = _EntertainmentClient()
        client.songs[0]["lrc"] = "https://media.example.invalid/song.lrc"
        client.songs[0]["metadata"] = "异常元数据"
        plugin = self._plugin(client)

        await _collect(plugin._music_list(_Event(), "1"))
        await _collect(plugin._music_select(_Event(), 1))
        lyrics = await _collect(plugin._music_lyrics(_Event()))

        self.assertEqual(client.fetched_urls, ["https://media.example.invalid/song.lrc"])
        self.assertIn("远程第一句", lyrics[0]["text"])
        self.assertNotIn("[00:", lyrics[0]["text"])

    async def test_music_handles_empty_error_and_invalid_metadata(self):
        client = _EntertainmentClient()
        client.shushu_music = AsyncMock(
            side_effect=[
                {"code": 0, "data": {"songs": []}},
                {"code": 500, "message": "音乐服务异常"},
            ]
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._music(_Event(), ""))
        error = await _collect(plugin._music(_Event(), ""))
        client.songs[0]["metadata"] = "异常元数据"
        listing = await _collect(plugin._music_list(_Event(), "1"))

        self.assertIn("未找到", empty[0]["text"])
        self.assertIn("音乐服务异常", error[0]["text"])
        self.assertIn("测试歌曲", listing[0]["text"])

    async def test_music_selection_and_lyrics_handle_expired_or_missing_data(self):
        client = _EntertainmentClient()
        plugin = self._plugin(client)

        expired_selection = await _collect(plugin._music_select(_Event(), 1))
        missing_lyrics = await _collect(plugin._music_lyrics(_Event()))

        plugin._music_lists["qq_mock-user"] = {
            "created_at": __import__("time").time(),
            "songs": client.songs,
        }
        out_of_range = await _collect(plugin._music_select(_Event(), 2))

        plugin._music_last["qq_mock-user"] = {
            "created_at": __import__("time").time(),
            "song": {"title": "无歌词歌曲", "url": "https://media.example.invalid/song.mp3"},
        }
        empty_lyrics = await _collect(plugin._music_lyrics(_Event()))

        plugin._music_last["qq_mock-user"]["song"]["lrc"] = "https://media.example.invalid/missing.lrc"
        client.fetch_text = AsyncMock(return_value="")
        download_error = await _collect(plugin._music_lyrics(_Event()))

        self.assertIn("音乐列表已失效", expired_selection[0]["text"])
        self.assertIn("暂无最近播放", missing_lyrics[0]["text"])
        self.assertIn("序号超出范围", out_of_range[0]["text"])
        self.assertIn("暂无歌词", empty_lyrics[0]["text"])
        self.assertIn("歌词下载失败", download_error[0]["text"])

    async def test_tts_resolves_character_and_polls_until_audio_is_ready(self):
        client = _EntertainmentClient()
        plugin = self._plugin(client)

        with patch("astrbot_plugin_sanjiaozhou.main.asyncio.sleep", new=AsyncMock()):
            results = await _collect(plugin._tts(_Event(), "麦晓雯 开心 测试文本"))

        self.assertEqual(
            client.tts_payload,
            {"character": "mai", "emotion": "happy", "text": "测试文本"},
        )
        self.assertEqual(client.tts_task_id, "mock-task")
        self.assertIn("任务已提交", results[0]["text"])
        self.assertEqual(
            results[-1]["chain"][-1].file,
            "https://api.example.invalid/api/v1/df/tts/audio/mock.wav?token=mock",
        )

    async def test_tts_reports_failed_task_status(self):
        client = _EntertainmentClient()
        client.tts_statuses = [{"code": 0, "data": {"status": "failed", "error": "模型不可用"}}]
        plugin = self._plugin(client)

        results = await _collect(plugin._tts(_Event(), "麦晓雯 测试文本"))

        self.assertIn("任务已提交", results[0]["text"])
        self.assertIn("模型不可用", results[-1]["text"])

    async def test_tts_metadata_formats_success_responses(self):
        client = SimpleNamespace(
            tts_health=AsyncMock(return_value={"code": 0, "data": {"tts_service": "available", "details": {"status": "ok"}}}),
            tts_presets=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {"presets": {"mai": {"name": "麦晓雯", "emotions": {"happy": {"name": "开心"}}}}},
                }
            ),
            tts_preset=AsyncMock(
                return_value={"code": 0, "data": {"name": "麦晓雯", "emotions": {"happy": {"name": "开心"}}}}
            ),
        )
        plugin = self._plugin(client)

        status = await _collect(plugin._tts_status(_Event()))
        presets = await _collect(plugin._tts_presets(_Event()))
        detail = await _collect(plugin._tts_preset(_Event(), "mai"))

        self.assertIn("服务：可用", status[0]["text"])
        self.assertIn("麦晓雯（mai），情感 1 种", presets[0]["text"])
        self.assertIn("开心（happy）", detail[0]["text"])
        client.tts_preset.assert_awaited_once_with("mai")

    async def test_tts_metadata_handles_empty_and_error_responses(self):
        client = SimpleNamespace(
            tts_health=AsyncMock(side_effect=[{"code": 0, "data": {}}, {"code": 500, "message": "状态服务异常"}]),
            tts_presets=AsyncMock(side_effect=[{"code": 0, "data": {"presets": {}}}, {"code": 500, "message": "预设服务异常"}]),
            tts_preset=AsyncMock(side_effect=[{"code": 0, "data": {}}, {"code": 404, "message": "角色不存在"}]),
        )
        plugin = self._plugin(client)

        status_empty = await _collect(plugin._tts_status(_Event()))
        status_error = await _collect(plugin._tts_status(_Event()))
        presets_empty = await _collect(plugin._tts_presets(_Event()))
        presets_error = await _collect(plugin._tts_presets(_Event()))
        detail_empty = await _collect(plugin._tts_preset(_Event(), "mai"))
        detail_error = await _collect(plugin._tts_preset(_Event(), "mai"))

        self.assertIn("未返回服务状态", status_empty[0]["text"])
        self.assertIn("状态服务异常", status_error[0]["text"])
        self.assertIn("暂无可用", presets_empty[0]["text"])
        self.assertIn("预设服务异常", presets_error[0]["text"])
        self.assertIn("未找到 TTS 角色", detail_empty[0]["text"])
        self.assertIn("角色不存在", detail_error[0]["text"])

    async def test_tts_synthesis_handles_empty_presets_and_submit_errors(self):
        client = SimpleNamespace(
            tts_presets=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"presets": {}}},
                    {"code": 500, "message": "预设读取失败"},
                    {"code": 0, "data": {"presets": {"mai": {"name": "麦晓雯"}}}},
                ]
            ),
            tts_synthesize=AsyncMock(return_value={"code": 500, "message": "合成服务异常"}),
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._tts(_Event(), "麦晓雯 测试文本"))
        preset_error = await _collect(plugin._tts(_Event(), "麦晓雯 测试文本"))
        submit_error = await _collect(plugin._tts(_Event(), "麦晓雯 测试文本"))

        self.assertIn("角色预设为空", empty[0]["text"])
        self.assertIn("预设读取失败", preset_error[0]["text"])
        self.assertIn("合成服务异常", submit_error[0]["text"])

    async def test_tts_recent_supports_file_and_voice_components(self):
        client = _EntertainmentClient()
        plugin = self._plugin(client)
        plugin._tts_last["qq_mock-user"] = {
            "created_at": 1_000,
            "audio_url": "https://media.example.invalid/tts.wav?token=mock",
            "filename": "mock.wav",
            "text": "测试文本",
            "character": "麦晓雯",
        }

        with patch("astrbot_plugin_sanjiaozhou.main.dt") as mock_dt:
            mock_dt.datetime.now.return_value.timestamp.return_value = 1_100
            uploaded = await _collect(plugin._tts_recent(_Event(), as_file=True))
            replayed = await _collect(plugin._tts_recent(_Event(), as_file=False))

        self.assertEqual(uploaded[0]["chain"][-1].name, "mock.wav")
        self.assertEqual(uploaded[0]["chain"][-1].url, "https://media.example.invalid/tts.wav?token=mock")
        self.assertEqual(replayed[0]["chain"][-1].file, "https://media.example.invalid/tts.wav?token=mock")

    async def test_music_cache_status_and_admin_clear(self):
        plugin = self._plugin(_EntertainmentClient())
        self.assertIn("3.00 MB", plugin._music_cache_status())

        cleared = await _collect(plugin._music_cache_clear(_Event()))
        self.assertIn("清理文件：2 个", cleared[0]["text"])

    async def test_music_cache_clear_requires_admin(self):
        class NonAdminEvent(_Event):
            def is_admin(self):
                return False

        plugin = self._plugin(_EntertainmentClient())
        plugin.music_cache.clear = Mock()

        result = await _collect(plugin._music_cache_clear(NonAdminEvent()))

        self.assertIn("只有管理员", result[0]["text"])
        plugin.music_cache.clear.assert_not_called()

    async def test_music_cache_persists_stats_and_clears_files(self):
        song = {
            "title": "缓存测试",
            "artist": "测试歌手",
            "download": {"url": "https://media.example.invalid/music.mp3"},
        }
        temporary = PLUGIN_DIR.parents[4] / ".tmp" / "music-cache-test"
        temporary.mkdir(parents=True, exist_ok=True)
        try:
            cache = MusicCache(str(temporary), max_file_bytes=1024 * 1024)
            path = await cache.get_or_download(song, _BinaryClient())
            self.assertTrue(Path(path).is_file())
            self.assertEqual(cache.stats()["total_files"], 1)

            reloaded = MusicCache(str(temporary))
            self.assertEqual(reloaded.stats()["metadata_count"], 1)
            cleared = reloaded.clear()
            self.assertEqual(cleared["removed_files"], 1)
            self.assertFalse(Path(path).exists())
        finally:
            metadata = temporary / "music_cache" / "metadata.json"
            metadata.unlink(missing_ok=True)
            try:
                (temporary / "music_cache").rmdir()
                temporary.rmdir()
            except OSError:
                pass

    async def test_readiness_session_uses_native_waiter_and_returns_result(self):
        sent = []
        inputs = ["500", "2", "2", "0"]

        def fake_session_waiter(*_args, **_kwargs):
            def decorator(handler):
                async def wrapper(_event):
                    controller = _SessionController()
                    for message in inputs:
                        await handler(controller, _WaiterEvent(message, sent))
                        if controller.stopped:
                            break
                return wrapper
            return decorator

        calculator = Mock()
        calculator.calculate_readiness.return_value = {
            "success": True,
            "targetReadiness": 500,
            "totalCombinations": 1,
            "topCombinations": [{
                "totalCost": 480,
                "totalReadiness": 520,
                "equipment": {},
            }],
        }
        plugin = self._plugin(_EntertainmentClient())
        plugin.calculator = calculator
        util = sys.modules["astrbot.api.util"]
        with patch.object(util, "session_waiter", fake_session_waiter), patch.object(
            util, "SessionController", _SessionController
        ):
            initial = await _collect(plugin._readiness_session(_Event()))

        self.assertIn("目标战备值", initial[0]["text"])
        self.assertIn("战备计算结果", sent[-1]["text"])
        calculator.calculate_readiness.assert_called_once_with(500, None, None, None)

    async def test_readiness_session_reports_timeout(self):
        def timeout_waiter(*_args, **_kwargs):
            def decorator(_handler):
                async def wrapper(_event):
                    raise TimeoutError

                return wrapper

            return decorator

        plugin = self._plugin(_EntertainmentClient())
        util = sys.modules["astrbot.api.util"]

        with patch.object(util, "session_waiter", timeout_waiter):
            result = await _collect(plugin._readiness_session(_Event()))

        self.assertIn("目标战备值", result[0]["text"])
        self.assertIn("会话已超时", result[-1]["text"])


if __name__ == "__main__":
    unittest.main()
