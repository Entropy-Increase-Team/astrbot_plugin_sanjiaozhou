import asyncio
import json
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, mock_open, patch
from urllib.parse import unquote

import httpx
import yaml


class _Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


class _Filter:
    @staticmethod
    def command(_name, alias=None):
        del alias

        def decorator(handler):
            return handler

        return decorator


class _Plain:
    def __init__(self, text: str):
        self.text = text


class _MessageChain:
    def __init__(self, chain=None):
        self.chain = list(chain or [])


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
    event.MessageChain = _MessageChain
    event.Plain = _Plain
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

from astrbot_plugin_sanjiaozhou.core.calculator import DeltaCalculator  # noqa: E402
from astrbot_plugin_sanjiaozhou.core.client import DeltaForceClient  # noqa: E402
from astrbot_plugin_sanjiaozhou.core.render import DeltaRenderer  # noqa: E402
from astrbot_plugin_sanjiaozhou.core.subscription import SubscriptionStore  # noqa: E402
from astrbot_plugin_sanjiaozhou.core.version import PLUGIN_VERSION  # noqa: E402
from astrbot_plugin_sanjiaozhou.main import DeltaForcePlugin  # noqa: E402


class _Event:
    unified_msg_origin = "aiocqhttp:GroupMessage:123"

    def get_sender_id(self):
        return "fixture-user"

    def get_group_id(self):
        return "123"

    def is_admin(self):
        return True

    def plain_result(self, text):
        return {"type": "plain", "text": text}

    def image_result(self, path):
        return {"type": "image", "path": path}


class _DataManager:
    @staticmethod
    def fmt_num(value, default="0"):
        try:
            return f"{float(value):,.0f}"
        except (TypeError, ValueError):
            return default

    @staticmethod
    def fmt_price(value):
        return _DataManager.fmt_num(value)

    @staticmethod
    def fmt_duration(value, unit="seconds"):
        del unit
        return f"{int(float(value or 0))}秒"

    @staticmethod
    def get_rank_by_score(_value, mode):
        return "烽火段位" if mode == "sol" else "全面段位"

    @staticmethod
    def get_rank_image_path(_name, mode):
        return f"imgs/rank/{mode}/fixture.webp"

    @staticmethod
    def get_map_name(value):
        return {"100": "零号大坝-常规", "200": "烬区"}.get(str(value), f"地图{value}")

    @staticmethod
    def get_map_image_path(name, mode="sol"):
        return f"imgs/map/{mode}-{name}.png"

    @staticmethod
    def get_operator_name(value):
        return {"10": "红狼", "20": "蜂医"}.get(str(value), f"干员{value}")

    @staticmethod
    def get_operator_image_path(name):
        return f"imgs/operator/{name}.png"

    @staticmethod
    def get_random_background():
        return "imgs/background/bg2-1.webp"

    @staticmethod
    def decode_text(value):
        return unquote(str(value or ""))


class _ReadinessDataManager:
    def __init__(self):
        self.data = {
            "equipment.json": {
                "equipment": {
                    "body_armor": [{"name": "测试甲（全新）", "marketPrice": 100, "readinessValue": 120, "quality": 1}],
                    "helmets": [{"name": "测试盔（全新）", "marketPrice": 50, "readinessValue": 60, "quality": 1}],
                    "chest_rigs": [{"name": "测试胸挂", "marketPrice": 30, "readinessValue": 40, "quality": 1}],
                    "backpacks": [{"name": "测试背包", "marketPrice": 20, "readinessValue": 30, "quality": 1}],
                }
            },
            "armors.json": {
                "armors": {
                    "body_armor": [{"name": "测试甲", "protectionLevel": 1}],
                    "helmets": [{"name": "测试盔", "protectionLevel": 1}],
                }
            },
            "weapons_sol.json": {
                "weapons": {
                    "assault_rifles": [{"name": "测试步枪", "marketPrice": 80, "readinessValue": 100}],
                    "pistols": [{"name": "测试手枪", "marketPrice": 10, "readinessValue": 20}],
                }
            },
        }

    def load_json_data(self, name):
        return self.data.get(name)


async def _collect(generator):
    return [item async for item in generator]


class CoreQueryTests(unittest.IsolatedAsyncioTestCase):
    def _plugin(self, client=None):
        plugin = object.__new__(DeltaForcePlugin)
        plugin.client = client or SimpleNamespace()
        plugin.data_mgr = _DataManager()
        plugin.config = {"enable_image_render": False}
        plugin.renderer = SimpleNamespace(res_path=(PLUGIN_DIR / "resources").resolve())

        async def need_token(_event):
            return "fixture-token"

        async def identity(_event, _token):
            return {
                "userName": "测试玩家",
                "userAvatar": "",
                "qqAvatarUrl": "https://example.invalid/avatar.png",
            }

        plugin._need_token = need_token
        plugin._render_identity = identity
        return plugin

    async def test_help_reports_configuration_read_error(self):
        plugin = self._plugin()
        plugin.plugin_path = str(PLUGIN_DIR)

        with patch("builtins.open", side_effect=OSError("帮助配置不可读")):
            result = await _collect(plugin._help(_Event(), "main"))

        self.assertIn("读取帮助配置失败", result[0]["text"])
        self.assertIn("帮助配置不可读", result[0]["text"])

    async def test_update_commands_use_native_manager_and_report_errors(self):
        manager = SimpleNamespace(
            update_plugin=AsyncMock(side_effect=[None, RuntimeError("远端更新失败")])
        )
        plugin = self._plugin()
        plugin.context = SimpleNamespace(_star_manager=manager)

        success = await _collect(plugin._update_plugin(_Event()))
        failure = await _collect(plugin._update_plugin(_Event(), force=True))

        self.assertIn("正在通过 AstrBot 插件管理器更新", success[0]["text"])
        self.assertIn("更新并重载成功", success[-1]["text"])
        self.assertIn("正在通过 AstrBot 插件管理器强制更新", failure[0]["text"])
        self.assertIn("远端更新失败", failure[-1]["text"])
        self.assertEqual(manager.update_plugin.await_args_list[0].args, ("sanjiaozhou",))

    async def test_update_command_requires_admin_and_native_manager(self):
        class NonAdminEvent(_Event):
            def is_admin(self):
                return False

        manager = SimpleNamespace(update_plugin=AsyncMock())
        plugin = self._plugin()
        plugin.context = SimpleNamespace(_star_manager=manager)

        denied = await _collect(plugin._update_plugin(NonAdminEvent()))
        plugin.context = SimpleNamespace()
        unavailable = await _collect(plugin._update_plugin(_Event()))

        self.assertIn("只有管理员", denied[0]["text"])
        self.assertIn("未提供插件更新管理器", unavailable[0]["text"])
        manager.update_plugin.assert_not_awaited()

    async def test_update_log_handles_success_empty_missing_and_read_errors(self):
        plugin = self._plugin()
        plugin.plugin_path = str(PLUGIN_DIR)

        success = await _collect(plugin._update_log(_Event()))
        with patch("builtins.open", mock_open(read_data="")):
            empty = await _collect(plugin._update_log(_Event()))
        with patch("builtins.open", side_effect=FileNotFoundError):
            missing = await _collect(plugin._update_log(_Event()))
        with patch("builtins.open", side_effect=OSError("读取失败")):
            error = await _collect(plugin._update_log(_Event()))

        self.assertIn("0.4.2", success[0]["text"])
        self.assertIn("暂无内容", empty[0]["text"])
        self.assertIn("未包含更新日志", missing[0]["text"])
        self.assertIn("读取更新日志失败", error[0]["text"])

    async def test_update_log_parses_recent_versions_and_renders_image(self):
        plugin = self._plugin()
        plugin.plugin_path = str(PLUGIN_DIR)
        plugin.config["enable_image_render"] = True
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(return_value="D:/fixture-version.png")
        )

        result = await _collect(plugin._update_log(_Event()))

        self.assertEqual(result[0]["type"], "image")
        render_call = plugin.renderer.render_html.await_args
        self.assertEqual(render_call.args[0], "help/version-info.html")
        self.assertEqual(render_call.args[1]["currentVersion"], PLUGIN_VERSION)
        self.assertEqual(
            [item["version"] for item in render_call.args[1]["changelogs"]],
            ["0.4.3", "0.4.2"],
        )
        self.assertEqual(render_call.args[1]["changelogs"][0]["sections"][0]["title"], "新增")

    async def test_update_log_falls_back_when_rendering_fails(self):
        plugin = self._plugin()
        plugin.plugin_path = str(PLUGIN_DIR)
        plugin.config["enable_image_render"] = True
        plugin.renderer = SimpleNamespace(render_html=AsyncMock(return_value=None))

        result = await _collect(plugin._update_log(_Event()))

        self.assertEqual(result[0]["type"], "plain")
        self.assertIn("0.4.2", result[0]["text"])

    def test_release_version_is_consistent_across_public_files(self):
        metadata = yaml.safe_load((PLUGIN_DIR / "metadata.yaml").read_text(encoding="utf-8"))
        readme = (PLUGIN_DIR / "README.md").read_text(encoding="utf-8")
        changelog = (PLUGIN_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
        client = object.__new__(DeltaForceClient)
        client.api_key = ""

        self.assertEqual(metadata["version"], PLUGIN_VERSION)
        self.assertIn(f"当前版本：`{PLUGIN_VERSION}`", readme)
        self.assertRegex(changelog, rf"(?m)^## \[{re.escape(PLUGIN_VERSION)}\]")
        self.assertEqual(
            client._headers()["User-Agent"],
            f"astrbot-plugin-deltaforce/{PLUGIN_VERSION}",
        )

    async def test_quick_repair_formats_success_and_rejects_invalid_inputs(self):
        calculator = SimpleNamespace(
            find_equipment=Mock(return_value={"name": "测试护甲"}),
            calculate_repair=Mock(
                return_value={
                    "success": True,
                    "mode": "局外维修",
                    "armor": "测试护甲",
                    "repairLevel": 3,
                    "initialMax": 100,
                    "currentDurability": 80,
                    "remainingDurability": 20,
                    "finalUpper": 70,
                    "repairLoss": 10,
                    "repairCost": 1000,
                    "wearPercentage": 30,
                    "marketStatus": "可出售",
                }
            ),
        )
        plugin = self._plugin()
        plugin.calculator = calculator

        success = await _collect(plugin._quick_repair(_Event(), "测试护甲", "20", "80", "局外"))
        invalid_number = await _collect(plugin._quick_repair(_Event(), "测试护甲", "错误", "80", "局外"))
        invalid_max = await _collect(plugin._quick_repair(_Event(), "测试护甲", "20", "0", "局外"))
        calculator.find_equipment.return_value = None
        missing = await _collect(plugin._quick_repair(_Event(), "不存在", "20", "80", "局外"))

        self.assertIn("维修计算结果", success[0]["text"])
        self.assertIn("维修花费: 1000", success[0]["text"])
        self.assertIn("耐久度参数无效", invalid_number[0]["text"])
        self.assertIn("当前上限必须大于 0", invalid_max[0]["text"])
        self.assertIn("未找到装备", missing[0]["text"])

    async def test_quick_damage_formats_success_and_rejects_invalid_inputs(self):
        result = {
            "success": True,
            "helmet": "测试头盔",
            "armor": "测试护甲",
            "weapon": "测试步枪",
            "bullet": "测试子弹",
            "penetrationLevel": 4,
            "distance": 50,
            "baseDamage": 40,
            "weaponDecayMultiplier": 0.9,
            "shotsToKill": 3,
            "totalDamage": 120,
            "totalArmorDamage": 50,
            "finalPlayerHealth": 0,
            "finalArmorDurability": 0,
            "maxArmorDurability": 50,
            "finalHelmetDurability": 10,
            "maxHelmetDurability": 40,
            "isKilled": True,
            "shotResults": [],
        }
        calculator = SimpleNamespace(
            mode=Mock(return_value="sol"),
            find_weapon=Mock(return_value={"name": "测试步枪", "caliber": "5.56"}),
            find_bullet=Mock(return_value={"name": "测试子弹"}),
            parse_armor=Mock(return_value=({"name": "测试头盔"}, {"name": "测试护甲"}, "")),
            parse_hit_parts=Mock(return_value=([{"part": "胸部", "count": 3}], "")),
            calculate_damage=Mock(return_value=result),
        )
        plugin = self._plugin()
        plugin.calculator = calculator

        success = await _collect(plugin._quick_damage(_Event(), "烽火 测试步枪 测试子弹 41:37 50 3 2:3"))
        bad_format = await _collect(plugin._quick_damage(_Event(), "参数不足"))
        calculator.mode.return_value = None
        bad_mode = await _collect(plugin._quick_damage(_Event(), "未知 测试步枪 测试子弹 41:37 50 3 2:3"))

        self.assertIn("击杀模拟结果", success[0]["text"])
        self.assertIn("击杀状态: 已击杀", success[0]["text"])
        self.assertIn("指令格式错误", bad_format[0]["text"])
        self.assertIn("游戏模式错误", bad_mode[0]["text"])

    def test_readiness_result_handles_failure_and_empty_combinations(self):
        self.assertIn(
            "静态数据不足",
            DeltaForcePlugin._readiness_result_text({"success": False, "error": "静态数据不足"}),
        )
        self.assertIn(
            "未找到满足条件",
            DeltaForcePlugin._readiness_result_text({"success": True, "topCombinations": []}),
        )

    async def test_client_uses_authoritative_record_and_map_parameters(self):
        client = object.__new__(DeltaForceClient)
        client.get = AsyncMock(return_value={"code": 0, "data": {}})

        await client.record("fixture-token", "4", "2")
        self.assertEqual(client.get.await_args.args[0], "/api/v1/df/person/record")
        self.assertEqual(client.get.await_args.kwargs["params"]["page"], "2")

        await client.room_info("fixture-token", "fixture-room", "5")
        self.assertEqual(client.get.await_args.args[0], "/api/v1/df/person/roominfo")
        self.assertEqual(
            client.get.await_args.kwargs["params"],
            {"roomId": "fixture-room", "type": "5"},
        )

        await client.map_stats("fixture-token", "sol", "all", "100")
        params = client.get.await_args.kwargs["params"]
        self.assertEqual(params, {"type": "sol", "serial": "all", "mapId": "100"})

    def test_readiness_calculator_returns_lowest_cost_combinations(self):
        calculator = DeltaCalculator(_ReadinessDataManager())
        result = calculator.calculate_readiness(150)

        self.assertTrue(result["success"])
        self.assertGreater(result["totalCombinations"], 0)
        costs = [item["totalCost"] for item in result["topCombinations"]]
        self.assertEqual(costs, sorted(costs))
        self.assertGreaterEqual(result["topCombinations"][0]["totalReadiness"], 150)

    async def test_client_uses_authoritative_tool_endpoints_and_parameters(self):
        client = object.__new__(DeltaForceClient)
        client.get = AsyncMock(return_value={"code": 0, "data": {}})
        client.post = AsyncMock(return_value={"code": 0, "data": {}})

        await client.operators(detail=False)
        self.assertEqual(client.get.await_args.args[0], "/api/v1/df/object/operator2")
        await client.operators(detail=True)
        self.assertEqual(client.get.await_args.args[0], "/api/v1/df/object/operator")

        await client.object_search("1001，1002")
        self.assertEqual(client.get.await_args.kwargs["params"]["objectID"], "1001,1002")

        await client.material_price("测试材料")
        self.assertEqual(client.get.await_args.kwargs["params"]["objectName"], "测试材料")
        self.assertNotIn("id", client.get.await_args.kwargs["params"])

        await client.ai_review("fixture-token", "sol", "rp")
        self.assertEqual(client.post.await_args.args[0], "/api/v1/df/tools/ai")
        self.assertEqual(client.post.await_args.kwargs["json_data"], {"type": "sol", "preset": "rp"})

        client.put = AsyncMock(return_value={"code": 0, "data": {}})
        await client.update_community_solution("fixture-uuid", {"description": "新描述"}, "qq_fixture")
        self.assertEqual(
            client.put.await_args.args[0],
            "/api/v1/df/gunmod/community/solutions/fixture-uuid",
        )
        self.assertEqual(client.put.await_args.kwargs["proxy_user_id"], "qq_fixture")

    async def test_client_preserves_detailed_health_data_from_http_503(self):
        def handler(request):
            self.assertEqual(request.url.path, "/health/detailed")
            return httpx.Response(
                503,
                json={
                    "code": 0,
                    "message": "degraded",
                    "data": {"status": "degraded", "dependencies": {}},
                },
            )

        client = DeltaForceClient(api_key="fixture-key", api_mode="default")
        await client.client.aclose()
        client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await client.health()
        finally:
            await client.close()

        self.assertEqual(result["code"], 0)
        self.assertEqual(result["data"]["status"], "degraded")

    async def test_client_uses_authoritative_record_subscription_endpoints(self):
        client = object.__new__(DeltaForceClient)
        client.get = AsyncMock(return_value={"code": 0, "data": {}})
        client.post = AsyncMock(return_value={"code": 0, "data": {}})
        client.delete = AsyncMock(return_value={"code": 0, "data": {}})

        await client.list_record_subscriptions("qq_fixture", "fixture-bot")
        self.assertEqual(client.get.await_args.args[0], "/api/v1/user/record-subscriptions")
        self.assertEqual(client.get.await_args.kwargs["user_identifier"], "qq_fixture")

        await client.create_record_subscription(
            "fixture-binding", "both", 300, True, "qq_fixture", "fixture-bot"
        )
        self.assertEqual(client.post.await_args.args[0], "/api/v1/user/record-subscriptions")
        self.assertEqual(
            client.post.await_args.kwargs["json_data"],
            {
                "binding_id": "fixture-binding",
                "subscription_type": "both",
                "poll_interval_sec": 300,
                "rank_detection_enabled": True,
            },
        )

        await client.delete_record_subscription("fixture-sub", "qq_fixture", "fixture-bot")
        self.assertEqual(
            client.delete.await_args.args[0],
            "/api/v1/user/record-subscriptions/fixture-sub",
        )

    def test_subscription_store_persists_targets_atomically(self):
        store = object.__new__(SubscriptionStore)
        store.path = PLUGIN_DIR / "fixture-subscriptions.json"
        store._data = {"subscriptions": {}}
        with patch.object(store, "_save"):
            store.upsert(
                "fixture-user",
                "fixture-binding",
                {"subscription_id": "fixture-sub", "subscription_type": "both"},
            )
            store.set_target(
                "fixture-user",
                "fixture-binding",
                "aiocqhttp:GroupMessage:123",
                "group",
                True,
            )
        item = store.get("fixture-user", "fixture-binding")
        self.assertEqual(item["subscription_id"], "fixture-sub")
        self.assertEqual(
            store.enabled_targets(),
            [{"umo": "aiocqhttp:GroupMessage:123", "binding_id": "fixture-binding"}],
        )
        with patch.object(Path, "write_text") as write_text, patch.object(Path, "replace") as replace:
            store._save()
        write_text.assert_called_once()
        self.assertEqual(write_text.call_args.kwargs["encoding"], "utf-8")
        replace.assert_called_once_with(store.path)

    def test_subscription_store_persists_scheduled_pushes(self):
        store = object.__new__(SubscriptionStore)
        store.path = PLUGIN_DIR / "fixture-subscriptions.json"
        store._data = {"subscriptions": {}, "scheduled_pushes": {}}
        with patch.object(store, "_save"):
            item = store.set_scheduled_push(
                "daily", "fixture-user", "fixture-binding", "aiocqhttp:GroupMessage:123", True
            )
            store.update_scheduled_push(item["key"], {"last_run_key": "2026-08-14"})

        rows = store.scheduled_pushes("daily")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["last_run_key"], "2026-08-14")

    async def test_record_subscription_success_empty_and_error(self):
        class Bindings:
            async def get_primary_binding(self, _user_id):
                return {"binding_id": "fixture-binding", "framework_token": "fixture-token"}

        class Store:
            def __init__(self):
                self.saved = None

            def upsert(self, user_id, binding_id, values):
                self.saved = (user_id, binding_id, values)
                return values

            def remove(self, *_args):
                return None

        client = SimpleNamespace(
            list_record_subscriptions=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"list": []}},
                    {"code": 0, "data": {"list": []}},
                    {"code": 500, "message": "fixture-error", "data": None},
                ]
            ),
            create_record_subscription=AsyncMock(
                return_value={"code": 0, "data": {"subscription": {"id": "fixture-sub"}}}
            ),
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()
        plugin.subscriptions = Store()
        plugin.config.update({"client_id": "fixture-bot", "record_poll_interval": 300})
        plugin._ws_requested = False
        plugin._ws_wakeup = asyncio.Event()

        success = await _collect(plugin._record_subscription(_Event(), "订阅 战绩"))
        empty = await _collect(plugin._record_subscription(_Event(), "订阅状态 战绩"))
        error = await _collect(plugin._record_subscription(_Event(), "订阅状态 战绩"))

        self.assertIn("已创建 both 战绩订阅", success[0]["text"])
        self.assertIn("没有战绩订阅", empty[0]["text"])
        self.assertIn("fixture-error", error[0]["text"])
        self.assertEqual(plugin.subscriptions.saved[2]["subscription_id"], "fixture-sub")

    async def test_record_subscription_cancel_and_switch_handle_empty_and_errors(self):
        class Bindings:
            async def get_primary_binding(self, _user_id):
                return {"binding_id": "fixture-binding", "framework_token": "fixture-token"}

        store = SimpleNamespace(remove=Mock(), upsert=Mock())
        current = {
            "id": "fixture-sub",
            "binding_id": "fixture-binding",
            "subscription_type": "sol",
            "enabled": True,
        }
        client = SimpleNamespace(
            list_record_subscriptions=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"list": []}},
                    {"code": 0, "data": {"list": [current]}},
                    {"code": 0, "data": {"list": [current]}},
                    {"code": 0, "data": {"list": [current]}},
                ]
            ),
            delete_record_subscription=AsyncMock(
                side_effect=[
                    {"code": 500, "message": "删除订阅失败"},
                    {"code": 0},
                    {"code": 500, "message": "旧订阅无法删除"},
                ]
            ),
            create_record_subscription=AsyncMock(),
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()
        plugin.subscriptions = store
        plugin._ws_wakeup = asyncio.Event()

        empty = await _collect(plugin._record_subscription(_Event(), "取消订阅 战绩"))
        delete_error = await _collect(plugin._record_subscription(_Event(), "取消订阅 战绩"))
        deleted = await _collect(plugin._record_subscription(_Event(), "取消订阅 战绩"))
        switch_error = await _collect(plugin._record_subscription(_Event(), "订阅 战绩 mp"))

        self.assertIn("没有可取消", empty[0]["text"])
        self.assertIn("删除订阅失败", delete_error[0]["text"])
        self.assertIn("已取消", deleted[0]["text"])
        self.assertIn("旧订阅无法删除", switch_error[0]["text"])
        store.remove.assert_called_once_with("fixture-user", "fixture-binding")
        client.create_record_subscription.assert_not_awaited()

    async def test_record_subscription_rejects_missing_created_subscription_id(self):
        class Bindings:
            async def get_primary_binding(self, _user_id):
                return {"binding_id": "fixture-binding", "framework_token": "fixture-token"}

        client = SimpleNamespace(
            list_record_subscriptions=AsyncMock(return_value={"code": 0, "data": {"list": []}}),
            create_record_subscription=AsyncMock(return_value={"code": 0, "data": {}}),
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()
        plugin.subscriptions = SimpleNamespace(upsert=Mock())

        result = await _collect(plugin._record_subscription(_Event(), "订阅 战绩 both"))

        self.assertIn("未返回订阅 ID", result[0]["text"])
        plugin.subscriptions.upsert.assert_not_called()

    async def test_subscription_target_handles_context_api_empty_and_disable(self):
        class Bindings:
            async def get_primary_binding(self, _user_id):
                return {"binding_id": "fixture-binding", "framework_token": "fixture-token"}

        class Store:
            def __init__(self):
                self.enabled = True
                self.targets = []

            def upsert(self, *_args):
                return None

            def set_target(self, _user_id, _binding_id, umo, kind, enabled):
                self.targets.append((umo, kind, enabled))
                self.enabled = enabled

            def enabled_targets(self):
                return ["target"] if self.enabled else []

        current = {"id": "fixture-sub", "binding_id": "fixture-binding"}
        client = SimpleNamespace(
            list_record_subscriptions=AsyncMock(
                side_effect=[
                    {"code": 500, "message": "订阅服务异常"},
                    {"code": 0, "data": {"list": []}},
                    {"code": 0, "data": {"list": [current]}},
                    {"code": 0, "data": {"list": [current]}},
                ]
            )
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()
        plugin.subscriptions = Store()
        plugin._ws_wakeup = asyncio.Event()
        plugin._ws_connection = SimpleNamespace(close=AsyncMock())

        wrong_context = await _collect(plugin._subscription_target(_Event(), "private", True))
        api_error = await _collect(plugin._subscription_target(_Event(), "group", True))
        empty = await _collect(plugin._subscription_target(_Event(), "group", True))
        enabled = await _collect(plugin._subscription_target(_Event(), "group", True))
        disabled = await _collect(plugin._subscription_target(_Event(), "group", False))

        self.assertIn("私聊中设置", wrong_context[0]["text"])
        self.assertIn("订阅服务异常", api_error[0]["text"])
        self.assertIn("没有战绩订阅", empty[0]["text"])
        self.assertIn("已开启本群", enabled[0]["text"])
        self.assertIn("已关闭本群", disabled[0]["text"])
        plugin._ws_connection.close.assert_awaited_once()

    async def test_solution_list_detail_and_upload_use_latest_fields(self):
        client = SimpleNamespace(
            community_solutions=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "solutionId": "fixture-uuid",
                                "solutionCode": "CODE123",
                                "weaponName": "M4A1",
                                "type": "sol",
                                "totalPrice": 12345,
                            }
                        ],
                        "total": 1,
                    },
                }
            ),
            community_solution_detail=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "solution": {
                            "solutionId": "fixture-uuid",
                            "weaponName": "M4A1",
                            "attachments": [{"slotId": "scope", "objectId": 1001, "objectName": "瞄准镜"}],
                        }
                    },
                }
            ),
            create_community_solution=AsyncMock(
                return_value={"code": 0, "data": {"solution": {"solutionId": "new-uuid"}}}
            ),
        )
        plugin = self._plugin(client)

        listing = await _collect(plugin._solution_list(_Event(), "烽火 page2", favorites=False))
        detail = await _collect(plugin._solution_detail(_Event(), "fixture-uuid"))
        uploaded = await _collect(
            plugin._solution_upload(
                _Event(),
                'CODE456 180100001 mp 新方案 [{"slotId":"scope","objectId":1001}]',
            )
        )

        self.assertIn("CODE123", listing[0]["text"])
        self.assertIn("瞄准镜", detail[0]["text"])
        self.assertIn("new-uuid", uploaded[0]["text"])
        self.assertEqual(client.community_solutions.await_args.args[0], {"page": 2, "pageSize": 20, "type": "sol"})
        self.assertEqual(
            client.create_community_solution.await_args.args[0],
            {
                "solutionCode": "CODE456",
                "description": "新方案",
                "type": "mp",
                "weaponId": 180100001,
                "attachments": [{"slotId": "scope", "objectId": 1001, "objectName": ""}],
            },
        )

    async def test_solution_upload_rejects_missing_or_invalid_attachments(self):
        client = SimpleNamespace(create_community_solution=AsyncMock())
        plugin = self._plugin(client)

        missing = await _collect(plugin._solution_upload(_Event(), "CODE 180100001 sol"))
        invalid = await _collect(plugin._solution_upload(_Event(), "CODE 180100001 sol []"))

        self.assertIn("缺少配件 JSON", missing[0]["text"])
        self.assertIn("非空数组", invalid[0]["text"])
        client.create_community_solution.assert_not_awaited()

    async def test_solution_queries_handle_empty_and_error_responses(self):
        client = SimpleNamespace(
            community_solutions=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"items": [], "total": 0}},
                    {"code": 500, "message": "方案列表服务异常"},
                ]
            ),
            my_community_favorites=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"items": [], "total": 0}},
                    {"code": 500, "message": "收藏列表服务异常"},
                ]
            ),
            community_solution_detail=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {}},
                    {"code": 404, "message": "方案不存在"},
                ]
            ),
        )
        plugin = self._plugin(client)

        list_empty = await _collect(plugin._solution_list(_Event(), "", favorites=False))
        list_error = await _collect(plugin._solution_list(_Event(), "", favorites=False))
        favorites_empty = await _collect(plugin._solution_list(_Event(), "", favorites=True))
        favorites_error = await _collect(plugin._solution_list(_Event(), "", favorites=True))
        detail_empty = await _collect(plugin._solution_detail(_Event(), "fixture-uuid"))
        detail_error = await _collect(plugin._solution_detail(_Event(), "fixture-uuid"))

        self.assertIn("未找到符合条件", list_empty[0]["text"])
        self.assertIn("方案列表服务异常", list_error[0]["text"])
        self.assertIn("未找到符合条件", favorites_empty[0]["text"])
        self.assertIn("收藏列表服务异常", favorites_error[0]["text"])
        self.assertIn("不存在或暂不可见", detail_empty[0]["text"])
        self.assertIn("方案不存在", detail_error[0]["text"])

    async def test_solution_write_operations_report_success_and_permission_errors(self):
        denied = {"code": 403, "message": "缺少 gunmod:community:write 权限"}
        client = SimpleNamespace(
            create_community_solution=AsyncMock(return_value=denied),
            update_community_solution=AsyncMock(side_effect=[{"code": 0}, denied]),
            delete_community_solution=AsyncMock(side_effect=[{"code": 0}, denied]),
            vote_community_solution=AsyncMock(side_effect=[{"code": 0}, denied]),
            favorite_community_solution=AsyncMock(side_effect=[{"code": 0}, denied]),
        )
        plugin = self._plugin(client)

        upload = await _collect(
            plugin._solution_upload(
                _Event(),
                'CODE456 180100001 sol 测试方案 [{"slotId":"scope","objectId":1001}]',
            )
        )
        update_ok = await _collect(plugin._solution_update(_Event(), "fixture-uuid", "新描述 公开"))
        update_error = await _collect(plugin._solution_update(_Event(), "fixture-uuid", "新描述"))
        delete_ok = await _collect(plugin._solution_delete(_Event(), "fixture-uuid"))
        delete_error = await _collect(plugin._solution_delete(_Event(), "fixture-uuid"))
        vote_ok = await _collect(plugin._solution_vote(_Event(), "fixture-uuid", 1))
        vote_error = await _collect(plugin._solution_vote(_Event(), "fixture-uuid", -1))
        favorite_ok = await _collect(plugin._solution_favorite(_Event(), "fixture-uuid", True))
        favorite_error = await _collect(plugin._solution_favorite(_Event(), "fixture-uuid", False))

        self.assertIn("gunmod:community:write", upload[0]["text"])
        self.assertIn("已更新", update_ok[0]["text"])
        self.assertIn("gunmod:community:write", update_error[0]["text"])
        self.assertIn("已删除", delete_ok[0]["text"])
        self.assertIn("gunmod:community:write", delete_error[0]["text"])
        self.assertIn("已点赞", vote_ok[0]["text"])
        self.assertIn("gunmod:community:write", vote_error[0]["text"])
        self.assertIn("已收藏", favorite_ok[0]["text"])
        self.assertIn("gunmod:community:write", favorite_error[0]["text"])

    async def test_record_event_push_is_deduplicated(self):
        plugin = self._plugin()
        plugin.config["enable_image_render"] = True
        plugin.context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(return_value="D:/fixture-record-push.png"),
            res_path=(PLUGIN_DIR / "resources").resolve(),
        )
        plugin.bindings = SimpleNamespace(
            get_user_bindings=AsyncMock(
                return_value=[
                    {
                        "binding_id": "fixture-binding",
                        "nickname": "%E6%B5%8B%E8%AF%95%E7%8E%A9%E5%AE%B6",
                    }
                ]
            )
        )
        plugin.subscriptions = SimpleNamespace(
            all=lambda: [
                {
                    "subscription_id": "fixture-sub",
                    "user_id": "fixture-user",
                    "binding_id": "fixture-binding",
                    "targets": {"aiocqhttp:GroupMessage:123": {"group": True}},
                }
            ]
        )
        plugin._seen_record_events = {}
        event_data = {
            "subscription_id": "fixture-sub",
            "record_id": "fixture-record",
            "record_type": "sol",
            "event_time": "2026-08-14T12:00:00Z",
            "is_recent": True,
            "record": {
                "MapId": "100",
                "ArmedForceId": "10",
                "EscapeFailReason": 1,
                "DurationS": 125,
                "FinalPrice": 250000,
                "flowCalGainedPrice": 100000,
                "KillCount": 3,
                "KillPlayerAICount": 2,
                "KillAICount": 1,
                "Rescue": 1,
            },
        }

        await plugin._push_record_event(event_data)
        await plugin._push_record_event(event_data)

        plugin.context.send_message.assert_awaited_once()
        plugin.renderer.render_html.assert_awaited_once()
        render_call = plugin.renderer.render_html.await_args
        self.assertEqual(render_call.args[0], "Template/recordPush/recordPush.html")
        self.assertEqual(render_call.args[1]["displayName"], "测试玩家")
        self.assertEqual(render_call.args[1]["map"], "零号大坝-常规")
        self.assertEqual(render_call.args[1]["operator"], "红狼")
        self.assertEqual(render_call.args[1]["status"], "撤离成功")
        self.assertEqual(render_call.args[1]["value"], "250,000")
        self.assertEqual(render_call.args[1]["income"], "100,000")
        self.assertIn("玩家 3", render_call.args[1]["killsHtml"])
        self.assertIn("AI玩家 2", render_call.args[1]["killsHtml"])
        self.assertIn("AI 1", render_call.args[1]["killsHtml"])
        chain = plugin.context.send_message.await_args.args[1]
        self.assertIn("零号大坝", chain.chain[0].text)
        self.assertIn("净收益：100,000", chain.chain[0].text)
        self.assertEqual(chain.chain[1].file, "file:///D:/fixture-record-push.png")

    async def test_mp_record_event_push_renders_score_card(self):
        plugin = self._plugin()
        plugin.config["enable_image_render"] = True
        plugin.context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(return_value="D:/fixture-record-push-mp.png"),
            res_path=(PLUGIN_DIR / "resources").resolve(),
        )
        plugin.subscriptions = SimpleNamespace(
            all=lambda: [
                {
                    "subscription_id": "fixture-sub",
                    "targets": {"aiocqhttp:GroupMessage:123": {"group": True}},
                }
            ]
        )
        plugin._seen_record_events = {}

        await plugin._push_record_event(
            {
                "subscription_id": "fixture-sub",
                "record_id": "fixture-mp-record",
                "record_type": "mp",
                "event_time": "2026-08-14T12:00:00Z",
                "display_name": "全面玩家",
                "record": {
                    "MapId": "200",
                    "ArmedForceId": "20",
                    "MatchResult": 1,
                    "gametime": 600,
                    "KillNum": 12,
                    "Death": 3,
                    "Assist": 8,
                    "TotalScore": 45678,
                    "RescueTeammateCount": 2,
                },
            }
        )

        render_data = plugin.renderer.render_html.await_args.args[1]
        self.assertEqual(render_data["status"], "胜利")
        self.assertEqual(render_data["kda"], "12/3/8")
        self.assertEqual(render_data["score"], "45,678")
        self.assertEqual(render_data["rescue"], 2)
        chain = plugin.context.send_message.await_args.args[1]
        self.assertIn("K/D/A：12/3/8", chain.chain[0].text)
        self.assertEqual(len(chain.chain), 2)

    async def test_record_event_render_failure_falls_back_to_text(self):
        plugin = self._plugin()
        plugin.config["enable_image_render"] = True
        plugin.context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(side_effect=RuntimeError("fixture-render-error")),
            res_path=(PLUGIN_DIR / "resources").resolve(),
        )
        plugin.subscriptions = SimpleNamespace(
            all=lambda: [
                {
                    "subscription_id": "fixture-sub",
                    "targets": {"aiocqhttp:GroupMessage:123": {"group": True}},
                }
            ]
        )
        plugin._seen_record_events = {}

        await plugin._push_record_event(
            {
                "subscription_id": "fixture-sub",
                "record_id": "fixture-render-error",
                "record_type": "sol",
                "record": {"MapName": "零号大坝", "EscapeFailReason": 2},
            }
        )

        chain = plugin.context.send_message.await_args.args[1]
        self.assertEqual(len(chain.chain), 1)
        self.assertIn("被玩家击杀", chain.chain[0].text)

    async def test_record_event_skips_renderer_when_images_are_disabled(self):
        plugin = self._plugin()
        plugin.context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(return_value="D:/should-not-render.png"),
            res_path=(PLUGIN_DIR / "resources").resolve(),
        )
        plugin.subscriptions = SimpleNamespace(
            all=lambda: [
                {
                    "subscription_id": "fixture-sub",
                    "targets": {"aiocqhttp:GroupMessage:123": {"group": True}},
                }
            ]
        )
        plugin._seen_record_events = {}

        await plugin._push_record_event(
            {
                "subscription_id": "fixture-sub",
                "record_id": "fixture-text-only",
                "record_type": "mp",
                "record": {"MapName": "烬区", "MatchResult": 2},
            }
        )

        plugin.renderer.render_html.assert_not_awaited()
        chain = plugin.context.send_message.await_args.args[1]
        self.assertEqual(len(chain.chain), 1)

    def test_ws_uri_reuses_subscription_client_id(self):
        plugin = self._plugin()
        plugin.client = SimpleNamespace(
            api_key="fixture-key",
            _base_urls=lambda: ["https://delta-test-api.shallow.ink"],
        )
        plugin.config = {}
        plugin.subscriptions = SimpleNamespace(all=lambda: [{"client_id": "fixture-bot"}])

        uri, origin = plugin._ws_uri()

        self.assertEqual(uri, "wss://delta-test-api.shallow.ink/ws")
        self.assertNotIn("fixture-key", uri)
        self.assertEqual(origin, "https://delta-test-api.shallow.ink")

    def test_ws_header_argument_supports_old_and_new_websockets(self):
        def old_connect(uri, *, extra_headers=None):
            return uri, extra_headers

        def new_connect(uri, *, additional_headers=None):
            return uri, additional_headers

        self.assertEqual(
            DeltaForcePlugin._ws_header_argument(old_connect), "extra_headers"
        )
        self.assertEqual(
            DeltaForcePlugin._ws_header_argument(new_connect), "additional_headers"
        )

    async def test_ws_run_once_sends_protocol_envelope_and_dispatches_record_event(self):
        event_data = {"subscription_id": "fixture-sub", "record_id": "fixture-record"}

        class Connection:
            def __init__(self):
                self.sent = []
                self.received = [
                    "非 JSON 消息",
                    json.dumps({"type": "connection.ready", "kind": "event", "data": {}}),
                ]

            async def send(self, value):
                self.sent.append(value)

            async def recv(self):
                if self.received:
                    return self.received.pop(0)
                request_id = json.loads(self.sent[0])["id"]
                return json.dumps(
                    {
                        "id": request_id,
                        "type": "record.client.subscribe",
                        "kind": "response",
                        "code": 0,
                        "data": {"subscribed": ["record:client:fixture:fixture-bot"]},
                    }
                )

            def __aiter__(self):
                async def messages():
                    yield json.dumps({"type": "record.new", "kind": "event", "data": event_data})

                return messages()

        class ConnectionContext:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, *_args):
                return False

        connection = Connection()
        connect = Mock(return_value=ConnectionContext())
        plugin = self._plugin()
        plugin.client = SimpleNamespace(
            api_key="fixture-key",
            _base_urls=lambda: ["https://delta-test-api.shallow.ink"],
        )
        plugin.config = {"client_id": "fixture-bot"}
        plugin._ws_stop = asyncio.Event()
        plugin._push_record_event = AsyncMock()

        with patch("astrbot_plugin_sanjiaozhou.main.websockets", SimpleNamespace(connect=connect)):
            await plugin._ws_run_once()

        envelope = json.loads(connection.sent[0])
        self.assertEqual(envelope["type"], "record.client.subscribe")
        self.assertEqual(envelope["kind"], "request")
        self.assertEqual(envelope["data"], {"client_id": "fixture-bot"})
        self.assertEqual(connect.call_args.kwargs["origin"], "https://delta-test-api.shallow.ink")
        self.assertEqual(connect.call_args.kwargs["additional_headers"], {"X-API-Key": "fixture-key"})
        self.assertNotIn("fixture-key", connect.call_args.args[0])
        plugin._push_record_event.assert_awaited_once_with(event_data)
        self.assertIsNone(plugin._ws_connection)

    async def test_ws_run_once_clears_stale_connection_after_consumer_error(self):
        class BrokenConnection:
            async def send(self, _value):
                return None

            async def recv(self):
                raise RuntimeError("连接读取失败")

        class ConnectionContext:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, *_args):
                return False

        connection = BrokenConnection()
        plugin = self._plugin()
        plugin.client = SimpleNamespace(
            api_key="fixture-key",
            _base_urls=lambda: ["https://delta-test-api.shallow.ink"],
        )
        plugin.config = {"client_id": "fixture-bot"}

        with patch(
            "astrbot_plugin_sanjiaozhou.main.websockets",
            SimpleNamespace(connect=Mock(return_value=ConnectionContext())),
        ):
            with self.assertRaisesRegex(RuntimeError, "连接读取失败"):
                await plugin._ws_run_once()

        self.assertIsNone(plugin._ws_connection)

    async def test_ws_run_once_rejects_failed_subscription_response(self):
        class RejectedConnection:
            def __init__(self):
                self.request_id = ""

            async def send(self, value):
                self.request_id = json.loads(value)["id"]

            async def recv(self):
                return json.dumps(
                    {
                        "id": self.request_id,
                        "type": "record.client.subscribe",
                        "kind": "response",
                        "code": 403,
                        "message": "拒绝",
                    }
                )

        class ConnectionContext:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, *_args):
                return False

        connection = RejectedConnection()
        plugin = self._plugin()
        plugin.client = SimpleNamespace(
            api_key="fixture-key",
            _base_urls=lambda: ["https://delta-test-api.shallow.ink"],
        )
        plugin.config = {"client_id": "fixture-bot"}

        with patch(
            "astrbot_plugin_sanjiaozhou.main.websockets",
            SimpleNamespace(connect=Mock(return_value=ConnectionContext())),
        ):
            with self.assertRaisesRegex(RuntimeError, "订阅请求被后端拒绝"):
                await plugin._ws_run_once()

        self.assertIsNone(plugin._ws_connection)

    async def test_websocket_commands_control_request_and_report_state(self):
        plugin = self._plugin()
        plugin._ws_wakeup = asyncio.Event()
        plugin._ws_requested = False
        plugin._ws_connection = SimpleNamespace(close=AsyncMock())

        status = await _collect(plugin._dispatch(_Event(), "ws状态"))
        stopped = await _collect(plugin._dispatch(_Event(), "ws断开"))
        started = await _collect(plugin._dispatch(_Event(), "ws连接"))

        self.assertIn("已连接", status[0]["text"])
        self.assertIn("已停止", stopped[0]["text"])
        self.assertIn("已请求连接", started[0]["text"])
        plugin._ws_connection.close.assert_awaited_once()
        self.assertTrue(plugin._ws_requested)

    async def test_record_event_continues_after_one_target_send_fails(self):
        plugin = self._plugin()
        plugin.config["enable_image_render"] = True
        plugin.context = SimpleNamespace(send_message=AsyncMock(side_effect=[RuntimeError("发送失败"), True]))
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(return_value="D:/fixture-shared-record-push.png"),
            res_path=(PLUGIN_DIR / "resources").resolve(),
        )
        plugin.subscriptions = SimpleNamespace(
            all=lambda: [
                {
                    "subscription_id": "fixture-sub",
                    "targets": {
                        "aiocqhttp:GroupMessage:1": {"group": True},
                        "aiocqhttp:GroupMessage:2": {"group": True},
                    },
                }
            ]
        )
        plugin._seen_record_events = {}

        await plugin._push_record_event(
            {
                "subscription_id": "fixture-sub",
                "record_id": "fixture-record",
                "event_time": "2026-08-14T12:00:00Z",
                "record_type": "mp",
                "record": {"mapName": "烬区"},
            }
        )

        self.assertEqual(plugin.context.send_message.await_count, 2)
        plugin.renderer.render_html.assert_awaited_once()

    def test_scheduled_run_keys_follow_configured_times(self):
        plugin = self._plugin()
        plugin.config.update(
            {
                "daily_push_hour": 10,
                "weekly_push_hour": 10,
                "weekly_push_weekday": 0,
                "keyword_push_hour": 8,
            }
        )
        monday = __import__("datetime").datetime(2026, 8, 10, 10, 0, 0)

        self.assertEqual(plugin._scheduled_run_key("daily", monday), "2026-08-10")
        self.assertEqual(plugin._scheduled_run_key("weekly", monday), "2026-W33")
        self.assertEqual(plugin._scheduled_run_key("keyword", monday), "2026-08-10")
        self.assertEqual(plugin._scheduled_run_key("daily", monday.replace(hour=9)), "")

    async def test_keyword_scheduled_push_uses_native_message_chain(self):
        plugin = self._plugin(
            SimpleNamespace(
                daily_keyword=AsyncMock(
                    return_value={
                        "code": 0,
                        "data": {"list": [{"mapName": "零号大坝", "secret": "1234"}]},
                    }
                )
            )
        )
        plugin.context = SimpleNamespace(send_message=AsyncMock(return_value=True))

        success = await plugin._run_fixed_push(
            {"umo": "aiocqhttp:GroupMessage:123", "user_id": "fixture-user"}, "keyword"
        )

        self.assertTrue(success)
        chain = plugin.context.send_message.await_args.args[1]
        self.assertIn("零号大坝：1234", chain.chain[0].text)

    async def test_daily_scheduled_push_renders_existing_template(self):
        class Bindings:
            async def get_user_bindings(self, _user_id):
                return [{"binding_id": "fixture-binding", "framework_token": "fixture-token"}]

        raw = {
            "sol": {"data": {"data": {"solDetail": {"recentGainDate": "20260814", "recentGain": 1000}}}},
            "mp": {"data": {"data": {"mpDetail": {"recentDate": "20260814", "totalFightNum": 1}}}},
        }
        plugin = self._plugin(SimpleNamespace(daily_record=AsyncMock(return_value={"code": 0, "data": raw})))
        plugin.bindings = Bindings()
        plugin.context = SimpleNamespace(send_message=AsyncMock(return_value=True))
        plugin.renderer = SimpleNamespace(render_html=AsyncMock(return_value="D:/fixture-daily.png"))
        plugin.config["enable_image_render"] = True
        plugin._render_identity = AsyncMock(return_value={"userName": "测试玩家"})

        success = await plugin._run_fixed_push(
            {
                "umo": "aiocqhttp:GroupMessage:123",
                "user_id": "fixture-user",
                "binding_id": "fixture-binding",
            },
            "daily",
        )

        self.assertTrue(success)
        plugin.renderer.render_html.assert_awaited_once()
        self.assertEqual(plugin.renderer.render_html.await_args.args[0], "Template/dailyReport/dailyReport.html")
        chain = plugin.context.send_message.await_args.args[1]
        self.assertEqual(chain.chain[1].file, "file:///D:/fixture-daily.png")

    async def test_place_push_keeps_job_until_due_and_only_sends_once(self):
        class Bindings:
            async def get_user_bindings(self, _user_id):
                return [{"binding_id": "fixture-binding", "framework_token": "fixture-token"}]

        store = object.__new__(SubscriptionStore)
        store.path = PLUGIN_DIR / "fixture-subscriptions.json"
        store._data = {"subscriptions": {}, "scheduled_pushes": {}}
        with patch.object(store, "_save"):
            item = store.set_scheduled_push(
                "place", "fixture-user", "fixture-binding", "aiocqhttp:GroupMessage:123", True
            )
        client = SimpleNamespace(
            place_status=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {
                            "places": [
                                {
                                    "id": "workbench",
                                    "placeName": "工作台",
                                    "pushTime": 1700000100,
                                    "objectId": 1001,
                                    "objectDetail": {"objectName": "高级零件"},
                                }
                            ]
                        },
                    },
                    {"code": 0, "data": {"places": []}},
                    {"code": 0, "data": {"places": []}},
                ]
            )
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()
        plugin.subscriptions = store
        plugin._send_scheduled_message = AsyncMock(return_value=True)

        with patch.object(store, "_save"):
            await plugin._run_place_push(item, __import__("datetime").datetime.fromtimestamp(1700000000))
            updated = store.scheduled_pushes("place")[0]
            await plugin._run_place_push(updated, __import__("datetime").datetime.fromtimestamp(1700000101))
            updated = store.scheduled_pushes("place")[0]
            await plugin._run_place_push(updated, __import__("datetime").datetime.fromtimestamp(1700000102))

        plugin._send_scheduled_message.assert_awaited_once()
        self.assertIn("高级零件", plugin._send_scheduled_message.await_args.args[1])

    async def test_place_status_formats_success_empty_and_error_responses(self):
        client = SimpleNamespace(
            place_status=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {
                            "places": [
                                {
                                    "placeName": "工作台",
                                    "level": 3,
                                    "status": "生产中",
                                    "leftTime": 600,
                                    "objectDetail": {"objectName": "高级零件"},
                                }
                            ],
                            "stats": {"total": 1, "producing": 1, "idle": 0},
                        },
                    },
                    {"code": 0, "data": {"places": [], "stats": {"total": 0}}},
                    {"code": 500, "message": "特勤处状态服务异常"},
                ]
            )
        )
        plugin = self._plugin(client)

        success = await _collect(plugin._place_status(_Event()))
        empty = await _collect(plugin._place_status(_Event()))
        error = await _collect(plugin._place_status(_Event()))

        self.assertIn("设施 1 个｜生产中 1 个", success[0]["text"])
        self.assertIn("工作台 Lv.3：生产中，生产 高级零件，剩余 10分钟", success[0]["text"])
        self.assertIn("没有可显示", empty[0]["text"])
        self.assertIn("特勤处状态服务异常", error[0]["text"])

    async def test_report_pushes_retry_api_errors_and_accept_empty_data(self):
        class Bindings:
            async def get_user_bindings(self, _user_id):
                return [{"binding_id": "fixture-binding", "framework_token": "fixture-token"}]

        client = SimpleNamespace(
            daily_record=AsyncMock(
                side_effect=[
                    {"code": 500, "message": "日报服务异常"},
                    {"code": 0, "data": {}},
                ]
            ),
            weekly_record=AsyncMock(
                side_effect=[
                    {"code": 500, "message": "周报服务异常"},
                    {"code": 0, "data": {}},
                ]
            ),
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()
        plugin._render_identity = AsyncMock(return_value={"userName": "测试玩家"})
        item = {
            "umo": "aiocqhttp:GroupMessage:123",
            "user_id": "fixture-user",
            "binding_id": "fixture-binding",
        }

        daily_error = await plugin._run_fixed_push(item, "daily")
        daily_empty = await plugin._run_fixed_push(item, "daily")
        weekly_error = await plugin._run_fixed_push(item, "weekly")
        weekly_empty = await plugin._run_fixed_push(item, "weekly")

        self.assertFalse(daily_error)
        self.assertTrue(daily_empty)
        self.assertFalse(weekly_error)
        self.assertTrue(weekly_empty)

    async def test_place_push_preserves_pending_job_after_api_or_delivery_failure(self):
        class Bindings:
            async def get_user_bindings(self, _user_id):
                return [{"binding_id": "fixture-binding", "framework_token": "fixture-token"}]

        class Store:
            def __init__(self):
                self.updated = []

            def update_scheduled_push(self, key, values):
                self.updated.append((key, values))

        client = SimpleNamespace(
            place_status=AsyncMock(
                side_effect=[
                    {"code": 500, "message": "特勤处服务异常"},
                    {
                        "code": 0,
                        "data": {
                            "places": [
                                {
                                    "id": "workbench",
                                    "placeName": "工作台",
                                    "pushTime": 1_700_000_000,
                                    "objectId": 1001,
                                    "objectDetail": {"objectName": "高级零件"},
                                }
                            ]
                        },
                    },
                ]
            )
        )
        plugin = self._plugin(client)
        plugin.bindings = Bindings()
        plugin.subscriptions = Store()
        plugin._send_scheduled_message = AsyncMock(return_value=False)
        item = {
            "key": "fixture-place",
            "umo": "aiocqhttp:GroupMessage:123",
            "user_id": "fixture-user",
            "binding_id": "fixture-binding",
        }
        now = __import__("datetime").datetime.fromtimestamp(1_700_000_001)

        await plugin._run_place_push(item, now)
        await plugin._run_place_push(item, now)

        self.assertEqual(len(plugin.subscriptions.updated), 1)
        jobs = plugin.subscriptions.updated[0][1]["place_jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertFalse(next(iter(jobs.values()))["notified"])

    async def test_toggle_daily_push_uses_current_group_umo(self):
        class Bindings:
            async def get_primary_binding(self, _user_id):
                return {"binding_id": "fixture-binding", "framework_token": "fixture-token"}

        store = SimpleNamespace(set_scheduled_push=Mock())
        plugin = self._plugin()
        plugin.bindings = Bindings()
        plugin.subscriptions = store

        result = await _collect(plugin._toggle_scheduled_push(_Event(), "daily", True))

        self.assertIn("已为本群开启日报推送", result[0]["text"])
        store.set_scheduled_push.assert_called_once_with(
            "daily",
            "fixture-user",
            "fixture-binding",
            "aiocqhttp:GroupMessage:123",
            True,
        )

    async def test_scheduler_marks_successful_run_and_retries_failure(self):
        class Store:
            def __init__(self):
                self.rows = [
                    {"key": "ok", "kind": "daily", "enabled": True},
                    {"key": "retry", "kind": "keyword", "enabled": True},
                ]
                self.updated = []

            def scheduled_pushes(self):
                return list(self.rows)

            def update_scheduled_push(self, key, values):
                self.updated.append((key, values))

        plugin = self._plugin()
        plugin.subscriptions = Store()
        plugin.config.update({"daily_push_hour": 10, "keyword_push_hour": 8})
        plugin._run_fixed_push = AsyncMock(side_effect=[True, False])

        await plugin._run_scheduled_pushes(__import__("datetime").datetime(2026, 8, 14, 10, 0, 0))

        self.assertEqual(plugin.subscriptions.updated, [("ok", {"last_run_key": "2026-08-14"})])

    async def test_scheduler_isolates_one_subscription_exception(self):
        class Store:
            def __init__(self):
                self.updated = []

            def scheduled_pushes(self):
                return [
                    {"key": "broken", "kind": "daily", "enabled": True},
                    {"key": "healthy", "kind": "keyword", "enabled": True},
                ]

            def update_scheduled_push(self, key, values):
                self.updated.append((key, values))

        plugin = self._plugin()
        plugin.subscriptions = Store()
        plugin.config.update({"daily_push_hour": 10, "keyword_push_hour": 8})
        plugin._run_fixed_push = AsyncMock(side_effect=[RuntimeError("渲染失败"), True])

        await plugin._run_scheduled_pushes(__import__("datetime").datetime(2026, 8, 14, 10, 0, 0))

        self.assertEqual(plugin._run_fixed_push.await_count, 2)
        self.assertEqual(plugin.subscriptions.updated, [("healthy", {"last_run_key": "2026-08-14"})])

    async def test_fixed_push_retries_api_and_delivery_failures_but_accepts_empty_data(self):
        keyword_client = SimpleNamespace(
            daily_keyword=AsyncMock(
                side_effect=[
                    {"code": 500, "message": "每日密码服务异常"},
                    {"code": 0, "data": {"list": []}},
                    {"code": 0, "data": {"list": [{"mapName": "零号大坝", "secret": "1234"}]}},
                ]
            )
        )
        plugin = self._plugin(keyword_client)
        plugin._send_scheduled_message = AsyncMock(return_value=False)
        item = {"umo": "aiocqhttp:GroupMessage:123", "user_id": "fixture-user"}

        api_error = await plugin._run_fixed_push(item, "keyword")
        empty = await plugin._run_fixed_push(item, "keyword")
        delivery_error = await plugin._run_fixed_push(item, "keyword")

        self.assertFalse(api_error)
        self.assertTrue(empty)
        self.assertFalse(delivery_error)

    async def test_terminate_cancels_all_background_tasks_and_closes_resources(self):
        plugin = self._plugin()

        async def pending():
            await asyncio.Event().wait()

        plugin._static_task = asyncio.create_task(pending())
        plugin._ws_task = asyncio.create_task(pending())
        plugin._push_task = asyncio.create_task(pending())
        plugin._ws_stop = asyncio.Event()
        plugin._ws_wakeup = asyncio.Event()
        plugin._ws_connection = SimpleNamespace(close=AsyncMock())
        plugin.client = SimpleNamespace(close=AsyncMock())
        plugin.renderer = SimpleNamespace(close=AsyncMock())

        await plugin.terminate()

        self.assertTrue(plugin._ws_stop.is_set())
        self.assertTrue(all(task.done() for task in (plugin._static_task, plugin._ws_task, plugin._push_task)))
        plugin._ws_connection.close.assert_awaited_once()
        plugin.client.close.assert_awaited_once()
        plugin.renderer.close.assert_awaited_once()

    async def test_user_info_success_missing_role_and_error_branches(self):
        success_payload = {
            "code": 0,
            "data": {
                "data": {"userData": {"charac_name": "测试角色"}, "careerData": {}},
                "roleInfo": {"uid": "12345678"},
            },
        }
        client = SimpleNamespace(
            personal_info=AsyncMock(
                side_effect=[
                    success_payload,
                    {"code": 0, "data": {"data": {}, "roleInfo": {}}},
                    {"code": 500, "message": "fixture-error", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        success = await _collect(plugin._user_info(_Event()))
        missing = await _collect(plugin._uid(_Event()))
        error = await _collect(plugin._user_info(_Event()))

        self.assertIn("测试角色", success[0]["text"])
        self.assertIn("未获取到", missing[0]["text"])
        self.assertIn("fixture-error", error[0]["text"])

    def test_personal_data_supports_single_and_double_mode_envelopes(self):
        plugin = self._plugin()
        single = {"data": {"data": {"solDetail": {"totalFight": 3}}}}
        both = {
            "sol": {"data": {"data": {"solDetail": {"totalFight": 3}}}},
            "mp": {"data": {"data": {"mpDetail": {"totalFight": 4}}}},
        }

        self.assertEqual(plugin._extract_mode_details(single, "sol")[0][1]["totalFight"], 3)
        self.assertEqual([mode for mode, _ in plugin._extract_mode_details(both, None)], ["sol", "mp"])
        self.assertEqual(plugin._extract_mode_details({"data": {"data": {}}}, "sol"), [])

    def test_personal_data_template_fields_are_preformatted(self):
        plugin = self._plugin()
        event = _Event()
        sol = plugin._build_personal_data(
            event,
            "sol",
            {"redTotalMoney": 123456, "totalGainedPrice": 789, "mapList": []},
            "7",
        )
        mp = plugin._build_personal_data(
            event,
            "mp",
            {"winRatio": 51.2, "totalScore": 9999, "mapList": []},
            "all",
        )

        self.assertEqual(sol["solDetail"]["redTotalMoneyFormatted"], "123,456")
        self.assertEqual(mp["mpDetail"]["winRatioFormatted"], "51.2%")
        self.assertEqual(mp["season"], "全部")

    async def test_personal_data_success_empty_and_error_branches(self):
        client = SimpleNamespace(
            personal_data=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"data": {"data": {"solDetail": {"totalFight": 3}}}}},
                    {"code": 0, "data": {"data": {"data": {}}}},
                    {"code": 500, "message": "fixture-error", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        success = await _collect(plugin._personal_data(_Event(), "烽火 7"))
        empty = await _collect(plugin._personal_data(_Event(), "烽火 7"))
        error = await _collect(plugin._personal_data(_Event(), "烽火 7"))

        self.assertIn("烽火个人数据", success[0]["text"])
        self.assertIn("暂未查询到", empty[0]["text"])
        self.assertIn("fixture-error", error[0]["text"])

    def test_record_adapter_includes_all_kill_types_and_teammates(self):
        plugin = self._plugin()
        item = plugin._record_item(
            {
                "MapId": "100",
                "ArmedForceId": "10",
                "EscapeFailReason": 1,
                "KillCount": 2,
                "KillPlayerAICount": 3,
                "KillAICount": 4,
                "teammateArr": [
                    {
                        "ArmedForceId": "20",
                        "EscapeFailReason": 2,
                        "KillCount": 1,
                        "KillPlayerAICount": 1,
                        "KillAICount": 1,
                    }
                ],
            },
            "sol",
            1,
        )

        self.assertIn("AI玩家 3", item["killsHtml"])
        self.assertEqual(item["teammates"][0]["kills"], 3)
        self.assertEqual(item["teammates"][0]["operator"], "蜂医")

    async def test_record_success_empty_and_error_branches(self):
        client = SimpleNamespace(
            record=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"list": [{"MapId": "100", "EscapeFailReason": 1}]}},
                    {"code": 0, "data": {"list": []}},
                    {"code": 500, "message": "fixture-error", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        success = await _collect(plugin._record(_Event(), "烽火 1"))
        empty = await _collect(plugin._record(_Event(), "烽火 2"))
        error = await _collect(plugin._record(_Event(), "烽火 3"))

        self.assertIn("烽火地带战绩", success[0]["text"])
        self.assertIn("暂无战绩", empty[0]["text"])
        self.assertIn("fixture-error", error[0]["text"])

    async def test_room_info_supports_sol_and_nested_mp_players(self):
        client = SimpleNamespace(
            room_info=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": [
                            {
                                "nickName": "%E6%B5%8B%E8%AF%95%E7%8E%A9%E5%AE%B6",
                                "TeamId": "1",
                                "ArmedForceId": "10",
                                "MapId": "100",
                                "dtEventTime": "2026-08-14 12:00:00",
                                "EscapeFailReason": 1,
                                "KillCount": 2,
                                "KillPlayerAICount": 3,
                                "KillAICount": 4,
                                "FinalPrice": "585563",
                                "Rescue": 1,
                                "Revive": 2,
                                "DurationS": 1021,
                            }
                        ],
                    },
                    {
                        "code": 0,
                        "data": {
                            "userList": [
                                {
                                    "MapId": "200",
                                    "dtEventTime": "2026-08-14 13:00:00",
                                    "KillNum": 12,
                                    "Death": 3,
                                    "Assist": 8,
                                    "TotalScore": 45678,
                                    "RescueTeammateCount": 2,
                                    "userDetail": {
                                        "nickName": "%E5%85%A8%E9%9D%A2%E7%8E%A9%E5%AE%B6",
                                        "teamId": "2",
                                        "armedForceId": "20",
                                    },
                                }
                            ]
                        },
                    },
                ]
            )
        )
        plugin = self._plugin(client)

        sol = await _collect(plugin._battle_room_info(_Event(), "烽火", "room-sol"))
        mp = await _collect(plugin._battle_room_info(_Event(), "全面", "room-mp"))

        self.assertIn("测试玩家", sol[0]["text"])
        self.assertIn("撤离成功", sol[0]["text"])
        self.assertIn("玩家 2 / AI玩家 3 / AI 4", sol[0]["text"])
        self.assertIn("585,563", sol[0]["text"])
        self.assertIn("全面玩家", mp[0]["text"])
        self.assertIn("K/D/A 12/3/8", mp[0]["text"])
        self.assertIn("45,678", mp[0]["text"])
        self.assertEqual(client.room_info.await_args_list[0].args, ("fixture-token", "room-sol", "4"))
        self.assertEqual(client.room_info.await_args_list[1].args, ("fixture-token", "room-mp", "5"))

    async def test_room_info_handles_empty_error_invalid_mode_and_unbound_account(self):
        client = SimpleNamespace(
            room_info=AsyncMock(
                side_effect=[
                    {"code": 0, "data": []},
                    {"code": 500, "message": "fixture-error", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._battle_room_info(_Event(), "4", "empty-room"))
        error = await _collect(plugin._battle_room_info(_Event(), "5", "error-room"))
        invalid = await _collect(plugin._battle_room_info(_Event(), "未知", "room"))

        async def missing_token(_event):
            return None

        plugin._need_token = missing_token
        unbound = await _collect(plugin._battle_room_info(_Event(), "烽火", "room"))

        self.assertIn("未查询到", empty[0]["text"])
        self.assertIn("fixture-error", error[0]["text"])
        self.assertIn("模式仅支持", invalid[0]["text"])
        self.assertIn("尚未绑定账号", unbound[0]["text"])

    async def test_room_dispatch_shows_usage_and_keeps_management_blocked(self):
        plugin = self._plugin()

        usage = await _collect(plugin._dispatch(_Event(), "房间信息"))
        blocked = await _collect(plugin._dispatch(_Event(), "创建房间"))

        self.assertIn("房间信息 <烽火/全面> <对局房间ID>", usage[0]["text"])
        self.assertIn("没有创建、加入、退出、踢人等房间管理路由", blocked[0]["text"])

    def test_daily_supports_single_and_double_mode_envelopes(self):
        plugin = self._plugin()
        single = {"data": {"data": {"solDetail": {"recentGainDate": "20260813"}}}}
        both = {
            "sol": {"data": {"data": {"solDetail": {"recentGainDate": "20260813"}}}},
            "mp": {"data": {"data": {"mpDetail": {"recentDate": "20260813"}}}},
        }

        sol, mp = plugin._daily_details(single, "sol")
        self.assertEqual(sol["recentGainDate"], "20260813")
        self.assertIsNone(mp)
        sol, mp = plugin._daily_details(both, None)
        self.assertTrue(sol and mp)

    async def test_daily_empty_error_and_yesterday_date_guard(self):
        client = SimpleNamespace(
            daily_record=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"sol": {}, "mp": {}}},
                    {"code": 500, "message": "fixture-error", "data": None},
                    {
                        "code": 0,
                        "data": {"data": {"data": {"solDetail": {"recentGainDate": "20000101"}}}},
                    },
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._daily(_Event(), "", False))
        error = await _collect(plugin._daily(_Event(), "", False))
        yesterday = await _collect(plugin._daily(_Event(), "", True))

        self.assertIn("暂无日报", empty[0]["text"])
        self.assertIn("fixture-error", error[0]["text"])
        self.assertIn("暂无昨日收益", yesterday[0]["text"])

    async def test_daily_success_branch(self):
        client = SimpleNamespace(
            daily_record=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "data": {
                            "data": {
                                "solDetail": {
                                    "recentGainDate": "2026-08-14",
                                    "recentGain": 100,
                                    "userCollectionTop": {"list": []},
                                }
                            }
                        }
                    },
                }
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._daily(_Event(), "烽火", False))

        self.assertIn("三角洲日报", results[0]["text"])

    def test_weekly_adapter_parses_usage_trend_and_teammates(self):
        plugin = self._plugin()
        raw = {
            "data": {
                "data": {
                    "total_sol_num": 2,
                    "Rank_Score": 100,
                    "Gained_Price": 300,
                    "consume_Price": 100,
                    "Total_Price": "Monday-x-100,Tuesday-x-100,Sunday-x-200",
                    "total_mapid_num": "{'MapId':'100','inum':2}",
                    "total_ArmedForceId_num": "{'ArmedForceId':'10','inum':2}",
                    "friends": [{"friend_openid": "abcdef123456", "Friend_total_sol_num": 1}],
                }
            }
        }
        sol, mp, report = plugin._weekly_details(raw, "sol")
        data = plugin._build_weekly(_Event(), sol, mp, report, "sol", "20260809")

        self.assertEqual(data["solData"]["mostUsedMap"], "零号大坝-常规")
        self.assertEqual(data["solData"]["mostUsedOperator"], "红狼")
        self.assertEqual(data["solData"]["profitRatio"], "3.00")
        self.assertEqual(data["solData"]["teammates"][0]["name"], "...123456")
        self.assertEqual(data["dateDisplay"], "2026-08-09")

    async def test_weekly_empty_and_error_branches(self):
        client = SimpleNamespace(
            weekly_record=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"sol": {}, "mp": {}}},
                    {"code": 500, "message": "fixture-error", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._weekly(_Event(), ""))
        error = await _collect(plugin._weekly(_Event(), ""))

        self.assertIn("暂无周报", empty[0]["text"])
        self.assertIn("fixture-error", error[0]["text"])

    async def test_weekly_success_branch(self):
        client = SimpleNamespace(
            weekly_record=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {"data": {"data": {"total_sol_num": 2, "Gained_Price": 100}}},
                }
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._weekly(_Event(), "烽火 20260809"))

        self.assertIn("三角洲周报", results[0]["text"])

    async def test_map_stats_queries_both_modes_and_formats_data(self):
        client = SimpleNamespace(
            map_stats=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {"list": [{"mapId": "100", "mapName": "零号大坝-常规", "data": {"zdj": 2, "isescapednum": 1}}]},
                    },
                    {
                        "code": 0,
                        "data": {"list": [{"mapId": "200", "mapName": "烬区", "data": {"zdjnum": 4, "winnum": 3}}]},
                    },
                ]
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._map_stats(_Event(), ""))

        self.assertEqual(client.map_stats.await_count, 2)
        self.assertEqual(client.map_stats.await_args_list[0].args[1:], ("sol", "all"))
        self.assertEqual(client.map_stats.await_args_list[1].args[1:], ("mp", "all"))
        self.assertIn("撤离率 50.0%", results[0]["text"])
        self.assertIn("胜率 75.0%", results[1]["text"])

    async def test_map_stats_search_empty_and_error_branches(self):
        client = SimpleNamespace(
            map_stats=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"list": []}},
                    {"code": 0, "data": {"list": []}},
                    {"code": 500, "message": "fixture-error", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._map_stats(_Event(), "大坝"))
        error = await _collect(plugin._map_stats(_Event(), "烽火"))

        self.assertIn("未找到", empty[0]["text"])
        self.assertIn("fixture-error", error[0]["text"])

    async def test_money_formats_authoritative_currency_list(self):
        client = SimpleNamespace(
            money=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "list": [
                            {"item": "17020000010", "name": "哈夫币", "totalMoney": "1234567"},
                            {"item": "17888808889", "name": "三角券", "totalMoney": "88"},
                        ]
                    },
                }
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._money(_Event()))

        self.assertIn("哈夫币: 1,234,567", results[0]["text"])
        self.assertIn("三角券: 88", results[0]["text"])

    async def test_money_handles_empty_and_error_responses(self):
        client = SimpleNamespace(
            money=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"list": []}},
                    {"code": 500, "message": "货币服务异常"},
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._money(_Event()))
        error = await _collect(plugin._money(_Event()))

        self.assertIn("未查询到任何货币", empty[0]["text"])
        self.assertIn("货币服务异常", error[0]["text"])

    async def test_flows_without_type_queries_all_three_categories(self):
        async def flows(_token, type_id, page):
            fixtures = {
                "1": {"LoginArr": [{"indtEventTime": "2026-08-14 10:00", "SystemHardware": "PC", "vClientIP": "127.0.0.1"}]},
                "2": {"itemArr": [{"dtEventTime": "2026-08-14 11:00", "Name": "测试物品", "AddOrReduce": "+1", "Reason": "%E6%B5%8B%E8%AF%95"}]},
                "3": {"iMoneyArr": [{"dtEventTime": "2026-08-14 12:00", "AddOrReduce": "-20", "leftMoney": "9980", "Reason": "%E8%B4%AD%E4%B9%B0"}]},
            }
            return {"code": 0, "data": {"list": [fixtures[type_id]]}}

        client = SimpleNamespace(flows=AsyncMock(side_effect=flows))
        plugin = self._plugin(client)

        results = await _collect(plugin._flows(_Event(), "", "1"))

        self.assertEqual(client.flows.await_count, 3)
        self.assertEqual([call.args[1] for call in client.flows.await_args_list], ["1", "2", "3"])
        self.assertIn("设备流水", results[0]["text"])
        self.assertIn("测试物品", results[1]["text"])
        self.assertIn("购买", results[2]["text"])

    async def test_flows_handles_empty_and_error_responses(self):
        client = SimpleNamespace(
            flows=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"list": []}},
                    {"code": 500, "message": "流水服务异常"},
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._flows(_Event(), "设备", "1"))
        error = await _collect(plugin._flows(_Event(), "设备", "1"))

        self.assertIn("暂无记录", empty[0]["text"])
        self.assertIn("流水服务异常", error[0]["text"])

    async def test_collection_merges_owned_items_with_public_mapping(self):
        client = SimpleNamespace(
            collection=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {"data": {"userData": [{"ItemId": "1001"}], "weponData": [{"ItemId": "1002"}]}},
                }
            ),
            object_collection_map=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "list": [
                            {"id": "1001", "name": "测试皮肤", "type": "干员皮肤", "rare": "橙"},
                            {"id": "1002", "name": "测试枪皮", "type": "枪皮", "rare": "紫"},
                        ]
                    },
                }
            ),
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._collection(_Event(), "枪皮"))

        self.assertIn("枪皮", results[0]["text"])
        self.assertIn("共 1 件", results[0]["text"])

    async def test_collection_handles_empty_and_error_responses(self):
        client = SimpleNamespace(
            collection=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"data": {"userData": [], "weponData": []}}},
                    {"code": 500, "message": "藏品服务异常"},
                ]
            ),
            object_collection_map=AsyncMock(return_value={"code": 0, "data": {"list": []}}),
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._collection(_Event(), ""))
        error = await _collect(plugin._collection(_Event(), ""))

        self.assertIn("藏品库为空", empty[0]["text"])
        self.assertIn("藏品服务异常", error[0]["text"])

    async def test_place_info_maps_chinese_type_level_and_template_fields(self):
        client = SimpleNamespace(
            place_info=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "places": [
                            {
                                "placeType": "workbench",
                                "placeName": "工作台",
                                "level": 3,
                                "upgradeInfo": {"hafCount": 5000, "condition": "解锁等级30；完成任务"},
                                "upgradeRequired": [{"objectID": "2001", "count": 2}],
                                "unlockInfo": {"properties": {"list": ["制造速度提升"]}, "props": []},
                            }
                        ],
                        "relateMap": {"2001": {"objectName": "测试材料", "pic": "https://example.invalid/item.png"}},
                    },
                }
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._place_info(_Event(), "工作台 3"))

        self.assertEqual(client.place_info.await_args.args[1], "workbench")
        self.assertIn("工作台 Lv.3", results[0]["text"])

    async def test_place_info_handles_empty_and_error_responses(self):
        client = SimpleNamespace(
            place_info=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"places": [], "relateMap": {}}},
                    {"code": 500, "message": "特勤处服务异常"},
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._place_info(_Event(), "工作台"))
        error = await _collect(plugin._place_info(_Event(), "工作台"))

        self.assertIn("未查询到符合条件", empty[0]["text"])
        self.assertIn("特勤处服务异常", error[0]["text"])

    async def test_operator_detail_uses_ams_fields(self):
        client = SimpleNamespace(
            operators=AsyncMock(
                return_value={
                    "code": 0,
                    "data": [
                        {
                            "operator": "乌鲁鲁",
                            "fullName": "大卫·费莱尔",
                            "armyType": "工程",
                            "abilitiesList": [{"abilityName": "巡飞弹", "abilityDesc": "发射巡飞弹"}],
                        }
                    ],
                }
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._operator_info(_Event(), "乌鲁鲁"))

        client.operators.assert_awaited_once_with(detail=True)
        self.assertIn("乌鲁鲁", results[0]["text"])
        self.assertIn("巡飞弹", results[0]["text"])

    async def test_object_list_parses_default_category_page_and_formats_items(self):
        client = SimpleNamespace(
            object_list=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "list": [{"objectID": 1001, "objectName": "测试藏品", "primaryClass": "props", "secondClass": "collection", "avgPrice": 1234}],
                        "total": 21,
                        "page": 2,
                    },
                }
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._object_list(_Event(), "2"))

        client.object_list.assert_awaited_once_with("props", "collection", "2", "20")
        self.assertIn("第 2 页", results[0]["text"])
        self.assertIn("测试藏品（1001）", results[0]["text"])

    async def test_object_list_handles_empty_and_error_responses(self):
        client = SimpleNamespace(
            object_list=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"list": [], "total": 0, "page": 1}},
                    {"code": 500, "message": "物品列表服务异常", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._object_list(_Event(), ""))
        error = await _collect(plugin._object_list(_Event(), "props collection 1"))

        self.assertIn("未找到符合条件的物品", empty[0]["text"])
        self.assertIn("物品列表服务异常", error[0]["text"])

    async def test_price_and_material_outputs_use_current_response_fields(self):
        client = SimpleNamespace(
            object_search=AsyncMock(return_value={"code": 0, "data": {"list": [{"objectID": 1001}]}}),
            current_price=AsyncMock(return_value={"code": 0, "data": {"items": [{"objectID": 1001, "avgPrice": 4567}]}}),
            object_value_search=AsyncMock(),
            material_price=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {"materials": [{"objectID": 2001, "objectName": "测试材料", "price": 88}], "pagination": {"page": 1, "total": 1}},
                }
            ),
        )
        plugin = self._plugin(client)

        price = await _collect(plugin._price_now(_Event(), "测试物品"))
        material = await _collect(plugin._material_price(_Event(), "测试材料"))

        self.assertIn("4,567", price[0]["text"])
        self.assertIn("测试材料（2001） 88", material[0]["text"])

    async def test_price_queries_handle_empty_and_error_responses(self):
        client = SimpleNamespace(
            object_search=AsyncMock(return_value={"code": 0, "data": {"list": [{"objectID": 1001}]}}),
            current_price=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"items": []}},
                    {"code": 500, "message": "实时价格服务异常"},
                ]
            ),
            object_value_search=AsyncMock(return_value={"code": 500, "message": "价格后备服务异常"}),
            price_history_v2=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"items": []}},
                    {"code": 500, "message": "价格历史服务异常"},
                ]
            ),
            object_value_history=AsyncMock(return_value={"code": 500, "message": "历史后备服务异常"}),
            material_price=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"materials": []}},
                    {"code": 500, "message": "材料价格服务异常"},
                ]
            ),
        )
        plugin = self._plugin(client)

        current_empty = await _collect(plugin._price_now(_Event(), "测试物品"))
        current_error = await _collect(plugin._price_now(_Event(), "测试物品"))
        history_empty = await _collect(plugin._price_history(_Event(), "测试物品"))
        history_error = await _collect(plugin._price_history(_Event(), "测试物品"))
        material_empty = await _collect(plugin._material_price(_Event(), "测试材料"))
        material_error = await _collect(plugin._material_price(_Event(), "测试材料"))

        self.assertIn("未查询到", current_empty[0]["text"])
        self.assertIn("价格后备服务异常", current_error[0]["text"])
        self.assertIn("未查询到", history_empty[0]["text"])
        self.assertIn("历史后备服务异常", history_error[0]["text"])
        self.assertIn("未查询到符合条件", material_empty[0]["text"])
        self.assertIn("材料价格服务异常", material_error[0]["text"])

    async def test_profit_history_resolves_positional_item_and_days(self):
        client = SimpleNamespace(
            object_search=AsyncMock(return_value={"code": 0, "data": {"list": [{"objectID": 3001}]}}),
            object_value_search=AsyncMock(),
            profit_history=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "objectInfo": {"objectName": "测试制品", "placeName": "工作台", "level": 3, "period": 2},
                        "history": [{"timestamp": 123, "salePrice": 500, "totalProfit": 100, "hourProfit": 50}],
                        "days": 14,
                    },
                }
            ),
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._profit(_Event(), "利润历史", "测试制品 14天"))

        client.profit_history.assert_awaited_once_with({"objectID": "3001", "days": "14"})
        self.assertIn("测试制品利润历史", results[0]["text"])
        self.assertIn("时均 +50", results[0]["text"])

    async def test_profit_rank_parses_chinese_place_sort_and_limit(self):
        client = SimpleNamespace(
            profit_rank=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {"items": [{"rank": 1, "objectName": "测试制品", "placeName": "工作台", "level": 3, "hourProfit": 99}], "sortType": "hour"},
                }
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._profit(_Event(), "利润排行", "工作台 时均 5"))

        client.profit_rank.assert_awaited_once_with({"limit": "5", "place": "workbench", "type": "hour"})
        self.assertIn("测试制品", results[0]["text"])
        self.assertIn("+99", results[0]["text"])

    async def test_profit_queries_handle_empty_and_error_responses(self):
        client = SimpleNamespace(
            object_search=AsyncMock(return_value={"code": 0, "data": {"list": [{"objectID": 3001}]}}),
            object_value_search=AsyncMock(),
            profit_history=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"history": []}},
                    {"code": 500, "message": "利润历史服务异常"},
                ]
            ),
            profit_rank=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"items": []}},
                    {"code": 500, "message": "利润排行服务异常"},
                ]
            ),
            place_profit=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"manufacturingPlaces": []}},
                    {"code": 500, "message": "特勤处利润服务异常"},
                ]
            ),
        )
        plugin = self._plugin(client)

        history_empty = await _collect(plugin._profit(_Event(), "利润历史", "测试制品"))
        history_error = await _collect(plugin._profit(_Event(), "利润历史", "测试制品"))
        rank_empty = await _collect(plugin._profit(_Event(), "利润排行", ""))
        rank_error = await _collect(plugin._profit(_Event(), "利润排行", ""))
        place_empty = await _collect(plugin._profit(_Event(), "特勤处利润", ""))
        place_error = await _collect(plugin._profit(_Event(), "特勤处利润", ""))

        self.assertIn("暂无该物品", history_empty[0]["text"])
        self.assertIn("利润历史服务异常", history_error[0]["text"])
        self.assertIn("没有利润排行", rank_empty[0]["text"])
        self.assertIn("利润排行服务异常", rank_error[0]["text"])
        self.assertIn("没有特勤处利润", place_empty[0]["text"])
        self.assertIn("特勤处利润服务异常", place_error[0]["text"])

    async def test_ai_review_returns_content_and_accepts_numeric_mode_alias(self):
        client = SimpleNamespace(
            ai_review=AsyncMock(
                return_value={"code": 0, "data": {"content": "这是一段测试锐评。", "preset": "rp", "presetName": "锐评"}}
            )
        )
        plugin = self._plugin(client)

        results = await _collect(plugin._ai_review(_Event(), "4 rp", preset_required=True))

        client.ai_review.assert_awaited_once_with("fixture-token", "sol", "rp")
        self.assertIn("烽火地带 AI锐评", results[0]["text"])
        self.assertIn("这是一段测试锐评", results[0]["text"])

    async def test_ai_review_handles_empty_content_and_error_responses(self):
        client = SimpleNamespace(
            ai_review=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"content": ""}},
                    {"code": 500, "message": "AI 服务暂不可用", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        empty = await _collect(plugin._ai_review(_Event(), "sol"))
        error = await _collect(plugin._ai_review(_Event(), "mp"))

        self.assertIn("后端未返回正文", empty[0]["text"])
        self.assertIn("AI 服务暂不可用", error[0]["text"])

    async def test_daily_keyword_formats_success_unavailable_empty_and_error(self):
        client = SimpleNamespace(
            daily_keyword=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {"list": [{"mapName": "零号大坝", "secret": "1234"}]},
                    },
                    {
                        "code": 0,
                        "data": {"available": False, "message": "公共账号池暂无可用凭证"},
                    },
                    {"code": 0, "data": {"list": []}},
                    {"code": 500, "message": "密码服务异常", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        success = await _collect(plugin._daily_keyword(_Event()))
        unavailable = await _collect(plugin._daily_keyword(_Event()))
        empty = await _collect(plugin._daily_keyword(_Event()))
        error = await _collect(plugin._daily_keyword(_Event()))

        self.assertIn("【零号大坝】: 1234", success[0]["text"])
        self.assertIn("公共账号池暂无可用凭证", unavailable[0]["text"])
        self.assertIn("暂无可用密码数据", empty[0]["text"])
        self.assertIn("密码服务异常", error[0]["text"])

    async def test_articles_format_latest_fields_and_handle_empty_and_error(self):
        client = SimpleNamespace(
            article_list=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {
                            "articles": {
                                "list": {
                                    "notice": [
                                        {
                                            "threadID": 1001,
                                            "title": "测试公告",
                                            "author": "官方",
                                            "createdAt": "2026-08-14 12:00:00",
                                            "viewCount": 20,
                                            "likedCount": 3,
                                            "summary": "公告摘要",
                                        }
                                    ]
                                }
                            }
                        },
                    },
                    {"code": 0, "data": {"articles": {"list": {}}}},
                    {"code": 503, "message": "文章公共池不可用", "data": None},
                ]
            ),
            article_detail=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {
                            "article": {
                                "id": 1001,
                                "title": "测试公告",
                                "author": {"nickname": "官方作者"},
                                "createdAt": "2026-08-14 12:00:00",
                                "viewCount": 20,
                                "likedCount": 3,
                                "ext": {"gicpTags": ["公告", "活动"]},
                                "content": {"text": "<p>第一段&nbsp;正文</p>"},
                            }
                        },
                    },
                    {"code": 0, "data": {}},
                    {"code": 404, "message": "文章不存在", "data": None},
                ]
            ),
        )
        plugin = self._plugin(client)

        listing = await _collect(plugin._article_list(_Event()))
        list_empty = await _collect(plugin._article_list(_Event()))
        list_error = await _collect(plugin._article_list(_Event()))
        detail = await _collect(plugin._article_detail(_Event(), "1001"))
        detail_empty = await _collect(plugin._article_detail(_Event(), "1002"))
        detail_error = await _collect(plugin._article_detail(_Event(), "1003"))

        self.assertIn("测试公告", listing[0]["text"])
        self.assertIn("ID: 1001", listing[0]["text"])
        self.assertIn("暂无文章数据", list_empty[0]["text"])
        self.assertIn("文章公共池不可用", list_error[0]["text"])
        self.assertIn("官方作者", detail[0]["text"])
        self.assertIn("标签: 公告, 活动", detail[0]["text"])
        self.assertIn("第一段 正文", detail[0]["text"])
        self.assertIn("文章不存在或已删除", detail_empty[0]["text"])
        self.assertIn("文章不存在", detail_error[0]["text"])

    async def test_client_article_detail_uses_only_authoritative_thread_id(self):
        client = object.__new__(DeltaForceClient)
        client.get = AsyncMock(return_value={"code": 0})

        await client.article_detail("1001")

        self.assertEqual(client.get.await_args.args[0], "/api/v1/df/tools/article/detail")
        self.assertEqual(client.get.await_args.kwargs["params"], {"threadID": "1001"})

    async def test_ai_presets_success_empty_and_error(self):
        client = SimpleNamespace(
            ai_presets=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {
                            "presets": [
                                {"code": "rp", "name": "锐评", "isDefault": True}
                            ]
                        },
                    },
                    {"code": 0, "data": {"presets": []}},
                    {"code": 500, "message": "预设读取失败", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        success = await _collect(plugin._ai_presets(_Event()))
        empty = await _collect(plugin._ai_presets(_Event()))
        error = await _collect(plugin._ai_presets(_Event()))

        self.assertIn("锐评 - rp（默认）", success[0]["text"])
        self.assertIn("暂无可用", empty[0]["text"])
        self.assertIn("预设读取失败", error[0]["text"])

    async def test_object_search_and_operator_queries_handle_empty_and_error(self):
        client = SimpleNamespace(
            object_search=AsyncMock(
                side_effect=[
                    {"code": 0, "data": {"list": []}},
                    {"code": 500, "message": "物品服务异常", "data": None},
                ]
            ),
            operators=AsyncMock(
                side_effect=[
                    {"code": 0, "data": []},
                    {"code": 500, "message": "干员服务异常", "data": None},
                    {"code": 0, "data": []},
                    {"code": 500, "message": "干员详情异常", "data": None},
                ]
            ),
        )
        plugin = self._plugin(client)
        plugin.data_mgr.search_local_items = Mock(return_value=[])

        search_empty = await _collect(plugin._object_search(_Event(), "不存在"))
        search_error = await _collect(plugin._object_search(_Event(), "错误物品"))
        operator_empty = await _collect(plugin._operator_list(_Event()))
        operator_error = await _collect(plugin._operator_list(_Event()))
        detail_empty = await _collect(plugin._operator_info(_Event(), "不存在"))
        detail_error = await _collect(plugin._operator_info(_Event(), "乌鲁鲁"))

        self.assertIn("未搜索到", search_empty[0]["text"])
        self.assertIn("物品服务异常", search_error[0]["text"])
        self.assertIn("未查询到任何干员", operator_empty[0]["text"])
        self.assertIn("干员服务异常", operator_error[0]["text"])
        self.assertIn("未找到干员", detail_empty[0]["text"])
        self.assertIn("干员详情异常", detail_error[0]["text"])

    async def test_ban_history_formats_success_empty_and_expired_credentials(self):
        client = SimpleNamespace(
            ban_history=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": [
                            {
                                "game_name": "三角洲行动",
                                "zone": "烽火地带",
                                "type": "封禁",
                                "reason": "违规行为",
                                "strategy_desc": "安全处罚",
                                "start_stmp": 1_700_000_000,
                                "duration": 7200,
                                "cheat_date": 1_699_999_000,
                            }
                        ],
                    },
                    {"code": 0, "data": []},
                    {"code": 401, "message": "QQSafe 登录凭证无效或已失效", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        success = await _collect(plugin._ban_history(_Event()))
        empty = await _collect(plugin._ban_history(_Event()))
        expired = await _collect(plugin._ban_history(_Event()))

        self.assertIn("三角洲行动（烽火地带）", success[0]["text"])
        self.assertIn("持续时间: 2小时", success[0]["text"])
        self.assertIn("作弊时间:", success[0]["text"])
        self.assertIn("暂无违规记录", empty[0]["text"])
        self.assertIn("凭证无效或已失效", expired[0]["text"])

    async def test_server_status_displays_degraded_dependencies_and_errors(self):
        client = SimpleNamespace(
            health=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {
                            "status": "healthy",
                            "timestamp": "2026-08-14T09:00:00+08:00",
                            "uptime": 60,
                            "dependencies": {
                                "mongodb": {"status": "connected", "latencyMs": 3},
                                "redis": {"status": "connected"},
                            },
                            "system": {},
                        },
                    },
                    {
                        "code": 0,
                        "message": "degraded",
                        "data": {
                            "status": "degraded",
                            "timestamp": "2026-08-14T10:00:00+08:00",
                            "uptime": 3661,
                            "dependencies": {
                                "mongodb": {"status": "connected", "latencyMs": 12},
                                "redis": {"status": "disconnected"},
                            },
                            "system": {
                                "goVersion": "go1.25",
                                "platform": "windows",
                                "arch": "amd64",
                                "goroutines": 18,
                                "memory": {"heapUsedMB": 20, "heapTotalMB": 40, "sysMB": 64},
                            },
                        },
                    },
                    {"code": 0, "data": []},
                    {"code": 502, "message": "上游服务无响应", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)

        healthy = await _collect(plugin._server_status(_Event()))
        degraded = await _collect(plugin._server_status(_Event()))
        empty = await _collect(plugin._server_status(_Event()))
        error = await _collect(plugin._server_status(_Event()))

        self.assertIn("服务状态: 正常", healthy[0]["text"])
        self.assertIn("Redis: 已连接", healthy[0]["text"])
        self.assertIn("服务状态: 降级", degraded[0]["text"])
        self.assertIn("MongoDB: 已连接（延迟 12 ms）", degraded[0]["text"])
        self.assertIn("Redis: 未连接", degraded[0]["text"])
        self.assertIn("go1.25 / windows / amd64", degraded[0]["text"])
        self.assertIn("返回数据格式异常", empty[0]["text"])
        self.assertIn("上游服务无响应", error[0]["text"])

    async def test_health_info_renders_success_and_handles_empty_and_error(self):
        client = SimpleNamespace(
            object_health=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": [
                            {
                                "healthyDetail": {
                                    "deBuffList": [
                                        {
                                            "area": "左臂",
                                            "list": [{"name": "骨折"}, {"name": "流血"}, {"name": "疼痛"}],
                                        }
                                    ],
                                    "buffList": [{"name": "止痛"}],
                                }
                            }
                        ],
                    },
                    {"code": 0, "data": []},
                    {"code": 401, "message": "公共凭证已失效", "data": None},
                ]
            )
        )
        plugin = self._plugin(client)
        plugin.config["enable_image_render"] = True
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(return_value="D:/fixture-health.png"),
            res_path=(PLUGIN_DIR / "resources").resolve(),
        )

        success = await _collect(plugin._health_info(_Event()))
        plugin.config["enable_image_render"] = False
        empty = await _collect(plugin._health_info(_Event()))
        error = await _collect(plugin._health_info(_Event()))

        self.assertEqual(success[0]["type"], "image")
        render_call = plugin.renderer.render_html.await_args
        self.assertEqual(render_call.args[0], "Template/healthInfo/healthInfo.html")
        self.assertEqual(len(render_call.args[1]["deBuffList"]), 2)
        self.assertTrue(render_call.args[1]["deBuffList"][0]["isMerged"])
        self.assertIn("未查询到健康状态详细信息", empty[0]["text"])
        self.assertIn("公共凭证已失效", error[0]["text"])

    async def test_local_user_stats_counts_bindings_and_checks_admin(self):
        plugin = self._plugin()
        plugin.bindings = SimpleNamespace(
            _data={
                "user-1": [
                    {"login_type": "qq", "is_valid": True},
                    {"login_type": "wechat", "is_valid": False},
                ],
                "user-2": [{"token_type": "qqsafe", "is_valid": True}],
            }
        )

        stats = await _collect(plugin._user_stats(_Event()))
        plugin.bindings._data = {}
        empty = await _collect(plugin._user_stats(_Event()))

        class NormalEvent(_Event):
            def is_admin(self):
                return False

        denied = await _collect(plugin._user_stats(NormalEvent()))

        self.assertIn("AstrBot 本地用户统计", stats[0]["text"])
        self.assertIn("绑定用户数: 2", stats[0]["text"])
        self.assertIn("绑定账号数: 3", stats[0]["text"])
        self.assertIn("有效账号数: 2", stats[0]["text"])
        self.assertIn("绑定用户数: 0", empty[0]["text"])
        self.assertIn("绑定账号数: 0", empty[0]["text"])
        self.assertIn("只有管理员", denied[0]["text"])

    async def test_red_list_uses_latest_records_layer_and_handles_empty_and_error(self):
        client = SimpleNamespace(
            personal_info=AsyncMock(return_value={"code": 0, "data": {}}),
            red_list=AsyncMock(
                side_effect=[
                    {
                        "code": 0,
                        "data": {"records": {"list": [{"itemId": "1001", "num": 2}]}},
                    },
                    {"code": 0, "data": {"records": {"list": []}}},
                    {"code": 401, "message": "登录凭证已过期", "data": None},
                ]
            ),
        )
        plugin = self._plugin(client)
        plugin._object_info_map = AsyncMock(
            return_value={"1001": {"objectName": "非洲之心", "avgPrice": 1_000_000}}
        )
        plugin._uncollected_red_count = AsyncMock(return_value=5)
        plugin.config["enable_image_render"] = True
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(return_value="D:/fixture-red-list.png"),
            res_path=(PLUGIN_DIR / "resources").resolve(),
        )

        success = await _collect(plugin._red_list(_Event(), "fixture-token"))
        plugin.config["enable_image_render"] = False
        empty = await _collect(plugin._red_list(_Event(), "fixture-token"))
        error = await _collect(plugin._red_list(_Event(), "fixture-token"))

        self.assertEqual(success[0]["type"], "image")
        render_call = plugin.renderer.render_html.await_args
        self.assertEqual(render_call.args[0], "Template/redRecordList/redRecordList.html")
        self.assertEqual(render_call.args[1]["records"][0]["name"], "非洲之心")
        self.assertEqual(render_call.args[1]["statistics"]["redTotalCount"], "2")
        self.assertIn("还没有任何藏品解锁记录", empty[0]["text"])
        self.assertIn("登录凭证已过期", error[0]["text"])

    async def test_red_one_uses_item_data_layer_and_template(self):
        client = SimpleNamespace(
            personal_info=AsyncMock(return_value={"code": 0, "data": {}}),
            red_one=AsyncMock(
                return_value={
                    "code": 0,
                    "data": {
                        "objectId": "1001",
                        "itemData": {
                            "total": 2,
                            "list": [
                                {"time": "2026-08-13 12:00:00", "mapid": "100", "num": 1},
                                {"time": "2026-08-14 12:00:00", "mapid": "200", "num": 1},
                            ],
                        },
                    },
                }
            ),
        )
        plugin = self._plugin(client)
        plugin._object_info = AsyncMock(
            return_value={"objectID": "1001", "objectName": "非洲之心", "objectType": "藏品"}
        )
        plugin.config["enable_image_render"] = True
        plugin.renderer = SimpleNamespace(
            render_html=AsyncMock(return_value="D:/fixture-red-one.png"),
            res_path=(PLUGIN_DIR / "resources").resolve(),
        )

        result = await _collect(plugin._red_one(_Event(), "fixture-token", "非洲之心"))

        self.assertEqual(result[0]["type"], "image")
        render_call = plugin.renderer.render_html.await_args
        self.assertEqual(render_call.args[0], "Template/redRecord/redRecord.html")
        self.assertEqual(render_call.args[1]["recordCount"], 2)
        self.assertEqual(render_call.args[1]["firstUnlockMap"], "零号大坝-常规")
        client.red_one.assert_awaited_once_with("fixture-token", "1001")

    async def test_core_templates_compile_with_adapted_fixture(self):
        renderer = DeltaRenderer(str(PLUGIN_DIR / "resources"))
        fixtures = {
            "Template/personalData/personalData.html": {
                "season": "7",
                "userName": "测试玩家",
                "solDetail": {"mapList": [], "gunPlayList": [], "redCollectionList": []},
            },
            "Template/dailyReport/dailyReport.html": {
                "type": "daily",
                "mode": "sol",
                "solDetail": {"isEmpty": True},
            },
            "Template/weeklyReport/weeklyReport.html": {
                "dateDisplay": "2026-08-09",
                "solData": {"isEmpty": True},
            },
            "Template/mapStats/mapStats.html": {
                "type": "sol",
                "mapStatsList": [],
                "totalMaps": 0,
            },
            "Template/record/record.html": {"modeName": "烽火地带", "page": 1, "records": []},
            "Template/recordPush/recordPush.html": {
                "isRecent": True,
                "displayName": "测试玩家",
                "modeName": "烽火地带",
                "time": "2026-08-14 12:00:00",
                "map": "零号大坝-常规",
                "operator": "红狼",
                "mapBg": "imgs/map/烽火-零号大坝-常规.png",
                "operatorImg": "imgs/operator/红狼.png",
                "status": "撤离成功",
                "statusClass": "success",
                "duration": "2分5秒",
                "value": "250,000",
                "income": "100,000",
                "incomeClass": "income-positive",
                "killsHtml": '<span class="kill-item kill-player">玩家 3</span>',
                "rescue": 1,
            },
            "Template/flows/flows.html": {"typeName": "货币", "typeValue": 3, "page": 1, "moneyColumns": []},
            "Template/collection/collection.html": {"typeName": "所有藏品", "totalCount": 0, "qualityStats": [], "categories": []},
            "Template/placeInfo/placeInfo.html": {"places": []},
            "Template/operator/operator.html": {
                "operatorName": "乌鲁鲁",
                "fullName": "大卫·费莱尔",
                "operatorPic": "",
                "armyType": "工程",
                "armyTypeDesc": "战术破坏",
                "abilitiesList": [
                    {
                        "abilityName": "巡飞弹",
                        "abilityType": "战术装备",
                        "abilityTypeCN": "战术装备",
                        "abilityDesc": "发射巡飞弹攻击指定区域。",
                        "abilityPic": "",
                    }
                ],
            },
            "Template/redCollection/redCollection.html": {
                "userName": "测试玩家",
                "userAvatar": "",
                "qqAvatarUrl": "",
                "userRank": "烽火地带",
                "seasonDisplay": "所有赛季",
                "title": "血色会计",
                "subtitle": "测试描述",
                "unlockDesc": "测试解锁条件",
                "statistics": {
                    "redGodCount": "0",
                    "redTotalCount": "0",
                    "redTotalValue": "0",
                    "unlockedCount": "",
                },
                "topCollections": [],
                "unlockedCollections": [],
            },
            "Template/redRecordList/redRecordList.html": {
                "userName": "测试玩家",
                "userAvatar": "",
                "qqAvatarUrl": "",
                "userRank": "烽火地带",
                "statistics": {
                    "redGodCount": "0",
                    "redTotalCount": "0",
                    "redTotalValue": "0",
                    "unlockedCount": "",
                },
                "records": [],
                "totalRecords": 0,
            },
            "Template/redRecord/redRecord.html": {
                "userName": "测试玩家",
                "userAvatar": "",
                "qqAvatarUrl": "",
                "userRank": "烽火地带",
                "itemName": "测试物品",
                "itemType": "藏品",
                "itemImageUrl": "",
                "firstUnlockTime": "-",
                "firstUnlockMap": "-",
                "firstUnlockMapBg": "",
                "records": [],
                "recordCount": 0,
            },
            "Template/healthInfo/healthInfo.html": {
                "deBuffList": [],
                "buffList": [],
            },
            "help/version-info.html": {
                "name": "三角洲行动",
                "currentVersion": PLUGIN_VERSION,
                "changelogs": [
                    {
                        "version": PLUGIN_VERSION,
                        "date": "2026-08-14",
                        "sections": [{"title": "新增", "items": ["测试更新日志"]}],
                    }
                ],
            },
        }
        for asset in (
            "imgs/redCollection/bg.webp",
            "imgs/redCollection/dw_bg.png",
            "imgs/redCollection/red_bg2.png",
            "imgs/redCollection/red_tit.webp",
            "imgs/others/logo.png",
            "imgs/map/烽火-零号大坝-常规.png",
            "imgs/map/全面-烬区.jpg",
            "imgs/operator/红狼.png",
            "help/version-bg.jpg",
            "fonts/p-med.ttf",
            "fonts/p-bold.ttf",
        ):
            self.assertTrue((PLUGIN_DIR / "resources" / asset).is_file(), asset)
        try:
            for name, data in fixtures.items():
                with self.subTest(template=name):
                    source = renderer._read(name)
                    adapted = renderer._adapt(source)
                    try:
                        template = renderer._env.from_string(adapted)
                    except Exception as exc:
                        line = int(getattr(exc, "lineno", 1) or 1)
                        context = "\n".join(adapted.splitlines()[max(0, line - 2):line + 1])
                        self.fail(f"{name} 第 {line} 行无法编译：{exc}\n{context}")
                    html = template.render(_res_path="file:///fixture/", **data)
                    self.assertIn("<html", html, name)
        finally:
            await renderer.close()


if __name__ == "__main__":
    unittest.main()
