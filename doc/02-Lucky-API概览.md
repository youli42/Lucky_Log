# 02 - Lucky-Admin API 概览

> 目标版本：Lucky-Admin 2.26.2（wanji）。所有接口均为实测验证。

## 基础信息

| 项目 | 值 |
|---|---|
| 前端入口 | `https://{host}:{port}/{base}/`（如 `/youlilucky/`） |
| API 基础路径 | `https://{host}:{port}/{base}/api/` |
| 返回格式 | JSON，`{"ret":0}` 成功；`ret=1` 参数错误；`ret=2` 资源不存在；`ret=-1` 未登录 |
| 未认证响应 | `{"msg":"login invalid","ret":-1}` |
| 未知路径响应 | `Are you ok? Request URL [GET][/path] not found`（HTTP 404） |
| 协议 | HTTPS（自签名证书）+ HTTP 均可用 |

## 鉴权（三种方式等价）

OpenToken 可直接替代登录，获得管理员全权限。

```bash
# ① Header
curl -k https://192.168.1.100:16601/youlilucky/api/status -H "OpenToken: TOKEN"

# ② URL 参数
curl -k "https://192.168.1.100:16601/youlilucky/api/status?openToken=TOKEN"

# ③ WebSocket 参数
wss://host:port/youlilucky/api/status/ws?Lucky-Admin-Token=TOKEN
```

> Token 在 `GET /api/baseconfigure` 响应的 `OpenToken` 字段中，后端开关 `EnableOpenToken`。

## 接口总览（按模块）

### 系统 / 鉴权
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/status` | 系统状态（CPU/内存/流量/uptime） |
| GET | `/api/info` | 版本/模块/构建信息 |
| GET | `/api/modules/list` | 已启用模块列表 |
| GET | `/api/netinterfaces` | 网卡信息 |
| GET | `/api/logs` | 系统运行日志（结构特殊，见 03） |
| GET/PUT | `/api/baseconfigure` | 基础配置读写 |
| POST | `/api/login` | 账号密码登录 |
| PUT | `/api/logout` | 登出 |
| GET | `/api/oauth/status` / `userinfo` | OAuth 状态 |
| GET | `/api/twofapassword` | 2FA 状态 |
| GET | `/api/reboot_program` | 重启程序 |
| GET | `/api/update/cancel` / PUT `comfire` | 更新控制 |
| GET | `/version` | 版本号 |
| GET | `/LoginPageConfig` | 登录页配置 |

### WebService（反向代理，日志重点）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/webservice/rules` | 规则（服务）列表/保存 |
| GET | `/api/webservice/rules_lite` | **服务树（规则→子代理）** |
| GET | `/api/webservice/logs` | 全部服务汇总日志 |
| GET | `/api/webservice/lastlogs` | 最近日志 |
| GET | `/api/webservice/{ruleKey}/httpserver/logs` | **指定服务运行日志** |
| GET | `/api/webservice/{ruleKey}/{subKey}/logs` | 子代理层日志 |
| GET | `/api/webservice/{ruleKey}/{subKey}/lastlogs` | 子代理最近日志 |
| GET | `/api/webservice/{ruleKey}/{subKey}/accessdetail` | 访问明细统计 |
| GET | `/api/webservice/groups` | 分组 |

### Docker
`/api/docker/`：`info` `containers` `images` `volumes` `networks` `logs` `version` `config` `tasks` `self-container` `container-groups` `registry/mirrors`，Compose 子模块 `compose/*`。

### 网络服务
| 模块 | 关键接口 |
|---|---|
| DDNS | `/api/ddns` `/api/ddns/configure` `/api/ddns/logs` `/api/ddnstasklist` `/api/ddns/webhooktest` |
| SSL | `/api/ssl` `/api/ssl/setting` `/api/ssl/logs` `/api/ssl/flush` |
| 端口转发 | `/api/portforwards` `/api/portforward/configure` |
| FRP | `/api/frp/list` `/api/frp/logs` |
| STUN | `/api/stunrulelist` `/api/stun/configure` |
| Cloudflared | `/api/cloudflared/list` `/api/cloudflared/logs` |
| WOL | `/api/wol/devices` `/api/wol/logs` `/api/wol/service/configure` |

### 存储 / 文件
| 模块 | 关键接口 |
|---|---|
| Rclone | `/api/rclone/remotelist` `/api/rclone/globalconfig` `/api/rclone/logs` |
| 网盘 OAuth | `/api/rclone/third/{115pan,alipan,baidupan}/*` |
| 存储管理 | `/api/storagemanagement/list` `/api/storagemanagement/logs` |
| FileBrowser | `/api/third/filebrowser/configure` `/api/third/filebrowser/logs` `/api/third/filebrowser/resetadmin` |
| WebDAV | `/api/webdav/configure` `/api/webdav/status` `/api/webdav/logs` |
| FTP | `/api/ftpserver/configure` `/api/ftpserver/logs` |
| DLNA | `/api/dlnaservice/configure` `/api/dlnaservice/logs` |

### 安全 / 控制
| 模块 | 关键接口 |
|---|---|
| IP 过滤 | `/api/ipfliter/list` `/api/ipfliter/listlite` `/api/ipfliter/logs` |
| IP 库 | `/api/ipdb/items` `/api/ipdb/query` `/api/ipdb/logs` |
| Coraza WAF | `/api/coraza/list` `/api/coraza/logs` |
| 三方认证 | `/api/thirdPartyAuthManager/list` `/api/thirdPartyAuthManager/logs` |

### WebTerminal
`/api/webterminal/`：`connections` `sessions` `shells` `security` `logs` `globalshortcuts` `splitlayout`，SFTP 子路径 `/api/webterminal/sftp/{id}/list|read|write|remove|upload|...`。

### 定时任务
`/api/cron/`：`list` `groups` `logs` `dojobs` `expressioncheck`。

### WebSocket（实时）
| 端点 | 用途 |
|---|---|
| `/api/status/ws` | 系统状态实时推送 |
| `/api/natdetect/ws` | NAT 检测 |
| `/api/webterminal/connect/{key}` | 终端连接 |
| `/api/webterminal/attach/{session}` | 附加会话 |
| `/api/webterminal/sftp/{id}/search` | SFTP 搜索 |
| `/api/docker/containers/{cid}/exec` | 容器内终端 |
| `/api/docker/images/upgrade-check-ws` | 镜像升级检测 |

## 服务树（rules_lite）结构示例

```json
{"list": [
  {"Key": "RULE_KEY_A", "Name": "443",
   "SubRuleList": [
     {"Key": "SUB_KEY_A1", "Name": "白板"},
     {"Key": "SUB_KEY_A2", "Name": "gitea"}
   ]},
  {"Key": "RULE_KEY_B", "Name": "Sync", "SubRuleList": [...]}
]}
```

> 日志可视化中用此结构做「规则 → 子代理」导航与筛选。

## 常用元接口响应

```bash
# 版本
GET /version  → {"buildTime":"2026-01-21 08:06:28","ret":0,"version":"2.26.2"}

# 模块列表
GET /api/modules/list → {"Modules":["thirdPartyAuthManager","ssl","rclone",...],"baseURL":"/yo..."}

# 服务列表（全量，含端口/协议/状态）
GET /api/webservice/rules → {"ret":0,"ruleList":[{RuleKey,RuleName,Network,ListenPort,EnableTLS,Enable,...}]}
```

## 关键约束（对日志可视化重要）

1. **无服务端时间过滤**：所有日志接口仅支持 `page`/`pageSize` 分页，时间过滤必须在客户端/本地做。
2. **分页倒序**：`page=1` 为最新，`total` 为总数；翻页到 `total` 即取完。
3. **并发限制**：目标对高并发有连接重置/超时，需节流 + 自动重试。
4. **自签名证书**：必须 `verify=False`。
