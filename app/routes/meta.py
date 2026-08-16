"""实例 / 服务树 / 模块 / 统计 API。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from ..db import Database

router = APIRouter(prefix="/api", tags=["meta"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


def _get_collector(request: Request):
    return request.app.state.collector


@router.get("/instances")
async def list_instances(request: Request):
    cfg = request.app.state.config
    collector = _get_collector(request)
    db = _get_db(request)
    out = []
    for inst in cfg.instances:
        info = {
            "name": inst.name,
            "host": inst.host,
            "port": inst.port,
            "base": inst.base,
            "https": inst.https,
            "enabled": inst.enabled,
            "modules": inst.modules,
            "last_collect": None,
            "last_error": None,
            "total": 0,
        }
        st = collector.status.get(inst.name, {})
        if st.get("last_collect"):
            info["last_collect"] = st["last_collect"]
        info["last_error"] = st.get("last_error")
        info["collecting"] = st.get("collecting", False)
        info["current"] = st.get("current", "")
        info["page"] = st.get("page", 0)
        info["source_total"] = st.get("total", 0)
        info["collected_rows"] = st.get("collected_rows", 0)
        info["started_at"] = st.get("started_at", 0)
        info["fail_count"] = st.get("fail_count", 0)
        info["backoff_until"] = st.get("backoff_until", 0)
        info["next_retry_in"] = st.get("next_retry_in", 0)
        info["paused"] = st.get("paused", False)
        stats = await db.instance_stats(inst.name)
        info["total"] = stats["total"]
        info["access"] = await db.access_instance_total(inst.name)
        out.append(info)
    return {"instances": out}


@router.get("/overview")
async def overview(
    request: Request,
    instance: Optional[str] = None,
    from_epoch: Optional[int] = None,
    to_epoch: Optional[int] = None,
    granularity: str = "hour",
):
    db = _get_db(request)
    by_module = await db.stats_by_module(instance, from_epoch, to_epoch)
    timeline = await db.stats_timeline(instance, None, from_epoch, to_epoch, granularity)
    by_service = await db.stats_by_service(instance, from_epoch, to_epoch)
    access_total = 0
    total_logs = 0
    if instance:
        total_logs = (await db.instance_stats(instance))["total"]
        access_total = await db.access_instance_total(instance)
    else:
        for inst in request.app.state.config.enabled_instances():
            total_logs += (await db.instance_stats(inst.name))["total"]
            access_total += await db.access_instance_total(inst.name)
    db_bytes = Path(db.path).stat().st_size if Path(db.path).exists() else 0
    return {
        "total_logs": total_logs,
        "access_total": access_total,
        "active_services": len(by_service),
        "db_bytes": db_bytes,
        "by_module": by_module,
        "timeline": timeline,
        "by_service": by_service,
    }


@router.get("/services")
async def list_services(
    request: Request,
    instance: str = Query(...),
):
    collector = _get_collector(request)
    db = _get_db(request)
    tree = collector.service_tree(instance)
    counts = await db.service_counts(instance)
    return {"tree": tree, "counts": counts}


@router.get("/modules")
async def list_modules(
    request: Request,
    instance: str = Query(...),
):
    db = _get_db(request)
    counts = await db.module_counts(instance)
    by_module = {m["module"]: m["count"] for m in counts}
    return {"modules": by_module}


@router.get("/stats")
async def stats(
    request: Request,
    instance: Optional[str] = None,
    module: Optional[str] = None,
    from_epoch: Optional[int] = None,
    to_epoch: Optional[int] = None,
    granularity: str = "hour",
):
    db = _get_db(request)
    by_module = await db.stats_by_module(instance, from_epoch, to_epoch)
    timeline = await db.stats_timeline(instance, module, from_epoch, to_epoch, granularity)
    by_service = await db.stats_by_service(instance, from_epoch, to_epoch)
    return {
        "by_module": by_module,
        "timeline": timeline,
        "by_service": by_service,
        "granularity": granularity,
    }
