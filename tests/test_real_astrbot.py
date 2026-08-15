import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
ASTRBOT_ROOT = PLUGIN_DIR.parents[2]


@unittest.skipUnless(
    os.environ.get("DELTA_REAL_ASTRBOT_TESTS") == "1",
    "未启用 DELTA_REAL_ASTRBOT_TESTS，跳过真实 AstrBot 注册测试。",
)
class RealAstrBotRegistrationTests(unittest.TestCase):
    def test_real_import_and_command_registration(self):
        script = textwrap.dedent(
            """
            import asyncio
            import importlib
            from collections import Counter
            from pathlib import Path
            from types import SimpleNamespace
            from unittest.mock import AsyncMock, patch

            from astrbot_plugin_sanjiaozhou.core.version import PLUGIN_VERSION
            from astrbot_plugin_sanjiaozhou.main import (
                DELTA_COMMAND_SPECS,
                DeltaForcePlugin,
            )
            from astrbot_plugin_sanjiaozhou.core.data import DeltaDataManager
            from astrbot.core.star.filter.command import CommandFilter
            from astrbot.core.star.filter.regex import RegexFilter
            from astrbot.core.star import command_management
            from astrbot.core.star.context import Context
            from astrbot.core.star.star import star_registry
            from astrbot.core.star.star_handler import star_handlers_registry
            from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
                AiocqhttpAdapter,
            )
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
                AiocqhttpMessageEvent,
            )
            from astrbot.core.star.session_plugin_manager import SessionPluginManager


            class Event:
                is_at_or_wake_command = True

                def __init__(self, message):
                    self.message = message
                    self.extra = {}

                def get_message_str(self):
                    return self.message

                def set_extra(self, key, value):
                    self.extra[key] = value


            module_name = "astrbot_plugin_sanjiaozhou.main"
            handlers = star_handlers_registry.get_handlers_by_module_name(module_name)
            command_filters = [
                item
                for handler in handlers
                for item in handler.event_filters
                if isinstance(item, CommandFilter)
            ]
            regex_filters = [
                item
                for handler in handlers
                for item in handler.event_filters
                if isinstance(item, RegexFilter)
            ]
            all_names = [
                name
                for item in command_filters
                for name in [item.command_name, *item.alias]
            ]
            duplicates = [
                name for name, count in Counter(all_names).items() if count > 1
            ]
            spaced_names = [
                name for name in all_names if any(char.isspace() for char in name)
            ]
            metadata = [item for item in star_registry if item.name == "sanjiaozhou"]

            hit_counts = []
            for name in all_names:
                hits = sum(
                    item.filter(Event(name + " 示例参数"), {})
                    for item in command_filters
                )
                hit_counts.append(hits)

            assert len(handlers) == len(DELTA_COMMAND_SPECS) == 108
            assert len(command_filters) == 108
            assert len(all_names) == 369
            assert not regex_filters
            assert not duplicates
            assert not spaced_names
            assert hit_counts and set(hit_counts) == {1}
            assert len(metadata) == 1
            assert metadata[0].version == PLUGIN_VERSION
            assert metadata[0].star_cls_type is DeltaForcePlugin


            class PipelineEvent(Event):
                def __init__(self, message):
                    super().__init__(message)
                    self.message_str = message
                    self._extras = self.extra
                    self.is_at_or_wake_command = False
                    self.is_wake = False
                    self.role = "member"
                    self.plugins_name = None
                    self.unified_msg_origin = "fixture:private:prefix"
                    self.stopped = False

                def get_message_str(self):
                    return self.message_str

                def get_messages(self):
                    return []

                def get_sender_id(self):
                    return "fixture-user"

                def get_self_id(self):
                    return "fixture-bot"

                def is_private_chat(self):
                    return True

                def get_extra(self, key=None, default=None):
                    if key is None:
                        return self._extras if self._extras else default
                    return self._extras.get(key, default)

                async def send(self, _result):
                    return None

                def stop_event(self):
                    self.stopped = True


            async def verify_wake_prefix():
                context = SimpleNamespace(
                    astrbot_config={
                        "admins_id": [],
                        "wake_prefix": ["!!"],
                        "plugin_set": ["sanjiaozhou"],
                        "disable_builtin_commands": False,
                        "platform_settings": {
                            "no_permission_reply": True,
                            "friend_message_needs_wake_prefix": True,
                            "ignore_bot_self_message": False,
                            "ignore_at_all": False,
                            "unique_session": False,
                        },
                    }
                )
                stage = WakingCheckStage()
                await stage.initialize(context)
                event = PipelineEvent("!!数据 烽火 2")

                async def passthrough(_event, handlers):
                    return handlers

                with patch.object(
                    SessionPluginManager,
                    "filter_handlers_by_session",
                    new=passthrough,
                ):
                    await stage.process(event)

                activated = event.get_extra("activated_handlers", [])
                parsed = event.get_extra("handlers_parsed_params", {})
                assert event.is_at_or_wake_command
                assert event.message_str == "数据 烽火 2"
                assert DeltaForcePlugin._message(None, event) == "数据 烽火 2"
                assert len(activated) == 1
                assert len(parsed) == 1
                active_commands = [
                    item.command_name
                    for item in activated[0].event_filters
                    if isinstance(item, CommandFilter)
                ]
                assert active_commands == ["数据"]


            async def verify_cross_plugin_conflict_resolution():
                for module in (
                    "astrbot_plugin_endfield.main",
                    "astrbot.builtin_stars.builtin_commands.main",
                ):
                    importlib.import_module(module)

                context = SimpleNamespace(
                    astrbot_config={
                        "admins_id": [],
                        "wake_prefix": ["!!"],
                        "plugin_set": ["*"],
                        "disable_builtin_commands": False,
                        "platform_settings": {
                            "no_permission_reply": True,
                            "friend_message_needs_wake_prefix": True,
                            "ignore_bot_self_message": False,
                            "ignore_at_all": False,
                            "unique_session": False,
                        },
                    }
                )
                stage = WakingCheckStage()
                await stage.initialize(context)

                async def passthrough(_event, active_handlers):
                    return active_handlers

                async def wake(message):
                    event = PipelineEvent("!!" + message)
                    with patch.object(
                        SessionPluginManager,
                        "filter_handlers_by_session",
                        new=passthrough,
                    ):
                        await stage.process(event)
                    return event.get_extra("activated_handlers", [])

                def plugin_hits(active_handlers):
                    return [
                        handler
                        for handler in active_handlers
                        if handler.handler_module_path == module_name
                    ]

                before = {
                    "help": await wake("help"),
                    "tts": await wake("tts 麦晓雯 你好"),
                    "干员列表": await wake("干员列表"),
                }
                assert len(plugin_hits(before["help"])) == 1
                assert len(plugin_hits(before["tts"])) == 1
                assert len(plugin_hits(before["干员列表"])) == 1
                assert len(before["help"]) == 2
                assert len(before["tts"]) == 2
                assert len(before["干员列表"]) == 2

                target_handlers = {}
                for handler in handlers:
                    command_filter = next(
                        (
                            item
                            for item in handler.event_filters
                            if isinstance(item, CommandFilter)
                        ),
                        None,
                    )
                    if command_filter:
                        target_handlers[command_filter.command_name] = handler

                configs = {}

                async def get_config(handler_full_name):
                    return configs.get(handler_full_name)

                async def upsert_config(**kwargs):
                    config = SimpleNamespace(**kwargs)
                    configs[config.handler_full_name] = config
                    return config

                async def get_configs():
                    return list(configs.values())

                async def delete_configs(_handler_full_names):
                    return None

                help_filter = next(
                    item for item in command_filters if item.command_name == "帮助"
                )
                help_aliases = sorted(help_filter.alias - {"help"})

                with (
                    patch.object(
                        command_management.db_helper,
                        "get_command_config",
                        new=get_config,
                    ),
                    patch.object(
                        command_management.db_helper,
                        "upsert_command_config",
                        new=upsert_config,
                    ),
                    patch.object(
                        command_management.db_helper,
                        "get_command_configs",
                        new=get_configs,
                    ),
                    patch.object(
                        command_management.db_helper,
                        "delete_command_configs",
                        new=delete_configs,
                    ),
                ):
                    await command_management.rename_command(
                        target_handlers["帮助"].handler_full_name,
                        "帮助",
                        help_aliases,
                    )
                    await command_management.rename_command(
                        target_handlers["干员列表"].handler_full_name,
                        "三角洲干员列表",
                        [],
                    )
                    await command_management.rename_command(
                        target_handlers["tts"].handler_full_name,
                        "三角洲tts",
                        [],
                    )

                assert not plugin_hits(await wake("help"))
                assert len(plugin_hits(await wake("帮助"))) == 1
                assert not plugin_hits(await wake("tts 麦晓雯 你好"))
                assert len(plugin_hits(await wake("三角洲tts 麦晓雯 你好"))) == 1
                assert not plugin_hits(await wake("干员列表"))
                assert len(plugin_hits(await wake("三角洲干员列表"))) == 1


            async def verify_record_push_platform_delivery():
                callback_event = object.__new__(AiocqhttpMessageEvent)
                callback_event.platform_meta = SimpleNamespace(name="aiocqhttp")
                callback_event.message_obj = SimpleNamespace(message_id="789")
                callback_event.bot = SimpleNamespace(delete_msg=AsyncMock())
                assert await DeltaForcePlugin._recall_oauth_callback(callback_event)
                callback_event.bot.delete_msg.assert_awaited_once_with(message_id=789)

                credential_event = object.__new__(AiocqhttpMessageEvent)
                credential_event.platform_meta = SimpleNamespace(name="aiocqhttp")
                credential_event.message_obj = SimpleNamespace(message_id="790")
                credential_event.bot = SimpleNamespace(delete_msg=AsyncMock())
                assert await DeltaForcePlugin._recall_sensitive_message(
                    credential_event,
                    "Cookie 凭证",
                )
                credential_event.bot.delete_msg.assert_awaited_once_with(message_id=790)

                adapter = AiocqhttpAdapter(
                    {
                        "id": "fixture-aiocqhttp",
                        "ws_reverse_host": "127.0.0.1",
                        "ws_reverse_port": 0,
                        "ws_reverse_token": "",
                    },
                    {},
                    asyncio.Queue(),
                )
                bot = SimpleNamespace(
                    send_group_msg=AsyncMock(),
                    send_private_msg=AsyncMock(),
                )
                adapter.bot = bot

                context = object.__new__(Context)
                context.platform_manager = SimpleNamespace(platform_insts=[adapter])

                plugin = object.__new__(DeltaForcePlugin)
                plugin.context = context
                plugin.config = {"enable_image_render": True}
                plugin_path = Path(importlib.import_module(module_name).__file__).resolve().parent
                plugin.renderer = SimpleNamespace(
                    render_html=AsyncMock(
                        return_value=str(plugin_path / "resources" / "imgs" / "others" / "logo.png")
                    )
                )
                plugin.subscriptions = SimpleNamespace(
                    all=lambda: [
                        {
                            "subscription_id": "fixture-subscription",
                            "targets": {
                                "fixture-aiocqhttp:GroupMessage:123": {"group": True},
                                "fixture-aiocqhttp:FriendMessage:456": {"private": True},
                            },
                        }
                    ]
                )
                plugin._seen_record_events = {}

                event_data = {
                    "subscription_id": "fixture-subscription",
                    "record_id": "fixture-record",
                    "record_type": "sol",
                    "event_time": "2026-08-15T10:00:00Z",
                    "display_name": "真实路由测试玩家",
                    "is_recent": True,
                    "record": {
                        "MapId": "100",
                        "MapName": "零号大坝-常规",
                        "ArmedForceId": "10",
                        "EscapeFailReason": 1,
                        "DurationS": 125,
                        "FinalPrice": 250000,
                        "flowCalGainedPrice": 100000,
                        "KillCount": 3,
                    },
                }

                plugin.data_mgr = DeltaDataManager(
                    str(plugin_path),
                    str(plugin_path / "config"),
                )
                with patch(
                    "astrbot.core.platform.platform.Metric.upload",
                    new=AsyncMock(),
                ):
                    await plugin._push_record_event(event_data)
                    await plugin._push_record_event(event_data)

                bot.send_group_msg.assert_awaited_once()
                bot.send_private_msg.assert_awaited_once()
                assert bot.send_group_msg.await_args.kwargs["group_id"] == 123
                assert bot.send_private_msg.await_args.kwargs["user_id"] == 456

                for call in (
                    bot.send_group_msg.await_args,
                    bot.send_private_msg.await_args,
                ):
                    payload = call.kwargs["message"]
                    assert [item["type"] for item in payload] == ["text", "image"]
                    assert "真实路由测试玩家" in payload[0]["data"]["text"]
                    assert "零号大坝" in payload[0]["data"]["text"]
                    assert payload[1]["data"]["file"].startswith("base64://")
                    assert len(payload[1]["data"]["file"]) > 100


            asyncio.run(verify_wake_prefix())
            asyncio.run(verify_cross_plugin_conflict_resolution())
            asyncio.run(verify_record_push_platform_delivery())
            print("REAL_ASTRBOT_REGISTRATION_OK")
            print("REAL_ASTRBOT_WAKE_PREFIX_OK")
            print("REAL_ASTRBOT_CONFLICT_RESOLUTION_OK")
            print("REAL_ASTRBOT_RECORD_PUSH_DELIVERY_OK")
            """
        )
        env = os.environ.copy()
        python_paths = [str(ASTRBOT_ROOT), str(PLUGIN_DIR.parent)]
        if env.get("PYTHONPATH"):
            python_paths.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        env["PYTHONUTF8"] = "1"

        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ASTRBOT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            f"真实 AstrBot 注册测试失败。\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn("REAL_ASTRBOT_REGISTRATION_OK", result.stdout)
        self.assertIn("REAL_ASTRBOT_WAKE_PREFIX_OK", result.stdout)
        self.assertIn("REAL_ASTRBOT_CONFLICT_RESOLUTION_OK", result.stdout)
        self.assertIn("REAL_ASTRBOT_RECORD_PUSH_DELIVERY_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
