<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, esc, fmtEpoch } from '../api'
import { store } from '../store'
import { useDataRefresh } from '../composables/useDataRefresh'
import EmptyState from '../components/EmptyState.vue'

const tab = ref('containers')
const overview = ref(null)
const containers = ref([])
const images = ref([])
const networks = ref([])
const volumes = ref([])
const fetchedAt = ref(0)
const detail = ref(null)       // {cid, stats, processes}
const logs = ref('')
const error = ref('')
const busy = ref(null)         // cid:action 操作中
let timer = null
let lastInstance = ''

const D = () => ({ instance: store.instance })

async function apiGet(path) {
  return api(path + (path.includes('?') ? '&' : '?') + new URLSearchParams(D()))
}

function applySnap(s) {
  overview.value = s.info ? { info: s.info, version: s.version } : null
  containers.value = s.containers || []
  images.value = s.images || []
  networks.value = s.networks || []
  volumes.value = s.volumes || []
  fetchedAt.value = s.fetched_at || 0
}

function fmtBytes(b) {
  if (b == null) return '—'
  const s = String(b).replace(/ B$/, '').trim()
  const n = parseFloat(s)
  if (isNaN(n)) return String(b)
  if (n >= 1e9) return (n / 1e9).toFixed(2) + ' GB'
  if (n >= 1e6) return (n / 1e6).toFixed(2) + ' MB'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + ' KB'
  return b + ' B'
}

const info = computed(() => overview.value?.info?.info || {})
const engine = computed(() => {
  const comps = overview.value?.version?.version?.Components || []
  const eng = comps.find((c) => c.Name === 'Engine')
  return eng ? `${eng.Name} ${eng.Version}` : '—'
})
const kpis = computed(() => [
  { title: '运行容器', value: info.value.ContainersRunning ?? 0, sub: '运行中', accent: 'var(--green)' },
  { title: '暂停', value: info.value.ContainersPaused ?? 0, sub: '已暂停', accent: 'var(--yellow)' },
  { title: '停止', value: info.value.ContainersStopped ?? 0, sub: '已停止', accent: 'var(--muted)' },
  { title: '镜像', value: info.value.Images ?? 0, sub: '本地镜像', accent: 'var(--accent)' },
  { title: 'Docker', value: engine.value, sub: (info.value.Driver || '—') + ' · 存储驱动', accent: 'var(--red)' },
])

async function loadSnapshot() {
  try { applySnap(await apiGet('/api/docker/snapshot')) } catch (e) { error.value = `加载失败: ${e.message}` }
}

async function refreshAll() {
  try {
    const q = new URLSearchParams(D())
    const s = await api(`/api/docker/refresh?${q}`, { method: 'POST' })
    applySnap(s)
  } catch (e) {
    error.value = `刷新失败: ${e.message}`
  }
}

async function loadDetail(cid) {
  try {
    detail.value = { cid, ...(await apiGet(`/api/docker/container/${encodeURIComponent(cid)}`)) }
    await loadLogs(cid)
  } catch (e) {
    error.value = `详情加载失败: ${e.message}`
  }
}
async function loadLogs(cid) {
  try {
    const d = await apiGet(`/api/docker/container/${encodeURIComponent(cid)}/logs`)
    logs.value = d.logs || ''
  } catch { /* ignore */ }
}

async function control(cid, action) {
  busy.value = `${cid}:${action}`
  try {
    const q = new URLSearchParams({ instance: store.instance, action })
    await api(`/api/docker/containers/${encodeURIComponent(cid)}/action?${q}`, { method: 'POST' })
    await refreshAll()
    if (detail.value && detail.value.cid === cid) await loadDetail(cid)
  } catch (e) {
    error.value = `操作失败: ${e.message}`
  } finally {
    busy.value = null
  }
}

function restartTimer() {
  clearInterval(timer)
  const sec = Number(store.refreshInterval) || 0
  if (sec > 0) {
    timer = setInterval(() => {
      refreshAll().catch(() => {})
      if (detail.value) { loadDetail(detail.value.cid).catch(() => {}) }
    }, sec * 1000)
  }
}

function onDataRefresh() {
  if (store.instance !== lastInstance) {
    lastInstance = store.instance
    detail.value = null
    logs.value = ''
    loadSnapshot()          // ① 切换实例：立即读新实例本地缓存（秒显，零网络等待）
  }
  refreshAll()              // ② 后台全量刷新（写缓存），完成后覆盖
}

// ---- 客户端排序（docker 列表量小，本地排即可） ----
const sortState = ref({ key: 'cname', dir: 'asc' })
function onSort(key) {
  const s = sortState.value
  if (s.key === key) s.dir = s.dir === 'asc' ? 'desc' : 'asc'
  else { s.key = key; s.dir = 'asc' }
}
function sortVal(c, key) {
  if (key === 'cname') return cName(c)
  const v = c[key]
  return typeof v === 'string' ? (v || '') : (v ?? 0)
}
function cmp(a, b) {
  const { key, dir } = sortState.value
  const av = sortVal(a, key), bv = sortVal(b, key)
  const r = typeof av === 'string' ? av.localeCompare(bv) : (av - bv)
  return dir === 'asc' ? r : -r
}
const sortedContainers = computed(() => [...containers.value].sort(cmp))
const sortedImages = computed(() => [...images.value].sort(cmp))

function cName(c) {
  const n = (c.Names && c.Names[0]) || ''
  return n.replace(/^\//, '')
}
function cCpu(c) { return c.stats?.cpu_percent || '0%' }
function cMem(c) {
  const s = c.stats || {}
  return s.memory_usage ? `${s.memory_usage} / ${s.memory_limit} (${s.memory_percent})` : '—'
}
function cNet(c) {
  const s = c.stats || {}
  return s.network_rx ? `↓${fmtBytes(s.network_rx)} ↑${fmtBytes(s.network_tx)}` : '—'
}
function actionsFor(c) {
  const st = c.State
  if (st === 'running') return [['stop', '停止'], ['restart', '重启'], ['pause', '暂停']]
  if (st === 'paused') return [['unpause', '恢复']]
  return [['start', '开始']]
}
function stateClass(c) {
  return c.State === 'running' ? 'ok' : (c.State === 'paused' ? 'warn' : 'muted')
}

onMounted(async () => {
  lastInstance = store.instance
  await loadSnapshot()      // 先读本地缓存，秒显
  await refreshAll().catch(() => {})  // 再后台全量刷新（写缓存）
  restartTimer()
})
watch(tab, () => { /* 数据来自快照，无需按 tab 单独加载 */ })
useDataRefresh(onDataRefresh)
watch(() => store.refreshInterval, restartTimer)
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div>
    <div class="head">
      <h2>Docker 面板</h2>
      <span v-if="fetchedAt" class="hint">快照更新于 {{ fmtEpoch(fetchedAt) }}</span>
      <span class="hint">自动刷新 {{ store.refreshInterval || '关' }}s（设置中统一配置）</span>
      <router-link to="/module/docker" class="hint link">Docker 模块日志</router-link>
      <span v-if="error" class="err">{{ error }}</span>
    </div>

    <div class="kpis">
      <div v-for="k in kpis" :key="k.title" class="kpi">
        <div class="title">{{ k.title }}</div>
        <div class="value" :style="{ color: k.accent }">{{ k.value }}</div>
        <div class="sub">{{ k.sub }}</div>
      </div>
    </div>

    <div class="tabs">
      <button :class="{ active: tab === 'containers' }" @click="tab = 'containers'">容器 ({{ containers.length }})</button>
      <button :class="{ active: tab === 'images' }" @click="tab = 'images'">镜像 ({{ images.length }})</button>
      <button :class="{ active: tab === 'networks' }" @click="tab = 'networks'">网络</button>
      <button :class="{ active: tab === 'volumes' }" @click="tab = 'volumes'">卷</button>
    </div>

    <!-- 容器 -->
    <div v-if="tab === 'containers'" class="card">
      <table class="t">
        <thead>
          <tr>
            <th @click="onSort('cname')">名称{{ sortState.key === 'cname' ? (sortState.dir === 'asc' ? ' ▲' : ' ▼') : '' }}</th>
            <th @click="onSort('Image')">镜像</th>
            <th>状态</th>
            <th>CPU</th>
            <th>内存</th>
            <th>网络</th>
            <th>创建</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in sortedContainers" :key="c.Id" class="row" @click="loadDetail(c.Id)">
            <td class="mono">{{ cName(c) }}</td>
            <td class="img">{{ c.Image }}</td>
            <td><span :class="['state', stateClass(c)]">{{ c.State }}</span> {{ c.Status }}</td>
            <td>{{ cCpu(c) }}</td>
            <td class="mono">{{ cMem(c) }}</td>
            <td class="mono">{{ cNet(c) }}</td>
            <td class="mono">{{ fmtEpoch(c.Created) }}</td>
            <td class="ops" @click.stop>
              <button v-for="[a, label] in actionsFor(c)" :key="a" :disabled="busy === c.Id + ':' + a" @click="control(c.Id, a)">
                {{ busy === c.Id + ':' + a ? '…' : label }}
              </button>
            </td>
          </tr>
          <tr v-if="!containers.length"><td colspan="8" class="muted">无容器</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 镜像 -->
    <div v-else-if="tab === 'images'" class="card">
      <table class="t">
        <thead><tr><th>仓库标签</th><th>大小</th><th>架构</th><th>被使用</th><th>创建</th></tr></thead>
        <tbody>
          <tr v-for="im in sortedImages" :key="im.Id">
            <td class="mono">{{ (im.RepoTags || []).join(', ') || im.Id.slice(0, 19) }}</td>
            <td>{{ fmtBytes(im.Size) }}</td>
            <td>{{ im.Architecture }}</td>
            <td>{{ im.Containers }}</td>
            <td class="mono">{{ fmtEpoch(im.Created) }}</td>
          </tr>
          <tr v-if="!images.length"><td colspan="5" class="muted">无镜像</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 网络 -->
    <div v-else-if="tab === 'networks'" class="card">
      <table class="t">
        <thead><tr><th>名称</th><th>Driver</th><th>Scope</th><th>子网</th><th>网关</th><th>连接容器</th></tr></thead>
        <tbody>
          <tr v-for="n in networks" :key="n.Id">
            <td class="mono">{{ n.Name }}</td>
            <td>{{ n.Driver }}</td>
            <td>{{ n.Scope }}</td>
            <td class="mono">{{ n.IPAM?.Config?.[0]?.Subnet || '—' }}</td>
            <td class="mono">{{ n.IPAM?.Config?.[0]?.Gateway || '—' }}</td>
            <td>{{ Object.keys(n.Containers || {}).length }}</td>
          </tr>
          <tr v-if="!networks.length"><td colspan="6" class="muted">无网络</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 卷 -->
    <div v-else class="card">
      <table class="t">
        <thead><tr><th>名称</th><th>Driver</th><th>挂载点</th><th>大小</th></tr></thead>
        <tbody>
          <tr v-for="v in volumes" :key="v.Name">
            <td class="mono">{{ v.Name }}</td>
            <td>{{ v.Driver }}</td>
            <td class="mono">{{ v.Mountpoint }}</td>
            <td>{{ v.UsageData?.Size != null ? fmtBytes(v.UsageData.Size) : '—' }}</td>
          </tr>
          <tr v-if="!volumes.length"><td colspan="4" class="muted">无卷</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 容器详情抽屉 -->
    <Teleport to="body">
      <div v-if="detail" class="mask" @click.self="detail = null">
        <aside class="drawer">
          <header>
            <span>容器详情</span>
            <button class="close" @click="detail = null">✕</button>
          </header>
          <div class="body">
            <section>
              <h4>实时资源</h4>
              <dl>
                <dt>CPU</dt><dd>{{ detail.stats?.cpu_percent || '—' }}</dd>
                <dt>内存</dt><dd>{{ detail.stats?.memory_usage || '—' }} / {{ detail.stats?.memory_limit || '—' }} ({{ detail.stats?.memory_percent || '—' }})</dd>
                <dt>网络</dt><dd class="mono">↓ {{ fmtBytes(detail.stats?.network_rx) }} / ↑ {{ fmtBytes(detail.stats?.network_tx) }}</dd>
                <dt>块IO</dt><dd class="mono">读 {{ detail.stats?.block_read || '—' }} / 写 {{ detail.stats?.block_write || '—' }}</dd>
              </dl>
            </section>
            <section>
              <h4>容器日志</h4>
              <pre class="logs">{{ logs || '暂无日志' }}</pre>
            </section>
            <section v-if="detail.processes && detail.processes.Processes">
              <h4>进程 ({{ detail.processes.Processes.length }})</h4>
              <table class="t">
                <tbody>
                  <tr v-for="(p, i) in detail.processes.Processes.slice(0, 30)" :key="i">
                    <td class="mono">{{ p.slice(0, 4).join('  ') }}</td>
                  </tr>
                </tbody>
              </table>
            </section>
          </div>
        </aside>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.head h2 { margin: 0; font-size: 16px; }
.hint { color: var(--muted); font-size: 11px; }
.hint.link { color: var(--accent); }
.err { color: var(--red); margin-left: 8px; }
.kpis { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
.kpi { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; min-width: 120px; }
.kpi .title { color: var(--muted); font-size: 12px; }
.kpi .value { font-size: 20px; font-weight: 700; margin: 4px 0; }
.kpi .sub { color: var(--muted); font-size: 11px; }
.tabs { display: flex; gap: 6px; margin-bottom: 12px; }
.tabs button { padding: 6px 14px; }
.tabs button.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
.t { width: 100%; border-collapse: collapse; font-size: 12px; }
.t th { text-align: left; color: var(--muted); padding: 7px 8px; border-bottom: 1px solid var(--border); font-weight: 600; cursor: pointer; user-select: none; }
.t th.sorted { color: var(--accent); }
.t td { padding: 7px 8px; border-bottom: 1px solid #1c2540; }
.t .row { cursor: pointer; }
.t .row:hover { background: #1a2336; }
.mono { font-family: Consolas, monospace; }
.img { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.state { padding: 1px 7px; border-radius: 10px; font-size: 11px; }
.state.ok { background: rgba(61,220,132,.15); color: var(--green); }
.state.warn { background: rgba(245,197,66,.15); color: var(--yellow); }
.state.muted { background: var(--panel2); color: var(--muted); }
.ops { white-space: nowrap; }
.muted { color: var(--muted); }
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000; }
.drawer { position: absolute; top: 0; right: 0; height: 100%; width: 520px; max-width: 94vw; background: var(--panel); border-left: 1px solid var(--border); display: flex; flex-direction: column; }
header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); font-weight: 700; }
.close { border: none; background: none; font-size: 14px; color: var(--muted); }
.body { flex: 1; overflow-y: auto; padding: 6px 16px 24px; }
section { margin-top: 14px; }
h4 { margin: 0 0 8px; font-size: 12px; color: var(--muted); }
dl { margin: 0; display: grid; grid-template-columns: 80px 1fr; gap: 5px 8px; }
dt { color: var(--muted); }
dd { margin: 0; word-break: break-all; }
.logs { background: var(--panel2); border: 1px solid var(--border); border-radius: 6px; padding: 8px; font-family: Consolas, monospace; font-size: 11px; white-space: pre-wrap; word-break: break-all; color: var(--muted); max-height: 300px; overflow-y: auto; }
</style>
