"""观测传感器状态流转、统计口径与导出对账的回归测试。"""
from __future__ import annotations

import pytest

from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    # store 是进程级单例，每个用例前重新装载，避免用例间状态污染
    from app import seed, store as store_module

    store_module.store.__init__()
    return TestClient(app)


def act(client: TestClient, entry_id: int, action: str) -> dict:
    response = client.post(
        f"/api/sensor/{entry_id}/actions",
        json={"values": {"action": action}},
    )
    return response.json()


def test_seed_stats_excludes_removed_from_collecting(client: TestClient) -> None:
    stats = client.get("/api/sensor/stats").json()
    assert stats == {
        "installed": 3,
        "collecting": 1,
        "pending": 1,
        "suspect": 1,
        "removed": 1,
        "expiry_missing": 1,
    }


def test_arrange_verification_is_idempotent_when_already_pending(client: TestClient) -> None:
    result = act(client, 1, "安排检定")
    assert result["ok"] is True
    assert result["changed"] is False
    assert result["entry"]["status"] == "待检定"
    assert result["entry"].get("history", []) == []  # seed 数据没有历史，不应凭空追加


def test_suspect_requires_passing_verification_first(client: TestClient) -> None:
    result = act(client, 1, "标记疑误")
    assert result["ok"] is False
    assert "不能标记疑误" in result["message"]
    assert client.get("/api/sensor/1").json()["status"] == "待检定"


def test_full_lifecycle_and_transition_rules(client: TestClient) -> None:
    assert act(client, 1, "检定通过")["entry"]["status"] == "正常采集"
    assert act(client, 1, "安排检定")["entry"]["status"] == "待检定"
    assert act(client, 1, "检定通过")["entry"]["status"] == "正常采集"
    assert act(client, 1, "标记疑误")["entry"]["status"] == "疑误待查"
    assert act(client, 1, "复检恢复")["entry"]["status"] == "正常采集"

    removed = act(client, 1, "拆除传感器")
    assert removed["entry"]["status"] == "已拆除"
    assert removed["entry"]["传感器状态"] == "已拆除"
    assert removed["entry"]["available_actions"] == []
    # 终态后任何动作都被拒绝
    assert act(client, 1, "标记疑误")["ok"] is False


def test_double_click_same_action_creates_single_history_entry(client: TestClient) -> None:
    act(client, 1, "检定通过")
    first = act(client, 1, "标记疑误")
    second = act(client, 1, "标记疑误")
    assert first["changed"] is True
    assert second["changed"] is False
    history = client.get("/api/sensor/1").json()["history"]
    suspect_entries = [h for h in history if h["action"] == "标记疑误"]
    assert len(suspect_entries) == 1


def test_removed_sensor_not_in_collecting_stats(client: TestClient) -> None:
    act(client, 2, "拆除传感器")  # id=2 原本正常采集
    stats = client.get("/api/sensor/stats").json()
    assert stats["collecting"] == 0
    assert stats["removed"] == 2
    assert stats["installed"] == 2


def test_list_export_and_stats_are_consistent(client: TestClient) -> None:
    act(client, 2, "拆除传感器")
    listed = client.get("/api/sensor").json()
    exported = client.get("/api/sensor/export").json()
    list_counts: dict[str, int] = {}
    for item in listed["items"]:
        list_counts[item["status"]] = list_counts.get(item["status"], 0) + 1
    export_counts: dict[str, int] = {}
    for item in exported["items"]:
        export_counts[item["status"]] = export_counts.get(item["status"], 0) + 1
    assert list_counts == export_counts
    assert exported["stats"] == client.get("/api/sensor/stats").json()
    assert listed["total"] == exported["total"]


def test_export_filters_match_list_filters(client: TestClient) -> None:
    removed_export = client.get("/api/sensor/export", params={"status": "已拆除"}).json()
    assert removed_export["total"] == 1
    assert all(item["status"] == "已拆除" for item in removed_export["items"])

    active_export = client.get("/api/sensor/export", params={"include_removed": False}).json()
    assert all(item["status"] != "已拆除" for item in active_export["items"])


def test_expiry_missing_is_findable(client: TestClient) -> None:
    # id=3 检定有效期为空：统计卡有数、列表能过滤、行内有 missing 标记
    assert client.get("/api/sensor/stats").json()["expiry_missing"] == 1
    filtered = client.get("/api/sensor", params={"expiry_missing": True}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["传感器编号"] == "SENS-0003"
    assert filtered["items"][0]["expiry_state"] == "missing"


def test_invalid_status_filter_rejected(client: TestClient) -> None:
    assert client.get("/api/sensor", params={"status": "不存在"}).status_code == 400


def test_missing_detail_returns_404(client: TestClient) -> None:
    assert client.get("/api/sensor/999").status_code == 404


def test_create_entry_initializes_consistent_fields(client: TestClient) -> None:
    bad = client.post("/api/sensor", json={"values": {"传感器编号": "SENS-X"}}).json()
    assert bad["ok"] is False

    created = client.post(
        "/api/sensor",
        json={"values": {"传感器编号": "SENS-9", "所属站点": "北山", "观测要素": "气压"}},
    ).json()
    entry = created["entry"]
    assert entry["status"] == "待检定"
    assert entry["传感器状态"] == "待检定"
    assert entry["expiry_state"] == "missing"
    assert entry["history"][0]["action"] == "登记建档"
