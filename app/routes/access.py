"""Web 访问日志分析 API：统计聚合 + 明细分页 + 导出。

富化：查询时为每行附加完整归属地（country/province/city/isp）、
完整客户端信息（浏览器/OS/设备 family+version+brand+model）与 IP 流量快照。
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter
from io import StringIO
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..access_parser import ua_detail
from ..db import Database
from ..geoip import geo_short, query as geo_query
from ..lucky_client import LuckyError

router = APIRouter(prefix="/api/access", tags=["access"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


def _geo_fields(ip: str) -> dict:
    """IP → 归属地字段（流量另附时用；与 _geo_traffic_fields 共用同一实现）。"""
    g = geo_query(ip) or {}
    return {
        "geo": g,
        "country": g.get("country", ""),
        "province": g.get("province", ""),
        "city": g.get("city", ""),
        "isp": g.get("isp", ""),
        "geo_short": geo_short(ip),
    }


def _geo_traffic_fields(ip: str, traffic: dict[str, dict]) -> dict:
    """IP → 归属地 + 流量快照字段（排行榜/明细共用，避免各处重复实现）。"""
    t = traffic.get(ip, {})
    return {
        **_geo_fields(ip),
        "connections": t.get("connections", 0),
        "traffic_in": t.get("traffic_in", 0),
        "traffic_out": t.get("traffic_out", 0),
        "last_access": t.get("last_access", 0),
    }


def _enrich(item: dict, traffic: dict[str, dict]) -> dict:
    """明细行富化：归属地 + 流量快照 + 完整客户端信息（UA 解析）。"""
    item.update(_geo_traffic_fields(item.get("client_ip") or "", traffic))
    item.update(ua_detail(item.get("ua") or ""))
    return item


@router.get("/stats")
async def access_stats(
    request: Request,
    instance: Optional[str] = None,
    rule: Optional[str] = None,
    sub: Optional[str] = None,
    host: Optional[str] = None,
    from_epoch: Optional[int] = None,
    to_epoch: Optional[int] = None,
    granularity: str = "hour",
    search: Optional[str] = None,
):
    db = _get_db(request)
    data = await db.access_stats(
        instance, rule, sub, host, from_epoch, to_epoch, granularity, search,
        ip_limit=300,
    )
    traffic = await db.traffic_map(instance, sub)
    region_counter: Counter[str] = Counter()
    # 排行榜先对 Top300 做轻量富化（仅归属地+流量）用于地区分布统计，
    # 展示只取 Top15；再对 Top15 补全与明细同构的完整字段。
    for row in data["top_ips"]:
        row.update(_geo_traffic_fields(row.get("k") or "", traffic))
        if row["geo_short"] != "未知":
            region_counter[row["geo_short"]] += row["count"]
    data["top_ips"] = data["top_ips"][:15]
    for row in data["top_ips"]:
        row["client_ip"] = row["k"]
        _enrich(row, traffic)
    data["region_dist"] = [
        {"region": k, "count": v} for k, v in region_counter.most_common(15)
    ]
    # 字段重命名：k → name，便于前端
    for key in ("top_paths", "browsers", "os", "devices", "device_types", "methods", "hosts"):
        data[key] = [{"name": r["k"] or "(未知)", "count": r["count"]} for r in data[key]]
    # 流量快照汇总（当前连接/累计流量，与时间筛选无关）
    ts = await db.traffic_summary(instance, sub)
    data["traffic"] = ts
    return data


@router.get("/logs")
async def access_logs(
    request: Request,
    instance: Optional[str] = None,
    rule: Optional[str] = None,
    sub: Optional[str] = None,
    host: Optional[str] = None,
    from_epoch: Optional[int] = None,
    to_epoch: Optional[int] = None,
    ip: Optional[str] = None,
    path: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    sort: Optional[str] = None,
    sort_dir: Optional[str] = None,
):
    db = _get_db(request)
    data = await db.query_access_logs(
        instance, rule, sub, host, from_epoch, to_epoch, ip, path, search,
        page, page_size, sort, sort_dir,
    )
    traffic = await db.traffic_map(instance, sub)
    data["items"] = [_enrich(r, traffic) for r in data["items"]]
    return data


@router.get("/ips")
async def access_ips(
    request: Request,
    instance: Optional[str] = None,
    rule: Optional[str] = None,
    sub: Optional[str] = None,
    host: Optional[str] = None,
    from_epoch: Optional[int] = None,
    to_epoch: Optional[int] = None,
    search: Optional[str] = None,
    sort: str = "count",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 500,
    limit: Optional[int] = None,
):
    db = _get_db(request)
    data = await db.access_ips(instance, rule, sub, host, from_epoch, to_epoch, search)
    items = data["items"]
    for row in items:
        row.update(_geo_fields(row["client_ip"]))
    items = _sort_ips(items, sort, sort_dir)
    if limit is not None:
        items = items[: max(0, limit)]
    else:
        page = max(1, page)
        page_size = min(50000, max(1, page_size))
        offset = (page - 1) * page_size
        items = items[offset:offset + page_size]
    return {"total": data["total"], "page": page, "page_size": page_size, "items": items}


_IP_SORT_KEYS = {
    "ip": "client_ip", "count": "count", "last_access": "last_access",
    "connections": "connections", "traffic_in": "traffic_in",
    "traffic_out": "traffic_out", "geo": "geo_short",
}


def _sort_ips(items: list, sort: str, sort_dir: str) -> list:
    key = _IP_SORT_KEYS.get(sort or "")
    if key is None:
        key = "count"
        sort_dir = "desc"
    reverse = str(sort_dir or "").lower().startswith("d")

    def val(row):
        v = row.get(key)
        return v if v is not None else (0 if key not in ("client_ip", "geo_short") else "")

    return sorted(items, key=val, reverse=reverse)


@router.get("/connections")
async def live_connections(request: Request, instance: str = Query(...)):
    """实时连接详情：即时拉取各子代理 accessdetail（连接数 / 流量 / IP 明细）。

    区别于采集器 30s 节流快照（ip_traffic），本接口是**查看面板时的实时数据**；
    带 10s 实例级冷却（collector.live_allowed）防频繁点击打爆 Lucky。
    客户端复用 collector 的实例客户端（共享全局并发限流 ≤2）。
    """
    collector = request.app.state.collector
    inst = next((i for i in request.app.state.config.instances if i.name == instance), None)
    if inst is None:
        raise HTTPException(404, "实例不存在")
    if not collector.live_allowed(instance):
        raise HTTPException(429, "操作过于频繁，请稍后再试")
    client = collector.get_client(inst)
    tree = collector.service_tree(instance)
    if not tree:  # 服务树未预热时现拉（复用采集端逻辑）
        tree = await client.fetch_service_tree()

    services: list[dict] = []
    total_connections = total_ips = 0
    total_in = total_out = 0
    for rule in tree:
        rule_key = rule.get("Key") or ""
        rule_name = rule.get("Name") or ""
        for sub in rule.get("SubRuleList") or []:
            sub_key = sub.get("Key") or ""
            sub_name = sub.get("Name") or ""
            try:
                data = await client.get_json(
                    f"/webservice/{rule_key}/{sub_key}/accessdetail",
                    {"pageSize": 500, "page": 1},
                )
            except LuckyError as e:
                if e.status == 404:  # 子代理无 accessdetail（未启用）→ 跳过
                    continue
                raise
            ips: list[dict] = []
            conn = in_b = out_b = 0
            for r in data.get("resList") or []:
                ip = r.get("IP")
                if not ip:
                    continue
                c = r.get("Connections") or 0
                i_in = r.get("TrafficIn") or 0
                i_out = r.get("TrafficOut") or 0
                conn += c
                in_b += i_in
                out_b += i_out
                ips.append({
                    "client_ip": ip,
                    "connections": c,
                    "traffic_in": i_in,
                    "traffic_out": i_out,
                    "last_access": r.get("LastAccess") or 0,
                    **_geo_fields(ip),
                })
            if ips:
                total_connections += conn
                total_ips += len(ips)
                total_in += in_b
                total_out += out_b
                services.append({
                    "rule_key": rule_key,
                    "rule_name": rule_name,
                    "sub_key": sub_key,
                    "sub_name": sub_name,
                    "connections": conn,
                    "ip_count": len(ips),
                    "traffic_in": in_b,
                    "traffic_out": out_b,
                    "ips": ips,
                })
    services.sort(key=lambda s: -s["connections"])
    return {
        "instance": instance,
        "fetched_at": int(time.time()),
        "total_connections": total_connections,
        "total_ips": total_ips,
        "traffic_in": total_in,
        "traffic_out": total_out,
        "services": services,
    }


@router.get("/export")
async def access_export(
    request: Request,
    instance: Optional[str] = None,
    rule: Optional[str] = None,
    sub: Optional[str] = None,
    host: Optional[str] = None,
    from_epoch: Optional[int] = None,
    to_epoch: Optional[int] = None,
    ip: Optional[str] = None,
    path: Optional[str] = None,
    search: Optional[str] = None,
    format: str = "csv",
    limit: int = 100000,
):
    db = _get_db(request)
    traffic = await db.traffic_map(instance, sub)

    if format == "json":
        rows = []
        async for r in db._access_export_rows(instance, rule, sub, host, from_epoch, to_epoch, ip, path, search, limit):
            rows.append(_enrich(r, traffic))
        return JSONResponse({"items": rows})

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "time", "host", "rule", "sub", "ip", "method", "path",
        "country", "province", "city", "isp", "geo",
        "browser", "browser_version", "os", "os_version",
        "device", "device_brand", "device_model", "device_type",
        "connections", "traffic_in", "traffic_out", "last_access",
    ])
    async for r in db._access_export_rows(instance, rule, sub, host, from_epoch, to_epoch, ip, path, search, limit):
        e = _enrich(r, traffic)
        writer.writerow([
            e["ts_text"], e["host"], e["rule_name"], e["sub_name"], e["client_ip"],
            e["method"], e["path"],
            e["country"], e["province"], e["city"], e["isp"], e["geo_short"],
            e["browser"], e["browser_version"], e["os"], e["os_version"],
            e["device"], e["device_brand"], e["device_model"], e["device_type"],
            e["connections"], e["traffic_in"], e["traffic_out"],
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e["last_access"])) if e["last_access"] else "",
        ])
    payload = "\ufeff" + buf.getvalue()
    filename = f"lucky_access_{int(time.time())}.csv"
    return StreamingResponse(
        iter([payload.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
