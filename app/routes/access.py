"""Web 访问日志分析 API：统计聚合 + 明细分页（含 IP 归属地）。"""
from __future__ import annotations

import csv
import json
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..db import Database
from ..geoip import province

router = APIRouter(prefix="/api/access", tags=["access"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


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
    # IP 归属地标注 + 地区分布
    region_counter: Counter[str] = Counter()
    for row in data["top_ips"]:
        region = province(row["k"] or "")
        row["region"] = region
        row["count"] = row.pop("count")
        if region != "未知":
            region_counter[region] += row["count"]
    data["top_ips"] = data["top_ips"][:15]
    data["region_dist"] = [
        {"region": k, "count": v} for k, v in region_counter.most_common(15)
    ]
    # 字段重命名：k → name，便于前端
    for key in ("top_paths", "browsers", "os", "devices", "device_types", "methods", "hosts"):
        data[key] = [{"name": r["k"] or "(未知)", "count": r["count"]} for r in data[key]]
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
):
    db = _get_db(request)
    data = await db.query_access_logs(
        instance, rule, sub, host, from_epoch, to_epoch, ip, path, search, page, page_size
    )
    for row in data["items"]:
        row["region"] = province(row["client_ip"] or "")
    return data


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
    from io import StringIO
    import time

    db = _get_db(request)
    if format == "json":
        rows = []
        async for r in db._access_export_rows(instance, rule, sub, host, from_epoch, to_epoch, ip, path, search, limit):
            r["region"] = province(r["client_ip"] or "")
            rows.append(r)
        return JSONResponse({"items": rows})

    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow(["time", "host", "rule", "sub", "ip", "method", "path", "browser", "os", "device", "device_type", "region"])
    async for r in db._access_export_rows(instance, rule, sub, host, from_epoch, to_epoch, ip, path, search, limit):
        writer.writerow([
            r["ts_text"], r["host"], r["rule_name"], r["sub_name"], r["client_ip"],
            r["method"], r["path"], r["browser"], r["os"], r["device"],
            r["device_type"], province(r["client_ip"] or ""),
        ])
    payload = "\ufeff" + buf.getvalue()
    filename = f"lucky_access_{int(time.time())}.csv"
    return StreamingResponse(
        iter([payload.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
