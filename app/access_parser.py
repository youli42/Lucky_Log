"""Web 访问日志解析：内嵌 ExtInfo JSON + UserAgent → 结构化访问行。

对齐 doc/03 子代理层日志结构：
  LogContent = {"ExtInfo":{"ClientIP","Host","Method","URL","UserAgent"},"level","msg"}
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from user_agents import parse as ua_parse

_BOT_RE = re.compile(r"bot|crawler|spider|slurp|curl|wget|python-requests|headless", re.I)


def parse_extinfo(content: str) -> dict[str, Any] | None:
    """从 LogContent 解析出 ExtInfo；非 Web 访问日志返回 None。"""
    if not content:
        return None
    try:
        obj = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    ext = obj.get("ExtInfo")
    if not isinstance(ext, dict):
        return None
    return ext


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
    """原始日志行 → access_logs 行；无法解析返回 None。"""
    ext = parse_extinfo(rec.get("LogContent") or "")
    if not ext:
        return None
    client_ip = ext.get("ClientIP") or ""
    if not client_ip:
        return None
    ua = ext.get("UserAgent") or ""
    parsed = ua_parse(ua) if ua else None
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
        "host": ext.get("Host") or "",
        "ts_epoch": parse_ts(rec.get("LogTime")),
        "ts_text": rec.get("LogTime") or "",
        "client_ip": client_ip,
        "method": ext.get("Method") or "",
        "path": ext.get("URL") or "",
        "ua": ua,
        "browser": browser,
        "os": os_family,
        "device": device,
        "device_type": device_type,
        "fetched_at": fetched_at or int(time.time()),
    }


def parse_ts(ts_text: Any) -> int:
    from datetime import datetime

    if not ts_text:
        return 0
    try:
        return int(datetime.strptime(str(ts_text), "%Y/%m/%d %H:%M:%S").timestamp())
    except (ValueError, TypeError):
        return 0


def ua_detail(ua: str) -> dict[str, str]:
    """UA → 完整客户端信息（family + version + brand + model）。"""
    parsed = ua_parse(ua) if ua else None
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
