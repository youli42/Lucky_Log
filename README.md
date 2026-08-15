# Lucky Log Viewer

一个基于浏览器后端的 Lucky-Admin 日志可视化面板。

通过 Lucky 的管理 API 拉取各模块日志，存储到本地 SQLite，并在可交互的 Web 页面中查看、筛选、搜索、去重和导出日志。

## 状态

> **快速开发阶段** — 任何功能与接口都可能被无预警变更，不保证兼容旧版本。详见 [AGENTS.md](AGENTS.md)。

## 功能概览

- 多 Lucky 实例配置与切换
- 全模块日志采集：WebService / 系统 / Docker / Cron / DDNS / SSL / WebTerminal / Rclone / FileBrowser / WOL 等
- 实时模式（自动刷新 / WebSocket 推送）与手动模式（手动刷新按钮）
- 按模块 / 服务 / 时间范围 / 关键词过滤
- 自动去重（按 时间+内容 或 内容）
- 图表可视化（模块分布 / 时间趋势 / 服务分布）
- CSV / JSON 导出
- SQLite 本地存储，可配置自动清理

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 编辑 config.json（目标实例 / OpenToken / 采集模块）

# 3. 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8666

# 4. 打开浏览器
#    http://127.0.0.1:8666
```

## 文档

分类文档见 [doc/](doc/)：

| 文档 | 内容 |
|---|---|
| [doc/01-目标与架构.md](doc/01-目标与架构.md) | 项目目标、总体架构、数据流 |
| [doc/02-Lucky-API概览.md](doc/02-Lucky-API概览.md) | Lucky API 有哪些接口、鉴权方式 |
| [doc/03-日志接口详解.md](doc/03-日志接口详解.md) | 各模块日志接口、参数、返回结构 |
| [doc/04-如何探测API.md](doc/04-如何探测API.md) | 从 JS 包静态分析到批量探测的完整方法 |
| [doc/05-日志采集设计.md](doc/05-日志采集设计.md) | 采集器增量策略、游标、去重 |
| [doc/06-可视化面板功能.md](doc/06-可视化面板功能.md) | 面板功能、交互、实时模式 |
| [doc/07-配置说明.md](doc/07-配置说明.md) | config.json 多实例配置 |

## 许可

内部研究工具。
