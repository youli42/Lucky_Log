# Lucky Log Viewer

一个基于浏览器后端的 Lucky-Admin 日志可视化面板。

通过 Lucky 的管理 API 拉取各模块日志，存储到本地 SQLite，并在可交互的 Web 页面中查看、筛选、搜索、去重和导出日志；Web 模块额外提供访问日志的结构化分析与图表展示。

## 状态

> **快速开发阶段** — 任何功能与接口都可能被无预警变更，不保证兼容旧版本。详见 [AGENTS.md](AGENTS.md)。

## 功能概览

- 多 Lucky 实例配置与切换
- 分栏导航：左侧模块分类（总览 / Web / System / Docker / Cron / DDNS / SSL / WebTerminal / Rclone / FileBrowser / WOL 等），进入后查看对应内容
- **总览大屏**：KPI 卡片（日志总量 / 今日新增 / 活跃服务 / Web 访问总数 / 采集状态）+ 模块分布 / 时间趋势 / Web 访问趋势 / 服务分布 / 最近日志实时流
- **Web 访问分析**：访问 IP 排行、设备型号、访问来源类型（设备类型 + Host 分组）、浏览器分布、访问路径、操作系统统计、访问趋势，全部图表化呈现；明细支持筛选 / 原始 JSON 展开 / 导出
- **IP 归属地**：ip2region 离线库，IP 排行附归属地，可按省份分布统计
- 实时模式（WebSocket 推送）与手动模式（手动刷新按钮）
- 按模块 / 服务 / 时间范围 / 关键词过滤；自动去重（时间+内容 / 内容 / 关闭）
- CSV / JSON 导出；SQLite 本地存储，可配置自动清理

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / uvicorn / httpx / aiosqlite |
| 存储 | SQLite（本地单文件） |
| 前端 | **Vue 3 + Vite + Chart.js（构建产物）** |
| IP 归属地 | ip2region（离线 xdb，`data/ip2region.xdb`） |
| UA 解析 | user-agents |

## 目录结构

```
Lucky_Log/
├── app/               # Python 后端包
│   ├── main.py        # FastAPI 入口
│   ├── config.py      # 配置加载
│   ├── lucky_client.py# Lucky API 客户端（鉴权/重试/分页）
│   ├── access_parser.py # Web 访问日志解析（ExtInfo + UA）
│   ├── geoip.py       # ip2region 归属地查询（降级容错）
│   ├── collector.py   # 日志采集器（后台任务）
│   ├── db.py          # SQLite 访问层（logs + access_logs）
│   └── routes/        # API 路由（meta / logs / access / stream）
├── frontend/          # Vue 3 + Vite 前端源码
│   ├── index.html  vite.config.js  package.json
│   └── src/           # 组件 / 视图 / store / api
├── static/            # 后端托管（frontend 构建产物 static/dist）
├── doc/               # 分类文档
├── scripts/           # 开发辅助脚本（smoke_test.py / ws_test.py）
├── config.json        # 运行配置（多实例，含 OpenToken，不入库）
├── requirements.txt
└── data/              # SQLite 数据库 + ip2region.xdb（运行时生成/下载）
```

## 快速开始

```bash
# 1. 安装后端依赖（推荐 uv；也可用 pip）
uv venv --python 3.12
uv pip install -r requirements.txt

# 2. 安装前端依赖并构建（产物输出到 static/dist）
cd frontend
npm install
npm run build
cd ..

# 3. 编辑 config.json（目标实例 / OpenToken / 采集模块）

# 4.（可选）下载 IP 归属地库 data/ip2region.xdb
.venv\Scripts\python.exe -m app.init_db --geoip

# 5. 初始化数据库（自动生成 data/logs.db）
.venv\Scripts\python.exe -m app.init_db

# 6. 启动
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8666

# 7. 打开浏览器
#    http://127.0.0.1:8666
```

### 前端开发模式

```bash
# 终端 A：后端（仅提供 /api 与 /ws）
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8666

# 终端 B：Vite dev server（5173，/api /ws 代理到 8666，热更新）
cd frontend && npm run dev
# 浏览器打开 http://127.0.0.1:5173
```

## 文档

分类文档见 [doc/](doc/)：

| 文档 | 内容 |
|---|---|
| [doc/01-目标与架构.md](doc/01-目标与架构.md) | 项目目标、总体架构、数据流 |
| [doc/02-Lucky-API概览.md](doc/02-Lucky-API概览.md) | Lucky API 有哪些接口、鉴权方式 |
| [doc/03-日志接口详解.md](doc/03-日志接口详解.md) | 各模块日志接口、参数、返回结构 |
| [doc/04-如何探测API.md](doc/04-如何探测API.md) | 从 JS 包静态分析到批量探测的完整方法 |
| [doc/05-日志采集设计.md](doc/05-日志采集设计.md) | 采集器增量策略、游标、去重、access_logs |
| [doc/06-可视化面板功能.md](doc/06-可视化面板功能.md) | 面板布局、交互、实时模式、视图 |
| [doc/07-配置说明.md](doc/07-配置说明.md) | config.json 多实例配置 |
| [doc/08-Web访问分析.md](doc/08-Web访问分析.md) | Web 访问日志解析、统计口径、图表、API |

## 许可

内部研究工具。
