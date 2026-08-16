# 04 - 如何探测 Lucky API

> 记录完整方法：从前端 JS 静态分析到批量实测。可复用于新版本或未知 Lucky 部署。

## 0. 前置

- 知道入口路径（如 `/youlilucky/`）与 OpenToken
- 工具：curl、Node.js、文本分析（正则提取）

## 1. 确认入口与指纹

```bash
# 探测入口页
curl -k -i https://192.168.1.100:16601/youlilucky/
# → 200, HTML: <title>Lucky</title>, src=./static/js/lucky_index-*.js

# 确认版本与登录态校验
curl -k https://192.168.1.100:16601/youlilucky/version
curl -k https://192.168.1.100:16601/youlilucky/api/status          # 无 token → {"msg":"login invalid","ret":-1}
curl -k https://192.168.1.100:16601/youlilucky/api/status -H "OpenToken: TOKEN"  # 成功
```

## 2. 静态分析前端 JS（发现接口全貌）

SPA 是分包懒加载，接口调用分散在入口 bundle 与各 chunk。

```powershell
# 下载入口 bundle
curl.exe -k -s https://host:port/youlilucky/static/js/lucky_index-*.js -o lucky_index.js

# 从入口 bundle 提取所有 chunk 文件名
# 正则: lucky_[a-zA-Z0-9_\-]+\.js
# 示例输出: lucky_reverseproxy-C4ng2key.js lucky_docker-CW7FS-e2.js ...

# 批量下载所有 chunk 到 chunks/
curl.exe -k -s https://host:port/youlilucky/static/js/<chunk>.js -o chunks/<chunk>.js

# 提取 API 调用 (方法, URL)
# 正则1 (url在前): url:"(/api/[^"]+)"[^}]{0,60}?method:"([a-z]+)"
# 正则2 (method在前): method:"([a-z]+)"[^}]{0,60}?url:"(/api/[^"]+)"
# 结果示例: "GET" "/api/webservice/logs"
```

### 动态路径识别

接口中有大量动态段，需从调用上下文推断：

```js
// /api/webservice/"+e+"/httpserver/logs   → e = ruleKey
// /api/webterminal/sftp/"+e+"/list        → e = 连接 id
// /api/webservice/"+e+"/"+t+"/logs        → e = ruleKey, t = subKey 或 "httpserver"
```

### WebSocket 端点识别

```js
// 正则: .{300}new WebSocket.{220}  （取上下文）
// 提取: wss://host:port/base/api/status/ws?Lucky-Admin-Token=...
//       /api/webterminal/connect/{key}
//       /api/docker/containers/{cid}/exec
//       /api/webterminal/sftp/{id}/search
```

## 3. 批量实测验证

用 Node 脚本批量 GET 探测，判定命中：`HTTP != 404` 或 `404 但 body 非 "not found"`。

要点：
- `NODE_TLS_REJECT_UNAUTHORIZED=0`（自签名）
- 目标并发有限 → `threads` 调低（2-4）、失败自动重试（retry 2-3）
- 大响应截断读取，避免 `req.destroy()` 造成进程提前退出

参考实现：`lucky_probe.js`（本项目早期产物，可作探测工具参考）。

## 4. 方法探测

对命中路径用 GET/POST/PUT/DELETE 各试一次，观察响应差异：
- `404 Request URL [PUT][...] not found` → 方法不支持
- `400 请求解析出错` → 方法支持但缺 body（PUT/POST 类）
- `200` → 支持

## 5. Fuzz 补全

用词根字典（模块名 + 子资源）拼接探测未在 JS 中显式出现的接口：

```
模块词根: login logout status info docker webterminal webservice ddns ssl cron wol ...
子资源: /list /logs /configure /enable /status /setting /flush /test /check ...
组合: /api/<词根> 与 /api/<词根><子资源>
```

## 6. 结果整理

按模块分类输出清单：
- 鉴权方式（三种）是否可用
- 接口方法 / 路径 / 动态段含义
- 返回结构示例
- 日志接口特殊标注（分页、时间过滤缺失、特殊结构）

## 7. 工具复用清单

| 工具 | 用途 |
|---|---|
| lucky_probe.js | 批量探测 + Fuzz + 多方法 |
| lucky_wslogs.js | WebService 服务日志获取（含时间过滤/去重） |
| wordlist_lucky.txt | Fuzz 词根字典 |

> 本项目 `doc/02-Lucky-API概览.md` 与 `doc/03-日志接口详解.md` 是已完成的探测成果。
