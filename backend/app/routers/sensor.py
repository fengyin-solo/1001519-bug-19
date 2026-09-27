"""观测传感器接口：维护观测传感器，覆盖安排检定、标记疑误、拆除传感器等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.sensor import STAT_LABELS, SensorService

router = APIRouter(prefix="/api/sensor", tags=["观测传感器"])

service = SensorService()

LIST_FIELDS = ["传感器编号", "所属站点", "观测要素", "设备型号", "出厂序列号", "安装高度", "检定有效期", "传感器状态"]
STATUSES = ["待检定", "正常采集", "疑误待查", "已拆除"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按传感器编号检索"),
    status: str | None = Query(default=None, description="待检定、正常采集、疑误待查、已拆除"),
    missing_validity: bool = Query(default=False, description="只看检定有效期缺失的记录"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按传感器编号、状态与检定有效期缺失过滤；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        missing_validity=missing_validity,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """采集统计卡：在装、正常采集、待检定、疑误待查、已拆除、检定有效期缺失。

    已拆除传感器不计入在装与采集口径，保证列表、统计卡、导出清单三处一致。
    """
    counts = service.stats()
    return {"items": [{"key": key, "label": label, "value": counts[key]} for key, label in STAT_LABELS]}


# 注意：/export 必须声明在 /{entry_id} 之前，否则「export」会被当成 entry_id 拦截报 422。
@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按传感器编号检索"),
    status: str | None = Query(default=None, description="待检定、正常采集、疑误待查、已拆除"),
    missing_validity: bool = Query(default=False, description="只看检定有效期缺失的记录"),
) -> dict[str, Any]:
    """导出观测传感器清单：过滤口径与列表完全一致，并随附统计卡数据。"""
    return service.export_entries(keyword=keyword, status=status, missing_validity=missing_validity)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条观测传感器明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"观测传感器 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条观测传感器，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="观测传感器已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条观测传感器执行安排检定、标记疑误、拆除传感器。

    状态机拦截非法流转；重复执行同一个动作不会产生第二条状态变化。
    """
    action = str(payload.values.get("action") or "").strip()
    if not action:
        return ActionResult(ok=False, message="缺少动作名称，请明确要执行安排检定、标记疑误还是拆除传感器")
    entry, message, changed = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message, changed=False)
    return ActionResult(ok=True, message=message, entry=entry, changed=changed)
