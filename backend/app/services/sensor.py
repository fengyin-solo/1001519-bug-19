"""观测传感器业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "sensor"
REQUIRED_FIELDS = ["传感器编号", "所属站点", "观测要素"]
STATUS_ORDER = ["待检定", "正常采集", "疑误待查", "已拆除"]
REMOVED_STATUS = "已拆除"

# 每个动作只允许从哪些状态流转过来：已拆除是终态，任何动作都不能再落在它身上。
ACTION_RULES: dict[str, dict[str, Any]] = {
    "安排检定": {"from": {"待检定", "疑误待查"}, "to": "正常采集"},
    "标记疑误": {"from": {"正常采集"}, "to": "疑误待查"},
    "拆除传感器": {"from": {"待检定", "正常采集", "疑误待查"}, "to": "已拆除"},
}
ACTION_MESSAGES = {
    "安排检定": "检定合格，已恢复正常采集",
    "标记疑误": "已标记疑误待查",
    "拆除传感器": "传感器已拆除，不再参与采集统计",
}

STAT_LABELS = [
    ("installed", "在装传感器"),
    ("collecting", "正常采集中"),
    ("pending_check", "待检定传感器"),
    ("suspect", "疑误待查"),
    ("removed", "已拆除"),
    ("missing_validity", "检定有效期缺失"),
]


def is_removed(entry: dict[str, Any]) -> bool:
    return entry.get("status") == REMOVED_STATUS


def validity_missing(entry: dict[str, Any]) -> bool:
    """检定有效期缺失：空白、占位样例文本或无法解析的日期都算缺失。"""
    raw = str(entry.get("检定有效期") or "").strip()
    if not raw or raw.startswith("观测传感器样例"):
        return True
    try:
        date.fromisoformat(raw[:10])
    except ValueError:
        return True
    return False


class SensorService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        missing_validity: bool = False,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("传感器编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if missing_validity:
            rows = [row for row in rows if validity_missing(row)]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str, bool]:
        """执行动作。

        返回 (记录, 说明, changed)：状态没变化时 changed=False，
        这样连点同一个动作也只会得到一次真实的状态变化，不会重复记账。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"观测传感器 {entry_id} 不存在或已归档", False
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于观测传感器可执行范围", False
        rule = ACTION_RULES[action]
        target = rule["to"]
        current = str(entry.get("status") or "")
        if current == target:
            return entry, f"传感器当前已是「{target}」状态，无需重复{action}", False
        if current not in rule["from"]:
            return None, f"「{current}」状态不允许执行{action}，请按检定→采集→疑误/拆除的顺序操作", False
        entry["status"] = target
        # 列表“传感器状态”列与内部 status 始终同源，避免两处显示对不上。
        entry["传感器状态"] = target
        entry["pending"] = target == "待检定"
        entry["abnormal"] = target == "疑误待查"
        return entry, ACTION_MESSAGES[action], True

    def stats(self) -> dict[str, int]:
        """统计卡口径：已拆除不参与采集统计；在装 = 未拆除。"""
        rows = store.rows(MODULE)
        installed = [row for row in rows if not is_removed(row)]
        return {
            "installed": len(installed),
            "collecting": sum(1 for row in rows if row.get("status") == "正常采集"),
            "pending_check": sum(1 for row in rows if row.get("status") == "待检定"),
            "suspect": sum(1 for row in rows if row.get("status") == "疑误待查"),
            "removed": sum(1 for row in rows if is_removed(row)),
            "missing_validity": sum(1 for row in installed if validity_missing(row)),
        }

    def export_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        missing_validity: bool = False,
    ) -> dict[str, Any]:
        """导出清单：与列表同一套过滤口径，并随附统计卡数据，三处共用一份口径。"""
        items, total = self.list_entries(
            keyword=keyword,
            status=status,
            missing_validity=missing_validity,
            page=1,
            size=10000,
        )
        return {
            "module": "sensor",
            "total": total,
            "stats": self.stats(),
            "items": items,
        }
