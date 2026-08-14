"""三角洲战绩订阅的本地目标存储。

后端只保存战绩订阅本身，AstrBot 的消息目标属于插件运行环境，因此单独
保存到 StarTools 数据目录，避免把用户会话信息写入插件源码目录。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrbot.api import logger


class SubscriptionStore:
    """使用 UTF-8 JSON 保存远程订阅与 AstrBot UMO 推送目标。"""

    def __init__(self, data_dir: str):
        self.path = Path(data_dir).resolve() / "deltaforce_subscriptions.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {"subscriptions": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("subscriptions"), dict):
                self._data = raw
        except Exception as exc:
            logger.warning(f"[三角洲订阅] 读取本地订阅失败：{type(exc).__name__}")

    def _save(self) -> None:
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

    @staticmethod
    def _key(user_id: Any, binding_id: Any) -> str:
        return f"{str(user_id or '').strip()}::{str(binding_id or '').strip()}"

    def get(self, user_id: Any, binding_id: Any) -> Optional[Dict[str, Any]]:
        item = self._data["subscriptions"].get(self._key(user_id, binding_id))
        return dict(item) if isinstance(item, dict) else None

    def upsert(self, user_id: Any, binding_id: Any, values: Dict[str, Any]) -> Dict[str, Any]:
        key = self._key(user_id, binding_id)
        old = self._data["subscriptions"].get(key)
        item = dict(old) if isinstance(old, dict) else {}
        item.update(values or {})
        item["user_id"] = str(user_id or "")
        item["binding_id"] = str(binding_id or "")
        item.setdefault("targets", {})
        item["updated_at"] = int(time.time())
        self._data["subscriptions"][key] = item
        self._save()
        return dict(item)

    def remove(self, user_id: Any, binding_id: Any) -> None:
        self._data["subscriptions"].pop(self._key(user_id, binding_id), None)
        self._save()

    def all(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._data["subscriptions"].values() if isinstance(item, dict)]

    def set_target(self, user_id: Any, binding_id: Any, umo: str, kind: str, enabled: bool) -> Dict[str, Any]:
        item = self.get(user_id, binding_id) or {"targets": {}}
        targets = item.get("targets") if isinstance(item.get("targets"), dict) else {}
        target = targets.get(umo) if isinstance(targets.get(umo), dict) else {}
        target[kind] = bool(enabled)
        target["updated_at"] = int(time.time())
        targets[umo] = target
        item["targets"] = targets
        return self.upsert(user_id, binding_id, item)

    def enabled_targets(self, user_id: Any = None, binding_id: Any = None) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        for item in self.all():
            if user_id is not None and str(item.get("user_id")) != str(user_id):
                continue
            if binding_id is not None and str(item.get("binding_id")) != str(binding_id):
                continue
            targets = item.get("targets") if isinstance(item.get("targets"), dict) else {}
            for umo, flags in targets.items():
                if not isinstance(flags, dict):
                    continue
                if flags.get("group") or flags.get("private"):
                    result.append({"umo": str(umo), "binding_id": str(item.get("binding_id") or "")})
        return result
