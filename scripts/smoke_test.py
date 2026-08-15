import asyncio
import json

from app.collector import Collector
from app.config import load_config
from app.db import Database


async def main():
    cfg = load_config()
    db = Database()
    await db.connect()
    c = Collector(cfg, db)
    await c._collect_once()
    print("status:", json.dumps(c.status, ensure_ascii=False, indent=2))
    total = await db.instance_stats(cfg.instances[0].name)
    print("total:", total)
    mods = await db.module_counts(cfg.instances[0].name)
    print("modules:", json.dumps(mods, ensure_ascii=False))
    res = await db.query_logs(instance=cfg.instances[0].name, page=1, page_size=5)
    print("sample items:", json.dumps(res["items"][:2], ensure_ascii=False, indent=2))
    tree = c.service_tree(cfg.instances[0].name)
    print("service tree:", json.dumps(tree, ensure_ascii=False))
    await db.close()
    await c.stop()


asyncio.run(main())
