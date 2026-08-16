# Lucky Log Viewer

> ⚠️ **玩具级项目警告 · 安全性自负**
>
> 这是一个**玩具级 / 个人研究工具**，**没有任何鉴权与权限控制**：
> - 默认只绑定 `127.0.0.1`（本机访问），请勿随意改绑 `0.0.0.0` 或对外暴露；
> - 一旦对外开放（局域网反代、frp、公网等），任何能访问到端口的人都能读取你配置里的 **OpenToken**、**启停/重启/暂停 Docker 容器**、**断开 SMB 连接**、**删除实例与数据**；
> - 请自行负责自己的安全：内网隔离、防火墙、反向代理加认证、定期轮换 Token 等，本项目不提供任何防护。

一个基于浏览器后端的 Lucky-Admin 日志可视化面板。

通过 Lucky 的管理 API 拉取各模块日志，存储到本地 SQLite，并在可交互的 Web 页面中查看、筛选、搜索、去重和导出日志；Web 模块额外提供访问日志的结构化分析与图表展示。

## 状态

> **快速开发阶段** — 任何功能与接口都可能被无预警变更，不保证兼容旧版本。详见 [AGENTS.md](AGENTS.md)。

## 功能概览

- 多 Lucky 实例配置与切换
- 分栏导航：左侧模块分类（总览 / Web / System / Docker / Cron / DDNS / SSL / WebTerminal / Rclone / FileBrowser / WOL 等），进入后查看对应内容
- **总览大屏**：KPI 卡片（日志总量 / 今日新增 / 活跃服务 / Web 访问总数 / 采集状态）+ 模块分布 / 时间趋势 / Web 访问趋势 / 服务分布 / 最近日志实时流
- **Web 访问分析**：访问 IP 排行、设备型号、访问来源类型（设备类型 + Host 分组）、浏览器分布、访问路径、操作系统统计、访问趋势，全部图表化呈现；明细支持筛选 / 原始 JSON 展开 / 导出
- **完整信息展示（不臃肿）**：表格精简列 + IP 悬停 Tooltip（完整归属地）+ 行点击右侧详情抽屉（国家/省/市/ISP、浏览器与 OS 版本、设备品牌型号、原始 UA）+ ⚙ 列显隐配置（localStorage 持久化）
- **全部历史 IP**：访问分析页按 IP 去重的全量分页列表（不限于 Top15），支持 IP 筛选，点击行直达该 IP 明细
- **IP 归属地**：ip2region 离线库，国家/省/市/ISP 完整字段，可按省份分布统计
- **IP 流量 / 连接统计**：采集 accessdetail 快照（Connections / TrafficIn / TrafficOut / LastAccess），连接/流量 KPI 每 30s 自动刷新并标注更新时间
- **Web 设置界面**：侧边栏「设置」可配置多实例（Lucky 地址 / OpenToken / 协议 / 采集模块）、测试连接、**手动采集（单实例/全部）与采集进度**（当前源/页数/已采条数，自动轮询）、**本地数据占用**（DB 大小/各表行数/每实例数据量）、全局设置（采集间隔 / 自动清理 / **失败指数退避 base·max·max_retries**），保存后采集器热生效且**多实例并发采集（HTTP 并发≤2）**；采集失败自动指数退避防风控，设置页显示「退避中」状态
- 实时模式（WebSocket 推送）与手动模式（手动刷新按钮）
- 按模块 / 服务 / 时间范围 / 关键词过滤；自动去重（时间+内容 / 内容 / 关闭）
- **表格优化**：表头点击全量排序（后端 sort 参数，跨页一致）+ 每页条数可配置（16~2048 / 全部显示）+ 无内部滚动条
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
│   ├── collector.py   # 日志采集器（后台任务，含 accessdetail 流量采集）
│   ├── db.py          # SQLite 访问层（logs + access_logs + ip_traffic）
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

# 2. 安装前端依赖并构建（产物输出到 static/dist，由后端托管）
cd frontend
npm install
npm run build
cd ..

# 3. 编辑 config.json（目标实例 / OpenToken / 采集模块）

# 4. 初始化数据库 + 下载 IP 归属地库（生成 data/logs.db + data/ip2region.xdb）
.venv\Scripts\python.exe -m app.init_db --geoip

# 5. 启动（默认仅本机访问；如需局域网访问自行改 config.json 的 web.host 并自负安全责任）
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8666

# 6. 打开浏览器
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
| [doc/09-使用指南.md](doc/09-使用指南.md) | 从安装配置到界面操作、常见问题排查的完整指南 |
| [doc/10-项目评审与改进建议.md](doc/10-项目评审与改进建议.md) | 初始化评审、问题清单、修复记录 |

## 时间戳约定（以 Lucky 为准）

Lucky 日志时间格式固定为 `YYYY/MM/DD HH:mm:ss`（无时区信息）。本项目**以 Lucky 端时间为准**：

- 按运行机器本地时区解析为 epoch 秒存储（内网部署默认采集机与 Lucky 同时区，解析结果即 Lucky 端时间）；
- epoch 仅用于排序 / 筛选 / 统计分组；展示一律使用原始时间字符串或按浏览器本地时区格式化；
- 若采集机与 Lucky 异时区，请保证两机时区一致（解析统一在 `app/timeutil.py::parse_lucky_ts`）。

## 如何新增一个采集模块

模块清单统一维护，新增一个模块只需三步（其余由代码自动接入）：

1. **后端** `app/collector.py` 的 `SINGLE_SOURCES` 加一行：`"模块名": "/api/模块名/logs"`（无日志端点的模块勿加，如 portforward/stun）；
2. **后端** `app/config.py` 的 `ALL_MODULES` 列表补上模块名（设置页/默认配置可见）；
3. **前端** `frontend/src/modules.js` 的 `MODULE_LABELS` 补一行中文/英文标签（侧边栏与设置页自动显示）。

## 许可

内部研究工具。
