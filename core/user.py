import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrbot.api import logger


class BindingManager:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "deltaforce_bindings.json"
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        self._load()

    def _load(self):
        if not self.path.exists():
            self._data = {}
            return
        try:
            data = json.loads(self.path.read_text("utf-8", errors="replace"))
            self._data = data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning(f"[DeltaForce User] 读取绑定文件失败: {exc}")
            self._data = {}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path)

    @staticmethod
    def _uid(user_id: Any) -> str:
        return str(user_id or "").strip()

    async def get_user_bindings(self, user_id: Any) -> List[Dict[str, Any]]:
        return [dict(x) for x in self._data.get(self._uid(user_id), [])]

    async def get_primary_binding(self, user_id: Any) -> Optional[Dict[str, Any]]:
        bindings = await self.get_user_bindings(user_id)
        if not bindings:
            return None
        for item in bindings:
            if item.get("is_primary"):
                return item
        return bindings[0]

    async def upsert_binding(self, user_id: Any, binding: Dict[str, Any]) -> Dict[str, Any]:
        uid = self._uid(user_id)
        bindings = self._data.setdefault(uid, [])
        now = int(time.time())
        item = self._normalize(binding)
        item.setdefault("created_at", now)
        item["updated_at"] = now

        match_index = -1
        for idx, old in enumerate(bindings):
            if item.get("binding_id") and old.get("binding_id") == item.get("binding_id"):
                match_index = idx
                break
            if item.get("framework_token") and old.get("framework_token") == item.get("framework_token"):
                match_index = idx
                break

        if match_index >= 0:
            merged = dict(bindings[match_index])
            merged.update({k: v for k, v in item.items() if v not in (None, "")})
            item = merged
            bindings[match_index] = item
        else:
            if not item.get("binding_id"):
                item["binding_id"] = f"local-{uuid.uuid4().hex[:12]}"
            item["is_primary"] = not bindings
            bindings.insert(0, item)

        if item.get("is_primary"):
            for old in bindings:
                if old is not item:
                    old["is_primary"] = False
        elif not any(x.get("is_primary") for x in bindings):
            bindings[0]["is_primary"] = True

        self._save()
        return dict(item)

    async def set_primary(self, user_id: Any, index: int) -> Optional[Dict[str, Any]]:
        uid = self._uid(user_id)
        bindings = self._data.get(uid, [])
        if index < 1 or index > len(bindings):
            return None
        for item in bindings:
            item["is_primary"] = False
        bindings[index - 1]["is_primary"] = True
        self._save()
        return dict(bindings[index - 1])

    async def delete_binding(self, user_id: Any, index: int) -> Optional[Dict[str, Any]]:
        uid = self._uid(user_id)
        bindings = self._data.get(uid, [])
        if index < 1 or index > len(bindings):
            return None
        removed = bindings.pop(index - 1)
        if bindings and not any(x.get("is_primary") for x in bindings):
            bindings[0]["is_primary"] = True
        self._save()
        return dict(removed)

    async def update_token(self, user_id: Any, binding_id: str, framework_token: str) -> bool:
        bindings = self._data.get(self._uid(user_id), [])
        for item in bindings:
            if item.get("binding_id") == binding_id:
                item["framework_token"] = framework_token
                item["updated_at"] = int(time.time())
                self._save()
                return True
        return False

    @staticmethod
    def _normalize(binding: Dict[str, Any]) -> Dict[str, Any]:
        source = dict(binding or {})
        if "binding" in source and isinstance(source["binding"], dict):
            source = source["binding"]
        return {
            "binding_id": str(source.get("binding_id") or source.get("id") or source.get("_id") or ""),
            "framework_token": str(source.get("framework_token") or source.get("frameworkToken") or ""),
            "token_type": str(source.get("token_type") or source.get("tokenType") or source.get("login_type") or ""),
            "login_type": str(source.get("login_type") or source.get("loginType") or source.get("token_type") or ""),
            "nickname": str(source.get("nickname") or source.get("charac_name") or source.get("name") or ""),
            "avatar": str(source.get("avatar") or source.get("picurl") or ""),
            "delta_uid": str(source.get("delta_uid") or source.get("uid") or source.get("role_id") or ""),
            "delta_openid": str(source.get("delta_openid") or source.get("openid") or ""),
            "is_primary": bool(source.get("is_primary") or source.get("isPrimary") or False),
            "is_valid": source.get("is_valid", source.get("isValid", True)),
        }
