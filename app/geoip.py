"""ip2region 离线 IP 归属地查询（懒加载，缺库/失败降级）。"""
from __future__ import annotations

import ipaddress
import threading
from pathlib import Path
from typing import Any

from .config import DATA_DIR

XDB_PATH = DATA_DIR / "ip2region.xdb"

_searcher: Any = None
_buffer: bytes | None = None
_lock = threading.Lock()

# IP → 归属地结果缓存（同 IP 在明细/排行/导出中会被反复查询）。
# 容量到上限时整体清空（简单有效，查询成本低）；xdb 未加载成功的查询不缓存，
# 避免负结果长期固化导致后续 xdb 就绪后仍返回旧值。
_cache: dict[str, dict[str, str] | None] = {}
_MAX_CACHE = 8192


def _load() -> Any:
    global _searcher, _buffer
    if _searcher is not None:
        return _searcher
    with _lock:
        if _searcher is None:
            if not XDB_PATH.exists():
                return None
            try:
                import ip2region.searcher as xdb
                import ip2region.util as util

                _buffer = util.load_content_from_file(str(XDB_PATH))
                _searcher = xdb.new_with_buffer(util.IPv4, _buffer)
            except Exception:  # noqa: BLE001
                _searcher = None
    return _searcher


def query(ip: str) -> dict[str, str] | None:
    """查询 IP，返回 {country, province, city, isp}；失败/内网返回 None。"""
    if not ip or ip in _cache:
        return _cache.get(ip)
    searcher = _load()
    if searcher is None:
        return None
    try:
        addr = ipaddress.ip_address(ip)
        if not addr.version == 4:
            return None
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            result = {"country": "内网/保留", "province": "", "city": "", "isp": ""}
        else:
            region = searcher.search(ip)
            if not region:
                return None
            parts = region.split("|")
            pick = lambda i: parts[i] if len(parts) > i and parts[i] not in ("", "0") else ""
            result = {
                "country": pick(0),
                "province": pick(1),
                "city": pick(2),
                "isp": pick(3),
            }
    except (ValueError, TypeError):
        return None
    if len(_cache) >= _MAX_CACHE:
        _cache.clear()
    _cache[ip] = result
    return result


def province(ip: str) -> str:
    """归属地短标签：中国 IP → 省（如 广东），国外 → 国家。"""
    r = query(ip)
    if not r:
        return "未知"
    if r["province"]:
        return r["province"]
    if r["country"]:
        return r["country"]
    return "未知"


def geo_short(ip: str) -> str:
    """表格用短标签：省·市（如 广东省·广州市），国外显国家。"""
    r = query(ip)
    if not r:
        return "未知"
    if r["province"]:
        city = r["city"]
        return f"{r['province']}·{city}" if city else r["province"]
    if r["country"]:
        return r["country"]
    return "未知"
