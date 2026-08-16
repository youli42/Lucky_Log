"""配置管理 API：读取/保存 config.json，测试连接，删除实例。"""
from __future__ import annotations

from typing import Optional

import pydantic
from fastapi import APIRouter, HTTPException, Request

from ..config import ALL_MODULES, AppConfig, InstanceConfig, save_config

router = APIRouter(prefix="/api/config", tags=["config"])


class TestBody(pydantic.BaseModel):
    host: str
    port: str
    base: str = "/youlilucky"
    token: str
    https: bool = True


@router.get("")
async def get_config(request: Request):
    cfg = request.app.state.config
    return {"config": cfg.model_dump(), "modules": ALL_MODULES}


@router.post("/test")
async def test_config(request: Request, body: TestBody):
    """用表单值临时测试连接（不保存）。"""
    from ..lucky_client import LuckyClient

    inst = InstanceConfig(
        name="_test", host=body.host, port=body.port,
        base=body.base, token=body.token, https=body.https,
    )
    client = LuckyClient(inst)
    try:
        data = await client.get_json("/api/status")
        if isinstance(data, dict):
            return {"ok": True, "ret": data.get("ret"), "host": inst.base_url}
        return {"ok": True, "host": inst.base_url}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    finally:
        await client.close()


@router.put("")
async def put_config(request: Request, body: AppConfig):
    """整体保存配置，热同步采集器。"""
    save_config(body)
    request.app.state.config = body
    collector = request.app.state.collector
    collector.cfg = body
    await collector.sync_instances()
    return {"config": body.model_dump()}


@router.delete("/instance/{name}")
async def delete_instance(request: Request, name: str, purge: bool = False):
    """删除实例；purge=true 时同时清除其已采集数据。"""
    cfg = request.app.state.config
    if not any(i.name == name for i in cfg.instances):
        raise HTTPException(404, "实例不存在")
    data = cfg.model_dump()
    data["instances"] = [i for i in data["instances"] if i["name"] != name]
    new_cfg = AppConfig.model_validate(data)
    save_config(new_cfg)
    request.app.state.config = new_cfg
    collector = request.app.state.collector
    collector.cfg = new_cfg
    await collector.sync_instances()
    if purge:
        await request.app.state.db.purge_instance(name)
    return {"config": new_cfg.model_dump()}
