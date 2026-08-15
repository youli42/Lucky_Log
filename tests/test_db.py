"""db 数据层测试：去重 / 查询 / 统计 / 导出 / 游标。"""
import json

import pytest

from app.db import Database

BASE = 1786820400  # 2026/08/16 03:00:00 (本地时区)


def _row(instance="inst1", module="docker", ts_text="2026/08/16 03:00:00",
         content="hello", ts_epoch=BASE, rule_key="", rule_name=""):
    return {
        "instance": instance, "module": module, "rule_key": rule_key,
        "rule_name": rule_name, "sub_key": "", "sub_name": "",
        "ts_epoch": ts_epoch, "ts_text": ts_text, "content": content,
        "raw_json": json.dumps({"LogContent": content, "LogTime": ts_text}),
        "fetched_at": BASE,
    }


@pytest.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "t.db"))
    await d.connect()
    yield d
    await d.close()


async def test_insert_dedup(db):
    rows = [
        _row(),
        _row(content="world"),
        _row(content="dup"),      # 与下一条完全相同 → 去重
        _row(content="dup"),
    ]
    inserted = await db.insert_logs(rows)
    assert inserted == 3
    inserted2 = await db.insert_logs(rows[:2])  # 重复插入
    assert inserted2 == 0
    res = await db.query_logs(instance="inst1")
    assert res["total"] == 3


async def test_query_filters_and_pagination(db):
    rows = []
    for i in range(10):
        rows.append(_row(
            module="docker" if i % 2 == 0 else "ssl",
            ts_text=f"2026/08/16 03:{i:02d}:00",
            ts_epoch=BASE + i * 60,
            content=f"line-{i}",
        ))
    await db.insert_logs(rows)
    res = await db.query_logs(instance="inst1", module="docker", page=1, page_size=5)
    assert res["total"] == 5
    assert len(res["items"]) == 5
    assert all(it["module"] == "docker" for it in res["items"])
    assert res["items"][0]["ts_epoch"] > res["items"][-1]["ts_epoch"]
    res = await db.query_logs(instance="inst1", from_epoch=BASE, to_epoch=BASE + 4 * 60)
    assert res["total"] == 5
    res = await db.query_logs(instance="inst1", search="line-3")
    assert res["total"] == 1
    assert res["items"][0]["content"] == "line-3"


async def test_query_dedup_content(db):
    await db.insert_logs([
        _row(ts_text="2026/08/16 03:00:00", ts_epoch=BASE, content="same"),
        _row(ts_text="2026/08/16 04:00:00", ts_epoch=BASE + 3600, content="same"),
    ])
    res = await db.query_logs(instance="inst1", dedup="time_content")
    assert res["total"] == 2
    res = await db.query_logs(instance="inst1", dedup="content")
    assert res["total"] == 1
    res = await db.query_logs(instance="inst1", dedup="off")
    assert res["total"] == 2


async def test_stats(db):
    await db.insert_logs([
        _row(module="docker", ts_epoch=BASE, ts_text="2026/08/16 03:00:00"),
        _row(module="docker", ts_epoch=BASE + 60, ts_text="2026/08/16 03:01:00"),
        _row(module="ssl", ts_epoch=BASE + 1800, ts_text="2026/08/16 03:30:00"),
    ])
    by_module = await db.stats_by_module("inst1", None, None)
    assert {m["module"]: m["count"] for m in by_module} == {"docker": 2, "ssl": 1}
    tl = await db.stats_timeline("inst1", None, None, None, "hour")
    assert sum(t["count"] for t in tl) == 3
    mod_counts = await db.module_counts("inst1")
    assert {m["module"]: m["count"] for m in mod_counts} == {"docker": 2, "ssl": 1}


async def test_export_rows(db):
    await db.insert_logs([_row(), _row(content="second")])
    out = [r async for r in db.export_rows(instance="inst1", limit=10)]
    assert len(out) == 2
    assert {r["content"] for r in out} == {"hello", "second"}


async def test_cursor_save_update_and_error(db):
    await db.save_cursor("inst1", "docker", "", "", last_ts=100, last_total=5)
    cur = await db.get_cursor("inst1", "docker", "", "")
    assert cur["last_ts"] == 100
    assert cur["last_total"] == 5
    assert cur["last_error"] is None
    await db.save_cursor("inst1", "docker", "", "", error="boom")
    cur = await db.get_cursor("inst1", "docker", "", "")
    assert cur["last_ts"] == 100
    assert cur["last_error"] == "boom"
    await db.save_cursor("inst1", "docker", "", "", last_ts=200, last_total=8)
    cur = await db.get_cursor("inst1", "docker", "", "")
    assert cur["last_ts"] == 200
    assert cur["last_total"] == 8


async def test_cleanup(db):
    await db.insert_logs([
        _row(ts_epoch=BASE - 100, ts_text="2026/08/15 22:58:20"),
        _row(ts_epoch=BASE - 10 * 86400, ts_text="2026/08/05 03:00:00"),
    ])
    deleted = await db.cleanup_old(days=7)
    assert deleted == 1
    res = await db.query_logs(instance="inst1")
    assert res["total"] == 1
