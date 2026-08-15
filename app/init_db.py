"""初始化数据库。

用法:
  python -m app.init_db            # 建表
  python -m app.init_db --geoip    # 同时下载 ip2region.xdb
"""
from __future__ import annotations

import asyncio
import sys

from .config import load_config
from .db import Database
from .geoip import XDB_PATH


def download_xdb() -> None:
    import urllib.request

    if XDB_PATH.exists():
        print(f"ip2region 已存在: {XDB_PATH}")
        return
    url = "https://raw.githubusercontent.com/lionsoul2014/ip2region/master/data/ip2region_v4.xdb"
    print(f"下载 ip2region 数据: {url}")
    XDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(XDB_PATH))
    print(f"下载完成: {XDB_PATH}")


async def main() -> None:
    load_config()  # 确保 config.json 存在
    db = Database()
    await db.connect()
    await db.close()
    print("数据库初始化完成: data/logs.db")
    if "--geoip" in sys.argv:
        download_xdb()


if __name__ == "__main__":
    asyncio.run(main())
