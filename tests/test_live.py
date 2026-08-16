"""实时连接详情接口测试（/api/access/connections）。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.lucky_client import LuckyError
from app.routes import access as access_router


class _Fake404(LuckyError):
    def __init__(self):
        super().__init__("HTTP 404: not found", status=404)


class FakeClient:
    def __init__(self, inst):
        pass

    async def fetch_service_tree(self):
        return [{
            "Key": "r1", "Name": "rule1",
            "SubRuleList": [{"Key": "s1", "Name": "sub1"}, {"Key": "s2", "Name": "sub2"}],
        }]

    async def get_json(self, path, params=None, **k):
        if "accessdetail" in path:
            if "s2" in path:  # 404 子代理 → 跳过
                raise _Fake404()
            return {
                "resList": [
                    {"IP": "198.51.100.7", "Connections": 2, "TrafficIn": 100, "TrafficOut": 50, "LastAccess": 1786820400},
                    {"IP": "198.51.100.8", "Connections": 1, "TrafficIn": 10, "TrafficOut": 5, "LastAccess": 1786820401},
                    {"IP": "", "Connections": 9, "TrafficIn": 0, "TrafficOut": 0},  # 空 IP 忽略
                ],
                "ret": 0,
            }
        raise AssertionError(f"unexpected path {path}")


class FakeCollector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.status = {}
        self.allowed = [True, True, False]  # 第三次调用返回 False（冷却）

    def get_client(self, inst):
        return FakeClient(inst)

    def service_tree(self, instance):
        return []  # 强制走 fetch_service_tree 分支

    def live_allowed(self, instance):
        return self.allowed.pop(0) if self.allowed else False


def _app():
    cfg = AppConfig.model_validate({
        "instances": [{"name": "a", "host": "h", "port": "1", "token": "t"}],
    })
    app = FastAPI()
    app.include_router(access_router.router)
    app.state.config = cfg
    app.state.collector = FakeCollector(cfg)
    return app


def test_live_connections():
    with TestClient(_app()) as c:
        r = c.get("/api/access/connections?instance=a")
        assert r.status_code == 200
        body = r.json()
        assert body["total_connections"] == 3  # 2+1（空 IP 的 9 忽略）
        assert body["total_ips"] == 2
        assert len(body["services"]) == 1  # s2 404 跳过
        svc = body["services"][0]
        assert svc["rule_name"] == "rule1" and svc["sub_name"] == "sub1"
        assert svc["connections"] == 3
        assert svc["ips"][0]["client_ip"] == "198.51.100.7"
        assert svc["ips"][0]["traffic_in"] == 100
        assert "geo_short" in svc["ips"][0]  # geo 富化


def test_live_connections_404_and_cooldown():
    with TestClient(_app()) as c:
        r = c.get("/api/access/connections?instance=nope")
        assert r.status_code == 404
        assert c.get("/api/access/connections?instance=a").status_code == 200
        assert c.get("/api/access/connections?instance=a").status_code == 200
        r = c.get("/api/access/connections?instance=a")  # 冷却 → 429
        assert r.status_code == 429
