"""Lucky 时间解析（统一入口，时间戳以 Lucky 为准）。

Lucky 日志时间格式固定为 ``YYYY/MM/DD HH:mm:ss``，**无时区信息**。
约定：

- 按运行机器本地时区解析为 epoch 秒。本项目场景为内网部署，采集机与
  Lucky 服务端同属一个时区，因此该解析结果即 Lucky 端本地时间；
- epoch 仅用于排序 / 筛选 / 统计分组，展示层一律使用原始 ``ts_text``
  或按浏览器本地时区格式化，不做任何"时区修正"；
- 若将采集机部署到与 Lucky 异时区的机器，需保证两机时区一致。

后端任何解析 Lucky 时间的地方都应复用本函数，禁止各自实现。
"""
from __future__ import annotations

from datetime import datetime

from typing import Any

LUCKY_TS_FORMAT = "%Y/%m/%d %H:%M:%S"


def parse_lucky_ts(ts_text: Any) -> int:
    """``YYYY/MM/DD HH:mm:ss`` → epoch 秒（本地时区，以 Lucky 为准）。解析失败返回 0。"""
    if not ts_text:
        return 0
    try:
        return int(datetime.strptime(str(ts_text), LUCKY_TS_FORMAT).timestamp())
    except (ValueError, TypeError):
        return 0
