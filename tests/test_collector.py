"""collector 归一化与 WS 推送测试。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.collector import normalize_record
from app.routes import stream
from app.timeutil import parse_lucky_ts


def test_parse_lucky_ts():
    assert parse_lucky_ts("2026/08/16 03:00:00") == 1786820400
    assert parse_lucky_ts(None) == 0
    assert parse_lucky_ts("bad") == 0


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
    # system 结构 {timestamp(纳秒), log, time} → 同一 normalize_record（ts_field="time"）
    rec = {"timestamp": "1786820400123456789", "log": "boot ok", "time": "2026/08/16 03:00:00"}
    row = normalize_record("inst", "system", rec, ts_field="time", content_field="log")
    assert row["ts_epoch"] == 1786820400  # 纳秒 → 秒
    assert row["module"] == "system"
    assert row["content"] == "boot ok"


def test_normalize_system_record_bad_ns():
    rec = {"timestamp": "not-a-number", "log": "x", "time": "2026/08/16 03:00:00"}
    row = normalize_record("inst", "system", rec, ts_field="time", content_field="log")
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
