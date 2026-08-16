<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import { useDataRefresh } from '../composables/useDataRefresh'
import { fmtBytes } from '../utils'

const data = ref(null)
const error = ref('')
const busyId = ref(null)
let timer = null

function fmtRate(b) {
  if (b == null || b === 0) return '0'
  return fmtBytes(b) + '/s'
}

async function load() {
  try {
    data.value = await api(`/api/smb/overview?instance=${encodeURIComponent(store.instance)}`)
    error.value = ''
  } catch (e) {
    error.value = `加载失败: ${e.message}`
  }
}

async function disconnect(conn) {
  busyId.value = conn.connID
  try {
    await api(`/api/smb/connections/${encodeURIComponent(conn.connID)}/disconnect?instance=${encodeURIComponent(store.instance)}`, { method: 'POST' })
    await load()
  } catch (e) {
    error.value = `断开失败: ${e.message}`
  } finally {
    busyId.value = null
  }
}

const summary = () => data.value?.runtime?.summary || {}
const users = () => data.value?.runtime?.users || []
const conns = () => data.value?.runtime?.connections || []

function restartTimer() {
  clearInterval(timer)
  const sec = Number(store.refreshInterval) || 0
  if (sec > 0) timer = setInterval(load, sec * 1000)
}

onMounted(async () => {
  await load()
  restartTimer()
})
useDataRefresh(load)
watch(() => store.refreshInterval, restartTimer)
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div>
    <div class="head"><h2>SMB 运行状态</h2><span class="hint">自动刷新 {{ store.refreshInterval || '关' }}s（设置中统一配置）</span></div>
    <div v-if="error" class="err">{{ error }}</div>

    <div class="kpis">
      <div class="kpi"><div class="title">服务状态</div><div class="value" :style="{ color: summary().enabled ? 'var(--green)' : 'var(--muted)' }">{{ summary().enabled ? '已启用' : '未启用' }}</div><div class="sub">{{ summary().errMsg || (summary().running ? '运行中' : '未运行') }}</div></div>
      <div class="kpi"><div class="title">连接数</div><div class="value" style="color:var(--accent)">{{ summary().connectionCount ?? 0 }}</div><div class="sub">当前连接</div></div>
      <div class="kpi"><div class="title">会话</div><div class="value" style="color:var(--green)">{{ summary().sessionCount ?? 0 }}</div><div class="sub">SMB 会话</div></div>
      <div class="kpi"><div class="title">在线用户</div><div class="value" style="color:var(--yellow)">{{ summary().onlineUserCount ?? 0 }}</div><div class="sub">在线</div></div>
      <div class="kpi"><div class="title">打开句柄</div><div class="value">{{ summary().openCount ?? 0 }}</div><div class="sub">已打开文件</div></div>
      <div class="kpi"><div class="title">上行速率</div><div class="value" style="color:var(--red)">{{ fmtRate(summary().uploadBytesPerSec) }}</div><div class="sub">写入</div></div>
      <div class="kpi"><div class="title">下行速率</div><div class="value" style="color:var(--green)">{{ fmtRate(summary().downloadBytesPerSec) }}</div><div class="sub">读取</div></div>
    </div>

    <div class="card">
      <h3>在线用户</h3>
      <table class="t">
        <thead><tr><th>用户</th><th>在线</th><th>连接</th><th>会话</th><th>上行</th><th>下行</th><th>最后活动</th></tr></thead>
        <tbody>
          <tr v-for="u in users()" :key="u.Username || u.username">
            <td>{{ u.Username || u.username || '匿名/未知' }}</td>
            <td>{{ u.online ? '是' : '否' }}</td>
            <td>{{ u.connectionCount ?? 0 }}</td>
            <td>{{ u.sessionCount ?? 0 }}</td>
            <td>{{ fmtRate(u.uploadBytesPerSec) }}</td>
            <td>{{ fmtRate(u.downloadBytesPerSec) }}</td>
            <td class="mono">{{ u.lastActivityAt || u.lastAccess || '—' }}</td>
          </tr>
          <tr v-if="!users().length"><td colspan="7" class="muted">暂无在线用户</td></tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>连接</h3>
      <table class="t">
        <thead><tr><th>远程地址</th><th>会话数</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="c in conns()" :key="c.connID">
            <td class="mono">{{ c.remoteAddr || '—' }}</td>
            <td>{{ c.sessionsCount ?? 0 }}</td>
            <td>
              <button :disabled="busyId === c.connID" @click="disconnect(c)">{{ busyId === c.connID ? '断开中…' : '断开' }}</button>
            </td>
          </tr>
          <tr v-if="!conns().length"><td colspan="3" class="muted">暂无连接</td></tr>
        </tbody>
      </table>
    </div>

    <div class="card">
      <h3>SMB 日志</h3>
      <router-link to="/module/smb">前往「模块日志 — smb」查看</router-link>
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.head h2 { margin: 0; font-size: 16px; }
.hint { color: var(--muted); font-size: 11px; }
.err { color: var(--red); margin-bottom: 10px; }
.kpis { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
.kpi { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; min-width: 130px; }
.kpi .title { color: var(--muted); font-size: 12px; }
.kpi .value { font-size: 20px; font-weight: 700; margin: 4px 0; }
.kpi .sub { color: var(--muted); font-size: 11px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-bottom: 12px; }
.card h3 { margin: 0 0 8px; font-size: 12px; color: var(--muted); font-weight: 600; }
.t { width: 100%; border-collapse: collapse; font-size: 12px; }
.t th { text-align: left; color: var(--muted); padding: 6px 8px; border-bottom: 1px solid var(--border); }
.t td { padding: 7px 8px; border-bottom: 1px solid #1c2540; }
.mono { font-family: Consolas, monospace; }
.muted { color: var(--muted); }
</style>
