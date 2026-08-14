import json
from typing import Any, Dict, Optional

import httpx
from astrbot.api import logger


DEFAULT_URLS = {
    "default": "https://delta-test-api.shallow.ink",
    "eo": "https://delta-test-api.shallow.ink",
    "esa": "https://delta-test-api.shallow.ink",
}


class DeltaForceClient:
    def __init__(
        self,
        api_key: str = "",
        api_mode: str = "auto",
        api_base_url: str = "",
        timeout: float = 30.0,
    ):
        self.api_key = (api_key or "").strip()
        self.api_mode = (api_mode or "auto").strip().lower()
        self.api_base_url = (api_base_url or "").strip().rstrip("/")
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        await self.client.aclose()

    @staticmethod
    def ok(res: Any) -> bool:
        if not isinstance(res, dict):
            return False
        if res.get("code") == 0 or res.get("success") is True:
            return True
        data = res.get("data")
        return isinstance(data, dict) and (data.get("code") == 0 or data.get("success") is True)

    @staticmethod
    def data(res: Any, default: Any = None) -> Any:
        if isinstance(res, dict) and "data" in res:
            return res.get("data")
        return default

    def _base_urls(self):
        if self.api_mode == "custom" and self.api_base_url:
            return [self.api_base_url]
        if self.api_mode == "default":
            return [DEFAULT_URLS["default"]]
        if self.api_mode in ("eo", "esa"):
            return [DEFAULT_URLS[self.api_mode]]
        urls = [DEFAULT_URLS["eo"], DEFAULT_URLS["esa"], DEFAULT_URLS["default"]]
        return list(dict.fromkeys(urls))

    def _headers(
        self,
        framework_token: str = "",
        user_identifier: str = "",
        client_id: str = "",
        json_body: bool = False,
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {"User-Agent": "astrbot-plugin-deltaforce/0.4.0"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if framework_token:
            headers["X-Framework-Token"] = framework_token
        if user_identifier:
            headers["X-User-Identifier"] = user_identifier
        if client_id:
            headers["X-Client-ID"] = client_id
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _normalize_params(self, params: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not params:
            return None
        result: Dict[str, Any] = {}
        for key, value in params.items():
            if value is None or value == "":
                continue
            if isinstance(value, (list, tuple, dict)):
                result[key] = json.dumps(value, ensure_ascii=False)
            else:
                result[key] = value
        return result

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        framework_token: str = "",
        user_identifier: str = "",
        client_id: str = "",
        require_key: bool = True,
    ) -> Dict[str, Any]:
        if require_key and (not self.api_key or self.api_key == "sk-xxxxxxx"):
            return {"code": 1000, "message": "API Key 未配置，请在插件配置中填写 api_key。", "data": None}

        clean_path = path if path.startswith("/") else f"/{path}"
        method = method.upper()
        retryable = method in {"GET", "HEAD", "OPTIONS"}
        last_error: Dict[str, Any] = {"code": -1, "message": "未发起请求", "data": None}

        for base_url in self._base_urls():
            url = f"{base_url.rstrip('/')}{clean_path}"
            headers = self._headers(
                framework_token=framework_token,
                user_identifier=user_identifier,
                client_id=client_id,
                json_body=json_data is not None,
            )
            try:
                resp = await self.client.request(
                    method,
                    url,
                    params=self._normalize_params(params),
                    json=json_data,
                    headers=headers,
                )
                try:
                    body = resp.json()
                except ValueError:
                    body = {"code": resp.status_code, "message": resp.text, "data": None}

                if 200 <= resp.status_code < 300:
                    return body if isinstance(body, dict) else {"code": 0, "message": "成功", "data": body}

                message = body.get("message") or body.get("msg") or resp.reason_phrase if isinstance(body, dict) else resp.text
                last_error = {
                    "code": resp.status_code,
                    "message": message,
                    "data": body if isinstance(body, dict) else None,
                }
                if resp.status_code < 500 or not retryable:
                    return last_error
            except httpx.RequestError as exc:
                last_error = {"code": -1, "message": "网络请求失败，请稍后重试。", "data": None}
                logger.warning(
                    f"[DeltaForce API] {method} {clean_path} 请求失败：{type(exc).__name__}"
                )
                if not retryable:
                    return last_error

        return last_error

    async def get(self, path: str, **kwargs) -> Dict[str, Any]:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> Dict[str, Any]:
        return await self.request("POST", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> Dict[str, Any]:
        return await self.request("DELETE", path, **kwargs)

    async def list_bindings(self, user_identifier: str, client_id: str, client_type: str = "bot"):
        return await self.get(
            "/api/v1/user/bindings",
            params={"user_identifier": user_identifier, "client_id": client_id, "client_type": client_type},
            user_identifier=user_identifier,
            client_id=client_id,
        )

    async def create_binding(self, framework_token: str, user_identifier: str, client_id: str, client_type: str = "bot"):
        return await self.post(
            "/api/v1/user/bindings",
            json_data={
                "framework_token": framework_token,
                "user_identifier": user_identifier,
                "client_type": client_type,
                "client_id": client_id,
            },
            user_identifier=user_identifier,
            client_id=client_id,
        )

    async def delete_binding(self, binding_id: str, user_identifier: str, client_id: str):
        return await self.delete(
            f"/api/v1/user/bindings/{binding_id}",
            params={"user_identifier": user_identifier, "client_id": client_id},
            user_identifier=user_identifier,
            client_id=client_id,
        )

    async def set_primary_binding(self, binding_id: str, user_identifier: str, client_id: str):
        return await self.post(
            f"/api/v1/user/bindings/{binding_id}/primary",
            params={"user_identifier": user_identifier, "client_id": client_id},
            user_identifier=user_identifier,
            client_id=client_id,
        )

    async def refresh_binding(self, binding_id: str, user_identifier: str, client_id: str):
        return await self.post(
            f"/api/v1/user/bindings/{binding_id}/refresh",
            params={"user_identifier": user_identifier, "client_id": client_id},
            user_identifier=user_identifier,
            client_id=client_id,
        )

    async def login_qr(self, platform: str):
        return await self.get(f"/api/v1/login/{platform}/qr")

    async def login_status(self, platform: str, framework_token: str):
        return await self.get(f"/api/v1/login/{platform}/status", framework_token=framework_token)

    async def login_token_status(self, platform: str, framework_token: str):
        return await self.get(f"/api/v1/login/{platform}/token", framework_token=framework_token)

    async def login_refresh(self, platform: str, framework_token: str):
        return await self.get(f"/api/v1/login/{platform}/refresh", framework_token=framework_token)

    async def login_delete(self, platform: str, framework_token: str):
        return await self.delete(f"/api/v1/login/{platform}/token", framework_token=framework_token)

    async def login_cookie(self, cookie: str):
        return await self.post("/api/v1/login/qq/ck", json_data={"cookie": cookie})

    async def oauth_url(self, platform: str, platform_id: str = "", bot_id: str = ""):
        return await self.get(
            f"/api/v1/login/{platform}/oauth",
            params={"platformID": platform_id, "botID": bot_id},
        )

    async def oauth_submit(self, platform: str, payload: Dict[str, Any]):
        return await self.post(f"/api/v1/login/{platform}/oauth", json_data=payload)

    async def oauth_status(self, platform: str, framework_token: str):
        return await self.get(f"/api/v1/login/{platform}/oauth/status", framework_token=framework_token)

    async def bind_character(self, framework_token: str):
        return await self.get("/api/v1/df/person/bind", params={"method": "bind"}, framework_token=framework_token)

    async def personal_info(self, framework_token: str, seasonid: str = "0"):
        return await self.get("/api/v1/df/person/personalinfo", params={"seasonid": seasonid}, framework_token=framework_token)

    async def personal_data(self, framework_token: str, mode: str = "", seasonid: str = ""):
        return await self.get(
            "/api/v1/df/person/personaldata",
            params={"type": mode, "seasonid": seasonid},
            framework_token=framework_token,
        )

    async def record(self, framework_token: str, type_id: str, page: str = "1", enrich: bool = True):
        return await self.get(
            "/api/v1/df/person/record",
            params={"type": type_id, "page": page, "enrich": "true" if enrich else ""},
            framework_token=framework_token,
        )

    async def map_stats(self, framework_token: str, mode: str = "", seasonid: str = "", map_id: str = ""):
        return await self.get(
            "/api/v1/df/person/mapstats",
            params={"type": mode, "serial": seasonid, "mapId": map_id},
            framework_token=framework_token,
        )

    async def money(self, framework_token: str):
        return await self.get("/api/v1/df/person/money", framework_token=framework_token)

    async def flows(self, framework_token: str, type_id: str = "", page: str = "1"):
        return await self.get(
            "/api/v1/df/person/flows",
            params={"type": type_id, "page": page},
            framework_token=framework_token,
        )

    async def collection(self, framework_token: str, version: int = 2):
        path = "/api/v2/df/person/collection" if version == 2 else "/api/v1/df/person/collection"
        return await self.get(path, framework_token=framework_token)

    async def title(self, framework_token: str):
        return await self.get("/api/v1/df/person/title", framework_token=framework_token)

    async def red_list(self, framework_token: str):
        return await self.get("/api/v1/df/person/redlist", framework_token=framework_token)

    async def red_one(self, framework_token: str, objectid: str):
        return await self.get("/api/v1/df/person/redone", params={"objectid": objectid}, framework_token=framework_token)

    async def daily_record(self, framework_token: str, mode: str = ""):
        return await self.get("/api/v1/df/person/dailyrecord", params={"type": mode}, framework_token=framework_token)

    async def weekly_record(self, framework_token: str, mode: str = "", date: str = "", show_extra: bool = False):
        return await self.get(
            "/api/v1/df/person/weeklyrecord",
            params={"type": mode, "date": date, "showExtra": "true" if show_extra else ""},
            framework_token=framework_token,
        )

    async def place_status(self, framework_token: str):
        return await self.get("/api/v1/df/person/placestatus", framework_token=framework_token)

    async def place_info(self, framework_token: str, place: str = ""):
        return await self.get("/api/v1/df/place/info", params={"place": place}, framework_token=framework_token)

    async def ban_history(self, framework_token: str):
        return await self.get("/api/v1/df/qqsafe/ban", framework_token=framework_token)

    async def daily_keyword(self):
        return await self.get("/api/v1/df/tools/dailykeyword")

    async def article_list(self):
        return await self.get("/api/v1/df/tools/article/list")

    async def article_detail(self, thread_id: str):
        return await self.get("/api/v1/df/tools/article/detail", params={"threadID": thread_id, "thread_id": thread_id})

    async def health(self):
        return await self.get("/health/detailed", require_key=False)

    async def maps(self):
        return await self.get("/api/v1/df/object/maps", require_key=False)

    async def operators(self, detail: bool = False):
        return await self.get("/api/v1/df/object/operator2" if detail else "/api/v1/df/object/operator", require_key=False)

    async def rank_score(self):
        return await self.get("/api/v1/df/object/rankscore", require_key=False)

    async def object_health(self):
        return await self.get("/api/v1/df/object/health", require_key=False)

    async def object_collection_map(self):
        return await self.get("/api/v1/df/object/collection", require_key=False)

    async def object_list(self, primary: str = "", second: str = "", page: str = "1", limit: str = "100"):
        return await self.get(
            "/api/v1/df/object/list",
            params={"primaryClass": primary, "secondClass": second, "page": page, "limit": limit},
            require_key=False,
        )

    async def object_search(self, keyword: str, page: str = "1", limit: str = "20"):
        params = {"page": page, "limit": limit}
        if str(keyword).isdigit():
            params["objectID"] = keyword
        else:
            params["objectName"] = keyword
        return await self.get("/api/v1/df/object/search", params=params, require_key=False)

    async def object_value_list(self, params: Optional[Dict[str, Any]] = None):
        return await self.get("/api/v1/df/object/value/list", params=params or {}, require_key=False)

    async def object_value_search(self, keyword: str):
        key = str(keyword or "").strip()
        params = {"id": key} if key.isdigit() else {"name": key}
        return await self.get("/api/v1/df/object/value/search", params=params, require_key=False)

    async def object_value_history(self, keyword: str, days: str = "30"):
        return await self.get("/api/v1/df/object/value/history", params={"id": keyword, "days": days}, require_key=False)

    async def price_history_v1(self, item_id: str, granularity: str = "day"):
        return await self.get(
            "/api/v1/df/object/price/ams/history/v1",
            params={"id": item_id, "granularity": granularity},
            require_key=False,
        )

    async def price_history_v2(self, keyword: str):
        key = str(keyword or "").strip()
        params = {"objectId": key} if key.isdigit() else {"objectName": key}
        return await self.get("/api/v1/df/object/price/ams/history/v2", params=params, require_key=False)

    async def current_price(self, item_id: str):
        return await self.get("/api/v1/df/object/price/ams/latest", params={"id": item_id}, require_key=False)

    async def material_price(self, item_id: str = ""):
        return await self.get("/api/v1/df/place/material/price", params={"id": item_id}, require_key=False)

    async def profit_history(self, params: Dict[str, Any]):
        return await self.get("/api/v1/df/place/profit/history", params=params, require_key=False)

    async def profit_rank(self, params: Dict[str, Any]):
        return await self.get("/api/v1/df/place/profit/rank", params=params, require_key=False)

    async def place_profit(self, params: Dict[str, Any]):
        return await self.get("/api/v1/df/place/profit", params=params, require_key=False)

    async def ai_presets(self):
        return await self.get("/api/v1/df/tools/ai/presets")

    async def ai_review(self, framework_token: str, mode: str, preset: str = ""):
        return await self.post(
            "/api/v1/df/tools/ai",
            json_data={"type": mode, "preset": preset},
            framework_token=framework_token,
        )

    async def shushu_music(self, params: Optional[Dict[str, Any]] = None):
        return await self.get("/api/v1/df/audio/shushu", params=params or {}, require_key=False)

    async def shushu_music_list(self, params: Optional[Dict[str, Any]] = None):
        return await self.get("/api/v1/df/audio/shushu/list", params=params or {}, require_key=False)

    async def audio_random(self, params: Optional[Dict[str, Any]] = None):
        return await self.get("/api/v1/df/audio/random", params=params or {}, require_key=False)

    async def audio_character(self, params: Optional[Dict[str, Any]] = None):
        return await self.get("/api/v1/df/audio/character", params=params or {}, require_key=False)

    async def audio_categories(self):
        return await self.get("/api/v1/df/audio/categories", require_key=False)

    async def audio_characters(self):
        return await self.get("/api/v1/df/audio/characters", require_key=False)

    async def audio_stats(self):
        return await self.get("/api/v1/df/audio/stats", require_key=False)

    async def audio_tags(self):
        return await self.get("/api/v1/df/audio/tags", require_key=False)

    async def tts_health(self):
        return await self.get("/api/v1/df/tts/health", require_key=False)

    async def tts_presets(self):
        return await self.get("/api/v1/df/tts/presets", require_key=False)

    async def tts_preset(self, character_id: str):
        return await self.get("/api/v1/df/tts/preset", params={"characterId": character_id}, require_key=False)

    async def tts_synthesize(self, params: Dict[str, Any]):
        return await self.post("/api/v1/df/tts/synthesize", json_data=params)

    async def tts_task(self, task_id: str):
        return await self.get("/api/v1/df/tts/task", params={"taskId": task_id}, require_key=False)

    async def tts_queue(self):
        return await self.get("/api/v1/df/tts/queue", require_key=False)

    async def solution_list(self, params: Dict[str, Any]):
        return await self.get("/api/v1/df/tools/solution/list", params=params)

    async def solution_detail(self, solution_id: str):
        return await self.get("/api/v1/df/tools/solution/detail", params={"solutionId": solution_id, "id": solution_id})

    async def gunmod_reverse(self, code: str):
        return await self.post("/api/v1/df/gunmod/reverse", json_data={"code": code})
