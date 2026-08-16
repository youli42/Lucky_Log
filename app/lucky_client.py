"""Lucky Admin API 客户端。

- 自签名证书 verify=False（抑制告警）
- OpenToken Header 鉴权
- 连接/限流错误自动重试（指数退避）
- 日志分页拉取、服务树获取
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import InstanceConfig

logger = logging.getLogger(__name__)

_SSL_WARN_MSG = "Enable fallback certificate verification"  # 抑制关键字

# 全局并发信号量：无论几个实例/手动任务并发，对 Lucky 目标的 HTTP 请求并发恒 ≤2
_GLOBAL_SEMAPHORE = asyncio.Semaphore(2)


class LuckyError(Exception):
    """Lucky API 调用异常（HTTP/网络/业务码）。status 为 HTTP 状态码，网络/业务错误为 None。"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class LuckyClient:
    def __init__(self, cfg: InstanceConfig):
        self.cfg = cfg
        self._client = httpx.AsyncClient(
            verify=False,
            timeout=httpx.Timeout(10.0, connect=8.0),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def url(self, path: str) -> str:
        return self.cfg.api_url(path)

    async def get_json(
        self, path: str, params: dict[str, Any] | None = None,
        retries: int = 3, expect_ret0: bool = True,
    ) -> Any:
        url = self.url(path)
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            async with _GLOBAL_SEMAPHORE:
                try:
                    resp = await self._client.get(url, params=params, headers={"OpenToken": self.cfg.token})
                except httpx.HTTPError as e:
                    last_err = e
                    logger.warning("[%s] GET %s 网络错误: %s (attempt %d/%d)", self.cfg.name, path, e, attempt, retries)
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
            if resp.status_code != 200:
                last_err = LuckyError(f"HTTP {resp.status_code}: {resp.text[:200]}", status=resp.status_code)
                # 4xx 不重试（模块未启用 404 等），5xx/网络类重试
                if 400 <= resp.status_code < 500:
                    raise last_err
                logger.warning("[%s] GET %s HTTP %s (attempt %d/%d)", self.cfg.name, path, resp.status_code, attempt, retries)
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            try:
                data = resp.json()
            except ValueError as e:
                last_err = LuckyError(f"JSON 解析失败: {resp.text[:200]}")
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            if expect_ret0 and isinstance(data, dict) and data.get("ret") not in (0, None):
                last_err = LuckyError(f"业务错误 ret={data.get('ret')}: {data.get('msg', '')}")
                # ret=-1 鉴权失败不重试
                if data.get("ret") == -1:
                    raise last_err
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                continue
            return data
        raise LuckyError(str(last_err))

    async def get_log_page(
        self, path: str, page: int, page_size: int = 100,
    ) -> dict[str, Any]:
        data = await self.get_json(path, {"pageSize": page_size, "page": page})
        if not isinstance(data, dict):
            raise LuckyError(f"日志响应非对象: {str(data)[:200]}")
        logs = data.get("logs") or []
        total = data.get("total") or len(logs)
        return {"logs": logs, "total": total, "page": page, "page_size": page_size}

    async def fetch_service_tree(self) -> list[dict[str, Any]]:
        """拉取 /api/webservice/rules_lite 服务树（规则→子代理）。"""
        data = await self.get_json("/webservice/rules_lite")
        if isinstance(data, dict) and isinstance(data.get("list"), list):
            return data["list"]
        return []
