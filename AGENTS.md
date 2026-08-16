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
python -m app.init_db --geoip

# 测试（后端）
python -m pytest tests/ -v
```

> **前端构建产物已入库**：`static/dist`（`npm run build` 输出）由后端直接托管并被 git 跟踪。改动 `frontend/src` 后需 `cd frontend && npm run build` 并连同 `static/dist` 一起提交，否则生产页面不会更新。

## 目录结构

```
Lucky_Log/
├── app/               # Python 后端包
│   ├── main.py        # FastAPI 入口
│   ├── config.py      # 配置加载
│   ├── lucky_client.py# Lucky API 客户端（鉴权/重试/分页）
│   ├── access_parser.py # Web 访问日志解析（ExtInfo + UA → browser/os/device）
│   ├── geoip.py       # ip2region 归属地查询（懒加载，缺库/失败降级）
│   ├── collector.py   # 日志采集器（后台任务，含 accessdetail 流量采集）
│   ├── db.py          # SQLite 访问层（logs + access_logs + ip_traffic）
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

## 前端侧边栏约定

- **已配置专用面板的视图放顶部固定区**（分隔线上方，独立入口）：`总览大屏 /overview`、`Web 访问分析 /access`、`Docker 面板 /docker`、`SMB 状态 /smb`。
- **通用模块日志**（无专用面板）放分隔线下方的模块列表，指向 `/module/{module}`。
- 一个模块**只能出现在一个位置**：有专用面板的，从 `Sidebar.vue` 的 `MODULES` 列表移除（避免重复），并在面板内提供「模块日志」跳转链接（如 Docker 面板 → `/module/docker`、SMB → `/module/smb`）。
- 新增专用面板时遵循同一约定：顶部固定入口 + 从模块列表移除 + 面板内补日志链接。
- 模块清单统一维护在 `frontend/src/modules.js`（`MODULE_LABELS` + `DEDICATED_PANEL_MODULES`），Sidebar 与设置页共用；新增模块勿在视图内另建清单。

## 自动刷新与通知约定（所有模块必须遵守）

- **定时自动刷新一律静默**：不切换 loading 遮罩、不重建组件，仅替换数据（`ChartBox.vue` 已按 props 响应式平滑 `chart.update()`，无闪烁）。
- 自动刷新**仅在有意义的变化时**通过全局通知 `notify()`（`frontend/src/notify.js`）弹右上角提示（ToastHost 渲染），并**必须带 `key` + `minInterval` 限频**（如 30s），禁止逐次刷新都弹窗。
- 刷新失败用 `notify({ type: 'error', ... })`；手动刷新 / 切换实例等用户主动操作的反馈用 `useDataRefresh(reload, { notifyMessage, notifyKey, notifyMinInterval })`。
- 禁止自造弹窗 / `alert` / 其他全局提示；新视图接入自动刷新或实时数据时必须遵守本约定。
- 实时数据接口（如 `GET /api/access/connections`）由后端节流（`Collector.live_allowed`，10s 冷却），前端遇 429 时展示冷却提示，不要绕过重试。

## 目标实例（开发期默认）

- `https://192.168.1.100:16601/youlilucky/api`
- OpenToken: 见 `config.json`（或用户配置）

## 注意事项

- Lucky API 使用自签名证书：httpx 需 `verify=False`，并抑制告警。
- Lucky API 无服务端时间过滤：日志增量需客户端游标管理。
- 目标对高并发有限制：采集需节流 + 重试；失败进入实例级指数退避（`backoff.base/max/max_retries`），防风控。
- Web 访问日志在**子代理层**（`/api/webservice/{ruleKey}/{subKey}/logs`），`LogContent` 为内嵌 JSON（`ExtInfo`，含 ClientIP/Host/Method/URL/UserAgent）；规则层为运行日志（如 TLS 错误）。子代理层日志采集后解析入 `access_logs` 表，用于 Web 访问分析（IP/浏览器/OS/设备/路径/归属地）。
- IP 流量/连接统计来自 `accessdetail` 端点（实时快照：Connections/TrafficIn/TrafficOut/LastAccess），采集器 30s 节流 UPSERT 入 `ip_traffic` 表；与 `access_logs` 的逐请求计数互补，非历史数据。
- 完整归属地（国家/省/市/ISP）与完整 UA 信息（浏览器/OS/设备 family+version+brand+model）在**查询时富化**（geoip + user-agents），不改 `access_logs` 表结构。
