"""Docker 路由代理测试。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import AppConfig
from app.db import Database
from app.routes import docker as docker_router

CID = "abc123"


def _app(monkeypatch, calls):
    class FakeClient:
        def __init__(self, inst):
            pass

        async def get_json(self, path, **k):
            if path == "/api/docker/info":
                return {"info": {"Containers": 3, "ContainersRunning": 2, "Images": 5}, "ret": 0}
            if path == "/api/docker/version":
                return {"version": {"Components": [{"Name": "Engine", "Version": "29.4.1"}]}}
            if path == "/api/docker/containers":
                return {"containers": [{"Id": CID, "Names": ["/web"], "State": "running"}], "ret": 0}
            if path == "/api/docker/containers/stats-cached":
                return {"data": {CID: {"cpu_percent": "2.0", "memory_usage": "50 MB"}}, "ret": 0}
            if path == f"/api/docker/containers/{CID}/stats":
                return {"data": {"cpu_percent": "3.0"}}
            if path == f"/api/docker/containers/{CID}/processes":
                return {"Processes": [["1", "root", "0.1", "10", "bash"]]}
            if path == f"/api/docker/containers/{CID}/logs":
                return {"logs": "\n".join(f"line{i}" for i in range(10))}
            if path == "/api/docker/images":
                return {"images": [{"Id": "img1", "RepoTags": ["lucky:v3"], "Size": 1000}]}
            if path == "/api/docker/networks":
                return {"networks": [{"Name": "bridge", "Driver": "bridge"}]}
            if path == "/api/docker/volumes":
                return {"volumes": []}
            raise AssertionError(f"unexpected path {path}")

        async def _request(self, method, path, **k):
            calls.append((method, path))
            return {"ret": 0}

        async def close(self):
            pass

    monkeypatch.setattr(docker_router, "LuckyClient", FakeClient)

    class FakeDB:
        def __init__(self):
            self.cache = {}

        async def save_docker_cache(self, instance, payload, fetched_at):
            self.cache[instance] = (payload, fetched_at)

        async def get_docker_cache(self, instance):
            if instance not in self.cache:
                return None
            payload, fetched_at = self.cache[instance]
            return {**payload, "instance": instance, "fetched_at": fetched_at}

    db = FakeDB()
    app = FastAPI()
    app.include_router(docker_router.router)
    app.state.config = AppConfig.model_validate({
        "instances": [{"name": "a", "host": "h", "port": "1", "token": "t"}],
    })
    app.state.db = db
    return app, db


def test_docker_overview(monkeypatch):
    app, _ = _app(monkeypatch, [])
    with TestClient(app) as c:
        r = c.get("/api/docker/overview?instance=a")
        assert r.status_code == 200
        assert r.json()["info"]["info"]["ContainersRunning"] == 2
        r = c.get("/api/docker/overview?instance=nope")
        assert r.status_code == 404


def test_docker_containers_merge_stats(monkeypatch):
    app, _ = _app(monkeypatch, [])
    with TestClient(app) as c:
        r = c.get("/api/docker/containers?instance=a")
        body = r.json()
        assert body["total"] == 1
        assert body["containers"][0]["stats"]["cpu_percent"] == "2.0"


def test_docker_detail_and_logs_tail(monkeypatch):
    app, _ = _app(monkeypatch, [])
    with TestClient(app) as c:
        r = c.get(f"/api/docker/container/{CID}?instance=a")
        assert r.json()["stats"]["cpu_percent"] == "3.0"
        assert len(r.json()["processes"]["Processes"]) == 1
        r = c.get(f"/api/docker/container/{CID}/logs?instance=a&tail=3")
        lines = r.json()["logs"].splitlines()
        assert lines == ["line7", "line8", "line9"]


def test_docker_action_mapping(monkeypatch):
    calls = []
    app, _ = _app(monkeypatch, calls)
    with TestClient(app) as c:
        for action, suffix in [
            ("start", "start"),
            ("stop", "stop"),
            ("restart", "restart"),
            ("pause", "pause"),
            ("unpause", "unpause"),
        ]:
            r = c.post(f"/api/docker/containers/{CID}/action?instance=a&action={action}")
            assert r.status_code == 200
            assert r.json()["ok"] is True
            assert ("POST", f"/api/docker/containers/{CID}/{suffix}") in calls
        r = c.post(f"/api/docker/containers/{CID}/action?instance=a&action=bogus")
        assert r.status_code == 400


def test_docker_lists(monkeypatch):
    app, _ = _app(monkeypatch, [])
    with TestClient(app) as c:
        assert c.get("/api/docker/images?instance=a").json()["images"][0]["RepoTags"] == ["lucky:v3"]
        assert c.get("/api/docker/networks?instance=a").json()["networks"][0]["Name"] == "bridge"
        assert c.get("/api/docker/volumes?instance=a").json()["volumes"] == []


def test_docker_snapshot_and_refresh(monkeypatch):
    app, db = _app(monkeypatch, [])
    with TestClient(app) as c:
        # 无缓存时 snapshot 返回空
        s = c.get("/api/docker/snapshot?instance=a").json()
        assert s["containers"] == []
        assert s["fetched_at"] == 0
        # refresh → 全量拉取并写缓存
        r = c.post("/api/docker/refresh?instance=a")
        assert r.status_code == 200
        body = r.json()
        assert body["containers"][0]["Id"] == CID
        assert body["fetched_at"] > 0
        assert db.cache["a"][0]["images"][0]["RepoTags"] == ["lucky:v3"]
        # 之后 snapshot 读缓存
        s = c.get("/api/docker/snapshot?instance=a").json()
        assert s["containers"][0]["Id"] == CID


async def test_docker_cache_db_roundtrip(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    assert await db.get_docker_cache("a") is None
    await db.save_docker_cache("a", {"info": {"x": 1}, "version": {}, "containers": [{"Id": "1"}],
                                       "images": [], "networks": [], "volumes": []}, 123)
    got = await db.get_docker_cache("a")
    assert got["fetched_at"] == 123
    assert got["containers"][0]["Id"] == "1"
    assert got["info"]["x"] == 1
    await db.close()
