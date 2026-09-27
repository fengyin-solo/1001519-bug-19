"""观测传感器业务规则：状态流转、字段校验、统计口径与筛选都收在这里。

状态流转（每一步都要求落在合理状态上，不允许跳变）：
    待检定 --检定通过--> 正常采集 --标记疑误--> 疑误待查 --复检恢复--> 正常采集
    正常采集/疑误待查 --安排检定--> 待检定
    待检定/正常采集/疑误待查 --拆除传感器--> 已拆除（终态）
重复执行同一动作视为幂等：不报错、不写第二条状态变化记录。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "sensor"
REQUIRED_FIELDS = ["传感器编号", "所属站点", "观测要素"]
STATUS_ORDER = ["待检定", "正常采集", "疑误待查", "已拆除"]
REMOVED = "已拆除"
COLLECTING = "正常采集"
SUSPECT = "疑误待查"
PENDING_VERIFY = "待检定"
DISPLAY_FIELD = "传感器状态"
EXPIRY_FIELD = "检定有效期"

# 每个动作允许的「当前状态 -> 目标状态」；已处于目标状态时按幂等处理。
ACTION_RULES: dict[str, dict[str, Any]] = {
    "安排检定": {"target": PENDING_VERIFY, "from": (COLLECTING, SUSPECT)},
    "检定通过": {"target": COLLECTING, "from": (PENDING_VERIFY,)},
    "标记疑误": {"target": SUSPECT, "from": (COLLECTING,)},
    "复检恢复": {"target": COLLECTING, "from": (SUSPECT,)},
    "拆除传感器": {"target": REMOVED, "from": (PENDING_VERIFY, COLLECTING, SUSPECT)},
}


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


class SensorService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        expiry_missing: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row
                for row in rows
                if any(keyword in str(row.get(field, "")) for field in ("传感器编号", "所属站点", "观测要素"))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if expiry_missing:
            rows = [
                row
                for row in rows
                if row.get("status") != REMOVED and _is_blank(row.get(EXPIRY_FIELD))
            ]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if _is_blank(values.get(field))]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 其余资料字段（型号、有效期等）能收就收，没有给空串，保持列对齐。
        for field in ("设备型号", "出厂序列号", "安装高度", EXPIRY_FIELD):
            entry[field] = str(values.get(field) or "").strip()
        entry["status"] = STATUS_ORDER[0]
        entry[DISPLAY_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        entry["history"] = [{"action": "登记建档", "from": None, "to": STATUS_ORDER[0]}]
        rows.append(entry)
        return entry, []

    def available_actions(self, status: str) -> list[str]:
        """按当前状态给出可执行动作；已拆除是终态，不再提供动作。"""
        if status == REMOVED:
            return []
        if status == PENDING_VERIFY:
            return ["检定通过", "拆除传感器"]
        if status == COLLECTING:
            return ["安排检定", "标记疑误", "拆除传感器"]
        if status == SUSPECT:
            return ["安排检定", "复检恢复", "拆除传感器"]
        return []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str, bool]:
        """执行动作，返回 (记录, 说明, 是否真正发生了状态变化)。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"观测传感器 {entry_id} 不存在或已归档", False
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于观测传感器可执行范围", False

        current = str(entry.get("status") or "")
        rule = ACTION_RULES[action]
        target = str(rule["target"])
        history = entry.setdefault("history", [])

        # 幂等：已经在目标状态，连续点两次也只算一次，不再追加状态变化。
        if current == target:
            return entry, f"传感器当前已是「{target}」，无需重复{action}", False

        if current not in rule["from"]:
            allowed = "、".join(rule["from"])
            return None, f"「{current}」状态下不能{action}，请先在「{allowed}」状态操作", False

        entry["status"] = target
        entry[DISPLAY_FIELD] = target
        entry["pending"] = target == PENDING_VERIFY
        entry["abnormal"] = target == SUSPECT
        history.append({"action": action, "from": current, "to": target})
        return entry, f"观测传感器已{action}：{current} → {target}", True

    def statistics(self) -> dict[str, int]:
        """统计卡口径：在装 = 未拆除；正常采集只数在装且正常的，拆除的不参与。"""
        rows = store.rows(MODULE)
        return {
            "installed": sum(1 for r in rows if r.get("status") != REMOVED),
            "collecting": sum(1 for r in rows if r.get("status") == COLLECTING),
            "pending": sum(1 for r in rows if r.get("status") == PENDING_VERIFY),
            "suspect": sum(1 for r in rows if r.get("status") == SUSPECT),
            "removed": sum(1 for r in rows if r.get("status") == REMOVED),
            "expiry_missing": sum(
                1 for r in rows if r.get("status") != REMOVED and _is_blank(r.get(EXPIRY_FIELD))
            ),
        }

    def expiry_state(self, entry: dict[str, Any]) -> str:
        """检定有效期：missing 缺失 / expired 已过期 / ok 正常 / removed 已拆除不提示。"""
        if entry.get("status") == REMOVED:
            return "removed"
        raw = str(entry.get(EXPIRY_FIELD) or "").strip()
        if not raw:
            return "missing"
        try:
            expiry = date.fromisoformat(raw)
        except ValueError:
            return "missing"
        return "expired" if expiry < date.today() else "ok"
