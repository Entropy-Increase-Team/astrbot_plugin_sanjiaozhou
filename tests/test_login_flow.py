import base64
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


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

    astrbot.api = api
    astrbot.core = core
    sys.modules.update(
        {
            "astrbot": astrbot,
            "astrbot.api": api,
            "astrbot.api.event": event,
            "astrbot.api.star": star,
            "astrbot.api.message_components": components,
            "astrbot.core": core,
        }
    )


PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR.parent))
_install_astrbot_stubs()

from astrbot_plugin_sanjiaozhou.core.client import DeltaForceClient  # noqa: E402
from astrbot_plugin_sanjiaozhou.main import DELTA_COMMAND_SPECS, DeltaForcePlugin  # noqa: E402


PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _Event:
    def get_sender_id(self):
        return "mock-user"

    def get_self_id(self):
        return "mock-bot"

    def plain_result(self, text):
        return {"type": "plain", "text": text}

    def chain_result(self, chain):
        return {"type": "chain", "chain": chain}

    def image_result(self, value):
        return {"type": "image", "value": value}


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
            },
        }

    async def login_status(self, _platform, _token):
        return self.statuses.pop(0)


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


class LoginFlowTests(unittest.IsolatedAsyncioTestCase):
    def _plugin(self, client):
        plugin = object.__new__(DeltaForcePlugin)
        plugin.client = client
        plugin.config = {"login_poll_timeout": 30, "login_poll_interval": 1}
        plugin._oauth_sessions = {}

        async def bind_token(_event, _token, login_type="", quiet=False):
            del login_type, quiet
            if False:
                yield None

        plugin._bind_token = bind_token
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

    def test_command_names_do_not_contain_spaces(self):
        names = [name for name, _aliases in DELTA_COMMAND_SPECS]
        aliases = [alias for _name, values in DELTA_COMMAND_SPECS for alias in values]
        self.assertFalse([value for value in names + aliases if " " in value])
        all_commands = names + aliases
        duplicates = {value for value in all_commands if all_commands.count(value) > 1}
        self.assertFalse(duplicates)
        self.assertIn(("订阅", {"取消订阅", "订阅状态"}), DELTA_COMMAND_SPECS)

    async def test_qr_login_sends_image_and_handles_numeric_status(self):
        plugin = self._plugin(_QrClient())
        with patch("astrbot_plugin_sanjiaozhou.main.asyncio.sleep", new=AsyncMock()):
            results = await _collect(plugin._login(_Event(), "登录"))

        self.assertEqual(results[0]["type"], "chain")
        image = next(item for item in results[0]["chain"] if isinstance(item, _Image))
        self.assertTrue(image.file.startswith("base64://"))
        self.assertNotIn("data:image", results[0]["chain"][0].text)
        self.assertIn("已扫码", results[1]["text"])
        self.assertIn("登录成功", results[2]["text"])

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
        self.assertNotIn(("mock-user", "qq"), plugin._oauth_sessions)

    async def test_oauth_rejects_mismatched_state(self):
        client = _OAuthClient()
        plugin = self._plugin(client)
        await _collect(plugin._oauth_login(_Event(), "qq", ""))
        callback = "https://example.invalid/qccallback.html?code=mock-code&state=other-state"

        results = await _collect(plugin._oauth_login(_Event(), "qq", callback))

        self.assertIn("state 与当前会话不匹配", results[0]["text"])
        self.assertIsNone(client.submit_payload)

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


if __name__ == "__main__":
    unittest.main()
