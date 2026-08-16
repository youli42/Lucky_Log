"""Docker 快照抓取（供采集器后台预热缓存与 /api/docker/refresh 共用）。"""
from __future__ import annotations

import asyncio
from typing import Any

from .lucky_client import LuckyClient


async def fetch_snapshot(client: LuckyClient) -> dict[str, Any]:
    """全量拉取 Docker 面板所需数据（含批量资源合并）。"""
    info = await client.get_json("/api/docker/info", expect_ret0=False)
    version = await client.get_json("/api/docker/version", expect_ret0=False)
    containers = await client.get_json("/api/docker/containers", expect_ret0=False)
    stats: dict[str, Any] = {}
    try:
        sc = await client.get_json("/api/docker/containers/stats-cached", expect_ret0=False)
        stats = sc.get("data") or {}
    except Exception:  # noqa: BLE001
        pass
    for c in containers.get("containers") or []:
        c["stats"] = stats.get(c.get("Id"), {})
    images = await client.get_json("/api/docker/images", expect_ret0=False)
    networks = await client.get_json("/api/docker/networks", expect_ret0=False)
    volumes = await client.get_json("/api/docker/volumes", expect_ret0=False)
    return {
        "info": info,
        "version": version,
        "containers": containers.get("containers") or [],
        "images": images.get("images") or [],
        "networks": networks.get("networks") or [],
        "volumes": volumes.get("volumes") or [],
    }
