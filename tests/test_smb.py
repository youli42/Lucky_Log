"""SMB 路由 + 404 跳过不退避测试。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.collector import Collector
from app.config import AppConfig
from app.db import Database
from app.lucky_client import LuckyError
from app.routes import smb as smb_router


async def test_poll_unified_404_skips(tmp_path):
    cfg = AppConfig.model_validate({"instances": [{"name": "a", "host": "h", "port": "1", "token": "t"}]})
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    col = Collector(cfg, db)

    class Fake404:
        async def get_log_page(self, path, page, page_size):
            raise LuckyError("HTTP 404: not found", status=404)

    col._clients["a"] = Fake404()
    inserted, acc = await col._poll_unified(cfg.instances[0], "docker", "/api/docker/logs")
    assert inserted == 0  # 404 → 跳过，不抛错、不退避

    class FakeNetErr:
        async def get_log_page(self, path, page, page_size):
            raise LuckyError("connection failed")

    col._clients["a"] = FakeNetErr()
    with pytest.raises(LuckyError):
        await col._poll_unified(cfg.instances[0], "docker", "/api/docker/logs")
    await db.close()


def _smb_app(monkeypatch):
    class FakeClient:
        def __init__(self, inst):
            pass

        async def get_json(self, path, **k):
            if "status" in path:
                return {"status": True, "errMsg": "", "ret": 0}
            return {"summary": {"enabled": True, "running": True}, "connections": [], "users": [], "ret": 0}

        async def post_json(self, path, **k):
            return {"ret": 0}

        async def close(self):
            pass

    monkeypatch.setattr(smb_router, "LuckyClient", FakeClient)
    app = FastAPI()
    app.include_router(smb_router.router)
    app.state.config = AppConfig.model_validate({
        "instances": [{"name": "a", "host": "h", "port": "1", "token": "t"}],
    })
    return app


def test_smb_overview(monkeypatch):
    with TestClient(_smb_app(monkeypatch)) as c:
        r = c.get("/api/smb/overview?instance=a")
        assert r.status_code == 200
        body = r.json()
        assert body["status"]["status"] is True
        assert body["runtime"]["summary"]["running"] is True
        r = c.get("/api/smb/overview?instance=nope")
        assert r.status_code == 404


def test_smb_disconnect(monkeypatch):
    with TestClient(_smb_app(monkeypatch)) as c:
        r = c.post("/api/smb/connections/abc/disconnect?instance=a")
        assert r.status_code == 200
        assert r.json()["ret"] == 0
