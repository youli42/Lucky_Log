"""Docker 面板 API：本地快照缓存 + 实时数据代理 + 容器控制。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..config import InstanceConfig
from ..docker_api import fetch_snapshot
from ..lucky_client import LuckyClient

router = APIRouter(prefix="/api/docker", tags=["docker"])

# 容器控制操作 → (方法, 路径模板, 是否带 timeout)
ACTIONS = {
    "start": ("POST", "/api/docker/containers/{id}/start", False),
    "stop": ("POST", "/api/docker/containers/{id}/stop", True),
    "restart": ("POST", "/api/docker/containers/{id}/restart", True),
    "pause": ("POST", "/api/docker/containers/{id}/pause", False),
    "unpause": ("POST", "/api/docker/containers/{id}/unpause", False),
}


def _instance(request: Request, name: str) -> InstanceConfig:
    inst = next((i for i in request.app.state.config.instances if i.name == name), None)
    if inst is None:
        raise HTTPException(404, "实例不存在")
    return inst


def _client(request: Request, instance: str) -> LuckyClient:
    return LuckyClient(_instance(request, instance))


@router.get("/snapshot")
async def snapshot(request: Request, instance: str):
    """本地缓存快照（采集器后台预热 / refresh 时更新），进面板秒显。"""
    return await request.app.state.db.get_docker_cache(instance) or {
        "instance": instance, "fetched_at": 0,
        "info": None, "version": None,
        "containers": [], "images": [], "networks": [], "volumes": [],
    }


@router.post("/refresh")
async def refresh(request: Request, instance: str):
    """全量拉取 Docker 数据并写入本地缓存，返回最新快照。"""
    client = _client(request, instance)
    try:
        snap = await fetch_snapshot(client)
    finally:
        await client.close()
    now = int(__import__("time").time())
    await request.app.state.db.save_docker_cache(instance, snap, now)
    snap["instance"] = instance
    snap["fetched_at"] = now
    return snap


@router.get("/overview")
async def overview(request: Request, instance: str):
    client = _client(request, instance)
    try:
        info = await client.get_json("/api/docker/info", expect_ret0=False)
        version = await client.get_json("/api/docker/version", expect_ret0=False)
        return {"info": info, "version": version}
    finally:
        await client.close()


@router.get("/containers")
async def containers(request: Request, instance: str):
    """容器列表 + 批量实时资源（stats-cached 合并）。"""
    client = _client(request, instance)
    try:
        data = await client.get_json("/api/docker/containers", expect_ret0=False)
        stats = {}
        try:
            sc = await client.get_json("/api/docker/containers/stats-cached", expect_ret0=False)
            stats = sc.get("data") or {}
        except Exception:
            stats = {}
        for c in data.get("containers") or []:
            c["stats"] = stats.get(c.get("Id"), {})
        return {"containers": data.get("containers") or [], "total": len(data.get("containers") or [])}
    finally:
        await client.close()


@router.get("/container/{cid}")
async def container_detail(request: Request, instance: str, cid: str):
    client = _client(request, instance)
    try:
        stats = await client.get_json(f"/api/docker/containers/{cid}/stats", expect_ret0=False)
        processes = {}
        try:
            processes = await client.get_json(f"/api/docker/containers/{cid}/processes", expect_ret0=False)
        except Exception:
            processes = {}
        return {"stats": stats.get("data") or stats, "processes": processes}
    finally:
        await client.close()


@router.get("/container/{cid}/logs")
async def container_logs(request: Request, instance: str, cid: str, tail: int = 200):
    client = _client(request, instance)
    try:
        data = await client.get_json(f"/api/docker/containers/{cid}/logs", expect_ret0=False)
        text = data.get("logs") or ""
        lines = text.splitlines()
        return {"logs": "\n".join(lines[-tail:]) if tail and tail > 0 else text}
    finally:
        await client.close()


@router.post("/containers/{cid}/action")
async def container_action(request: Request, instance: str, cid: str, action: str, timeout: int = 10):
    if action not in ACTIONS:
        raise HTTPException(400, f"不支持的操作: {action}")
    method, path, with_timeout = ACTIONS[action]
    client = _client(request, instance)
    try:
        url = path.format(id=cid)
        data = await client._request(
            method, url,
            data={"timeout": timeout} if with_timeout else None,
            expect_ret0=False,
        )
        return {"ok": True, "action": action, "result": data}
    except Exception as e:
        return {"ok": False, "action": action, "error": str(e)[:200]}
    finally:
        await client.close()


@router.get("/images")
async def images(request: Request, instance: str):
    client = _client(request, instance)
    try:
        data = await client.get_json("/api/docker/images", expect_ret0=False)
        return {"images": data.get("images") or []}
    finally:
        await client.close()


@router.get("/networks")
async def networks(request: Request, instance: str):
    client = _client(request, instance)
    try:
        data = await client.get_json("/api/docker/networks", expect_ret0=False)
        return {"networks": data.get("networks") or []}
    finally:
        await client.close()


@router.get("/volumes")
async def volumes(request: Request, instance: str):
    client = _client(request, instance)
    try:
        data = await client.get_json("/api/docker/volumes", expect_ret0=False)
        return {"volumes": data.get("volumes") or []}
    finally:
        await client.close()
