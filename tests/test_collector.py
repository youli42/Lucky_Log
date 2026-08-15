"""collector 归一化与 WS 推送测试。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.collector import normalize_record, normalize_system_record, parse_ts_text
from app.routes import stream


def test_parse_ts_text():
    assert parse_ts_text("2026/08/16 03:00:00") == 1786820400
    assert parse_ts_text(None) == 0
    assert parse_ts_text("bad") == 0


def test_normalize_record():
    rec = {"LogContent": "hi", "LogTime": "2026/08/16 03:00:00", "ShowTime": False}
    row = normalize_record("inst", "docker", rec, rule_key="rk", rule_name="rn")
    assert row["instance"] == "inst"
    assert row["module"] == "docker"
    assert row["rule_key"] == "rk"
    assert row["rule_name"] == "rn"
    assert row["ts_epoch"] == 1786820400
    assert row["content"] == "hi"
    assert row["raw_json"].startswith("{")


def test_normalize_system_record():
    rec = {"timestamp": "1786820400123456789", "log": "boot ok", "time": "2026/08/16 03:00:00"}
    row = normalize_system_record("inst", rec)
    assert row["ts_epoch"] == 1786820400  # 纳秒 → 秒
    assert row["module"] == "system"
    assert row["content"] == "boot ok"


def test_normalize_system_record_bad_ns():
    rec = {"timestamp": "not-a-number", "log": "x", "time": "2026/08/16 03:00:00"}
    row = normalize_system_record("inst", rec)
    assert row is not None
    assert row["ts_epoch"] == 1786820400


class FakeCollector:
    def __init__(self):
        self.queues = set()

    def subscribe(self, q):
        self.queues.add(q)

    def unsubscribe(self, q):
        self.queues.discard(q)

    def push(self, payload):
        for q in list(self.queues):
            q.put_nowait(payload)


def test_ws_stream_push():
    app = FastAPI()
    app.include_router(stream.router)
    fake = FakeCollector()
    app.state.collector = fake
    with TestClient(app) as client:
        with client.websocket_connect("/ws/stream") as ws:
            fake.push({"type": "logs", "items": [{"id": 1, "module": "docker", "content": "hi"}]})
            data = ws.receive_json()
            assert data["type"] == "logs"
            assert data["items"][0]["content"] == "hi"
