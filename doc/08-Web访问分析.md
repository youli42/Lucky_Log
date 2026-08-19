# 08 - Web 访问分析

## 数据来源

子代理层日志 `/api/webservice/{ruleKey}/{subKey}/logs`，`LogContent` 为内嵌 JSON。
Lucky 存在**两种格式**（解析器向后兼容）：

- 旧版（约 2026-08-16 前）：`ExtInfo` 包裹，大写下划线字段

  ```json
  {"ExtInfo":{"ClientIP":"203.0.113.1","Host":"www.example.com",
    "Method":"GET","URL":"/favicon.ico",
    "UserAgent":"Mozilla/5.0 (Linux; Android 11; V2068A) ... VivoBrowser/30.3.0.0"}}
  ```

- 新版（约 2026-08-16 后）：扁平、小写字段、无 `ExtInfo` 包裹

  ```json
  {"client_ip":"10.10.10.9","host":"10.10.10.2:10002","method":"GET",
   "url":"/api/setup/status","user_agent":"","event":"[10.10.10.2]","level":"info"}
  ```

采集器对每条子代理层日志调用 `access_parser.parse_access_row`：
1. `LogContent` → JSON；优先取 `ExtInfo`，否则按扁平结构解析（字段大小写兼容 `ClientIP`/`client_ip` 等）；缺 `client_ip` 则跳过（非访问日志）。
2. `UserAgent`/`user_agent` 用 `user-agents` 解析 → `browser / os / device / device_type`。
3. `device_type` 分类：`bot / mobile / tablet / desktop / unknown`（含 UA 关键词兜底）。
4. 结构化行写入 `access_logs` 表。

> 格式切换（~2026-08-16）导致切换前的历史访问日志缺失，可用 `python -m app.backfill_access` 从 `logs` 表重新解析回填 `access_logs`。

> 局限：日志无 `Referer` 与状态码，因此「访问来源类型」按**设备类型 + Host 域名**分组，而非搜索引擎/外链来源。

## 表结构（access_logs）

| 字段 | 说明 |
|---|---|
| instance / rule_key / rule_name / sub_key / sub_name | 实例与归属服务 |
| host | 访问域名（如 www.example.com） |
| ts_epoch / ts_text | 访问时间 |
| client_ip | 访问 IP |
| method / path | 请求方法 / 路径 |
| ua | 原始 UserAgent |
| browser / os / device / device_type | UA 解析结果 |

去重：唯一索引 `(instance, sub_key, ts_text, client_ip, method, path)`。

## IP 归属地

`app/geoip.py` 封装 ip2region（离线 xdb，`data/ip2region.xdb`，`init_db --geoip` 下载）：

- 懒加载 + 整库缓存（`new_with_buffer`，并发安全）。
- 结果 `中国|广东省|广州市|电信` → `{country, province, city, isp}`。
- 私有/保留地址 → `内网/保留`；缺库/查询失败 → `未知`（整体功能降级不报错）。
- 展示简写 `geo_short(ip)`：`省·市`（国外显国家），如 `广东·广州` / `澳大利亚`。

## IP 流量 / 连接（accessdetail → ip_traffic）

- 数据源：`/api/webservice/{ruleKey}/{subKey}/accessdetail`（实时快照，`Connections / TrafficIn / TrafficOut / LastAccess`）。
- 采集器 30s 节流 UPSERT 入 `ip_traffic`（PK: instance, sub_key, client_ip）；详见 doc/05。
- 展示：IP 排行/明细/详情抽屉附 `connections / traffic_in / traffic_out / last_access`；新增 KPI「总流量 / 连接总数」。
- 前端标注"实时快照，30s 刷新"；数据未到显示 `—`。

## 查询时富化（不改 access_logs 表）

| 字段 | 来源 |
|---|---|
| country / province / city / isp | `geoip.query(ip)` |
| geo_short | 省·市 / 国家 简写 |
| browser_version / os_version | `user_agents`：`browser.version_string` / `os.version_string` |
| device_brand / device_model | `user_agents`：`device.brand` / `device.model` |
| connections / traffic_in / traffic_out / last_access | LEFT JOIN `ip_traffic` |

> 明细每页 100 行 ≈ geoip + UA 解析各 100 次（内存缓存），<30ms。

## 统计口径（/api/access/stats）

| 返回项 | 口径 |
|---|---|
| total / unique_ips / unique_paths | 满足筛选的访问总数 / 独立 IP / 独立路径 |
| traffic | 流量快照合计 `{connections, traffic_in, traffic_out}`（来自 ip_traffic，非时间筛选） |
| timeline | 按 hour/day 桶聚合（`(ts_epoch/step)*step`） |
| top_ips | 访问次数 Top15，附完整归属地 + 流量/连接；用 Top300 IP 聚合出 region_dist 地区分布 |
| top_paths / browsers / os / devices / device_types / methods / hosts | 对应字段分组计数 |

筛选参数：`instance / rule / sub / host / from_epoch / to_epoch / search`。

## 全部历史 IP（/api/access/ips）

- 按 `client_ip` 去重的**全量** IP 分页列表（默认每页 50），`ORDER BY count DESC`。
- 每项附：访问次数、归属地（country/province/city/isp/geo_short）、连接/流量快照、最后访问。
- 支持 `search` 按 IP 前缀/包含筛选；前端点击某 IP 行可直接跳到「访问明细」按该 IP 过滤。
- 用途：IP 排行图表仅展示 Top15（可读性），全部历史 IP 在此完整查看。

## API 清单

- `GET /api/access/stats` — 聚合统计（含地区分布、流量快照合计）。
- `GET /api/access/logs` — 明细分页（每行附完整归属地 + UA 版本 + 流量）。
- `GET /api/access/ips` — 全部历史 IP 分页列表。
- `GET /api/access/export?format=csv|json` — 全字段导出（含归属地 4 项、UA 版本、流量 4 项）。

## 前端图表映射

| 需求 | 图表 | 数据 |
|---|---|---|
| 访问 IP | 横向条形 Top | top_ips（IP + 归属地 + 流量） |
| 设备型号 | 柱状 | devices |
| 访问来源类型 | 环形（设备）+ 柱状（域名） | device_types / hosts |
| 浏览器分布 | 环形 | browsers |
| 访问路径 | 横向条形 Top | top_paths |
| 访问 IP 排行 | 条形 + 明细表 | top_ips / ip_traffic |
| 操作系统统计 | 环形 | os |
| 访问趋势 | 折线 | timeline |
| 地区分布 | 环形 | region_dist |

## 明细完整信息展示

- 默认精简列：时间 | 归属地(省·市) | IP | 方法 | 路径 | 客户端(浏览器·OS)。
- IP 悬停 Tooltip：完整归属地（国家/省/市/ISP）+ 连接数/流量入出/最后访问。
- 行点击右侧详情抽屉：请求 / 访问者（含流量）/ 客户端（浏览器与 OS 版本、设备品牌型号、原始 UA）。
- ⚙ 列显隐配置（localStorage）：22 个可开关列。
- 连接/流量为 accessdetail 快照（连接稳定时基本不变，非每秒实时计数）；访问分析页每 30s 自动刷新并在筛选区标注「更新于 HH:mm:ss」。
