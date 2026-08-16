"""collector 归一化与 WS 推送测试。"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.collector import Collector, normalize_record
from app.config import AppConfig
from app.db import Database
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


async def test_poll_unified_normalizes_records(tmp_path):
    """回归：_poll_unified 真实调用路径（非 ns 分支）必须能归一化入库。

    曾因 normalize_record 改 keyword-only 后旧位置参数调用未同步而崩
    （takes 3 positional arguments but 7 were given）。
    """
    cfg = AppConfig.model_validate({"instances": [{"name": "a", "host": "h", "port": "1", "token": "t"}]})
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    col = Collector(cfg, db)

    class FakeOK:
        async def get_log_page(self, path, page, page_size):
            return {
                "logs": [
                    {"LogTime": "2026/08/16 03:00:00", "LogContent": "hello"},
                    {"LogTime": "2026/08/16 03:01:00", "LogContent": "world"},
                ],
                "total": 2, "page": 1, "page_size": page_size,
            }

    col._clients["a"] = FakeOK()
    inserted, acc = await col._poll_unified(cfg.instances[0], "docker", "/api/docker/logs")
    assert inserted == 2
    rows = await db.query_logs(instance="a")
    assert rows["total"] == 2
    assert rows["items"][0]["content"] == "world"
    # 游标推进
    cur = await db.get_cursor("a", "docker", "", "")
    assert cur["last_ts"] == 1786820460
    await db.close()


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
