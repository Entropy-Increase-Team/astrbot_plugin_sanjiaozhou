import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


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
    components.Record = _Record
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
from astrbot_plugin_sanjiaozhou.core.render import DeltaRenderer  # noqa: E402
from astrbot_plugin_sanjiaozhou.main import DeltaForcePlugin  # noqa: E402


class _Event:
    def get_sender_id(self):
        return "fixture-user"

    def plain_result(self, text):
        return {"type": "plain", "text": text}


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
        return str(value or "")


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

    async def test_client_uses_authoritative_record_and_map_parameters(self):
        client = object.__new__(DeltaForceClient)
        client.get = AsyncMock(return_value={"code": 0, "data": {}})

        await client.record("fixture-token", "4", "2")
        self.assertEqual(client.get.await_args.args[0], "/api/v1/df/person/record")
        self.assertEqual(client.get.await_args.kwargs["params"]["page"], "2")

        await client.map_stats("fixture-token", "sol", "all", "100")
        params = client.get.await_args.kwargs["params"]
        self.assertEqual(params, {"type": "sol", "serial": "all", "mapId": "100"})

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
        }
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
