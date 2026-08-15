"""后台日志采集器（asyncio）。

按「实例 × 源」为采集单元定时轮询，游标增量入库，并通过内存队列广播增量。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from .config import AppConfig, InstanceConfig
from .db import Database
from .lucky_client import LuckyClient, LuckyError

logger = logging.getLogger(__name__)

TREE_REFRESH_SECONDS = 300
PAGE_SIZE = 100
MAX_PAGES_PER_POLL = 20
INTER_SOURCE_DELAY = 0.4

# 模块 → 统一日志端点（游标 LogTime）
SINGLE_SOURCES: dict[str, str] = {
    "system": "/api/logs",
    "webservice": "/api/webservice/logs",
    "docker": "/api/docker/logs",
    "cron": "/api/cron/logs",
    "ddns": "/api/ddns/logs",
    "ssl": "/api/ssl/logs",
    "webterminal": "/api/webterminal/logs",
    "rclone": "/api/rclone/logs",
    "filebrowser": "/api/third/filebrowser/logs",
    "wol": "/api/wol/logs",
    "ftpserver": "/api/ftpserver/logs",
    "webdav": "/api/webdav/logs",
    "dlnaservice": "/api/dlnaservice/logs",
    "frp": "/api/frp/logs",
    "cloudflared": "/api/cloudflared/logs",
    "ipdb": "/api/ipdb/logs",
    "storagemanagement": "/api/storagemanagement/logs",
    "thirdPartyAuthManager": "/api/thirdPartyAuthManager/logs",
}

# webservice 按规则源（游标 LogTime）
BY_RULE_SOURCE = "/api/webservice/{ruleKey}/httpserver/logs"


def parse_ts_text(ts_text: Any) -> int:
    """YYYY/MM/DD HH:mm:ss → epoch 秒。解析失败返回 0。"""
    if not ts_text:
        return 0
    try:
        return int(datetime.strptime(str(ts_text), "%Y/%m/%d %H:%M:%S").timestamp())
    except (ValueError, TypeError):
        return 0


def normalize_record(
    instance: str, module: str, rec: dict[str, Any],
    rule_key: str = "", rule_name: str = "", sub_key: str = "", sub_name: str = "",
) -> dict[str, Any] | None:
    """把远程日志行归一化为入库行。返回 None 表示不可解析。"""
    ts_epoch = parse_ts_text(rec.get("LogTime"))
    content = rec.get("LogContent")
    if ts_epoch <= 0 and not content:
        return None
    return {
        "instance": instance,
        "module": module,
        "rule_key": rule_key,
        "rule_name": rule_name,
        "sub_key": sub_key,
        "sub_name": sub_name,
        "ts_epoch": ts_epoch,
        "ts_text": rec.get("LogTime") or "",
        "content": content or "",
        "raw_json": __import__("json").dumps(rec, ensure_ascii=False),
        "fetched_at": int(time.time()),
    }


def normalize_system_record(instance: str, rec: dict[str, Any]) -> dict[str, Any] | None:
    """系统日志特殊结构：{timestamp(纳秒), log, time}。"""
    try:
        ns = int(rec["timestamp"]) if rec.get("timestamp") is not None else None
    except (ValueError, TypeError):
        ns = None
    content = rec.get("log")
    if ns is None and not content:
        return None
    ts_epoch = int(ns // 1_000_000_000) if ns else parse_ts_text(rec.get("time"))
    return {
        "instance": instance,
        "module": "system",
        "rule_key": "",
        "rule_name": "",
        "sub_key": "",
        "sub_name": "",
        "ts_epoch": ts_epoch,
        "ts_text": rec.get("time") or "",
        "content": content or "",
        "raw_json": __import__("json").dumps(rec, ensure_ascii=False),
        "fetched_at": int(time.time()),
    }


class Collector:
    def __init__(self, cfg: AppConfig, db: Database):
        self.cfg = cfg
        self.db = db
        self._clients: dict[str, LuckyClient] = {}
        self._trees: dict[str, list[dict[str, Any]]] = {}
        self._tree_ts: dict[str, float] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._running = False
        # 状态展示：instance → {last_collect, last_error}
        self.status: dict[str, dict[str, Any]] = {}

    # ---------- 生命周期 ----------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for client in self._clients.values():
            await client.close()
        self._clients.clear()

    def _client(self, inst: InstanceConfig) -> LuckyClient:
        if inst.name not in self._clients:
            self._clients[inst.name] = LuckyClient(inst)
        return self._clients[inst.name]

    # ---------- 服务树缓存 ----------

    async def _ensure_tree(self, inst: InstanceConfig) -> list[dict[str, Any]]:
        now = time.time()
        if inst.name in self._trees and now - self._tree_ts.get(inst.name, 0) < TREE_REFRESH_SECONDS:
            return self._trees[inst.name]
        try:
            tree = await self._client(inst).fetch_service_tree()
            self._trees[inst.name] = tree
            self._tree_ts[inst.name] = now
        except LuckyError:
            tree = self._trees.get(inst.name, [])
        return tree

    def service_tree(self, instance: str) -> list[dict[str, Any]]:
        return self._trees.get(instance, [])

    # ---------- 主循环 ----------

    async def _run_loop(self) -> None:
        interval = max(2, self.cfg.collect_interval)
        logger.info("采集器启动，间隔 %ss", interval)
        while self._running:
            started = time.time()
            try:
                await self._collect_once()
            except Exception as e:  # noqa: BLE001
                logger.exception("采集循环异常: %s", e)
            # 固定间隔轮询，给目标留出喘息空间；一轮超时也不连续补跑
            await asyncio.sleep(interval)

    async def _collect_once(self) -> None:
        instances = self.cfg.enabled_instances()
        for inst in instances:
            st = self.status.setdefault(
                inst.name, {"last_collect": 0, "last_error": None}
            )
            try:
                await self._collect_instance(inst)
                st["last_collect"] = int(time.time())
                st["last_error"] = None
            except Exception as e:  # noqa: BLE001
                logger.exception("[%s] 采集失败: %s", inst.name, e)
                st["last_error"] = str(e)

    async def _collect_instance(self, inst: InstanceConfig) -> None:
        modules = set(inst.modules or SINGLE_SOURCES.keys())
        for module in sorted(modules):
            if module == "webservice":
                await self._poll_single(inst, module, SINGLE_SOURCES[module])
                await asyncio.sleep(INTER_SOURCE_DELAY)
                await self._poll_by_rule(inst)
            elif module in SINGLE_SOURCES:
                await self._poll_single(inst, module, SINGLE_SOURCES[module])
                await asyncio.sleep(INTER_SOURCE_DELAY)
            else:
                logger.debug("[%s] 忽略未知模块 %s", inst.name, module)

    # ---------- 单源采集 ----------

    async def _poll_single(self, inst: InstanceConfig, module: str, path: str) -> None:
        if module == "system":
            await self._poll_system(inst)
            return
        cursor = await self.db.get_cursor(inst.name, module, "", "")
        client = self._client(inst)
        old_ts = cursor["last_ts"]
        new_rows: list[dict[str, Any]] = []
        newest_ts = old_ts
        try:
            page = 1
            total = None
            while page <= MAX_PAGES_PER_POLL:
                data = await client.get_log_page(path, page, PAGE_SIZE)
                if total is None:
                    total = data["total"]
                logs = data["logs"]
                if not logs:
                    break
                page_rows: list[dict[str, Any]] = []
                for rec in logs:
                    row = normalize_record(inst.name, module, rec)
                    if row and row["ts_epoch"] >= old_ts:
                        page_rows.append(row)
                        if row["ts_epoch"] > newest_ts:
                            newest_ts = row["ts_epoch"]
                new_rows.extend(page_rows)
                oldest_in_page = min(
                    (parse_ts_text(r.get("LogTime")) for r in logs if r.get("LogTime")), default=0
                )
                if oldest_in_page < old_ts:
                    break
                if page * PAGE_SIZE >= total:
                    break
                page += 1
                await asyncio.sleep(INTER_SOURCE_DELAY)
            inserted = await self.db.insert_logs(new_rows)
            await self.db.save_cursor(
                inst.name, module, "", "",
                last_ts=newest_ts, last_total=total or 0,
            )
            if inserted:
                self.broadcast(new_rows)
            logger.debug("[%s] %s 新增 %d 条", inst.name, module, inserted)
        except LuckyError as e:
            await self.db.save_cursor(inst.name, module, "", "", error=str(e))
            logger.warning("[%s] %s 采集错误: %s", inst.name, module, e)

    # ---------- 系统日志（纳秒游标） ----------

    async def _poll_system(self, inst: InstanceConfig) -> None:
        cursor = await self.db.get_cursor(inst.name, "system", "", "")
        old_ns = cursor["last_ns"]
        new_rows: list[dict[str, Any]] = []
        newest_ns = old_ns
        try:
            page = 1
            total = None
            while page <= MAX_PAGES_PER_POLL:
                data = await self._client(inst).get_log_page("/api/logs", page, PAGE_SIZE)
                if total is None:
                    total = data["total"]
                logs = data["logs"]
                if not logs:
                    break
                page_rows: list[dict[str, Any]] = []
                for rec in logs:
                    ns = rec.get("timestamp")
                    if ns is None:
                        continue
                    ns = int(ns)
                    if ns < old_ns:
                        continue
                    row = normalize_system_record(inst.name, rec)
                    if row:
                        page_rows.append(row)
                        if ns > newest_ns:
                            newest_ns = ns
                new_rows.extend(page_rows)
                oldest_in_page = min((int(r.get("timestamp") or 0) for r in logs), default=0)
                if oldest_in_page < old_ns:
                    break
                if page * PAGE_SIZE >= total:
                    break
                page += 1
                await asyncio.sleep(INTER_SOURCE_DELAY)
            inserted = await self.db.insert_logs(new_rows)
            await self.db.save_cursor(
                inst.name, "system", "", "",
                last_ns=newest_ns, last_ts=0, last_total=total or 0,
            )
            if inserted:
                self.broadcast(new_rows)
        except LuckyError as e:
            await self.db.save_cursor(inst.name, "system", "", "", error=str(e))
            logger.warning("[%s] system 采集错误: %s", inst.name, e)

    # ---------- 按规则（服务）采集 ----------

    async def _poll_by_rule(self, inst: InstanceConfig) -> None:
        tree = await self._ensure_tree(inst)
        client = self._client(inst)
        for rule in tree:
            rule_key = rule.get("Key") or ""
            rule_name = rule.get("Name") or ""
            path = BY_RULE_SOURCE.format(ruleKey=rule_key)
            cursor = await self.db.get_cursor(inst.name, "webservice", rule_key, "")
            old_ts = cursor["last_ts"]
            new_rows: list[dict[str, Any]] = []
            newest_ts = old_ts
            try:
                page = 1
                total = None
                while page <= MAX_PAGES_PER_POLL:
                    data = await client.get_log_page(path, page, PAGE_SIZE)
                    if total is None:
                        total = data["total"]
                    logs = data["logs"]
                    if not logs:
                        break
                    page_rows: list[dict[str, Any]] = []
                    for rec in logs:
                        row = normalize_record(inst.name, "webservice", rec, rule_key, rule_name)
                        if row and row["ts_epoch"] >= old_ts:
                            page_rows.append(row)
                            if row["ts_epoch"] > newest_ts:
                                newest_ts = row["ts_epoch"]
                    new_rows.extend(page_rows)
                    oldest_in_page = min(
                        (parse_ts_text(r.get("LogTime")) for r in logs if r.get("LogTime")), default=0
                    )
                    if oldest_in_page < old_ts:
                        break
                    if page * PAGE_SIZE >= total:
                        break
                    page += 1
                    await asyncio.sleep(INTER_SOURCE_DELAY)
                inserted = await self.db.insert_logs(new_rows)
                await self.db.save_cursor(
                    inst.name, "webservice", rule_key, "",
                    last_ts=newest_ts, last_total=total or 0,
                )
                if inserted:
                    self.broadcast(new_rows)
            except LuckyError as e:
                await self.db.save_cursor(inst.name, "webservice", rule_key, "", error=str(e))
                logger.warning("[%s] %s 采集错误: %s", inst.name, rule_name, e)
            await asyncio.sleep(INTER_SOURCE_DELAY)

    # ---------- 广播（WebSocket 实时推送） ----------

    def subscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def broadcast(self, rows: list[dict[str, Any]]) -> None:
        if not self._subscribers or not rows:
            return
        msg = {"type": "logs", "items": rows}
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass
