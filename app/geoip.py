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
    searcher = _load()
    if searcher is None:
        return None
    try:
        addr = ipaddress.ip_address(ip)
        if not addr.version == 4:
            return None
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return {"country": "内网/保留", "province": "", "city": "", "isp": ""}
        region = searcher.search(ip)
    except (ValueError, TypeError, Exception):  # noqa: BLE001
        return None
    if not region:
        return None
    parts = region.split("|")
    pick = lambda i: parts[i] if len(parts) > i and parts[i] not in ("", "0") else ""

    return {
        "country": pick(0),
        "province": pick(1),
        "city": pick(2),
        "isp": pick(3),
    }


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
