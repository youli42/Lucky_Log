"""配置管理 API 与采集器热同步测试。"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.collector import Collector
from app.config import AppConfig
from app.db import Database
from app.routes import config as config_router


class FakeCollector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.synced = 0

    async def sync_instances(self):
        self.synced += 1


class FakeDB:
    def __init__(self):
        self.purged = []

    async def purge_instance(self, name):
        self.purged.append(name)


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = AppConfig.model_validate({
        "instances": [
            {"name": "a", "host": "h", "port": "1", "token": "t", "modules": ["docker"]},
        ]
    })
    app = FastAPI()
    app.include_router(config_router.router)
    app.state.config = cfg
    app.state.collector = FakeCollector(cfg)
    app.state.db = FakeDB()
    monkeypatch.setattr(config_router, "save_config", lambda *a, **k: None)
    with TestClient(app) as c:
        yield c, cfg, app


def test_get_config(client):
    c, cfg, _ = client
    r = c.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["config"]["instances"][0]["token"] == "t"
    assert "modules" in body and "webservice" in body["modules"]


def test_put_config(client):
    c, cfg, app = client
    body = cfg.model_dump()
    body["instances"].append({"name": "b", "host": "h2", "port": "2", "token": "t2"})
    r = c.put("/api/config", json=body)
    assert r.status_code == 200
    names = [i["name"] for i in r.json()["config"]["instances"]]
    assert names == ["a", "b"]
    assert app.state.collector.synced == 1
    assert app.state.collector.cfg is app.state.config


def test_delete_instance(client):
    c, cfg, app = client
    r = c.delete("/api/config/instance/a")
    assert r.status_code == 200
    assert r.json()["config"]["instances"] == []
    r = c.delete("/api/config/instance/not-exist")
    assert r.status_code == 404
    # purge
    cfg2 = AppConfig.model_validate({
        "instances": [{"name": "x", "host": "h", "port": "1", "token": "t"}],
    })
    app.state.config = cfg2
    app.state.collector.cfg = cfg2
    r = c.delete("/api/config/instance/x?purge=true")
    assert r.status_code == 200
    assert app.state.db.purged == ["x"]


def test_test_endpoint_ok(client, monkeypatch):
    c, _, _ = client

    class FakeClient:
        def __init__(self, inst):
            pass

        async def get_json(self, path, **k):
            return {"ret": 0}

        async def close(self):
            pass

    monkeypatch.setattr("app.lucky_client.LuckyClient", FakeClient)
    r = c.post("/api/config/test", json={"host": "h", "port": "1", "token": "t"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_test_endpoint_fail(client, monkeypatch):
    c, _, _ = client

    class BadClient:
        def __init__(self, inst):
            pass

        async def get_json(self, path, **k):
            raise RuntimeError("boom")

        async def close(self):
            pass

    monkeypatch.setattr("app.lucky_client.LuckyClient", BadClient)
    r = c.post("/api/config/test", json={"host": "h", "port": "1", "token": "t"})
    assert r.json()["ok"] is False
    assert "boom" in r.json()["error"]


async def test_sync_instances_drops_changed(tmp_path):
    cfg = AppConfig.model_validate({
        "instances": [{"name": "a", "host": "h", "port": "1", "token": "t"}],
    })
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    col = Collector(cfg, db)

    class FakeClient:
        def __init__(self, params):
            self.cfg = SimpleNamespace(**params)
            self.closed = False

        async def close(self):
            self.closed = True

    col._clients["a"] = FakeClient(dict(host="h", port="1", base="/youlilucky", https=True, token="t"))
    # token 变化 → 应关闭并移除客户端 a
    cfg.instances[0].token = "new-token"
    await col.sync_instances()
    assert "a" not in col._clients
    # 新增实例 b（无缓存客户端）→ 不清除任何东西
    cfg.instances = AppConfig.model_validate({
        "instances": [
            {"name": "a", "host": "h", "port": "1", "token": "new-token"},
            {"name": "b", "host": "h2", "port": "2", "token": "t2"},
        ],
    }).instances
    await col.sync_instances()
    assert col._clients == {}
    await db.close()


async def test_sync_instances_keeps_unchanged(tmp_path):
    cfg = AppConfig.model_validate({
        "instances": [{"name": "a", "host": "h", "port": "1", "token": "t"}],
    })
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    col = Collector(cfg, db)

    class FakeClient:
        def __init__(self, params):
            self.cfg = SimpleNamespace(**params)
            self.closed = False

        async def close(self):
            self.closed = True

    fc = FakeClient(dict(host="h", port="1", base="/youlilucky", https=True, token="t"))
    col._clients["a"] = fc
    await col.sync_instances()
    assert col._clients.get("a") is fc
    assert not fc.closed
    await db.close()
