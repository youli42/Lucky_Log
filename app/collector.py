"""后台日志采集器（asyncio）。

按「实例 × 源」为采集单元定时轮询，游标增量入库，并通过内存队列广播增量。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from .access_parser import parse_access_row
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
SUB_RULE_SOURCE = "/api/webservice/{ruleKey}/{subKey}/logs"


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

    # ---------- 统一分页采集 ----------

    async def _poll_unified(
        self, inst: InstanceConfig, module: str, path: str,
        *,
        rule_key: str = "", rule_name: str = "", sub_key: str = "", sub_name: str = "",
        cursor_ns: bool = False, build_access: bool = False,
    ) -> tuple[int, int]:
        """按 LogTime（或系统日志纳秒）游标翻页采集，写 logs（+可选 access_logs）。"""
        cursor = await self.db.get_cursor(inst.name, module, rule_key, sub_key)
        old = cursor["last_ns"] if cursor_ns else cursor["last_ts"]
        client = self._client(inst)
        new_rows: list[dict[str, Any]] = []
        access_rows: list[dict[str, Any]] = []
        newest = old
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
                page_ts: list[int] = []
                for rec in logs:
                    if cursor_ns:
                        try:
                            ts = int(rec.get("timestamp") or 0)
                        except (ValueError, TypeError):
                            ts = 0
                        if ts < old:
                            continue
                        row = normalize_system_record(inst.name, rec)
                        page_ts.append(ts)
                        if ts > newest:
                            newest = ts
                    else:
                        ts = parse_ts_text(rec.get("LogTime"))
                        if ts < old:
                            continue
                        row = normalize_record(
                            inst.name, module, rec, rule_key, rule_name, sub_key, sub_name
                        )
                        page_ts.append(ts)
                        if ts > newest:
                            newest = ts
                    if row:
                        new_rows.append(row)
                    if build_access:
                        arow = parse_access_row(
                            inst.name, rec,
                            rule_key=rule_key, rule_name=rule_name,
                            sub_key=sub_key, sub_name=sub_name,
                        )
                        if arow:
                            access_rows.append(arow)
                oldest_in_page = min(page_ts, default=0)
                if oldest_in_page < old:
                    break
                if page * PAGE_SIZE >= total:
                    break
                page += 1
                await asyncio.sleep(INTER_SOURCE_DELAY)
            inserted = await self.db.insert_logs(new_rows)
            inserted_access = await self.db.insert_access_logs(access_rows)
            await self.db.save_cursor(
                inst.name, module, rule_key, sub_key,
                last_ts=None if cursor_ns else newest,
                last_ns=newest if cursor_ns else None,
                last_total=total or 0,
            )
            if inserted:
                self.broadcast(new_rows)
            if inserted_access or inserted:
                logger.debug(
                    "[%s] %s/%s 新增日志 %d 访问 %d", inst.name, module, sub_key or rule_key, inserted, inserted_access
                )
            return inserted, inserted_access
        except LuckyError as e:
            await self.db.save_cursor(inst.name, module, rule_key, sub_key, error=str(e))
            logger.warning("[%s] %s/%s 采集错误: %s", inst.name, module, sub_key or rule_key, e)
            return 0, 0

    async def _poll_single(self, inst: InstanceConfig, module: str, path: str) -> None:
        if module == "system":
            await self._poll_unified(inst, "system", path, cursor_ns=True)
            return
        await self._poll_unified(inst, module, path)

    # ---------- 按规则 + 子代理采集 ----------

    async def _poll_by_rule(self, inst: InstanceConfig) -> None:
        tree = await self._ensure_tree(inst)
        for rule in tree:
            rule_key = rule.get("Key") or ""
            rule_name = rule.get("Name") or ""
            await self._poll_unified(
                inst, "webservice", BY_RULE_SOURCE.format(ruleKey=rule_key),
                rule_key=rule_key, rule_name=rule_name,
            )
            await asyncio.sleep(INTER_SOURCE_DELAY)
            for sub in rule.get("SubRuleList") or []:
                sub_key = sub.get("Key") or ""
                sub_name = sub.get("Name") or ""
                await self._poll_unified(
                    inst, "webservice", SUB_RULE_SOURCE.format(ruleKey=rule_key, subKey=sub_key),
                    rule_key=rule_key, rule_name=rule_name,
                    sub_key=sub_key, sub_name=sub_name,
                    build_access=True,
                )
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
