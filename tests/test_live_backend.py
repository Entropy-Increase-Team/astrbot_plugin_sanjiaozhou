import asyncio
import base64
import inspect
import io
import json
import logging
import os
import sys
import types
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from PIL import Image as PillowImage

PLUGIN_DIR = Path(__file__).resolve().parents[1]
ASTRBOT_ROOT = PLUGIN_DIR.parents[2]
LIVE_API_KEY = os.environ.get("DELTA_LIVE_API_KEY", "").strip()

if LIVE_API_KEY:
    if "astrbot.api" not in sys.modules:
        astrbot_module = types.ModuleType("astrbot")
        astrbot_api_module = types.ModuleType("astrbot.api")
        astrbot_api_module.logger = logging.getLogger("delta.live_backend")
        astrbot_module.api = astrbot_api_module
        sys.modules.update(
            {
                "astrbot": astrbot_module,
                "astrbot.api": astrbot_api_module,
            }
        )
    sys.path.insert(0, str(ASTRBOT_ROOT))
    sys.path.insert(0, str(PLUGIN_DIR.parent))
    from astrbot_plugin_sanjiaozhou.core.client import DeltaForceClient  # noqa: E402
else:
    DeltaForceClient = None


@unittest.skipUnless(
    LIVE_API_KEY,
    "未设置 DELTA_LIVE_API_KEY，跳过真实后端测试。",
)
class LiveBackendTests(unittest.IsolatedAsyncioTestCase):
    _quiet_logger_names = ("websockets", "httpx", "httpcore", "asyncio")
    _original_logger_levels = {}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._original_logger_levels = {
            name: logging.getLogger(name).level for name in cls._quiet_logger_names
        }
        for name in cls._quiet_logger_names:
            logging.getLogger(name).setLevel(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        for name, level in cls._original_logger_levels.items():
            logging.getLogger(name).setLevel(level)
        super().tearDownClass()

    async def asyncSetUp(self):
        self.client = DeltaForceClient(
            api_key=LIVE_API_KEY,
            api_mode="custom" if os.environ.get("DELTA_LIVE_BASE_URL") else "auto",
            api_base_url=os.environ.get("DELTA_LIVE_BASE_URL", ""),
            timeout=20,
        )

    async def asyncTearDown(self):
        await self.client.close()

    @staticmethod
    def _payload(response):
        payload = DeltaForceClient.data(response, {})
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            nested = payload["data"]
            if any(
                key in nested
                for key in ("frameworkToken", "framework_token", "loginUrl", "qr_image")
            ):
                return nested
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _assert_success(response, action):
        if not DeltaForceClient.ok(response):
            raise AssertionError(f"{action}未返回成功响应。")

    @staticmethod
    def _websocket_response_shape(response):
        payload = response.get("data") if isinstance(response.get("data"), dict) else {}
        fields = ",".join(sorted(str(key) for key in payload)) or "无"
        return (
            f"code={response.get('code')!r}, kind={response.get('kind')!r}, "
            f"type={response.get('type')!r}, data_fields={fields}"
        )

    async def test_live_health_and_public_metadata(self):
        health = await self.client.health()
        maps = await self.client.maps()
        operators = await self.client.operators(detail=False)

        self._assert_success(health, "健康检查")
        self._assert_success(maps, "地图元数据查询")
        self._assert_success(operators, "干员元数据查询")
        self.assertIsInstance(DeltaForceClient.data(health, {}), dict)
        self.assertTrue(DeltaForceClient.data(maps, {}))
        self.assertTrue(DeltaForceClient.data(operators, {}))

    async def test_live_public_and_tool_query_contracts(self):
        cases = [
            ("段位元数据", self.client.rank_score, dict, {"sol", "tdm"}),
            ("健康元数据", self.client.object_health, list, set()),
            (
                "物品列表",
                lambda: self.client.object_list(page="1", limit="1"),
                dict,
                {"list", "total"},
            ),
            (
                "物品搜索",
                lambda: self.client.object_search("金条", page="1", limit="1"),
                dict,
                {"list", "total"},
            ),
            (
                "物品价值列表",
                lambda: self.client.object_value_list({"page": 1, "limit": 1}),
                dict,
                {"list", "total"},
            ),
            (
                "物品价值搜索",
                lambda: self.client.object_value_search("金条"),
                dict,
                {"list", "total"},
            ),
            (
                "材料价格",
                lambda: self.client.material_price(page="1", page_size="1"),
                dict,
                {"materials", "pagination"},
            ),
            ("语音分类", self.client.audio_categories, dict, {"categories"}),
            ("语音角色", self.client.audio_characters, dict, {"characters", "totalCount"}),
            ("语音统计", self.client.audio_stats, dict, {"categories", "totalFiles"}),
            ("语音标签", self.client.audio_tags, dict, {"tags"}),
            ("TTS 健康", self.client.tts_health, dict, {"tts_service"}),
            ("TTS 预设", self.client.tts_presets, dict, {"presets"}),
            ("TTS 队列", self.client.tts_queue, dict, {"processing", "queueLength"}),
            ("每日密码", self.client.daily_keyword, dict, {"list"}),
            ("文章列表", self.client.article_list, dict, {"articles"}),
            ("AI 预设", self.client.ai_presets, dict, {"presets"}),
            (
                "公开改枪方案",
                lambda: self.client.community_solutions({"page": 1, "pageSize": 1}),
                dict,
                {"items", "total"},
            ),
            (
                "旧版改枪方案",
                lambda: self.client.solution_list({"page": 1, "limit": 1}),
                dict,
                {"list", "totalCount"},
            ),
        ]

        for action, request, expected_type, required_fields in cases:
            with self.subTest(action=action):
                response = await request()
                self._assert_success(response, action)
                payload = DeltaForceClient.data(response, None)
                self.assertIsInstance(payload, expected_type, f"{action}响应类型不符合契约。")
                if isinstance(payload, dict):
                    self.assertTrue(
                        required_fields.issubset(payload),
                        f"{action}缺少字段：{','.join(sorted(required_fields - payload.keys()))}",
                    )

    async def test_live_qq_login_bootstrap_and_pending_status(self):
        response = await self.client.login_qr("qq")
        self._assert_success(response, "QQ 扫码初始化")
        payload = self._payload(response)
        framework_token = str(
            payload.get("frameworkToken") or payload.get("framework_token") or ""
        )
        qr_value = str(
            payload.get("qr_image")
            or payload.get("qrImage")
            or payload.get("qrCode")
            or payload.get("qrcode")
            or ""
        )
        self.assertTrue(framework_token, "QQ 扫码初始化未返回临时凭证。")
        self.assertTrue(qr_value, "QQ 扫码初始化未返回二维码。")

        encoded = qr_value.split(",", 1)[1] if qr_value.startswith("data:image/") else qr_value
        if encoded.startswith("base64://"):
            encoded = encoded[len("base64://"):]
        image_bytes = base64.b64decode(encoded, validate=True)
        with PillowImage.open(io.BytesIO(image_bytes)) as image:
            image.verify()

        status_response = await self.client.login_status("qq", framework_token)
        self._assert_success(status_response, "QQ 扫码状态查询")
        status_payload = self._payload(status_response)
        status = str(
            status_payload.get("status")
            or status_payload.get("state")
            or status_payload.get("code")
            or ""
        ).lower()
        self.assertIn(status, {"1", "2", "pending", "scanned"})

    async def test_live_qq_oauth_bootstrap(self):
        response = await self.client.oauth_url("qq")
        self._assert_success(response, "QQ OAuth 初始化")
        payload = self._payload(response)
        login_url = str(
            payload.get("loginUrl")
            or payload.get("login_url")
            or payload.get("auth_url")
            or payload.get("url")
            or ""
        )
        framework_token = str(
            payload.get("frameworkToken") or payload.get("framework_token") or ""
        )
        self.assertTrue(login_url.startswith(("http://", "https://")))
        self.assertTrue(framework_token, "QQ OAuth 初始化未返回临时凭证。")

    async def test_live_existing_binding_query_or_expiry(self):
        framework_token = os.environ.get("DELTA_LIVE_FRAMEWORK_TOKEN", "").strip()
        if not framework_token:
            self.skipTest("未设置 DELTA_LIVE_FRAMEWORK_TOKEN。")

        response = await self.client.personal_info(framework_token)

        if response.get("code") == 401:
            self.assertFalse(DeltaForceClient.ok(response), "失效绑定不应被识别为成功响应。")
            self.assertIsInstance(response.get("message"), str)
            return
        self._assert_success(response, "已绑定账号信息查询")
        self.assertTrue(DeltaForceClient.data(response, {}))

    async def test_live_websocket_subscription_handshake(self):
        client_id = os.environ.get("DELTA_LIVE_CLIENT_ID", "").strip()
        if not client_id:
            self.skipTest("未设置 DELTA_LIVE_CLIENT_ID。")

        import websockets

        base = self.client._base_urls()[0]
        parsed = urlparse(base)
        uri = urlunparse(
            ("wss" if parsed.scheme == "https" else "ws", parsed.netloc, "/ws", "", "", "")
        )
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parameters = inspect.signature(websockets.connect).parameters
        header_argument = (
            "extra_headers"
            if "extra_headers" in parameters and "additional_headers" not in parameters
            else "additional_headers"
        )
        options = {
            "origin": origin,
            "ping_interval": 20,
            "ping_timeout": 20,
            "close_timeout": 5,
            header_argument: {"X-API-Key": self.client.api_key},
        }
        request_id = f"astrbot-live-{uuid.uuid4().hex}"
        request = {
            "id": request_id,
            "type": "record.client.subscribe",
            "kind": "request",
            "data": {"client_id": client_id},
        }

        async with websockets.connect(uri, **options) as connection:
            await connection.send(json.dumps(request, ensure_ascii=False))
            response = None
            for _attempt in range(10):
                raw = await asyncio.wait_for(connection.recv(), timeout=3)
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if isinstance(message, dict) and message.get("id") == request_id:
                    response = message
                    break

        self.assertIsInstance(response, dict, "WebSocket 未返回订阅响应。")
        response_shape = self._websocket_response_shape(response)
        self.assertEqual(
            response.get("kind"),
            "response",
            f"WebSocket 订阅请求被拒绝：{response_shape}",
        )
        self.assertIn(
            response.get("code"),
            {None, 0},
            f"WebSocket 订阅请求被拒绝：{response_shape}",
        )
        payload = response.get("data") if isinstance(response.get("data"), dict) else {}
        self.assertTrue(
            payload.get("subscribed"),
            f"WebSocket 未确认订阅频道：{response_shape}",
        )


if __name__ == "__main__":
    unittest.main()
