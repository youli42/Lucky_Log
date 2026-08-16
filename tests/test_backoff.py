"""采集失败指数退避测试。"""
import asyncio
import time

from app.collector import Collector
from app.config import AppConfig
from app.db import Database
from app.lucky_client import LuckyError


def _cfg():
    return AppConfig.model_validate({
        "instances": [{"name": "a", "host": "h", "port": "1", "token": "t"}],
        "backoff": {"base": 2, "max": 60, "max_retries": 3},
    })


async def _collector(tmp_path, fake):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    col = Collector(_cfg(), db)
    col._collect_instance = fake
    return db, col


async def test_failure_backoff_and_growth(tmp_path):
    async def fail(inst):
        raise LuckyError("boom", status=None)

    db, col = await _collector(tmp_path, fail)
    await col._run_instance(col.cfg.instances[0])
    st = col.status["a"]
    assert st["fail_count"] == 1
    assert st["backoff_until"] > int(time.time())
    assert st["next_retry_in"] >= 1
    assert "boom" in st["last_error"]

    # 连续失败 → 退避增长（指数）
    prev = st["backoff_until"]
    await col._run_instance(col.cfg.instances[0])
    assert col.status["a"]["fail_count"] == 2
    assert col.status["a"]["backoff_until"] > prev
    await db.close()


async def test_success_resets_backoff(tmp_path):
    async def ok(inst):
        pass

    db, col = await _collector(tmp_path, ok)
    inst = col.cfg.instances[0]
    await col._run_instance(inst)  # 成功
    st = col.status["a"]
    assert st["last_error"] is None
    assert st["fail_count"] == 0
    assert st["backoff_until"] == 0
    assert st["last_collect"] > 0
    await db.close()


async def test_collect_once_skips_backoff(tmp_path):
    calls = []
    async def fail(inst):
        calls.append(inst.name)
        raise LuckyError("boom")

    db, col = await _collector(tmp_path, fail)
    inst = col.cfg.instances[0]
    await col._run_instance(inst)  # 第 1 次失败 → 进入退避
    assert col.status["a"]["fail_count"] == 1
    calls.clear()
    await col._collect_once()  # 退避中 → 跳过
    assert calls == []
    # 手动采集无视退避
    assert col.collect_now("a") is True
    await asyncio.sleep(0.05)
    assert calls == ["a"]
    await db.close()


async def test_long_cooldown_after_max_retries(tmp_path):
    async def fail(inst):
        raise LuckyError("boom")

    db, col = await _collector(tmp_path, fail)
    inst = col.cfg.instances[0]
    for _ in range(4):  # 超过 max_retries=3
        await col._run_instance(inst)
    st = col.status["a"]
    assert st["fail_count"] == 4
    # 超过 max_retries 后进入长冷却 = backoff.max
    assert st["next_retry_in"] <= 60
    assert st["next_retry_in"] > 20  # 不再是快速重试的小退避
    await db.close()


def test_lucky_error_status():
    e = LuckyError("HTTP 404: nope", status=404)
    assert e.status == 404
    e2 = LuckyError("网络错误")
    assert e2.status is None
