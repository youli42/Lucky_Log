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
from .docker_api import fetch_snapshot
from .lucky_client import LuckyClient, LuckyError

logger = logging.getLogger(__name__)

TREE_REFRESH_SECONDS = 300
PAGE_SIZE = 100
MAX_PAGES_PER_POLL = 20
INTER_SOURCE_DELAY = 0.4
TRAFFIC_INTERVAL = 30  # accessdetail 实时快照刷新节流
DOCKER_CACHE_INTERVAL = 60  # docker 面板快照后台预热节流

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
    # Lucky 3.0.0 新增模块
    "smb": "/api/smb/logs",
    "coraza": "/api/coraza/logs",
    "iconlib": "/api/iconlib/logs",
    # 注：portforward/stun 的 /logs 返回 ret=1 业务错误（无日志端点），不采集
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
        self._traffic_ts: dict[tuple[str, str], float] = {}
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self._instance_sem = asyncio.Semaphore(2)
        self._collecting: set[str] = set()
        # 状态展示：instance → {last_collect, last_error, collecting, current, ...}
        self.status: dict[str, dict[str, Any]] = {}

    def _conn_params(self, inst: InstanceConfig) -> tuple:
        return (inst.host, inst.port, inst.base, inst.https, inst.token)

    async def sync_instances(self) -> None:
        """配置保存后热同步：关闭/移除连接参数变化或被删除实例的客户端与服务树。

        新增实例无需处理 —— _collect_once 每轮重读 self.cfg.enabled_instances()。
        """
        async with self._lock:
            by_name = {i.name: i for i in self.cfg.instances}
            keep: dict[str, LuckyClient] = {}
            to_drop: list[LuckyClient] = []
            for name, client in self._clients.items():
                inst = by_name.get(name)
                if inst is not None and self._conn_params(inst) == self._conn_params_by_client(client):
                    keep[name] = client
                else:
                    to_drop.append(client)
            self._clients = keep
            for name in list(self._trees):
                if name not in by_name:
                    self._trees.pop(name, None)
                    self._tree_ts.pop(name, None)
            for name in list(self.status):
                if name not in by_name:
                    self.status.pop(name, None)
                else:
                    # 保存配置视为用户意图恢复采集：清除暂停/失败退避状态
                    st = self.status[name]
                    st["paused"] = False
                    st["fail_count"] = 0
                    st["backoff_until"] = 0
                    st["next_retry_in"] = 0
        for client in to_drop:
            await client.close()

    def _conn_params_by_client(self, client: LuckyClient) -> tuple:
        return (
            client.cfg.host, client.cfg.port, client.cfg.base,
            client.cfg.https, client.cfg.token,
        )

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
        except LuckyError as e:
            if e.status == 404:
                self._trees[inst.name] = []
                self._tree_ts[inst.name] = now
                return []
            raise
        self._trees[inst.name] = tree
        self._tree_ts[inst.name] = now
        return tree

    def service_tree(self, instance: str) -> list[dict[str, Any]]:
        return self._trees.get(instance, [])

    # ---------- 主循环 ----------

    @staticmethod
    def _default_status() -> dict[str, Any]:
        return {
            "last_collect": 0, "last_error": None, "collecting": False,
            "current": "", "page": 0, "total": 0, "collected_rows": 0,
            "started_at": 0, "fail_count": 0, "backoff_until": 0,
            "next_retry_in": 0, "paused": False,
        }

    def _status(self, inst: InstanceConfig) -> dict[str, Any]:
        return self.status.setdefault(inst.name, self._default_status())

    def _set_current(self, inst: InstanceConfig, current: str, page: int = 0, total: int = 0) -> None:
        st = self._status(inst)
        st["current"] = current
        if page:
            st["page"] = page
        if total:
            st["total"] = total

    def _add_collected(self, inst: InstanceConfig, n: int) -> None:
        st = self._status(inst)
        st["collected_rows"] = st.get("collected_rows", 0) + n

    async def _run_loop(self) -> None:
        interval = max(2, self.cfg.collect_interval)
        logger.info(
            "采集器启动，间隔 %ss，退避 base=%s max=%s max_retries=%s",
            interval, self.cfg.backoff.base, self.cfg.backoff.max, self.cfg.backoff.max_retries,
        )
        while self._running:
            try:
                await self._collect_once()
            except Exception as e:  # noqa: BLE001
                logger.exception("采集循环异常: %s", e)
            # 全部实例退避中时睡到最早可重试时刻，避免空转；否则固定间隔
            await asyncio.sleep(self._next_sleep(interval))

    def _backoff_seconds(self, fail_count: int) -> int:
        """指数退避：base×2^(n-1)，超过 max_retries 进入长冷却（=max）；±20% 抖动后封顶 max。"""
        import random

        b = self.cfg.backoff
        if fail_count <= b.max_retries:
            secs = b.base * (2 ** (fail_count - 1))
        else:
            secs = b.max
        return max(1, min(b.max, int(secs * random.uniform(0.8, 1.2))))

    def _next_sleep(self, interval: int) -> int:
        """若所有启用实例都在退避中，睡到最早可重试时刻；否则固定间隔。"""
        now = time.time()
        enabled = {i.name for i in self.cfg.enabled_instances()}
        if not enabled:
            return interval
        retries = [
            st.get("backoff_until", 0) - now
            for name, st in self.status.items()
            if name in enabled and st.get("backoff_until", 0) > now
        ]
        if len(retries) == len(enabled) and retries:
            return max(1, int(min(retries)))
        return interval

    async def _run_instance(self, inst: InstanceConfig) -> None:
        """采集单个实例（防重入）：失败进入指数退避。"""
        if inst.name in self._collecting:
            return
        self._collecting.add(inst.name)
        st = self._status(inst)
        st["collecting"] = True
        st["started_at"] = int(time.time())
        st["current"] = ""
        st["page"] = 0
        st["total"] = 0
        st["collected_rows"] = 0
        try:
            await self._collect_instance(inst)
            st["last_collect"] = int(time.time())
            st["last_error"] = None
            st["fail_count"] = 0
            st["backoff_until"] = 0
            st["next_retry_in"] = 0
            st["paused"] = False
        except Exception as e:  # noqa: BLE001
            st["fail_count"] = st.get("fail_count", 0) + 1
            if st["fail_count"] >= self.cfg.backoff.max_retries:
                # 连续失败达上限 → 暂停自动采集（手动采集或保存配置恢复）
                st["paused"] = True
                st["backoff_until"] = 0
                st["next_retry_in"] = 0
                logger.error(
                    "[%s] 采集失败已达 %d 次，暂停自动采集（可手动采集或保存配置恢复）: %s",
                    inst.name, st["fail_count"], e,
                )
            else:
                backoff = self._backoff_seconds(st["fail_count"])
                st["backoff_until"] = int(time.time()) + backoff
                st["next_retry_in"] = backoff
                logger.error("[%s] 采集失败(第%d次, 退避%ss): %s", inst.name, st["fail_count"], backoff, e)
            st["last_error"] = str(e)
        finally:
            st["collecting"] = False
            st["current"] = ""
            self._collecting.discard(inst.name)

    async def _collect_once(self) -> None:
        now = time.time()
        instances = [
            i for i in self.cfg.enabled_instances()
            if not self.status.get(i.name, {}).get("paused", False)
            and self.status.get(i.name, {}).get("backoff_until", 0) <= now
        ]

        async def guarded(inst: InstanceConfig) -> None:
            async with self._instance_sem:
                await self._run_instance(inst)

        if instances:
            await asyncio.gather(*(guarded(i) for i in instances))

    def collect_now(self, name: str) -> bool:
        """立即采集指定实例（异步任务）。已在采/不存在返回 False。"""
        inst = next((i for i in self.cfg.instances if i.name == name), None)
        if inst is None or not inst.enabled:
            return False
        if name in self._collecting:
            return False
        asyncio.create_task(self._run_instance(inst))
        return True

    def collect_all(self) -> int:
        """立即采集全部启用实例，返回新启动的任务数。"""
        started = 0
        for inst in self.cfg.enabled_instances():
            if inst.name not in self._collecting:
                asyncio.create_task(self._run_instance(inst))
                started += 1
        return started

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
        if "docker" in modules:
            await self._refresh_docker_cache(inst)

    async def _refresh_docker_cache(self, inst: InstanceConfig) -> None:
        """后台预热 Docker 面板快照到本地缓存（60s 节流），进面板秒显。"""
        now = time.time()
        throttle_key = (inst.name, "docker_cache")
        if now - self._traffic_ts.get(throttle_key, 0) < DOCKER_CACHE_INTERVAL:
            return
        self._traffic_ts[throttle_key] = now
        try:
            snap = await fetch_snapshot(self._client(inst))
            await self.db.save_docker_cache(inst.name, snap, int(now))
            logger.debug("[%s] docker 缓存已刷新", inst.name)
        except LuckyError as e:
            if e.status != 404:
                logger.warning("[%s] docker 缓存刷新失败: %s", inst.name, e)

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
        label = module
        if rule_name or sub_name:
            label += "/" + (sub_name or rule_name)
        self._set_current(inst, label)
        try:
            page = 1
            total = None
            while page <= MAX_PAGES_PER_POLL:
                data = await client.get_log_page(path, page, PAGE_SIZE)
                if total is None:
                    total = data["total"]
                self._set_current(inst, label, page=page, total=total)
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
            if inserted:
                self._add_collected(inst, inserted)
            if inserted_access or inserted:
                logger.debug(
                    "[%s] %s/%s 新增日志 %d 访问 %d", inst.name, module, sub_key or rule_key, inserted, inserted_access
                )
            return inserted, inserted_access
        except LuckyError as e:
            await self.db.save_cursor(inst.name, module, rule_key, sub_key, error=str(e))
            if e.status == 404:
                # 模块/资源未启用（404）→ 源不可用，跳过继续，不触发退避
                logger.debug("[%s] %s/%s 源不可用(404): %s", inst.name, module, sub_key or rule_key, e)
                return 0, 0
            logger.warning("[%s] %s/%s 采集错误: %s", inst.name, module, sub_key or rule_key, e)
            raise

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
            self._set_current(inst, f"webservice/{rule_name or rule_key}")
            await self._poll_unified(
                inst, "webservice", BY_RULE_SOURCE.format(ruleKey=rule_key),
                rule_key=rule_key, rule_name=rule_name,
            )
            await asyncio.sleep(INTER_SOURCE_DELAY)
            for sub in rule.get("SubRuleList") or []:
                sub_key = sub.get("Key") or ""
                sub_name = sub.get("Name") or ""
                self._set_current(inst, f"webservice/{rule_name or rule_key}/{sub_name or sub_key}")
                await self._poll_unified(
                    inst, "webservice", SUB_RULE_SOURCE.format(ruleKey=rule_key, subKey=sub_key),
                    rule_key=rule_key, rule_name=rule_name,
                    sub_key=sub_key, sub_name=sub_name,
                    build_access=True,
                )
                await asyncio.sleep(INTER_SOURCE_DELAY)
                await self._poll_accessdetail(inst, rule_key, sub_key, rule_name, sub_name)

    # ---------- IP 流量快照（accessdetail） ----------

    async def _poll_accessdetail(self, inst: InstanceConfig, rule_key: str, sub_key: str,
                                 rule_name: str = "", sub_name: str = "") -> None:
        """轮询子代理 accessdetail，UPSERT 入 ip_traffic；30s 节流。"""
        now = time.time()
        throttle_key = (inst.name, sub_key)
        if now - self._traffic_ts.get(throttle_key, 0) < TRAFFIC_INTERVAL:
            return
        self._traffic_ts[throttle_key] = now
        self._set_current(inst, f"accessdetail: {sub_name or sub_key}")
        rows: list[dict[str, Any]] = []
        try:
            page = 1
            while page <= MAX_PAGES_PER_POLL:
                data = await self._client(inst).get_json(
                    f"/webservice/{rule_key}/{sub_key}/accessdetail",
                    {"pageSize": PAGE_SIZE, "page": page},
                )
                res = data.get("resList") or []
                total = data.get("ipTotal") or len(res)
                for r in res:
                    ip = r.get("IP")
                    if not ip:
                        continue
                    rows.append({
                        "instance": inst.name,
                        "sub_key": sub_key,
                        "client_ip": ip,
                        "last_access": r.get("LastAccess") or 0,
                        "connections": r.get("Connections") or 0,
                        "traffic_in": r.get("TrafficIn") or 0,
                        "traffic_out": r.get("TrafficOut") or 0,
                        "fetched_at": int(now),
                    })
                if len(res) < PAGE_SIZE or page * PAGE_SIZE >= total:
                    break
                page += 1
                await asyncio.sleep(INTER_SOURCE_DELAY)
            if rows:
                await self.db.upsert_ip_traffic(rows)
                logger.debug("[%s] %s accessdetail %d IP", inst.name, sub_key, len(rows))
        except LuckyError as e:
            if e.status == 404:
                logger.debug("[%s] %s accessdetail 源不可用(404)", inst.name, sub_key)
                return
            logger.warning("[%s] %s accessdetail 错误: %s", inst.name, sub_key, e)
            raise

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
