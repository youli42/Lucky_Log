"""Web 访问日志解析：内嵌 ExtInfo JSON + UserAgent → 结构化访问行。

对齐 doc/03 子代理层日志结构：
  LogContent = {"ExtInfo":{"ClientIP","Host","Method","URL","UserAgent"},"level","msg"}
"""
from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from typing import Any

from user_agents import parse as ua_parse

from .timeutil import parse_lucky_ts

_BOT_RE = re.compile(r"bot|crawler|spider|slurp|curl|wget|python-requests|headless", re.I)

# UA 解析较慢且同一 UA 会被反复解析（采集 + 明细/导出富化），做进程内 LRU 缓存。
_ua_parse_cached = lru_cache(maxsize=8192)(ua_parse)


def parse_extinfo(content: str) -> dict[str, Any] | None:
    """从 LogContent 解析出访问信息字典；非 Web 访问日志返回 None。

    兼容 Lucky 子代理层两种日志格式（实测均有，需向后兼容）：

    - 旧版（约 2026-08-16 前）：``{"ExtInfo":{"ClientIP","Host","Method","URL","UserAgent"}, ...}``
    - 新版（约 2026-08-16 后）：``{"client_ip","host","method","url","user_agent","event", ...}``
      扁平、小写、无 ``ExtInfo`` 包裹。
    """
    if not content:
        return None
    try:
        obj = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    # 旧版：ExtInfo 包裹
    if isinstance(obj.get("ExtInfo"), dict):
        return obj["ExtInfo"]
    # 新版：扁平结构（含小写 client_ip/method/url/host/user_agent 之一）
    if any(k in obj for k in ("client_ip", "host", "method", "url", "user_agent")):
        return obj
    return None


def _classify_device(parsed: Any, ua: str) -> str:
    if not ua:
        return "unknown"
    if _BOT_RE.search(ua):
        return "bot"
    if parsed is None:
        return "unknown"
    if parsed.is_bot:
        return "bot"
    if parsed.is_tablet:
        return "tablet"
    if parsed.is_mobile:
        return "mobile"
    if parsed.is_pc:
        return "desktop"
    return "unknown"


def parse_access_row(
    instance: str,
    rec: dict[str, Any],
    *,
    rule_key: str = "",
    rule_name: str = "",
    sub_key: str = "",
    sub_name: str = "",
    fetched_at: int | None = None,
) -> dict[str, Any] | None:
    """原始日志行 → access_logs 行；无法解析返回 None。

    访问字段兼容新旧两种大小写（ClientIP/Host/Method/URL/UserAgent 与
    client_ip/host/method/url/user_agent）。
    """
    ext = parse_extinfo(rec.get("LogContent") or "")
    if not ext:
        return None

    def pick(*keys: str) -> str:
        for k in keys:
            v = ext.get(k)
            if v:
                return str(v)
        return ""

    client_ip = pick("ClientIP", "client_ip")
    if not client_ip:
        return None
    ua = pick("UserAgent", "user_agent")
    parsed = _ua_parse_cached(ua) if ua else None
    if parsed is not None:
        browser = parsed.browser.family or ""
        os_family = parsed.os.family or ""
        device = parsed.device.family or ""
        device_type = _classify_device(parsed, ua)
    else:
        browser = os_family = device = ""
        device_type = _classify_device(None, ua)
    return {
        "instance": instance,
        "rule_key": rule_key,
        "rule_name": rule_name,
        "sub_key": sub_key,
        "sub_name": sub_name,
        "host": pick("Host", "host"),
        "ts_epoch": parse_lucky_ts(rec.get("LogTime")),
        "ts_text": rec.get("LogTime") or "",
        "client_ip": client_ip,
        "method": pick("Method", "method"),
        "path": pick("URL", "url"),
        "ua": ua,
        "browser": browser,
        "os": os_family,
        "device": device,
        "device_type": device_type,
        "fetched_at": fetched_at or int(time.time()),
    }


@lru_cache(maxsize=8192)
def ua_detail(ua: str) -> dict[str, str]:
    """UA → 完整客户端信息（family + version + brand + model）。"""
    parsed = _ua_parse_cached(ua) if ua else None
    if parsed is None:
        return {
            "browser": "", "browser_version": "", "os": "", "os_version": "",
            "device": "", "device_brand": "", "device_model": "", "device_type": "unknown",
        }
    return {
        "browser": parsed.browser.family or "",
        "browser_version": parsed.browser.version_string or "",
        "os": parsed.os.family or "",
        "os_version": parsed.os.version_string or "",
        "device": parsed.device.family or "",
        "device_brand": parsed.device.brand or "",
        "device_model": parsed.device.model or "",
        "device_type": _classify_device(parsed, ua),
    }
