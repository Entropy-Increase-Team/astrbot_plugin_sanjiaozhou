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
            from collections import Counter

            from astrbot_plugin_sanjiaozhou.core.version import PLUGIN_VERSION
            from astrbot_plugin_sanjiaozhou.main import (
                DELTA_COMMAND_SPECS,
                DeltaForcePlugin,
            )
            from astrbot.core.star.filter.command import CommandFilter
            from astrbot.core.star.filter.regex import RegexFilter
            from astrbot.core.star.star import star_registry
            from astrbot.core.star.star_handler import star_handlers_registry


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

            assert len(handlers) == len(DELTA_COMMAND_SPECS) == 82
            assert len(command_filters) == 82
            assert not regex_filters
            assert not duplicates
            assert not spaced_names
            assert hit_counts and set(hit_counts) == {1}
            assert len(metadata) == 1
            assert metadata[0].version == PLUGIN_VERSION
            assert metadata[0].star_cls_type is DeltaForcePlugin
            print("REAL_ASTRBOT_REGISTRATION_OK")
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
            timeout=90,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            f"真实 AstrBot 注册测试失败。\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )
        self.assertIn("REAL_ASTRBOT_REGISTRATION_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
