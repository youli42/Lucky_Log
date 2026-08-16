"""并发采集 / 手动采集 / 进度 / 存储统计测试。"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.collector import Collector
from app.config import AppConfig
from app.db import Database
from app.routes import collect as collect_router
from tests.test_access import _access_rec
from tests.test_db import _row
from app.access_parser import parse_access_row


def _cfg(instances):
    return AppConfig.model_validate({"instances": instances})


async def test_collect_once_runs_all_instances(tmp_path):
    cfg = _cfg([
        {"name": "a", "host": "h", "port": "1", "token": "t"},
        {"name": "b", "host": "h", "port": "1", "token": "t"},
    ])
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    col = Collector(cfg, db)
    ran = []

    async def fake_collect(inst):
        ran.append(inst.name)
        await asyncio.sleep(0.01)

    col._collect_instance = fake_collect
    await col._collect_once()
    assert sorted(ran) == ["a", "b"]
    assert col.status["a"]["last_collect"] > 0
    assert col.status["a"]["collecting"] is False
    assert col.status["b"]["last_collect"] > 0
    await db.close()


async def test_collect_now_guards_reentry(tmp_path):
    cfg = _cfg([{"name": "a", "host": "h", "port": "1", "token": "t"}])
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    col = Collector(cfg, db)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_collect(inst):
        started.set()
        await release.wait()

    col._collect_instance = fake_collect
    assert col.collect_now("a") is True
    await started.wait()
    assert col.collect_now("a") is False  # 采集中 → 防重
    assert col.collect_now("no-such") is False
    release.set()
    for _ in range(50):
        if "a" not in col._collecting:
            break
        await asyncio.sleep(0.02)
    assert "a" not in col._collecting
    await db.close()


async def test_collect_all_counts(tmp_path):
    cfg = _cfg([
        {"name": "a", "host": "h", "port": "1", "token": "t"},
        {"name": "b", "host": "h", "port": "1", "token": "t"},
    ])
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    col = Collector(cfg, db)
    ran = []

    async def fake_collect(inst):
        ran.append(inst.name)
        await asyncio.sleep(0.01)

    col._collect_instance = fake_collect
    started = col.collect_all()
    assert started == 2
    await asyncio.sleep(0.1)
    assert sorted(ran) == ["a", "b"]
    await db.close()


async def test_storage_stats(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    await db.insert_logs([_row(instance="inst1"), _row(instance="inst2")])
    await db.insert_access_logs([
        parse_access_row("inst1", _access_rec(), sub_key="s1"),
    ])
    s = await db.storage_stats()
    assert s["db_bytes"] > 0
    assert s["tables"]["logs"]["rows"] == 2
    assert s["tables"]["logs"]["bytes"] > 0
    assert s["tables"]["access_logs"]["rows"] == 1
    by = {p["name"]: p for p in s["per_instance"]}
    assert by["inst1"]["logs"] == 1
    assert by["inst1"]["access"] == 1
    assert by["inst2"]["logs"] == 1
    await db.close()


class FakeCollector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.started = []
        self.status = {}

    def collect_now(self, name):
        self.started.append(name)
        return True

    def collect_all(self):
        return 2


class FakeDB:
    async def storage_stats(self):
        return {"db_bytes": 123, "tables": {}, "per_instance": []}


def test_collect_endpoints(tmp_path):
    cfg = _cfg([{"name": "a", "host": "h", "port": "1", "token": "t"}])
    app = FastAPI()
    app.include_router(collect_router.router)
    app.state.config = cfg
    app.state.collector = FakeCollector(cfg)
    app.state.db = FakeDB()
    with TestClient(app) as c:
        r = c.post("/api/collect?instance=a")
        assert r.status_code == 200
        assert r.json()["started"] is True
        r = c.post("/api/collect?instance=nope")
        assert r.status_code == 404
        r = c.post("/api/collect/all")
        assert r.json()["started"] == 2
        r = c.get("/api/storage")
        assert r.json()["db_bytes"] == 123
