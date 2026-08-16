"""日志导出路由回归测试（P0：service 未定义导致 /api/export 500）。"""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import Database
from app.routes import logs as logs_router


class FakeDB:
    def __init__(self):
        self.rows = [
            {"ts_text": "2026/08/16 03:00:00", "module": "docker",
             "rule_name": "", "sub_name": "", "content": "hello"},
            {"ts_text": "2026/08/16 03:01:00", "module": "ssl",
             "rule_name": "", "sub_name": "", "content": "world"},
        ]

    async def export_rows(self, *args, **kwargs):
        # 验证 service 参数已透传（回归点）
        assert kwargs.get("service") is None
        for r in self.rows:
            yield r


def _app(db=None):
    app = FastAPI()
    app.include_router(logs_router.router)
    app.state.db = db or FakeDB()
    return app


def test_export_csv():
    with TestClient(_app()) as c:
        r = c.get("/api/export?format=csv&limit=10")
        assert r.status_code == 200
        text = r.text
        assert "time,module,rule_name,sub_name,content" in text
        assert "hello" in text and "world" in text
        assert text.startswith("\ufeff")  # Excel BOM


def test_export_json():
    with TestClient(_app()) as c:
        r = c.get("/api/export?format=json&limit=10")
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert body["items"][0]["content"] == "hello"


def test_export_service_filter_passthrough():
    """service 参数存在且可透传（原 NameError 触发点）。"""

    class DB:
        async def export_rows(self, *args, **kwargs):
            assert kwargs.get("service") == "svc-1"
            for r in [{"ts_text": "t", "module": "m", "rule_name": "r",
                       "sub_name": "s", "content": "c"}]:
                yield r

    with TestClient(_app(DB())) as c:
        r = c.get("/api/export?format=json&service=svc-1")
        assert r.status_code == 200
