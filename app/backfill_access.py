"""历史回填：将 logs 表中 webservice 子代理层原始日志重新解析进 access_logs。

Lucky 子代理层 LogContent 在 ~2026-08-16 变更格式（ExtInfo 包裹 → 扁平小写），
导致该日期之后的访问日志未写入 access_logs。本脚本用修复后的
app.access_parser.parse_access_row 重新解析已入库的 logs 行并补写 access_logs。

用法：
    python -m app.backfill_access
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.access_parser import parse_access_row
from app.db import DB_PATH, Database

BATCH = 500


async def backfill() -> int:
    db = Database(str(DB_PATH))
    await db.connect()
    rows = await db._fetchall(
        "SELECT instance, rule_key, rule_name, sub_key, sub_name, raw_json "
        "FROM logs WHERE module='webservice' AND sub_key!=''",
    )
    total = 0
    inserted = 0
    batch: list[dict] = []
    for r in rows:
        total += 1
        try:
            rec = json.loads(r["raw_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        arow = parse_access_row(
            r["instance"], rec,
            rule_key=r.get("rule_key") or "", rule_name=r.get("rule_name") or "",
            sub_key=r.get("sub_key") or "", sub_name=r.get("sub_name") or "",
        )
        if not arow:
            continue
        batch.append(arow)
        if len(batch) >= BATCH:
            inserted += await db.insert_access_logs(batch)
            batch = []
    if batch:
        inserted += await db.insert_access_logs(batch)
    await db.close()
    print(f"backfill scanned={total} access_inserted={inserted}")
    return inserted


if __name__ == "__main__":
    asyncio.run(backfill())
