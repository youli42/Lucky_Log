"""SMB 模块 API：运行状态概览 + 连接断开（Lucky 3.0.0 新增模块）。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..config import InstanceConfig
from ..lucky_client import LuckyClient

router = APIRouter(prefix="/api/smb", tags=["smb"])


def _instance(request: Request, name: str) -> InstanceConfig:
    inst = next((i for i in request.app.state.config.instances if i.name == name), None)
    if inst is None:
        raise HTTPException(404, "实例不存在")
    return inst


@router.get("/overview")
async def overview(request: Request, instance: str):
    inst = _instance(request, instance)
    client = LuckyClient(inst)
    try:
        status = await client.get_json("/api/smb/status")
        runtime = await client.get_json("/api/smb/runtime")
        return {"status": status, "runtime": runtime}
    finally:
        await client.close()


@router.post("/connections/{conn_id}/disconnect")
async def disconnect(request: Request, conn_id: str, instance: str):
    inst = _instance(request, instance)
    client = LuckyClient(inst)
    try:
        return await client.post_json(f"/api/smb/connections/{conn_id}/disconnect", expect_ret0=False)
    finally:
        await client.close()
