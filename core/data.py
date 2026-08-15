import json
import random
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from astrbot.api import logger


class DeltaDataManager:
    SOL_RANK_CODES = {
        "青铜 V": "1_5",
        "青铜 IV": "1_4",
        "青铜 III": "1_3",
        "青铜 II": "1_2",
        "青铜 I": "1_1",
        "白银 V": "2_5",
        "白银 IV": "2_4",
        "白银 III": "2_3",
        "白银 II": "2_2",
        "白银 I": "2_1",
        "黄金 V": "3_5",
        "黄金 IV": "3_4",
        "黄金 III": "3_3",
        "黄金 II": "3_2",
        "黄金 I": "3_1",
        "铂金 V": "4_5",
        "铂金 IV": "4_4",
        "铂金 III": "4_3",
        "铂金 II": "4_2",
        "铂金 I": "4_1",
        "钻石 V": "5_5",
        "钻石 IV": "5_4",
        "钻石 III": "5_3",
        "钻石 II": "5_2",
        "钻石 I": "5_1",
        "黑鹰 V": "6_5",
        "黑鹰 IV": "6_4",
        "黑鹰 III": "6_3",
        "黑鹰 II": "6_2",
        "黑鹰 I": "6_1",
        "三角洲巅峰": "7",
    }
    MP_RANK_CODES = {
        "列兵 V": "1_5",
        "列兵 IV": "1_4",
        "列兵 III": "1_3",
        "列兵 II": "1_2",
        "列兵 I": "1_1",
        "上等兵 V": "2_5",
        "上等兵 IV": "2_4",
        "上等兵 III": "2_3",
        "上等兵 II": "2_2",
        "上等兵 I": "2_1",
        "军士长 V": "3_5",
        "军士长 IV": "3_4",
        "军士长 III": "3_3",
        "军士长 II": "3_2",
        "军士长 I": "3_1",
        "尉官 V": "4_5",
        "尉官 IV": "4_4",
        "尉官 III": "4_3",
        "尉官 II": "4_2",
        "尉官 I": "4_1",
        "校官 V": "5_5",
        "校官 IV": "5_4",
        "校官 III": "5_3",
        "校官 II": "5_2",
        "校官 I": "5_1",
        "将军 V": "6_5",
        "将军 IV": "6_4",
        "将军 III": "6_3",
        "将军 II": "6_2",
        "将军 I": "6_1",
        "统帅": "7",
    }

    def __init__(self, plugin_path: str, cache_dir: str):
        self.plugin_path = Path(plugin_path).resolve()
        self.resources = self.plugin_path / "resources"
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.maps: Dict[str, str] = self._load_yaml("maps.yaml")
        self.operators: Dict[str, str] = self._load_yaml("operators.yaml")
        self.rankscore: Dict[str, Dict[str, str]] = self._load_yaml("rankscore.yaml")
        self._json_cache: Dict[str, Any] = {}

    def _load_yaml(self, name: str) -> Dict[str, Any]:
        for path in [self.cache_dir / name, self.plugin_path / "config" / name]:
            if not path.exists():
                continue
            try:
                data = yaml.safe_load(path.read_text("utf-8", errors="replace")) or {}
                return {str(k): v for k, v in data.items()} if isinstance(data, dict) else {}
            except Exception as exc:
                logger.warning(f"[DeltaForce Data] 读取缓存失败 {path}: {exc}")
        return {}

    def _save_yaml(self, name: str, data: Dict[str, Any]):
        try:
            (self.cache_dir / name).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=True), "utf-8")
        except Exception as exc:
            logger.warning(f"[DeltaForce Data] 保存缓存失败 {name}: {exc}")

    @staticmethod
    def _api_data(res: Any) -> Any:
        if isinstance(res, dict) and "data" in res:
            return res.get("data")
        return res

    @staticmethod
    def _extract_list(data: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if not isinstance(data, dict):
            return []
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        for value in data.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value
        return []

    async def refresh_static(self, client):
        try:
            maps_res = await client.maps()
            maps_data = self._api_data(maps_res)
            rows = self._extract_list(maps_data, ("maps", "list", "items", "data"))
            if rows:
                self.maps = {
                    str(x.get("id") or x.get("mapID") or x.get("mapId")): str(x.get("name") or x.get("mapName") or "")
                    for x in rows
                    if x.get("id") or x.get("mapID") or x.get("mapId")
                }
                self._save_yaml("maps.yaml", self.maps)
        except Exception as exc:
            logger.debug(f"[DeltaForce Data] 地图同步跳过: {exc}")

        try:
            op_res = await client.operators(detail=False)
            op_data = self._api_data(op_res)
            rows = self._extract_list(op_data, ("operators", "list", "items", "data"))
            if rows:
                self.operators = {
                    str(x.get("id") or x.get("operatorId") or x.get("operatorID")): str(x.get("name") or x.get("operatorName") or "")
                    for x in rows
                    if x.get("id") or x.get("operatorId") or x.get("operatorID")
                }
                self._save_yaml("operators.yaml", self.operators)
        except Exception as exc:
            logger.debug(f"[DeltaForce Data] 干员同步跳过: {exc}")

        try:
            rank_res = await client.rank_score()
            rank_data = self._api_data(rank_res)
            if isinstance(rank_data, dict) and rank_data:
                processed: Dict[str, Dict[str, str]] = {}
                for mode, rows in rank_data.items():
                    if isinstance(rows, list):
                        processed[str(mode)] = {
                            str(x.get("score") or x.get("minScore") or x.get("threshold")): str(x.get("name") or x.get("rankName") or "")
                            for x in rows
                            if isinstance(x, dict) and (x.get("score") or x.get("minScore") or x.get("threshold")) is not None
                        }
                    elif isinstance(rows, dict):
                        processed[str(mode)] = {str(k): str(v) for k, v in rows.items()}
                if processed:
                    self.rankscore = processed
                    self._save_yaml("rankscore.yaml", self.rankscore)
        except Exception as exc:
            logger.debug(f"[DeltaForce Data] 段位同步跳过: {exc}")

    def get_map_name(self, value: Any) -> str:
        if value is None or value == "":
            return "未知地图"
        return self.maps.get(str(value), f"未知地图({value})")

    def get_operator_name(self, value: Any) -> str:
        if value is None or value == "":
            return "未知干员"
        return self.operators.get(str(value), f"未知干员({value})")

    def get_rank_by_score(self, score: Any, mode: str = "sol") -> str:
        try:
            num = int(float(score))
        except Exception:
            return "-" if score in (None, "") else f"{score}分"
        mode_key = "mp" if mode in ("mp", "tdm") else "sol"
        data = self.rankscore.get(mode_key) or self.rankscore.get("tdm" if mode_key == "mp" else mode_key)
        if not data:
            return f"{num}分"
        thresholds = sorted((int(k) for k in data.keys() if str(k).lstrip("-").isdigit()), reverse=True)
        if not thresholds:
            return f"{num}分"
        for threshold in thresholds:
            if num >= threshold:
                name = data.get(str(threshold), "")
                if name and ((mode_key == "sol" and threshold == 6000) or (mode_key == "mp" and threshold == 5000)):
                    stars = max(0, (num - threshold) // 50)
                    if stars:
                        return f"{name}{stars}星 ({num})"
                return f"{name or threshold} ({num})"
        return f"{data.get(str(thresholds[-1]), thresholds[-1])} ({num})"

    def get_rank_image_path(self, rank_name: str, mode: str = "sol") -> Optional[str]:
        if not rank_name or "未知" in rank_name or "无效" in rank_name:
            return None
        clean = re.sub(r"\s*\(\d+\)", "", str(rank_name))
        clean = re.sub(r"\d+星", "", clean).strip()
        mode_key = "mp" if mode in ("mp", "tdm") else "sol"
        code = (self.MP_RANK_CODES if mode_key == "mp" else self.SOL_RANK_CODES).get(clean)
        return f"imgs/rank/{mode_key}/{code}.webp" if code else None

    def get_operator_image_path(self, operator_name: str) -> Optional[str]:
        if not operator_name or "未知" in operator_name or "无" == operator_name:
            return None
        clean = re.sub(r"\s*\([^)]*\)", "", str(operator_name)).strip()
        if not clean:
            return None
        return f"imgs/operator/{clean}.png"

    def get_map_image_path(self, map_name: str, mode: str = "sol") -> Optional[str]:
        if not map_name or "未知" in str(map_name):
            return None
        clean = re.sub(r"\s*\([^)]*\)", "", str(map_name)).strip()
        mode_key = "mp" if mode in ("mp", "tdm") else "sol"
        prefix = "全面-" if mode_key == "mp" else "烽火-"
        if mode_key == "mp":
            base = clean.split("-")[0].strip()
            return f"imgs/map/{prefix}{base}.webp"
        base, _, difficulty = clean.partition("-")
        map_dir = self.resources / "imgs" / "map"
        candidates = []
        if difficulty:
            candidates.append(f"{prefix}{base}-{difficulty}.webp")
        for diff in ("常规", "机密", "绝密", "适应", "普通", "困难", "极限"):
            candidates.append(f"{prefix}{base}-{diff}.webp")
        candidates.append(f"{prefix}{base}.webp")
        for name in candidates:
            if (map_dir / name).exists():
                return f"imgs/map/{name}"
        return f"imgs/map/{prefix}{base}-常规.webp"

    @staticmethod
    def get_random_background() -> str:
        return f"imgs/background/bg2-{random.randint(1, 7)}.webp"

    @staticmethod
    def decode_text(value: Any) -> str:
        from urllib.parse import unquote

        text = "" if value is None else str(value)
        try:
            return unquote(text)
        except Exception:
            return text

    @staticmethod
    def fmt_num(value: Any, default: str = "0") -> str:
        try:
            if value is None or value == "":
                return default
            num = float(value)
            if num.is_integer():
                return f"{int(num):,}"
            return f"{num:,.2f}"
        except Exception:
            return str(value) if value not in (None, "") else default

    @staticmethod
    def fmt_price(value: Any) -> str:
        try:
            num = float(value or 0)
        except Exception:
            return "-"
        sign = "-" if num < 0 else ""
        num = abs(num)
        if num >= 1_000_000_000:
            return f"{sign}{num / 1_000_000_000:.2f}B"
        if num >= 1_000_000:
            return f"{sign}{num / 1_000_000:.2f}M"
        if num >= 1_000:
            return f"{sign}{num / 1_000:.1f}K"
        return f"{sign}{int(num):,}"

    @staticmethod
    def fmt_duration(value: Any, unit: str = "seconds") -> str:
        try:
            num = int(float(value or 0))
        except Exception:
            return "未知"
        seconds = num * 60 if unit == "minutes" else num
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours:
            return f"{hours}小时{minutes}分{secs}秒"
        if minutes:
            return f"{minutes}分{secs}秒"
        return f"{secs}秒"

    def load_json_data(self, name: str) -> Any:
        if name in self._json_cache:
            return self._json_cache[name]
        path = self.resources / "data" / name
        try:
            data = json.loads(path.read_text("utf-8", errors="replace"))
        except Exception:
            data = None
        self._json_cache[name] = data
        return data

    def search_local_items(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        keyword = str(keyword or "").strip().lower()
        if not keyword:
            return []
        results: List[Dict[str, Any]] = []
        for filename in (
            "weapons_sol.json",
            "weapons_mp.json",
            "battlefield_weapons.json",
            "armors.json",
            "bullets.json",
            "equipment.json",
            "melee_weapons.json",
        ):
            self._walk_items(self.load_json_data(filename), keyword, filename, results, limit)
            if len(results) >= limit:
                break
        return results[:limit]

    def _walk_items(self, obj: Any, keyword: str, source: str, results: List[Dict[str, Any]], limit: int):
        if len(results) >= limit:
            return
        if isinstance(obj, dict):
            name = obj.get("name") or obj.get("objectName") or obj.get("object_name")
            object_id = obj.get("objectID") or obj.get("objectId") or obj.get("id")
            if name and keyword in str(name).lower():
                results.append({"name": name, "id": object_id or "", "source": source})
                if len(results) >= limit:
                    return
            for value in obj.values():
                self._walk_items(value, keyword, source, results, limit)
        elif isinstance(obj, list):
            for item in obj:
                self._walk_items(item, keyword, source, results, limit)
                if len(results) >= limit:
                    return
