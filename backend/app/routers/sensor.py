"""观测传感器接口：维护观测传感器，覆盖安排检定、检定通过、标记疑误、复检恢复、拆除传感器等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.sensor import REMOVED, SensorService

router = APIRouter(prefix="/api/sensor", tags=["观测传感器"])

service = SensorService()

STATUSES = ["待检定", "正常采集", "疑误待查", "已拆除"]


def _decorate(row: dict[str, Any]) -> dict[str, Any]:
    """列表/导出统一加工：可用动作与有效期提示都从同一份数据派生，保证口径一致。"""
    item = dict(row)
    item["available_actions"] = service.available_actions(str(row.get("status") or ""))
    item["expiry_state"] = service.expiry_state(row)
    return item


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按传感器编号检索"),
    status: str | None = Query(default=None, description="待检定、正常采集、疑误待查、已拆除"),
    expiry_missing: bool = Query(default=False, description="只看检定有效期缺失的在装传感器"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按传感器编号与状态过滤观测传感器列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail="状态取值不合法")
    items, total = service.list_entries(
        keyword=keyword, status=status, expiry_missing=expiry_missing, page=page, size=size
    )
    return PageResult(items=[_decorate(row) for row in items], total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, int]:
    """统计卡口径与列表同源：在装、正常采集、待检定、疑误待查、已拆除、有效期缺失。"""
    return service.statistics()


@router.get("/export")
def export_entries(
    status: str | None = Query(default=None, description="可选：只导出指定状态"),
    expiry_missing: bool = Query(default=False, description="可选：只导出有效期缺失记录"),
    include_removed: bool = Query(default=True, description="是否包含已拆除传感器，默认包含"),
) -> dict[str, Any]:
    """导出清单与列表页同一过滤口径；同时回填统计，便于三处对账。"""
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=400, detail="状态取值不合法")
    items, total = service.list_entries(
        status=status, expiry_missing=expiry_missing, page=1, size=10000
    )
    if not include_removed and status is None:
        items = [row for row in items if row.get("status") != REMOVED]
        total = len(items)
    payload = service.statistics()
    return {
        "module": "sensor",
        "total": total,
        "include_removed": include_removed,
        "status": status,
        "expiry_missing": expiry_missing,
        "stats": payload,
        "items": [_decorate(row) for row in items],
    }


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条观测传感器明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"观测传感器 {entry_id} 不存在或已归档")
    item = _decorate(entry)
    return item


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条观测传感器，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="观测传感器已登记", entry=_decorate(entry))


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条传感器执行动作；不允许的跳转被拦下并说明原因，重复执行同一动作幂等。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message, changed = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message, changed=False)
    return ActionResult(ok=True, message=message, entry=_decorate(entry), changed=changed)
