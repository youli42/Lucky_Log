"""手动采集与本地存储统计 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api", tags=["collect"])


@router.post("/collect")
async def collect(request: Request, instance: str):
    """立即采集指定实例（异步）。返回 started 是否新启动。"""
    collector = request.app.state.collector
    if not any(i.name == instance for i in collector.cfg.instances):
        raise HTTPException(404, "实例不存在")
    started = collector.collect_now(instance)
    st = collector.status.get(instance, {})
    return {"started": started, "collecting": st.get("collecting", False)}


@router.post("/collect/all")
async def collect_all(request: Request):
    """立即采集全部启用实例。"""
    collector = request.app.state.collector
    started = collector.collect_all()
    return {"started": started}


@router.get("/storage")
async def storage(request: Request):
    db = request.app.state.db
    return await db.storage_stats()
