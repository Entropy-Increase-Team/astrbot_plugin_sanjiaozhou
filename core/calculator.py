import math
from typing import Any, Dict, List, Optional, Tuple


class DeltaCalculator:
    PARTS = {
        "1": "头部",
        "2": "胸部",
        "3": "腹部",
        "4": "大臂",
        "5": "小臂",
        "6": "大腿",
        "7": "小腿",
        "头": "头部",
        "head": "头部",
        "胸": "胸部",
        "chest": "胸部",
        "腹": "腹部",
        "abdomen": "腹部",
        "大臂": "大臂",
        "upper_arm": "大臂",
        "小臂": "小臂",
        "lower_arm": "小臂",
        "大腿": "大腿",
        "thigh": "大腿",
        "小腿": "小腿",
        "calf": "小腿",
    }

    ARMOR_ALIASES = {
        "dt": "DT-AVS防弹衣",
        "fs": "FS复合防弹衣",
        "hvk": "Hvk-2 防弹衣",
        "hvk2": "Hvk-2 防弹衣",
        "tt": "泰坦防弹装甲",
        "泰坦": "泰坦防弹装甲",
        "jg": "金刚防弹衣",
        "tlk": "特里克MAS2.0装甲",
        "gn": "GN重型头盔",
        "dich": "DICH-9重型头盔",
        "dich-9": "DICH-9重型头盔",
        "dich9": "DICH-9重型头盔",
        "gt5": "GT5指挥官头盔",
        "h70": "H70夜视精英头盔",
    }

    WEAPON_ALIASES = {
        "腾龙": "腾龙突击步枪",
        "qbz": "QBZ-191",
        "ak": "AK-74",
        "m4": "M4A1",
        "kc17": "KC17突击步枪",
        "k437": "K437突击步枪",
        "asval": "AS VAL突击步枪",
        "car15": "CAR-15 突击步枪",
        "ptr32": "PTR-32突击步枪",
        "g3": "G3战斗步枪",
        "scarh": "SCAR-H战斗步枪",
        "ak12": "AK12突击步枪",
        "sg552": "SG552突击步枪",
        "m7": "M7战斗步枪",
        "aug": "AUG突击步枪",
        "k416": "K416突击步枪",
        "ash12": "ASH-12战斗步枪",
        "aks74u": "AKS-74U突击步枪",
    }

    BULLET_ALIASES = {
        "dvc12": "DVC12",
        "dbp87": "DBP87",
        "dvp88": "DVP88",
        "dbp10": "DBP10",
        "rrlp": "RRLP",
        "m855": "M855",
        "m855a1": "M855A1",
        "m995": "M995",
        "m80": "M80",
        "m61": "M61",
        "m62": "M62",
        "prs": "PRS",
        "ps": "PS",
        "bt": "BT",
        "bs": "BS",
        "ap": "AP",
        "fmj": "FMJ",
        "jhp": "JHP",
        "hp": "HP",
    }

    def __init__(self, data_mgr):
        self.data_mgr = data_mgr

    def mode(self, text: str) -> Optional[str]:
        value = str(text or "").strip().lower()
        if value in {"sol", "烽火", "烽火地带", "摸金"}:
            return "sol"
        if value in {"mp", "战场", "全面", "大战场", "全面战场"}:
            return "mp"
        return None

    def armor_list(self) -> List[Dict[str, Any]]:
        data = self.data_mgr.load_json_data("armors.json") or {}
        armors = data.get("armors") if isinstance(data, dict) else {}
        result: List[Dict[str, Any]] = []
        for key in ("body_armor", "helmets"):
            for item in armors.get(key, []) or []:
                if isinstance(item, dict):
                    result.append({**item, "category": key})
        return sorted(result, key=lambda x: int(x.get("protectionLevel") or 0))

    def weapon_list(self, mode: str) -> List[Dict[str, Any]]:
        file_name = "weapons_mp.json" if mode == "mp" else "weapons_sol.json"
        data = self.data_mgr.load_json_data(file_name) or {}
        groups = data.get("weapons") if isinstance(data, dict) else {}
        if not groups and mode == "mp":
            data = self.data_mgr.load_json_data("battlefield_weapons.json") or {}
            groups = data.get("battlefield_weapons") if isinstance(data, dict) else {}
        return self._flatten_groups(groups)

    def bullet_list(self, caliber: str) -> List[Dict[str, Any]]:
        data = self.data_mgr.load_json_data("bullets.json") or {}
        groups = data.get("bullets") if isinstance(data, dict) else {}
        if not isinstance(groups, dict):
            return []
        if caliber in groups:
            return [x for x in groups.get(caliber, []) if isinstance(x, dict)]
        lower = str(caliber or "").lower()
        for key, items in groups.items():
            if str(key).lower() == lower:
                return [x for x in items if isinstance(x, dict)]
        return []

    @staticmethod
    def _flatten_groups(groups: Any) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        if not isinstance(groups, dict):
            return result
        for category, items in groups.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    result.append({**item, "category": category})
        return result

    @staticmethod
    def is_helmet(item: Optional[Dict[str, Any]]) -> bool:
        name = str((item or {}).get("name") or "")
        category = str((item or {}).get("category") or "")
        return category == "helmets" or any(x in name for x in ("头盔", "帽", "盔"))

    def find_equipment(self, keyword: str, expect_helmet: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        items = self.armor_list()
        raw = str(keyword or "").strip()
        lower = raw.lower()
        if lower in {"", "0", "1", "无", "none"}:
            return None
        if lower.isdigit():
            idx = int(lower) - 2
            if 0 <= idx < len(items):
                item = items[idx]
                if expect_helmet is None or self.is_helmet(item) == expect_helmet:
                    return item
        alias = self.ARMOR_ALIASES.get(lower, raw)
        for predicate in (
            lambda x: str(x.get("name") or "").lower() == lower,
            lambda x: alias and alias in str(x.get("name") or ""),
            lambda x: lower and lower in str(x.get("name") or "").lower(),
            lambda x: lower and all(ch in str(x.get("name") or "").lower() for ch in lower),
        ):
            for item in items:
                if expect_helmet is not None and self.is_helmet(item) != expect_helmet:
                    continue
                if predicate(item):
                    return item
        return None

    def find_weapon(self, keyword: str, mode: str) -> Optional[Dict[str, Any]]:
        items = self.weapon_list(mode)
        raw = str(keyword or "").strip()
        lower = raw.lower()
        alias = self.WEAPON_ALIASES.get(lower, raw)
        return self._fuzzy_find(items, raw, alias)

    def find_bullet(self, keyword: str, caliber: str) -> Optional[Dict[str, Any]]:
        items = self.bullet_list(caliber)
        raw = str(keyword or "").strip()
        lower = raw.lower()
        alias = self.BULLET_ALIASES.get(lower, raw)
        return self._fuzzy_find(items, raw, alias)

    @staticmethod
    def _fuzzy_find(items: List[Dict[str, Any]], raw: str, alias: str) -> Optional[Dict[str, Any]]:
        lower = raw.lower()
        for predicate in (
            lambda x: str(x.get("name") or "").lower() == lower,
            lambda x: alias and alias in str(x.get("name") or ""),
            lambda x: lower and lower in str(x.get("name") or "").lower(),
            lambda x: lower and all(ch in str(x.get("name") or "").lower() for ch in lower),
        ):
            for item in items:
                if predicate(item):
                    return item
        return None

    def parse_armor(self, text: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
        value = str(text or "").strip()
        for sep in (":", "：", ",", "，"):
            if sep in value:
                left, right = [x.strip() for x in value.split(sep, 1)]
                helmet = self.find_equipment(left, True)
                armor = self.find_equipment(right, False)
                if not helmet:
                    return None, None, f"头盔解析失败：{left}"
                if not armor:
                    return None, None, f"护甲解析失败：{right}"
                return helmet, armor, None
        item = self.find_equipment(value)
        if not item:
            if value.lower() in {"0", "1", "无", "none"}:
                return None, None, None
            return None, None, f"未找到装备：{value}"
        return (item, None, None) if self.is_helmet(item) else (None, item, None)

    def parse_hit_parts(self, text: str, total_shots: int) -> Tuple[Optional[List[str]], Optional[str]]:
        parts: List[str] = []
        for raw in str(text or "").split(","):
            raw = raw.strip()
            if not raw:
                continue
            if ":" not in raw and "：" not in raw:
                return None, f"命中部位格式错误：{raw}"
            key, count_text = [x.strip() for x in raw.replace("：", ":").split(":", 1)]
            part = self.PARTS.get(key.lower()) or self.PARTS.get(key)
            if not part:
                return None, f"不支持的命中部位：{key}"
            try:
                count = int(count_text)
            except Exception:
                return None, f"命中次数不是整数：{count_text}"
            if count < 0:
                return None, "命中次数不能小于 0"
            parts.extend([part] * count)
        if len(parts) != total_shots:
            return None, f"部位分配合计 {len(parts)} 发，与射击次数 {total_shots} 不一致"
        return parts, None

    def calculate_damage(
        self,
        weapon: Dict[str, Any],
        bullet: Dict[str, Any],
        helmet: Optional[Dict[str, Any]],
        armor: Optional[Dict[str, Any]],
        distance: float,
        hit_parts: List[str],
    ) -> Dict[str, Any]:
        try:
            decay = self.weapon_decay(distance, weapon)
            player_health = 100.0
            armor_durability = float((armor or {}).get("initialMax") or 0)
            helmet_durability = float((helmet or {}).get("initialMax") or 0)
            armor_level = int((armor or {}).get("protectionLevel") or 0)
            helmet_level = int((helmet or {}).get("protectionLevel") or 0)
            weapon_damage = float(weapon.get("baseDamage") or 0)
            weapon_armor_damage = float(weapon.get("armorDamage") or 0)
            penetration_level = int(bullet.get("penetrationLevel") or 0)
            base_damage_multiplier = float(bullet.get("baseDamageMultiplier") or 1)
            base_armor_multiplier = float(bullet.get("baseArmorMultiplier") or 1)
            armor_decay_factors = bullet.get("armorDecayFactors") or []
            is_338 = str(bullet.get("caliber") or "").lower() == "338lapmag" or ".338 Lap Mag" in str(bullet.get("name") or "")
            shot_results = []
            total_damage = 0.0
            total_armor_damage = 0.0

            for idx, hit_part in enumerate(hit_parts, 1):
                is_helmet_protected = hit_part == "头部" and helmet_level > 0 and helmet_durability > 0
                is_armor_protected = (
                    armor_level > 0
                    and armor_durability > 0
                    and hit_part in self._armor_protected_parts(str((armor or {}).get("type") or ""))
                )
                protector_type = ""
                protector_level = 0
                current_protector_durability = 0.0
                if is_helmet_protected:
                    protector_type = "helmet"
                    protector_level = helmet_level
                    current_protector_durability = helmet_durability
                elif is_armor_protected:
                    protector_type = "armor"
                    protector_level = armor_level
                    current_protector_durability = armor_durability

                is_protected = bool(protector_type)
                protector_destroyed = False
                armor_damage_dealt = 0.0
                part_multiplier = self.part_multiplier(weapon, hit_part)

                if is_protected:
                    level_diff = penetration_level - protector_level
                    if level_diff < 0:
                        penetration_multiplier = 0.0
                    elif level_diff == 0:
                        penetration_multiplier = 0.5
                    elif level_diff == 1:
                        penetration_multiplier = 0.75
                    else:
                        penetration_multiplier = 1.0
                    armor_decay = float(armor_decay_factors[protector_level - 1]) if 0 < protector_level <= len(armor_decay_factors) else 0.0
                    armor_damage_value = weapon_armor_damage * base_armor_multiplier * armor_decay * decay
                    remaining = max(0.0, current_protector_durability - armor_damage_value)
                    protector_destroyed = remaining <= 0
                    armor_damage_dealt = current_protector_durability - remaining
                    total_armor_damage += armor_damage_dealt
                    if protector_type == "helmet":
                        helmet_durability = remaining
                    else:
                        armor_durability = remaining

                    if is_338:
                        final_damage = weapon_damage * base_damage_multiplier * part_multiplier * decay
                    else:
                        denominator = weapon_armor_damage * base_armor_multiplier * decay * armor_decay
                        if denominator == 0:
                            final_damage = weapon_damage * base_damage_multiplier * part_multiplier * decay
                        elif current_protector_durability >= armor_damage_value:
                            final_damage = weapon_damage * base_damage_multiplier * part_multiplier * penetration_multiplier * decay
                        else:
                            ratio = current_protector_durability / denominator
                            part1 = ratio * weapon_damage * base_damage_multiplier * part_multiplier * penetration_multiplier * decay
                            part2 = (1 - ratio) * weapon_damage * base_damage_multiplier * part_multiplier * decay
                            final_damage = part1 + part2
                else:
                    final_damage = weapon_damage * base_damage_multiplier * part_multiplier * decay

                final_damage = round(final_damage, 2)
                player_health -= final_damage
                total_damage += final_damage
                shot_results.append(
                    {
                        "shotNumber": idx,
                        "hitPart": hit_part,
                        "damage": final_damage,
                        "armorDamage": round(armor_damage_dealt, 2),
                        "isProtected": is_protected,
                        "protectorDestroyed": protector_destroyed,
                        "protectorType": protector_type,
                        "playerHealthAfter": max(0, round(player_health, 2)),
                        "armorDurabilityAfter": round(armor_durability, 1),
                        "helmetDurabilityAfter": round(helmet_durability, 1),
                        "isKill": player_health <= 0,
                    }
                )
                if player_health <= 0:
                    break

            return {
                "success": True,
                "weapon": weapon.get("name") or "未知武器",
                "armor": (armor or {}).get("name") or "无",
                "helmet": (helmet or {}).get("name") or "无",
                "bullet": bullet.get("name") or "未知子弹",
                "distance": distance,
                "baseDamage": weapon_damage,
                "weaponDecayMultiplier": round(decay, 3),
                "penetrationLevel": penetration_level,
                "is338LapMag": is_338,
                "shotsToKill": len(shot_results),
                "totalDamage": round(total_damage, 2),
                "totalArmorDamage": round(total_armor_damage, 2),
                "shotResults": shot_results,
                "finalPlayerHealth": max(0, round(player_health, 2)),
                "finalArmorDurability": round(armor_durability, 1),
                "finalHelmetDurability": round(helmet_durability, 1),
                "maxArmorDurability": float((armor or {}).get("initialMax") or 0),
                "maxHelmetDurability": float((helmet or {}).get("initialMax") or 0),
                "isKilled": player_health <= 0,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @staticmethod
    def _armor_protected_parts(armor_type: str) -> List[str]:
        mapping = {
            "半甲": ["胸部", "腹部"],
            "全甲": ["胸部", "腹部"],
            "重甲": ["胸部", "腹部", "大臂"],
        }
        return mapping.get(armor_type, ["胸部", "腹部"])

    @staticmethod
    def part_multiplier(weapon: Dict[str, Any], part: str) -> float:
        key_map = {
            "头部": "headMultiplier",
            "胸部": "chestMultiplier",
            "腹部": "abdomenMultiplier",
            "大臂": "upperArmMultiplier",
            "小臂": "lowerArmMultiplier",
            "大腿": "thighMultiplier",
            "小腿": "calfMultiplier",
        }
        return float(weapon.get(key_map.get(part, ""), 1.0) or 1.0)

    @staticmethod
    def weapon_decay(distance: float, weapon: Dict[str, Any]) -> float:
        distances = weapon.get("decayDistances") or weapon.get("decay_distances") or []
        multipliers = weapon.get("decayMultipliers") or weapon.get("decay_factors") or []
        if not distances:
            return 1.0
        pairs = sorted(
            [(float(dist), float(multipliers[idx] if idx < len(multipliers) else 1.0)) for idx, dist in enumerate(distances)],
            key=lambda x: x[0],
        )
        if distance <= pairs[0][0]:
            return 1.0
        for dist, multiplier in pairs:
            if distance <= dist:
                return multiplier
        return pairs[-1][1]

    def calculate_repair(self, armor: Dict[str, Any], current: float, remaining: float, mode: str) -> Dict[str, Any]:
        if remaining > current:
            return {"success": False, "error": "剩余耐久不能大于当前上限"}
        if mode == "inside":
            return self._inside_repair(armor, current, remaining)
        return self._outside_repair(armor, current, remaining)

    def _inside_repair(self, armor: Dict[str, Any], current: float, remaining: float) -> Dict[str, Any]:
        initial_max = float(armor.get("initialMax") or 0)
        repair_loss = armor.get("repairLoss")
        if not initial_max or repair_loss is None:
            return {"success": False, "error": f"{armor.get('name')} 缺少维修损耗数据"}
        repair_loss = float(repair_loss)
        ratio = (current - remaining) / current if current else 0
        log_term = math.log10(current / initial_max) if current > 0 and initial_max > 0 else 0
        repaired_max = current - current * ratio * (repair_loss - log_term)
        delta = round(repaired_max, 2) - remaining
        packages = []
        for key, name in (
            ("self_made", "自制维修包"),
            ("standard", "标准维修包"),
            ("precision", "精密维修包"),
            ("advanced", "高级维修组合"),
        ):
            efficiency = self.repair_efficiency(armor, key)
            if efficiency is None:
                consumption: Any = "暂无数据"
            elif efficiency == 0:
                consumption = "无穷大"
            elif delta <= 0:
                consumption = "无效值"
            else:
                consumption = math.floor(delta / efficiency)
            packages.append({"name": name, "efficiency": efficiency, "consumption": consumption})
        return {
            "success": True,
            "mode": "局内维修",
            "armor": armor.get("name"),
            "currentMax": current,
            "remainingDurability": remaining,
            "repairedMax": round(repaired_max, 1),
            "repairLoss": repair_loss,
            "repairPackages": packages,
        }

    def _outside_repair(self, armor: Dict[str, Any], current: float, remaining: float) -> Dict[str, Any]:
        initial_max = float(armor.get("initialMax") or 0)
        repair_loss = armor.get("repairLoss")
        repair_price = armor.get("repairPrice")
        if not initial_max or repair_loss is None or repair_price is None:
            return {"success": False, "error": f"{armor.get('name')} 缺少维修数据"}
        current_upper = math.floor(current)
        if self.is_helmet(armor) and current_upper < 5:
            return {"success": False, "error": f"当前头盔上限({current_upper})小于5，不可维修"}
        if not self.is_helmet(armor) and current_upper < 10:
            return {"success": False, "error": f"当前护甲上限({current_upper})小于10，不可维修"}
        term1 = (current_upper - remaining) / current_upper
        log_value = current_upper / initial_max
        if log_value <= 0:
            return {"success": False, "error": "对数计算参数必须大于0"}
        repaired_upper = current_upper - current_upper * term1 * (float(repair_loss) - math.log10(log_value))
        final_upper = max(1, math.floor(repaired_upper))
        repair_cost = max(0, round((final_upper - math.floor(remaining) + 1) * float(repair_price)))
        wear = round((1 - final_upper / initial_max) * 100, 1)
        non_tradable = {"金刚防弹衣", "特里克MAS2.0装甲", "泰坦防弹装甲", "DICH-9重型头盔", "GT5指挥官头盔", "H70夜视精英头盔"}
        if str(armor.get("name")) in non_tradable:
            market_status = "不可在市场进行交易"
        elif final_upper >= math.floor(initial_max * 0.85):
            market_status = "略有磨损，可在市场出售"
        elif final_upper >= math.floor(initial_max * 0.70):
            market_status = "久经沙场，可在市场出售"
        else:
            market_status = "破损不堪，不可在市场出售"
        return {
            "success": True,
            "mode": "局外维修",
            "armor": armor.get("name"),
            "repairLevel": "中级维修",
            "initialMax": initial_max,
            "currentDurability": current_upper,
            "remainingDurability": remaining,
            "finalUpper": final_upper,
            "repairLoss": repair_loss,
            "repairCost": repair_cost,
            "wearPercentage": wear,
            "marketStatus": market_status,
        }

    @staticmethod
    def repair_efficiency(armor: Dict[str, Any], repair_type: str) -> Optional[float]:
        efficiencies = armor.get("repairEfficiencies") or {}
        if not isinstance(efficiencies, dict):
            return None
        old_keys = {"self_made": "3", "standard": "6", "precision": "8", "advanced": "9"}
        if any(key in efficiencies for key in old_keys.values()):
            value = efficiencies.get(old_keys[repair_type])
            return float(value) if value is not None else None
        keys = sorted(efficiencies.keys(), key=lambda x: float(x))
        index = {"self_made": 0, "standard": 1, "precision": 2, "advanced": 3}[repair_type]
        return float(keys[index]) if index < len(keys) else None

    def mapping_text(self) -> str:
        lines = [
            "【三角洲计算映射表】",
            "模式：烽火=sol/烽火/烽火地带/摸金；全面=mp/战场/全面/大战场/全面战场",
            "部位：1头部 2胸部 3腹部 4大臂 5小臂 6大腿 7小腿；简写支持 头/胸/腹",
            "护甲组合：头盔:护甲，例如 2:5、dich-1:fs、gn:泰坦",
            "常用护甲简写：fs=FS复合防弹衣，dt=DT-AVS，tt/泰坦=泰坦防弹装甲，gn=GN重型头盔，dich=DICH-9",
            "常用武器简写：腾龙、kc17、k437、m4、ak、g3、scarh、k416、aug",
            "常用子弹简写：dvc12、dbp10、m855、m855a1、m995、m80、m61、bt、bs、ap、fmj",
            "示例：伤害 烽火 腾龙 dvc12 41:37 50 6 1:2,2:4",
            "示例：修甲 fs 0/100 局内",
        ]
        return "\n".join(lines)
