"""初始化数据库。

用法: python -m app.init_db
"""
from __future__ import annotations

import asyncio

from .config import load_config
from .db import Database


async def main() -> None:
    load_config()  # 确保 config.json 存在
    db = Database()
    await db.connect()
    await db.close()
    print("数据库初始化完成: data/logs.db")


if __name__ == "__main__":
    asyncio.run(main())
