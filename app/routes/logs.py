"""日志查询 / 导出 API。"""
from __future__ import annotations

import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..db import Database

router = APIRouter(prefix="/api", tags=["logs"])


def _get_db(request: Request) -> Database:
    return request.app.state.db


@router.get("/logs")
async def query_logs(
    request: Request,
    instance: Optional[str] = None,
    module: Optional[str] = None,
    service: Optional[str] = None,
    from_epoch: Optional[int] = None,
    to_epoch: Optional[int] = None,
    search: Optional[str] = None,
    dedup: str = "time_content",
    page: int = 1,
    page_size: int = 200,
):
    db = _get_db(request)
    return await db.query_logs(
        instance=instance,
        module=module,
        rule_key=service,
        from_epoch=from_epoch,
        to_epoch=to_epoch,
        search=search,
        dedup=dedup,
        page=page,
        page_size=page_size,
    )


@router.get("/export")
async def export_logs(
    request: Request,
    instance: Optional[str] = None,
    module: Optional[str] = None,
    from_epoch: Optional[int] = None,
    to_epoch: Optional[int] = None,
    search: Optional[str] = None,
    dedup: str = "time_content",
    format: str = "csv",
    limit: int = 100000,
):
    db = _get_db(request)
    if format == "json":
        rows = [
            {
                "time": r["ts_text"], "module": r["module"],
                "rule_name": r["rule_name"], "sub_name": r["sub_name"],
                "content": r["content"],
            }
            async for r in db.export_rows(
                instance, module, from_epoch, to_epoch, search, dedup, limit
            )
        ]
        return JSONResponse({"items": rows})

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["time", "module", "rule_name", "sub_name", "content"])
    async for r in db.export_rows(
        instance, module, from_epoch, to_epoch, search, dedup, limit
    ):
        writer.writerow(
            [r["ts_text"], r["module"], r["rule_name"], r["sub_name"], r["content"]]
        )
    data = buf.getvalue()
    # UTF-8 BOM，Excel 兼容
    payload = "\ufeff" + data
    filename = f"lucky_logs_{int(__import__('time').time())}.csv"
    return StreamingResponse(
        iter([payload.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
