"""后端排序 / IP 全量排序与 limit 测试。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import Database
from app.routes import access as access_router
from app.routes.access import _sort_ips
from tests.test_db import _row


async def test_query_logs_sort(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    await db.insert_logs([
        _row(module="docker", ts_epoch=100, ts_text="2026/08/15 00:00:00"),
        _row(module="ssl", ts_epoch=300, ts_text="2026/08/15 00:05:00"),
        _row(module="cron", ts_epoch=200, ts_text="2026/08/15 00:10:00"),
    ])
    r = await db.query_logs(instance="inst1", sort="module", sort_dir="asc")
    assert [i["module"] for i in r["items"]] == ["cron", "docker", "ssl"]
    r = await db.query_logs(instance="inst1", sort="module", sort_dir="desc")
    assert [i["module"] for i in r["items"]] == ["ssl", "docker", "cron"]
    r = await db.query_logs(instance="inst1", sort="content", sort_dir="asc")
    assert r["total"] == 3
    # 非法键 → 回退时间倒序
    r = await db.query_logs(instance="inst1", sort="bogus", sort_dir="asc")
    assert r["items"][0]["ts_epoch"] == 300
    await db.close()


async def test_query_access_logs_sort(tmp_path):
    from app.access_parser import parse_access_row
    from tests.test_access import _access_rec

    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    await db.insert_access_logs([
        parse_access_row("inst1", _access_rec(ip="9.9.9.9", url="/b")),
        parse_access_row("inst1", _access_rec(ip="1.1.1.1", url="/a")),
    ])
    r = await db.query_access_logs(instance="inst1", sort="ip", sort_dir="asc")
    assert [i["client_ip"] for i in r["items"]] == ["1.1.1.1", "9.9.9.9"]
    r = await db.query_access_logs(instance="inst1", sort="path", sort_dir="asc")
    assert [i["path"] for i in r["items"]] == ["/a", "/b"]
    await db.close()


def test_sort_ips():
    items = [
        {"client_ip": "b", "count": 1, "geo_short": "广东省", "connections": 0, "traffic_in": 0, "traffic_out": 0, "last_access": 0},
        {"client_ip": "a", "count": 3, "geo_short": "北京市", "connections": 2, "traffic_in": 10, "traffic_out": 20, "last_access": 5},
    ]
    assert _sort_ips(items, "count", "desc")[0]["client_ip"] == "a"
    assert _sort_ips(items, "ip", "asc")[0]["client_ip"] == "a"
    assert _sort_ips(items, "geo", "asc")[0]["client_ip"] == "a"  # 北京 < 广东
    assert _sort_ips(items, "traffic_out", "desc")[0]["client_ip"] == "a"
    assert _sort_ips(items, "bogus", "asc")[0]["client_ip"] == "a"  # 默认 count 降序


class FakeDB:
    def __init__(self):
        self.items = [
            {"client_ip": "10.0.0.2", "count": 1, "connections": 0, "traffic_in": 0, "traffic_out": 0, "last_access": 0},
            {"client_ip": "10.0.0.1", "count": 5, "connections": 3, "traffic_in": 100, "traffic_out": 200, "last_access": 9},
        ]

    async def access_ips(self, *a, **k):
        return {"total": 2, "items": list(self.items)}


def test_access_ips_route_sort_and_limit(monkeypatch):
    app = FastAPI()
    app.include_router(access_router.router)
    app.state.db = FakeDB()
    monkeypatch.setattr(access_router, "geo_query", lambda ip: None)
    monkeypatch.setattr(access_router, "geo_short", lambda ip: "未知")
    with TestClient(app) as c:
        r = c.get("/api/access/ips?sort=count&sort_dir=desc&page_size=10")
        items = r.json()["items"]
        assert items[0]["client_ip"] == "10.0.0.1"
        r = c.get("/api/access/ips?sort=ip&sort_dir=asc&limit=1")
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["client_ip"] == "10.0.0.1"
        assert r.json()["total"] == 2
