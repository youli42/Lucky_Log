<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { api, fmtEpoch, qp } from '../api'
import { refreshInstances, store } from '../store'
import { MODULE_LABELS } from '../modules'
import { fmtBytes } from '../utils'

const cfg = ref(null)
const allModules = ref([])
const instStats = ref([])
const storage = ref(null)
const editing = ref(null)
const isNew = ref(false)
const testing = ref(false)
const testResult = ref(null)
const confirmDel = ref(null)
const purgeDel = ref(false)
const saved = ref(false)
const err = ref('')
let savedTimer = null
let pollTimer = null
let storageTimer = null

async function load() {
  const [c, inst] = await Promise.all([
    api('/api/config'),
    api('/api/instances'),
  ])
  cfg.value = c.config
  allModules.value = c.modules || []
  instStats.value = inst.instances || []
  await loadStorage()
}

async function loadStorage() {
  try {
    storage.value = await api('/api/storage')
  } catch { /* ignore */ }
}

function statusFor(name) {
  return instStats.value.find((i) => i.name === name) || {}
}

function isBackoff(name) {
  const st = statusFor(name)
  return !st.collecting && st.backoff_until > Math.floor(Date.now() / 1000)
}

function isPaused(name) {
  return statusFor(name).paused
}

async function collectInstance(name) {
  try {
    await api(`/api/collect?instance=${encodeURIComponent(name)}`, { method: 'POST' })
    await poll()
  } catch (e) {
    err.value = `采集触发失败: ${e.message}`
  }
}

async function collectAllInst() {
  try {
    await api('/api/collect/all', { method: 'POST' })
    await poll()
  } catch (e) {
    err.value = `采集触发失败: ${e.message}`
  }
}

async function poll() {
  try {
    const inst = await api('/api/instances')
    instStats.value = inst.instances || []
  } catch { /* ignore */ }
}

function emptyInst() {
  return {
    name: '', host: '', port: '443', base: '/youlilucky',
    token: '', https: true, enabled: true, modules: ['system', 'webservice', 'docker', 'cron', 'ddns', 'ssl', 'webterminal', 'rclone', 'filebrowser', 'wol', 'smb'],
  }
}
function startNew() {
  editing.value = emptyInst()
  isNew.value = true
  testResult.value = null
  err.value = ''
}
function startEdit(inst) {
  editing.value = { ...inst, modules: [...(inst.modules || [])] }
  isNew.value = false
  testResult.value = null
  err.value = ''
}
function cancelEdit() {
  editing.value = null
  isNew.value = false
  testResult.value = null
}
function toggleModule(m) {
  const list = editing.value.modules
  const i = list.indexOf(m)
  if (i >= 0) list.splice(i, 1)
  else list.push(m)
}

async function testConn() {
  if (!editing.value) return
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await api('/api/config/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        host: editing.value.host, port: editing.value.port,
        base: editing.value.base, token: editing.value.token, https: editing.value.https,
      }),
    })
  } catch (e) {
    testResult.value = { ok: false, error: e.message }
  } finally {
    testing.value = false
  }
}

function toast() {
  saved.value = true
  clearTimeout(savedTimer)
  savedTimer = setTimeout(() => { saved.value = false }, 2500)
}

async function saveInstance() {
  if (!editing.value) return
  err.value = ''
  if (!editing.value.name.trim()) { err.value = '实例名称不能为空'; return }
  if (!editing.value.host.trim()) { err.value = '地址不能为空'; return }
  const list = cfg.value.instances || []
  const idx = list.findIndex((i) => i.name === editing.value.name)
  const item = JSON.parse(JSON.stringify(editing.value))
  if (isNew.value) {
    if (idx >= 0) { err.value = '实例名称已存在'; return }
    list.push(item)
  } else {
    if (idx >= 0) list[idx] = item
  }
  await putConfig()
  editing.value = null
  isNew.value = false
}

async function saveGlobal() {
  err.value = ''
  cfg.value.collect_interval = Math.max(2, Number(cfg.value.collect_interval) || 10)
  cfg.value.cleanup.days = Math.max(1, Number(cfg.value.cleanup.days) || 7)
  await putConfig()
}

async function putConfig() {
  try {
    await api('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg.value),
    })
    await load()
    await refreshInstances()
    store.refreshInterval = cfg.value.refresh_interval ?? 10
    toast()
  } catch (e) {
    err.value = `保存失败: ${e.message}`
  }
}

async function doDelete() {
  const name = confirmDel.value
  if (!name) return
  try {
    await api(`/api/config/instance/${encodeURIComponent(name)}?${qp({ purge: purgeDel.value })}`, { method: 'DELETE' })
    await load()
    await refreshInstances()
    confirmDel.value = null
    purgeDel.value = false
    toast()
  } catch (e) {
    err.value = `删除失败: ${e.message}`
  }
}

onMounted(async () => {
  await load()
  await refreshInstances()
  pollTimer = setInterval(poll, 5000)
  storageTimer = setInterval(loadStorage, 15000)
})
onUnmounted(() => {
  clearInterval(pollTimer)
  clearInterval(storageTimer)
  clearTimeout(savedTimer)
})
</script>

<template>
  <div v-if="cfg">
    <div class="head"><h2>设置</h2></div>
    <div v-if="saved" class="toast">已保存</div>
    <div v-if="err" class="err">{{ err }}</div>

    <!-- 全局设置 -->
    <div class="card">
      <h3>全局设置</h3>
      <div class="form-row">
        <label>采集间隔（秒）</label>
        <input v-model.number="cfg.collect_interval" type="number" min="2" style="width:120px">
        <span class="hint">每轮采集间隔，目标并发敏感，建议 ≥5</span>
      </div>
      <div class="form-row">
        <label>面板刷新间隔（秒）</label>
        <input v-model.number="cfg.refresh_interval" type="number" min="0" style="width:120px">
        <span class="hint">各面板（Docker/SMB/访问分析）统一自动刷新间隔；0 = 关闭自动刷新</span>
      </div>
      <div class="form-row">
        <label>自动清理</label>
        <input v-model="cfg.cleanup.enabled" type="checkbox">
        <span class="hint">开启后删除超过以下天数的旧日志</span>
        <input v-model.number="cfg.cleanup.days" type="number" min="1" style="width:90px" :disabled="!cfg.cleanup.enabled">
        <span class="hint">天</span>
      </div>
      <div class="form-row">
        <label>失败退避</label>
        <input v-model.number="cfg.backoff.base" type="number" min="1" style="width:70px" title="初始退避秒">
        <span class="hint">初始秒</span>
        <input v-model.number="cfg.backoff.max" type="number" min="1" style="width:70px" title="最大退避/冷却秒">
        <span class="hint">最大/冷却秒</span>
        <input v-model.number="cfg.backoff.max_retries" type="number" min="1" style="width:60px" title="连续失败多少次后进入长冷却">
        <span class="hint">连续失败次数后长冷却（指数退避，防风控）</span>
      </div>
      <div class="form-row">
        <label>监听地址</label>
        <input :value="cfg.web.host" disabled style="width:140px">
        <span>:</span>
        <input :value="cfg.web.port" disabled style="width:80px">
        <span class="hint">仅运行时可改（--port），此处只读，改动需重启后端</span>
      </div>
      <button @click="saveGlobal">保存全局设置</button>
    </div>

    <!-- 实例列表 -->
    <div class="card">
      <div class="card-head">
        <h3>实例（Lucky 地址 / Token / 模块）</h3>
        <div class="head-actions">
          <button @click="collectAllInst">采集全部</button>
          <button @click="startNew">+ 新增实例</button>
        </div>
      </div>
      <table class="inst-table">
        <thead>
          <tr><th>名称</th><th>地址</th><th>协议</th><th>启用</th><th>模块数</th><th>采集状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="i in cfg.instances || []" :key="i.name">
            <td><strong>{{ i.name }}</strong></td>
            <td class="mono">{{ i.host }}:{{ i.port }}{{ i.base }}</td>
            <td>{{ i.https ? 'HTTPS' : 'HTTP' }}</td>
            <td>{{ i.enabled ? '是' : '否' }}</td>
            <td>{{ (i.modules || []).length }}</td>
            <td class="st">
              <template v-if="!i.enabled"><span class="muted">未启用</span></template>
              <template v-else>
                <span v-if="statusFor(i.name).collecting" class="busy">
                  采集中<template v-if="statusFor(i.name).current"> · {{ statusFor(i.name).current }}</template>
                  <template v-if="statusFor(i.name).page"> · 页 {{ statusFor(i.name).page }}/{{ statusFor(i.name).source_total || '?' }}</template>
                  <template v-if="statusFor(i.name).collected_rows"> · 已采 {{ statusFor(i.name).collected_rows }} 条</template>
                </span>
                <template v-else-if="isPaused(i.name)">
                  <span class="red">已暂停<template v-if="statusFor(i.name).fail_count"> · 连续失败 {{ statusFor(i.name).fail_count }} 次</template><template v-if="statusFor(i.name).last_error"> · {{ statusFor(i.name).last_error }}</template></span>
                  <span class="hint"> · 点「立即采集」或保存配置恢复</span>
                </template>
                <template v-else-if="isBackoff(i.name)">
                  <span class="red">退避中<template v-if="statusFor(i.name).next_retry_in"> · 下次 {{ fmtEpoch(statusFor(i.name).backoff_until) }}</template><template v-if="statusFor(i.name).fail_count"> · 连续失败 {{ statusFor(i.name).fail_count }} 次</template></span>
                </template>
                <template v-else-if="statusFor(i.name).last_collect">
                  <span>最近采集 {{ fmtEpoch(statusFor(i.name).last_collect) }} · 日志 {{ statusFor(i.name).total }} · 访问 {{ statusFor(i.name).access }}</span>
                  <span v-if="statusFor(i.name).last_error" class="red"> · 错误: {{ statusFor(i.name).last_error }}</span>
                </template>
                <template v-else>
                  <span class="muted">等待首次采集…</span>
                  <span v-if="statusFor(i.name).last_error" class="red"> · 错误: {{ statusFor(i.name).last_error }}</span>
                </template>
              </template>
            </td>
            <td class="ops">
              <button :disabled="statusFor(i.name).collecting" @click="collectInstance(i.name)">{{ statusFor(i.name).collecting ? '采集中…' : '立即采集' }}</button>
              <button @click="startEdit(i)">编辑</button>
              <button class="danger" @click="confirmDel = i.name; purgeDel = false">删除</button>
            </td>
          </tr>
          <tr v-if="!cfg.instances?.length"><td colspan="7" class="muted">暂无实例，点击「+ 新增实例」添加</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 本地数据 -->
    <div class="card">
      <div class="card-head"><h3>本地数据</h3><span class="hint">DB 文件 {{ fmtBytes(storage?.db_bytes) }} · 每 15s 刷新</span></div>
      <table class="inst-table">
        <thead><tr><th>表</th><th>行数</th><th>估算字节</th></tr></thead>
        <tbody>
          <tr v-for="(v, k) in storage?.tables || {}" :key="k">
            <td class="mono">{{ k }}</td><td>{{ v.rows }}</td><td>{{ fmtBytes(v.bytes) }}</td>
          </tr>
        </tbody>
      </table>
      <table class="inst-table">
        <thead><tr><th>实例</th><th>日志</th><th>访问</th><th>流量 IP</th><th>估算字节</th></tr></thead>
        <tbody>
          <tr v-for="p in storage?.per_instance || []" :key="p.name">
            <td>{{ p.name }}</td><td>{{ p.logs }}</td><td>{{ p.access }}</td><td>{{ p.traffic_ips }}</td><td>{{ fmtBytes(p.bytes) }}</td>
          </tr>
          <tr v-if="!storage?.per_instance?.length"><td colspan="5" class="muted">暂无数据</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 编辑/新增 -->
    <div v-if="editing" class="card">
      <h3>{{ isNew ? '新增实例' : '编辑实例' }}</h3>
      <div class="form-grid">
        <div class="form-row"><label>名称 *</label><input v-model="editing.name" placeholder="如 lucky-main"></div>
        <div class="form-row"><label>地址 *</label><input v-model="editing.host" placeholder="192.168.1.100"></div>
        <div class="form-row"><label>端口</label><input v-model="editing.port" style="width:110px"></div>
        <div class="form-row"><label>Base 路径</label><input v-model="editing.base" style="width:160px" placeholder="/youlilucky"></div>
        <div class="form-row"><label>协议</label>
          <select v-model="editing.https" style="width:110px">
            <option :value="true">HTTPS</option>
            <option :value="false">HTTP</option>
          </select>
        </div>
        <div class="form-row"><label>启用采集</label><input v-model="editing.enabled" type="checkbox"></div>
        <div class="form-row full"><label>OpenToken</label>
          <input v-model="editing.token" type="password" autocomplete="off" style="width:420px" placeholder="Lucky OpenToken（可见可编辑）">
          <button :disabled="testing" @click="testConn">{{ testing ? '测试中…' : '测试连接' }}</button>
          <span v-if="testResult" :class="testResult.ok ? 'ok' : 'red'">
            {{ testResult.ok ? `连接成功 · ${testResult.host}` : `连接失败: ${testResult.error}` }}
          </span>
        </div>
      </div>
      <div class="mods">
        <h4>采集模块</h4>
        <label v-for="m in allModules" :key="m" class="mod">
          <input type="checkbox" :checked="editing.modules.includes(m)" @change="toggleModule(m)">
          {{ MODULE_LABELS[m] || m }}
        </label>
      </div>
      <div class="actions">
        <button class="primary" @click="saveInstance">保存</button>
        <button @click="cancelEdit">取消</button>
      </div>
    </div>

    <!-- 删除确认 -->
    <Teleport to="body">
      <div v-if="confirmDel" class="mask" @click.self="confirmDel = null">
        <div class="dlg">
          <h3>删除实例「{{ confirmDel }}」</h3>
          <p>将停止采集该实例（已采集数据默认保留，如需恢复可重建同名实例）。</p>
          <label><input v-model="purgeDel" type="checkbox"> 同时清除该实例已采集的数据（不可恢复）</label>
          <div class="actions">
            <button class="danger" @click="doDelete">删除</button>
            <button @click="confirmDel = null">取消</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.head h2 { margin: 0 0 12px; font-size: 16px; }
.toast { position: fixed; top: 64px; right: 20px; z-index: 2000; background: var(--green); color: #062; padding: 8px 16px; border-radius: 8px; font-weight: 600; }
.err { color: var(--red); margin-bottom: 10px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px; margin-bottom: 14px; }
.card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.head-actions { display: flex; gap: 8px; }
.card h3, .card-head h3 { margin: 0; font-size: 13px; color: var(--muted); }
.busy { color: var(--yellow); }
.ops { white-space: nowrap; }
.form-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.form-row label { width: 90px; color: var(--muted); }
.form-row .hint { color: var(--muted); font-size: 11px; }
.form-row .ok { color: var(--green); }
.form-row .red { color: var(--red); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 16px; }
.full { grid-column: 1 / -1; }
.mods { margin-top: 8px; }
.mods h4 { margin: 0 0 6px; font-size: 12px; color: var(--muted); }
.mods .mod { display: inline-flex; align-items: center; gap: 4px; margin: 0 14px 6px 0; font-size: 12px; cursor: pointer; }
.inst-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.inst-table th { text-align: left; color: var(--muted); padding: 6px 8px; border-bottom: 1px solid var(--border); font-weight: 600; }
.inst-table td { padding: 7px 8px; border-bottom: 1px solid #1c2540; }
.mono { font-family: Consolas, monospace; }
.muted { color: var(--muted); }
.red { color: var(--red); }
.actions { display: flex; gap: 8px; margin-top: 12px; }
.danger { border-color: var(--red); color: var(--red); }
.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1500; display: flex; align-items: center; justify-content: center; }
.dlg { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 20px; width: 420px; max-width: 92vw; }
.dlg h3 { margin: 0 0 10px; }
.dlg p { color: var(--muted); }
.dlg label { display: flex; gap: 6px; align-items: center; color: var(--muted); }
</style>
