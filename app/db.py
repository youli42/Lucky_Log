"""SQLite 数据层。

- logs 表：日志存储（doc/05 表结构）
- cursors 表：每「实例×源」采集游标与状态（LogTime / 纳秒 timestamp / total 差分）
"""
from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

import aiosqlite
from pathlib import Path

from .config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  instance   TEXT NOT NULL,
  module     TEXT NOT NULL,
  rule_key   TEXT,
  rule_name  TEXT,
  sub_key    TEXT,
  sub_name   TEXT,
  ts_epoch   INTEGER NOT NULL,
  ts_text    TEXT NOT NULL,
  content    TEXT NOT NULL,
  raw_json   TEXT,
  fetched_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_inst_module_ts ON logs(instance, module, ts_epoch);
CREATE INDEX IF NOT EXISTS idx_logs_inst_ts ON logs(instance, ts_epoch);
CREATE INDEX IF NOT EXISTS idx_logs_content ON logs(content);
CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_dedup
  ON logs(instance, module, COALESCE(rule_key,''), COALESCE(sub_key,''), ts_text, content);
CREATE TABLE IF NOT EXISTS access_logs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  instance    TEXT NOT NULL,
  rule_key    TEXT,
  rule_name   TEXT,
  sub_key     TEXT,
  sub_name    TEXT,
  host        TEXT,
  ts_epoch    INTEGER NOT NULL,
  ts_text     TEXT NOT NULL,
  client_ip   TEXT,
  method      TEXT,
  path        TEXT,
  ua          TEXT,
  browser     TEXT,
  os          TEXT,
  device      TEXT,
  device_type TEXT,
  fetched_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_access_inst_ts ON access_logs(instance, ts_epoch);
CREATE INDEX IF NOT EXISTS idx_access_ip ON access_logs(client_ip);
CREATE INDEX IF NOT EXISTS idx_access_path ON access_logs(path);
CREATE UNIQUE INDEX IF NOT EXISTS idx_access_dedup
  ON access_logs(instance, COALESCE(sub_key,''), ts_text, client_ip, method, path);
CREATE TABLE IF NOT EXISTS ip_traffic (
  instance    TEXT NOT NULL,
  sub_key     TEXT,
  client_ip   TEXT NOT NULL,
  last_access INTEGER NOT NULL DEFAULT 0,
  connections INTEGER NOT NULL DEFAULT 0,
  traffic_in  INTEGER NOT NULL DEFAULT 0,
  traffic_out INTEGER NOT NULL DEFAULT 0,
  fetched_at  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (instance, sub_key, client_ip)
);
CREATE TABLE IF NOT EXISTS cursors (
  instance   TEXT NOT NULL,
  module     TEXT NOT NULL,
  rule_key   TEXT,
  sub_key    TEXT,
  last_ts    INTEGER NOT NULL DEFAULT 0,
  last_ns    INTEGER NOT NULL DEFAULT 0,
  last_total INTEGER NOT NULL DEFAULT 0,
  last_ok_at INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  PRIMARY KEY (instance, module, rule_key, sub_key)
);
"""

_LOG_COLS = (
    "id", "instance", "module", "rule_key", "rule_name",
    "sub_key", "sub_name", "ts_epoch", "ts_text", "content",
    "raw_json", "fetched_at",
)


def _row_to_dict(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    if "raw_json" in d and d["raw_json"] is not None:
        try:
            d["raw"] = json.loads(d["raw_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or str(DB_PATH)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._conn is None:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self.path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.executescript(_SCHEMA)
            await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        assert self._conn is not None, "db not connected"
        cur = await self._conn.execute(sql, params)
        return cur

    async def _fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        cur = await self._execute(sql, params)
        rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def _fetchone(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        cur = await self._execute(sql, params)
        row = await cur.fetchone()
        return _row_to_dict(row)

    # ---------- 采集写入 ----------

    async def insert_logs(self, rows: list[dict[str, Any]]) -> int:
        """批量入库，按 (instance, module, rule_key, ts_text, content) 去重。返回实际写入条数。"""
        if not rows:
            return 0
        sql = (
            "INSERT OR IGNORE INTO logs"
            "(instance, module, rule_key, rule_name, sub_key, sub_name,"
            " ts_epoch, ts_text, content, raw_json, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        )
        cur = await self._conn.executemany(
            sql,
            [
                (
                    r["instance"], r["module"], r.get("rule_key") or "", r.get("rule_name"),
                    r.get("sub_key") or "", r.get("sub_name"), r["ts_epoch"], r["ts_text"],
                    r["content"], r.get("raw_json"), r["fetched_at"],
                )
                for r in rows
            ],
        )
        await self._conn.commit()
        return cur.rowcount

    async def insert_access_logs(self, rows: list[dict[str, Any]]) -> int:
        """访问日志批量入库，按 (instance, sub_key, ts_text, client_ip, method, path) 去重。"""
        if not rows:
            return 0
        sql = (
            "INSERT OR IGNORE INTO access_logs"
            "(instance, rule_key, rule_name, sub_key, sub_name, host, ts_epoch, ts_text,"
            " client_ip, method, path, ua, browser, os, device, device_type, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        cur = await self._conn.executemany(
            sql,
            [
                (
                    r["instance"], r.get("rule_key") or "", r.get("rule_name"),
                    r.get("sub_key") or "", r.get("sub_name"), r.get("host") or "",
                    r["ts_epoch"], r.get("ts_text") or "",
                    r.get("client_ip"), r.get("method"), r.get("path"),
                    r.get("ua"), r.get("browser"), r.get("os"),
                    r.get("device"), r.get("device_type"), r.get("fetched_at"),
                )
                for r in rows
            ],
        )
        await self._conn.commit()
        return cur.rowcount

    async def save_cursor(
        self, instance: str, module: str, rule_key: str | None, sub_key: str | None,
        *,
        last_ts: int | None = None, last_ns: int | None = None,
        last_total: int | None = None, error: str | None = None,
    ) -> None:
        now = int(time.time())
        ins_params = (
            instance, module, rule_key, sub_key,
            last_ts or 0, last_ns or 0, last_total or 0, now, error,
        )
        upd_params = (last_ts, last_ns, last_total, now, error)
        sql = (
            "INSERT INTO cursors (instance, module, rule_key, sub_key, last_ts, last_ns,"
            " last_total, last_ok_at, last_error) VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(instance, module, rule_key, sub_key) DO UPDATE SET"
            " last_ts=COALESCE(?, last_ts), last_ns=COALESCE(?, last_ns),"
            " last_total=COALESCE(?, last_total),"
            " last_ok_at=COALESCE(?, last_ok_at),"
            " last_error=?"
        )
        await self._conn.execute(sql, ins_params + upd_params)
        await self._conn.commit()

    async def get_cursor(
        self, instance: str, module: str, rule_key: str | None, sub_key: str | None,
    ) -> dict[str, Any]:
        row = await self._fetchone(
            "SELECT * FROM cursors WHERE instance=? AND module=? AND rule_key=? AND sub_key=?",
            (instance, module, rule_key, sub_key),
        )
        return row or {
            "instance": instance, "module": module, "rule_key": rule_key or "",
            "sub_key": sub_key or "", "last_ts": 0, "last_ns": 0, "last_total": 0,
            "last_ok_at": 0, "last_error": None,
        }

    # ---------- 查询 ----------

    def _build_filters(
        self,
        instance: str | None, module: str | None, rule_key: str | None,
        sub_key: str | None, from_epoch: int | None, to_epoch: int | None,
        search: str | None, with_rule_name: bool = False,
        service: str | None = None, level: str | None = None,
    ) -> tuple[str, list]:
        conds: list[str] = []
        params: list = []
        if instance:
            conds.append("instance=?")
            params.append(instance)
        if module:
            conds.append("module=?")
            params.append(module)
        if service:
            conds.append("(rule_key=? OR sub_key=?)")
            params.extend([service, service])
        if level == "rule":
            conds.append("sub_key=''")
        elif level == "sub":
            conds.append("sub_key!=''")
        if rule_key:
            conds.append("rule_key=?")
            params.append(rule_key)
        if sub_key:
            conds.append("sub_key=?")
            params.append(sub_key)
        if with_rule_name and module in (None, "webservice"):
            pass  # 服务分布过滤用 rule_name 时单独处理
        if from_epoch is not None:
            conds.append("ts_epoch>=?")
            params.append(from_epoch)
        if to_epoch is not None:
            conds.append("ts_epoch<=?")
            params.append(to_epoch)
        if search:
            conds.append("content LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(search)}%")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        return where, params

    @staticmethod
    def _dedup_key(dedup: str | None) -> tuple[str, ...]:
        key = (dedup or "time_content").strip().lower()
        if key in ("off", "none", "false", "no"):
            return ()
        if key == "content":
            return ("content",)
        return ("ts_text", "content")

    async def query_logs(
        self,
        instance: str | None = None, module: str | None = None,
        rule_key: str | None = None, sub_key: str | None = None,
        from_epoch: int | None = None, to_epoch: int | None = None,
        search: str | None = None, dedup: str | None = "time_content",
        page: int = 1, page_size: int = 200, service: str | None = None,
        level: str | None = None,
    ) -> dict[str, Any]:
        where, params = self._build_filters(
            instance, module, rule_key, sub_key, from_epoch, to_epoch, search,
            service=service, level=level,
        )
        keys = self._dedup_key(dedup)
        page = max(1, page)
        page_size = min(500, max(1, page_size))
        offset = (page - 1) * page_size

        if keys:
            part = ", ".join(keys)
            cnt_sql = f"SELECT COUNT(*) AS c FROM (SELECT 1 FROM logs {where} GROUP BY {part})"
            base = (
                f"SELECT * FROM (SELECT *, ROW_NUMBER() OVER ("
                f"PARTITION BY {part} ORDER BY ts_epoch DESC, id DESC) AS __rn "
                f"FROM logs {where}) WHERE __rn=1"
            )
        else:
            cnt_sql = f"SELECT COUNT(*) AS c FROM logs {where}"
            base = f"SELECT * FROM logs {where}"

        total = (await self._fetchone(cnt_sql, params))["c"]
        rows = await self._fetchall(
            f"{base} ORDER BY ts_epoch DESC, id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        return {"total": total, "page": page, "page_size": page_size, "items": rows}

    # ---------- 统计 ----------

    async def stats_by_module(
        self, instance: str | None, from_epoch: int | None, to_epoch: int | None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        where, params = self._build_filters(instance, None, None, None, from_epoch, to_epoch, search)
        return await self._fetchall(
            f"SELECT module, COUNT(*) AS count FROM logs {where} GROUP BY module ORDER BY count DESC",
            params,
        )

    async def stats_timeline(
        self, instance: str | None, module: str | None,
        from_epoch: int | None, to_epoch: int | None,
        granularity: str = "hour", search: str | None = None,
    ) -> list[dict[str, Any]]:
        where, params = self._build_filters(instance, module, None, None, from_epoch, to_epoch, search)
        step = 3600 if granularity != "day" else 86400
        return await self._fetchall(
            f"SELECT (ts_epoch/{step})*{step} AS bucket, COUNT(*) AS count "
            f"FROM logs {where} GROUP BY bucket ORDER BY bucket",
            params,
        )

    async def stats_by_service(
        self, instance: str | None, from_epoch: int | None, to_epoch: int | None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        where, params = self._build_filters(instance, "webservice", None, None, from_epoch, to_epoch, search)
        return await self._fetchall(
            f"SELECT rule_name, COUNT(*) AS count FROM logs {where} "
            f"GROUP BY rule_name ORDER BY count DESC",
            params,
        )

    async def module_counts(self, instance: str) -> list[dict[str, Any]]:
        return await self._fetchall(
            "SELECT module, COUNT(*) AS count FROM logs WHERE instance=? GROUP BY module",
            (instance,),
        )

    async def instance_stats(self, instance: str) -> dict[str, Any]:
        row = await self._fetchone(
            "SELECT COUNT(*) AS total, COALESCE(MAX(fetched_at),0) AS last_fetch "
            "FROM logs WHERE instance=?",
            (instance,),
        )
        return row or {"total": 0, "last_fetch": 0}

    async def distinct_services(self, instance: str) -> list[dict[str, Any]]:
        return await self._fetchall(
            "SELECT DISTINCT rule_key, rule_name, sub_key, sub_name FROM logs "
            "WHERE instance=? AND module='webservice' ORDER BY rule_name, sub_name",
            (instance,),
        )

    async def service_counts(self, instance: str) -> list[dict[str, Any]]:
        """规则 + 子代理各自的日志/访问条数（用于服务下拉与总览）。"""
        logs = await self._fetchall(
            "SELECT 'rule' AS kind, rule_key AS key, rule_name AS name, "
            "NULL AS parent_name, COUNT(*) AS logs_count, 0 AS access_count "
            "FROM logs WHERE instance=? AND module='webservice' AND rule_key!='' AND sub_key='' "
            "GROUP BY rule_key",
            (instance,),
        )
        sub = await self._fetchall(
            "SELECT 'sub' AS kind, sub_key AS key, sub_name AS name, "
            "rule_name AS parent_name, COUNT(*) AS logs_count, 0 AS access_count "
            "FROM logs WHERE instance=? AND module='webservice' AND sub_key!='' "
            "GROUP BY sub_key",
            (instance,),
        )
        access_by_rule = {
            a["rule_key"]: a["c"]
            for a in await self._fetchall(
                "SELECT rule_key, COUNT(*) AS c FROM access_logs "
                "WHERE instance=? GROUP BY rule_key", (instance,)
            )
        }
        access_by_sub = {
            a["sub_key"]: a["c"]
            for a in await self._fetchall(
                "SELECT sub_key, COUNT(*) AS c FROM access_logs "
                "WHERE instance=? GROUP BY sub_key", (instance,)
            )
        }
        for row in logs:
            row["access_count"] = access_by_rule.get(row["key"], 0)
        for row in sub:
            row["access_count"] = access_by_sub.get(row["key"], 0)
        return logs + sub

    # ---------- Web 访问分析 ----------

    def _build_access_filters(
        self,
        instance: str | None, rule_key: str | None, sub_key: str | None,
        host: str | None, from_epoch: int | None, to_epoch: int | None,
        ip: str | None = None, path: str | None = None, search: str | None = None,
    ) -> tuple[str, list]:
        conds: list[str] = []
        params: list = []
        if instance:
            conds.append("instance=?")
            params.append(instance)
        if rule_key:
            conds.append("rule_key=?")
            params.append(rule_key)
        if sub_key:
            conds.append("sub_key=?")
            params.append(sub_key)
        if host:
            conds.append("host=?")
            params.append(host)
        if from_epoch is not None:
            conds.append("ts_epoch>=?")
            params.append(from_epoch)
        if to_epoch is not None:
            conds.append("ts_epoch<=?")
            params.append(to_epoch)
        if ip:
            conds.append("client_ip=?")
            params.append(ip)
        if path:
            conds.append("path LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(path)}%")
        if search:
            conds.append("(client_ip LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\' OR ua LIKE ? ESCAPE '\\')")
            like = f"%{_escape_like(search)}%"
            params.extend([like, like, like])
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        return where, params

    async def access_stats(
        self,
        instance: str | None = None, rule_key: str | None = None, sub_key: str | None = None,
        host: str | None = None, from_epoch: int | None = None, to_epoch: int | None = None,
        granularity: str = "hour", search: str | None = None, ip_limit: int = 15,
    ) -> dict[str, Any]:
        where, params = self._build_access_filters(
            instance, rule_key, sub_key, host, from_epoch, to_epoch, search=search
        )
        total = (await self._fetchone(
            f"SELECT COUNT(*) AS c FROM access_logs {where}", params
        ))["c"]
        uniq = {}
        for label, col in [("ips", "client_ip"), ("paths", "path")]:
            if not where:
                uniq[label] = (await self._fetchone(
                    f"SELECT COUNT(DISTINCT {col}) AS c FROM access_logs"
                ))["c"]
            else:
                uniq[label] = (await self._fetchone(
                    f"SELECT COUNT(DISTINCT {col}) AS c FROM access_logs {where}", params
                ))["c"]

        def grouped(col: str, limit: int | None = None) -> list[dict[str, Any]]:
            sql = f"SELECT {col} AS k, COUNT(*) AS count FROM access_logs {where} GROUP BY {col} ORDER BY count DESC"
            if limit:
                sql += f" LIMIT {limit}"
            return self._fetchall(sql, params)

        step = 3600 if granularity != "day" else 86400
        timeline = await self._fetchall(
            f"SELECT (ts_epoch/{step})*{step} AS bucket, COUNT(*) AS count "
            f"FROM access_logs {where} GROUP BY bucket ORDER BY bucket",
            params,
        )
        return {
            "total": total,
            "unique_ips": uniq["ips"],
            "unique_paths": uniq["paths"],
            "timeline": timeline,
            "top_ips": await grouped("client_ip", ip_limit),
            "top_paths": await grouped("path", 15),
            "browsers": await grouped("browser", 15),
            "os": await grouped("os", 15),
            "devices": await grouped("device", 15),
            "device_types": await grouped("device_type"),
            "methods": await grouped("method"),
            "hosts": await grouped("host", 15),
        }

    async def query_access_logs(
        self,
        instance: str | None = None, rule_key: str | None = None, sub_key: str | None = None,
        host: str | None = None, from_epoch: int | None = None, to_epoch: int | None = None,
        ip: str | None = None, path: str | None = None, search: str | None = None,
        page: int = 1, page_size: int = 100,
    ) -> dict[str, Any]:
        where, params = self._build_access_filters(
            instance, rule_key, sub_key, host, from_epoch, to_epoch, ip, path, search
        )
        page = max(1, page)
        page_size = min(500, max(1, page_size))
        offset = (page - 1) * page_size
        total = (await self._fetchone(
            f"SELECT COUNT(*) AS c FROM access_logs {where}", params
        ))["c"]
        rows = await self._fetchall(
            f"SELECT * FROM access_logs {where} ORDER BY ts_epoch DESC, id DESC LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        return {"total": total, "page": page, "page_size": page_size, "items": rows}

    async def access_instance_total(self, instance: str) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS c FROM access_logs WHERE instance=?", (instance,)
        )
        return row["c"] if row else 0

    async def access_ips(
        self,
        instance: str | None = None, rule_key: str | None = None, sub_key: str | None = None,
        host: str | None = None, from_epoch: int | None = None, to_epoch: int | None = None,
        search: str | None = None, page: int = 1, page_size: int = 50,
    ) -> dict[str, Any]:
        """全部历史 IP（去重），按访问次数倒序分页，附带流量快照。"""
        conds: list[str] = []
        params: list = []
        if instance:
            conds.append("instance=?")
            params.append(instance)
        if rule_key:
            conds.append("rule_key=?")
            params.append(rule_key)
        if sub_key:
            conds.append("sub_key=?")
            params.append(sub_key)
        if host:
            conds.append("host=?")
            params.append(host)
        if from_epoch is not None:
            conds.append("ts_epoch>=?")
            params.append(from_epoch)
        if to_epoch is not None:
            conds.append("ts_epoch<=?")
            params.append(to_epoch)
        if search:
            conds.append("client_ip LIKE ? ESCAPE '\\'")
            params.append(f"%{_escape_like(search)}%")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        page = max(1, page)
        page_size = min(200, max(1, page_size))
        offset = (page - 1) * page_size
        total = (await self._fetchone(
            f"SELECT COUNT(*) AS c FROM (SELECT 1 FROM access_logs {where} GROUP BY client_ip)",
            params,
        ))["c"]
        rows = await self._fetchall(
            f"SELECT client_ip, COUNT(*) AS count, MAX(ts_epoch) AS last_access "
            f"FROM access_logs {where} GROUP BY client_ip "
            f"ORDER BY count DESC, client_ip LIMIT ? OFFSET ?",
            params + [page_size, offset],
        )
        traffic = await self.traffic_map(instance, sub_key)
        for r in rows:
            t = traffic.get(r["client_ip"], {})
            r["connections"] = t.get("connections", 0)
            r["traffic_in"] = t.get("traffic_in", 0)
            r["traffic_out"] = t.get("traffic_out", 0)
        return {"total": total, "page": page, "page_size": page_size, "items": rows}

    async def _access_export_rows(
        self,
        instance: str | None, rule_key: str | None, sub_key: str | None,
        host: str | None, from_epoch: int | None, to_epoch: int | None,
        ip: str | None, path: str | None, search: str | None, limit: int,
    ) -> AsyncIterator[dict[str, Any]]:
        where, params = self._build_access_filters(
            instance, rule_key, sub_key, host, from_epoch, to_epoch, ip, path, search
        )
        sql = f"SELECT * FROM access_logs {where} ORDER BY ts_epoch DESC, id DESC LIMIT ?"
        cur = await self._execute(sql, params + [limit])
        while True:
            rows = await cur.fetchmany(5000)
            if not rows:
                break
            for row in rows:
                yield _row_to_dict(row)

    # ---------- IP 流量（accessdetail 实时快照） ----------

    async def upsert_ip_traffic(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        sql = (
            "INSERT INTO ip_traffic (instance, sub_key, client_ip, last_access,"
            " connections, traffic_in, traffic_out, fetched_at) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(instance, sub_key, client_ip) DO UPDATE SET"
            " last_access=excluded.last_access, connections=excluded.connections,"
            " traffic_in=excluded.traffic_in, traffic_out=excluded.traffic_out,"
            " fetched_at=excluded.fetched_at"
        )
        cur = await self._conn.executemany(
            sql,
            [
                (
                    r["instance"], r.get("sub_key") or "", r["client_ip"],
                    r.get("last_access") or 0, r.get("connections") or 0,
                    r.get("traffic_in") or 0, r.get("traffic_out") or 0,
                    r.get("fetched_at") or 0,
                )
                for r in rows
            ],
        )
        await self._conn.commit()
        return cur.rowcount

    async def traffic_map(self, instance: str, sub_key: str | None = None) -> dict[str, dict[str, Any]]:
        """client_ip → 聚合流量（跨子代理汇总连接/流量/最后访问）。"""
        if sub_key:
            rows = await self._fetchall(
                "SELECT * FROM ip_traffic WHERE instance=? AND sub_key=?",
                (instance, sub_key),
            )
        else:
            rows = await self._fetchall(
                "SELECT * FROM ip_traffic WHERE instance=?", (instance,)
            )
        m: dict[str, dict[str, Any]] = {}
        for r in rows:
            ip = r["client_ip"]
            agg = m.setdefault(
                ip, {"connections": 0, "traffic_in": 0, "traffic_out": 0, "last_access": 0}
            )
            agg["connections"] += r["connections"] or 0
            agg["traffic_in"] += r["traffic_in"] or 0
            agg["traffic_out"] += r["traffic_out"] or 0
            agg["last_access"] = max(agg["last_access"], r["last_access"] or 0)
        return m

    async def traffic_summary(self, instance: str, sub_key: str | None = None) -> dict[str, Any]:
        m = await self.traffic_map(instance, sub_key)
        return {
            "connections": sum(v["connections"] for v in m.values()),
            "traffic_in": sum(v["traffic_in"] for v in m.values()),
            "traffic_out": sum(v["traffic_out"] for v in m.values()),
        }

    # ---------- 导出 / 清理 ----------

    async def export_rows(
        self,
        instance: str | None = None, module: str | None = None,
        from_epoch: int | None = None, to_epoch: int | None = None,
        search: str | None = None, dedup: str | None = "time_content",
        limit: int = 100000, service: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        where, params = self._build_filters(
            instance, module, None, None, from_epoch, to_epoch, search, service=service
        )
        keys = self._dedup_key(dedup)
        if keys:
            part = ", ".join(keys)
            base = (
                f"SELECT * FROM (SELECT *, ROW_NUMBER() OVER ("
                f"PARTITION BY {part} ORDER BY ts_epoch DESC, id DESC) AS __rn "
                f"FROM logs {where}) WHERE __rn=1"
            )
        else:
            base = f"SELECT * FROM logs {where}"
        sql = f"{base} ORDER BY ts_epoch DESC, id DESC LIMIT ?"
        cur = await self._execute(sql, params + [limit])
        while True:
            rows = await cur.fetchmany(5000)
            if not rows:
                break
            for row in rows:
                yield _row_to_dict(row)

    async def cleanup_old(self, days: int) -> int:
        cutoff = int(time.time()) - days * 86400
        cur = await self._conn.execute("DELETE FROM logs WHERE ts_epoch < ?", (cutoff,))
        await self._conn.commit()
        await self._conn.execute("VACUUM")
        return cur.rowcount

    async def purge_instance(self, name: str) -> None:
        """删除实例后清除其全部采集数据（logs/access_logs/ip_traffic/cursors）。"""
        for table in ("logs", "access_logs", "ip_traffic", "cursors"):
            await self._conn.execute(f"DELETE FROM {table} WHERE instance=?", (name,))
        await self._conn.commit()
