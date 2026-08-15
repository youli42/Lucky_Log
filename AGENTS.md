# AGENTS.md

## 项目状态：快速开发阶段（Rapid Prototype）

本项目当前处于**快速开发/原型阶段**。规则如下：

- **破坏性更新可接受**：任何代码、数据结构、API、配置格式都可能被无预警重构。
- **无需兼容旧版本**：不维护旧版兼容层，不保证跨版本迁移。
- **提交自由**：鼓励频繁提交、激进重构、随时推倒重来。
- **文档优先**：每次较大的设计决策需同步更新 `doc/` 下的文档。

## 技术栈

- 后端：Python 3.10+，FastAPI + uvicorn + httpx + aiosqlite
- 存储：SQLite（本地单文件）
- 前端：Vue 3 + Vite + Chart.js（构建产物由后端托管）
- 辅助：user-agents（UA 解析）、ip2region（离线 IP 归属地，`data/ip2region.xdb`）

## 常用命令

```bash
# 启动后端（开发模式，自动重载）
python -m uvicorn app.main:app --reload --port 8666

# 前端开发（Vite dev server，5173，/api /ws 代理到 8666）
cd frontend && npm run dev

# 前端构建（产物输出到 static/dist）
cd frontend && npm run build

# 初始化数据库（--geoip 时同时下载 ip2region.xdb）
python -m app.init_db

# 测试（后端）
python -m pytest tests/ -v
```

## 目录结构

```
Lucky_Log/
├── app/               # Python 后端包
│   ├── main.py        # FastAPI 入口
│   ├── config.py      # 配置加载
│   ├── lucky_client.py# Lucky API 客户端（鉴权/重试/分页）
│   ├── access_parser.py # Web 访问日志解析（ExtInfo + UA → browser/os/device）
│   ├── geoip.py       # ip2region 归属地查询（懒加载，缺库/失败降级）
│   ├── collector.py   # 日志采集器（后台任务）
│   ├── db.py          # SQLite 访问层（logs + access_logs）
│   └── routes/        # API 路由（meta / logs / access / stream）
├── frontend/          # Vue 3 + Vite 前端源码
│   ├── index.html  vite.config.js  package.json
│   └── src/           # 组件 / 视图 / store / api
├── static/            # 后端托管前端构建产物（static/dist）
├── doc/               # 分类文档
├── scripts/           # 开发辅助脚本
├── config.json        # 运行配置（多实例，含 OpenToken，不入库）
├── requirements.txt
└── data/              # SQLite 数据库 + ip2region.xdb（运行时生成/下载）
```

## 目标实例（开发期默认）

- `https://10.10.10.11:16601/youlilucky/api`
- OpenToken: 见 `config.json`（或用户配置）

## 注意事项

- Lucky API 使用自签名证书：httpx 需 `verify=False`，并抑制告警。
- Lucky API 无服务端时间过滤：日志增量需客户端游标管理。
- 目标对高并发有限制：采集需节流 + 重试。
- Web 访问日志在**子代理层**（`/api/webservice/{ruleKey}/{subKey}/logs`），`LogContent` 为内嵌 JSON（`ExtInfo`）；规则层为运行日志（如 TLS 错误）。
