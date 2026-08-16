"""FastAPI 入口 + 生命周期。

用法: python -m uvicorn app.main:app --host 0.0.0.0 --port 8666
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .collector import Collector
from .config import ROOT_DIR, load_config
from .db import Database
from .routes import access, collect, config as config_routes, logs, meta, smb, stream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    db = Database()
    await db.connect()
    collector = Collector(cfg, db)
    app.state.config = cfg
    app.state.db = db
    app.state.collector = collector
    collector.start()
    try:
        yield
    finally:
        await collector.stop()
        await db.close()


app = FastAPI(title="Lucky Log Viewer", lifespan=lifespan)

app.include_router(meta.router)
app.include_router(logs.router)
app.include_router(access.router)
app.include_router(config_routes.router)
app.include_router(collect.router)
app.include_router(smb.router)
app.include_router(stream.router)

_static_dir = ROOT_DIR / "static"
_dist_dir = ROOT_DIR / "static" / "dist"
if _dist_dir.exists():
    app.mount("/", StaticFiles(directory=str(_dist_dir), html=True), name="static")
elif _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
