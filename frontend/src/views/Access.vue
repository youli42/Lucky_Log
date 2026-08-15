<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { api, qp } from '../api'
import { store, onRealtime } from '../store'
import { donutOptions, barOptions, lineOptions, paletteOf } from '../charts'
import KpiCard from '../components/KpiCard.vue'
import ChartBox from '../components/ChartBox.vue'
import LogTable from '../components/LogTable.vue'
import EmptyState from '../components/EmptyState.vue'

const tab = ref('analytics')
const rule = ref('')
const sub = ref('')
const host = ref('')
const search = ref('')
const detailSearch = ref('')
const detailIp = ref('')
const detailPath = ref('')
const page = ref(1)
const pageSize = 100

const stats = ref(null)
const services = ref([])
const detail = ref({ total: 0, items: [] })
const runtime = ref({ total: 0, items: [] })
const runtimePage = ref(1)
const loading = ref(false)

const accessParams = () => ({
  instance: store.instance,
  rule: rule.value,
  sub: sub.value,
  host: host.value,
  from_epoch: store.from,
  to_epoch: store.to,
  search: search.value,
})

async function loadServices() {
  const s = await api(`/api/services?instance=${encodeURIComponent(store.instance)}`)
  services.value = s.tree || []
}

async function loadStats() {
  loading.value = true
  try {
    stats.value = await api(`/api/access/stats?${qp(accessParams())}`)
  } finally {
    loading.value = false
  }
}

async function loadDetail() {
  const p = new URLSearchParams(accessParams())
  p.set('search', detailSearch.value)
  p.set('ip', detailIp.value)
  p.set('path', detailPath.value)
  p.set('page', page.value); p.set('page_size', pageSize)
  detail.value = await api(`/api/access/logs?${p}`)
}

async function loadRuntime() {
  const p = new URLSearchParams({
    instance: store.instance, module: 'webservice', level: 'rule',
    from_epoch: store.from, to_epoch: store.to, dedup: 'off',
    page: runtimePage.value, page_size: 100,
  })
  runtime.value = await api(`/api/logs?${p}`)
}

// ---- 分析图表 ----
const kpis = computed(() => [
  { title: '总访问', value: stats.value?.total ?? 0, sub: '访问日志条数', accent: 'var(--accent)' },
  { title: '独立 IP', value: stats.value?.unique_ips ?? 0, sub: '去重后访问 IP', accent: 'var(--green)' },
  { title: '独立路径', value: stats.value?.unique_paths ?? 0, sub: '去重后访问路径', accent: 'var(--yellow)' },
  { title: '域名', value: stats.value?.hosts?.length ?? 0, sub: '访问 Host 数', accent: 'var(--red)' },
])

const trendChart = computed(() => {
  const rows = stats.value?.timeline || []
  return {
    labels: rows.map((r) => bucketLabel(r.bucket)),
    datasets: [{ label: '访问', data: rows.map((r) => r.count), borderColor: '#4f8cff', backgroundColor: 'rgba(79,140,255,.15)', fill: true, tension: .3, pointRadius: 1 }],
  }
})
const ipChart = computed(() => {
  const rows = stats.value?.top_ips || []
  return {
    labels: rows.map((r) => `${r.k}${r.region ? ' (' + r.region + ')' : ''}`),
    datasets: [{ label: '次数', data: rows.map((r) => r.count), backgroundColor: paletteOf(rows.length) }],
  }
})
const regionChart = computed(() => {
  const rows = stats.value?.region_dist || []
  return { labels: rows.map((r) => r.region), datasets: [{ data: rows.map((r) => r.count), backgroundColor: paletteOf(rows.length) }] }
})
function donutOf(rows) {
  return { labels: (rows || []).map((r) => r.name), datasets: [{ data: (rows || []).map((r) => r.count), backgroundColor: paletteOf(rows.length) }] }
}
const browserChart = computed(() => donutOf(stats.value?.browsers))
const osChart = computed(() => donutOf(stats.value?.os))
const deviceTypeChart = computed(() => donutOf(stats.value?.device_types))
const deviceChart = computed(() => {
  const rows = stats.value?.devices || []
  return { labels: rows.map((r) => r.name), datasets: [{ label: '数量', data: rows.map((r) => r.count), backgroundColor: paletteOf(rows.length) }] }
})
const pathChart = computed(() => {
  const rows = stats.value?.top_paths || []
  return { labels: rows.map((r) => r.name), datasets: [{ label: '次数', data: rows.map((r) => r.count), backgroundColor: paletteOf(rows.length) }] }
})
const hostChart = computed(() => {
  const rows = stats.value?.hosts || []
  return { labels: rows.map((r) => r.name), datasets: [{ label: '次数', data: rows.map((r) => r.count), backgroundColor: paletteOf(rows.length) }] }
})
const methodChart = computed(() => {
  const rows = stats.value?.methods || []
  return { labels: rows.map((r) => r.name), datasets: [{ label: '次数', data: rows.map((r) => r.count), backgroundColor: paletteOf(rows.length) }] }
})

function bucketLabel(bucket) {
  const d = new Date(bucket * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:00`
}

function exportCsv() {
  window.location.href = `/api/access/export?${qp({ ...accessParams(), search: detailSearch.value, ip: detailIp.value, path: detailPath.value, format: 'csv' })}`
}

const detailTotalPages = computed(() => Math.max(1, Math.ceil(detail.value.total / pageSize)))
const runtimeTotalPages = computed(() => Math.max(1, Math.ceil(runtime.value.total / 100)))

let off = null
onMounted(async () => {
  await loadServices()
  await Promise.all([loadStats(), loadDetail(), loadRuntime()])
  off = onRealtime((msg) => {
    if (msg.type !== 'logs' || !Array.isArray(msg.items)) return
    const incoming = msg.items.filter((r) => r.instance === store.instance && r.sub_key)
    if (incoming.length) {
      loadStats()
      if (tab.value === 'detail') loadDetail()
    }
  })
})
watch(() => [store.instance, store.from, store.to], () => { page.value = 1; loadServices(); loadStats(); loadDetail(); loadRuntime() })
watch([rule, sub, host, search], () => { page.value = 1; loadStats(); loadDetail() })
</script>

<template>
  <div :class="{ loading }">
    <div class="head">
      <h2>Web 访问分析</h2>
      <div class="tabs">
        <button :class="{ active: tab === 'analytics' }" @click="tab = 'analytics'">访问分析</button>
        <button :class="{ active: tab === 'detail' }" @click="tab = 'detail'">访问明细</button>
        <button :class="{ active: tab === 'runtime' }" @click="tab = 'runtime'">运行日志</button>
      </div>
    </div>

    <div class="filters">
      <select v-model="rule" title="规则">
        <option value="">全部规则</option>
        <option v-for="r in services" :key="r.Key" :value="r.Key">{{ r.Name || r.Key }}</option>
      </select>
      <select v-model="sub" title="子代理">
        <option value="">全部子代理</option>
        <template v-for="r in services" :key="r.Key">
          <option v-for="s in r.SubRuleList || []" :key="s.Key" :value="s.Key">{{ r.Name || r.Key }} / {{ s.Name || s.Key }}</option>
        </template>
      </select>
      <select v-model="host" title="域名">
        <option value="">全部域名</option>
        <option v-for="h in stats?.hosts || []" :key="h.name" :value="h.name">{{ h.name }}</option>
      </select>
      <input v-model="search" placeholder="IP/路径关键词…" @keydown.enter="page = 1; loadStats()">
      <button @click="page = 1; loadStats()">查询</button>
    </div>

    <!-- Tab 1: 访问分析 -->
    <template v-if="tab === 'analytics'">
      <div class="kpis">
        <KpiCard v-for="k in kpis" :key="k.title" v-bind="k" />
      </div>
      <div class="grid">
        <div class="card span2"><h3>访问趋势</h3><div class="wrap"><ChartBox type="line" :labels="trendChart.labels" :datasets="trendChart.datasets" :options="lineOptions()" /></div></div>
        <div class="card"><h3>地区分布</h3><div class="wrap"><ChartBox type="doughnut" :labels="regionChart.labels" :datasets="regionChart.datasets" :options="donutOptions" /></div></div>
        <div class="card"><h3>访问 IP 排行 Top{{ ipChart.labels.length }}</h3><div class="wrap"><ChartBox type="bar" :labels="ipChart.labels" :datasets="ipChart.datasets" :options="barOptions(true)" /></div></div>
        <div class="card"><h3>浏览器分布</h3><div class="wrap"><ChartBox type="doughnut" :labels="browserChart.labels" :datasets="browserChart.datasets" :options="donutOptions" /></div></div>
        <div class="card"><h3>操作系统统计</h3><div class="wrap"><ChartBox type="doughnut" :labels="osChart.labels" :datasets="osChart.datasets" :options="donutOptions" /></div></div>
        <div class="card"><h3>来源类型（设备）</h3><div class="wrap"><ChartBox type="doughnut" :labels="deviceTypeChart.labels" :datasets="deviceTypeChart.datasets" :options="donutOptions" /></div></div>
        <div class="card"><h3>设备型号</h3><div class="wrap"><ChartBox type="bar" :labels="deviceChart.labels" :datasets="deviceChart.datasets" :options="barOptions()" /></div></div>
        <div class="card"><h3>访问路径 Top</h3><div class="wrap"><ChartBox type="bar" :labels="pathChart.labels" :datasets="pathChart.datasets" :options="barOptions(true)" /></div></div>
        <div class="card"><h3>域名 Host 分布</h3><div class="wrap"><ChartBox type="bar" :labels="hostChart.labels" :datasets="hostChart.datasets" :options="barOptions(true)" /></div></div>
        <div class="card"><h3>请求方法</h3><div class="wrap"><ChartBox type="bar" :labels="methodChart.labels" :datasets="methodChart.datasets" :options="barOptions()" /></div></div>
      </div>
    </template>

    <!-- Tab 2: 访问明细 -->
    <template v-else-if="tab === 'detail'">
      <div class="detail-filters">
        <input v-model="detailSearch" placeholder="IP / 路径 / UA 关键词…" @keydown.enter="page = 1; loadDetail()">
        <input v-model="detailIp" placeholder="精确 IP" @keydown.enter="page = 1; loadDetail()">
        <input v-model="detailPath" placeholder="路径包含…" @keydown.enter="page = 1; loadDetail()">
        <button @click="page = 1; loadDetail()">查询</button>
        <button @click="exportCsv()">导出 CSV</button>
      </div>
      <div class="card table-card">
        <LogTable
          :items="detail.items"
          :columns="['time', 'ip', 'method', 'path', 'ua', 'region', 'service']"
        />
        <EmptyState v-if="!detail.items.length" message="无匹配访问日志" />
      </div>
      <div class="foot">
        <span>共 {{ detail.total }} 条</span>
        <div class="pager">
          <button :disabled="page <= 1" @click="page--; loadDetail()">‹</button>
          <span>{{ page }} / {{ detailTotalPages }}</span>
          <button :disabled="page >= detailTotalPages" @click="page++; loadDetail()">›</button>
        </div>
      </div>
    </template>

    <!-- Tab 3: 运行日志 -->
    <template v-else>
      <div class="card table-card">
        <LogTable v-if="runtime.items.length" :items="runtime.items" />
        <EmptyState v-else message="该实例暂无 WebService 规则层运行日志" detail="如 TLS 握手错误等；通常只有少数服务存在" />
      </div>
      <div class="foot">
        <span>共 {{ runtime.total }} 条</span>
        <div class="pager">
          <button :disabled="runtimePage <= 1" @click="runtimePage--; loadRuntime()">‹</button>
          <span>{{ runtimePage }} / {{ runtimeTotalPages }}</span>
          <button :disabled="runtimePage >= runtimeTotalPages" @click="runtimePage++; loadRuntime()">›</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.head h2 { margin: 0; font-size: 16px; }
.tabs { display: flex; gap: 6px; }
.tabs button { padding: 6px 14px; }
.tabs button.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.filters, .detail-filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.kpis { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
.card h3 { margin: 0 0 8px; font-size: 12px; color: var(--muted); font-weight: 600; }
.card .wrap { height: 230px; }
.span2 { grid-column: span 2; }
.table-card { margin-bottom: 12px; }
.table-card :deep(.table-wrap) { height: 460px; }
.foot { display: flex; justify-content: space-between; align-items: center; color: var(--muted); }
.pager { display: flex; gap: 8px; align-items: center; }
</style>
