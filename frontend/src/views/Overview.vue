<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { api, esc, qp } from '../api'
import { store, onRealtime } from '../store'
import { PALETTE, donutOptions, lineOptions, barOptions, paletteOf } from '../charts'
import KpiCard from '../components/KpiCard.vue'
import ChartBox from '../components/ChartBox.vue'
import LogTable from '../components/LogTable.vue'
import EmptyState from '../components/EmptyState.vue'

const overview = ref(null)
const access = ref(null)
const logs = ref([])
const logTotal = ref(0)
const inst = ref(null)
const loading = ref(false)

const params = () => ({
  instance: store.instance,
  from_epoch: store.from,
  to_epoch: store.to,
})

const kpis = computed(() => [
  { title: '日志总量', value: overview.value?.total_logs ?? 0, sub: '本地库内全部日志', accent: 'var(--accent)' },
  { title: 'Web 访问', value: overview.value?.access_total ?? 0, sub: '访问日志条数', accent: 'var(--green)' },
  { title: '活跃服务', value: overview.value?.active_services ?? 0, sub: '有日志的服务', accent: 'var(--yellow)' },
  { title: '本地数据', value: overview.value?.db_bytes != null ? fmtBytes(overview.value.db_bytes) : '—', sub: 'SQLite 文件大小', accent: 'var(--red)' },
  { title: '采集状态', value: inst.value?.collecting ? '采集中' : (inst.value?.last_collect ? fmt(inst.value.last_collect) : '—'),
    sub: inst.value?.collecting ? (inst.value.current || '正在采集…') : (inst.value?.last_error || '运行正常'),
    accent: inst.value?.collecting ? 'var(--yellow)' : (inst.value?.last_error ? 'var(--red)' : 'var(--green)') },
])
function fmt(ts) {
  const d = new Date(ts * 1000); const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function fmtBytes(b) {
  if (b == null) return '—'
  if (b >= 1e9) return (b / 1e9).toFixed(2) + ' GB'
  if (b >= 1e6) return (b / 1e6).toFixed(2) + ' MB'
  if (b >= 1e3) return (b / 1e3).toFixed(1) + ' KB'
  return b + ' B'
}

const moduleChart = computed(() => {
  const rows = overview.value?.by_module || []
  return {
    labels: rows.map((r) => r.module),
    datasets: [{ data: rows.map((r) => r.count), backgroundColor: paletteOf(rows.length) }],
  }
})
const timelineChart = computed(() => {
  const rows = overview.value?.timeline || []
  return {
    labels: rows.map((r) => bucketLabel(r.bucket)),
    datasets: [{ label: '日志数', data: rows.map((r) => r.count), borderColor: '#4f8cff', backgroundColor: 'rgba(79,140,255,.15)', fill: true, tension: .3, pointRadius: 1 }],
  }
})
const accessChart = computed(() => {
  const rows = access.value?.timeline || []
  return {
    labels: rows.map((r) => bucketLabel(r.bucket)),
    datasets: [{ label: '访问', data: rows.map((r) => r.count), borderColor: '#3ddc84', backgroundColor: 'rgba(61,220,132,.15)', fill: true, tension: .3, pointRadius: 1 }],
  }
})
const serviceChart = computed(() => {
  const rows = (overview.value?.by_service || []).slice(0, 10)
  return {
    labels: rows.map((r) => r.rule_name || '(全部)'),
    datasets: [{ label: '条数', data: rows.map((r) => r.count), backgroundColor: paletteOf(rows.length) }],
  }
})
function bucketLabel(bucket) {
  const d = new Date(bucket * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:00`
}

const logColDefs = [
  { key: 'time', label: '时间', cls: 'ts', render: (r) => esc(r.ts_text) },
  { key: 'module', label: '模块', render: (r) => `<span class="tag">${esc(r.module)}</span>` },
  { key: 'svc', label: '服务', render: (r) => esc(r.rule_name || r.sub_name || '—') },
  { key: 'content', label: '内容', render: (r) => esc(r.content) },
]

async function loadAll() {
  loading.value = true
  try {
    const [ov, ac, instData] = await Promise.all([
      api(`/api/overview?${qp(params())}`),
      api(`/api/access/stats?${qp(params())}`),
      api('/api/instances'),
    ])
    overview.value = ov
    access.value = ac
    inst.value = (instData.instances || []).find((i) => i.name === store.instance)
    await loadLogs(true)
  } finally {
    loading.value = false
  }
}

async function loadLogs(reset) {
  const p = new URLSearchParams(qp(params()))
  p.set('page', 1); p.set('page_size', 50); p.set('dedup', 'off')
  const data = await api(`/api/logs?${p}`)
  logTotal.value = data.total
  if (reset) logs.value = data.items
  else logs.value = data.items
}

let off = null
onMounted(() => {
  loadAll()
  off = onRealtime((msg) => {
    if (msg.type !== 'logs' || !Array.isArray(msg.items)) return
    const incoming = msg.items.filter((r) => !store.instance || r.instance === store.instance)
    if (incoming.length) {
      logs.value = [...incoming, ...logs.value].slice(0, 200)
      loadAll()
    }
  })
})
watch(() => [store.instance, store.from, store.to], loadAll)
onBeforeUnmount(() => off && off())
</script>

<template>
  <div :class="{ loading }">
    <div class="kpis">
      <KpiCard v-for="k in kpis" :key="k.title" v-bind="k" />
    </div>
    <div class="grid">
      <div class="card"><h3>模块分布</h3><div class="wrap"><ChartBox type="doughnut" :labels="moduleChart.labels" :datasets="moduleChart.datasets" :options="donutOptions" /></div></div>
      <div class="card"><h3>日志趋势（按小时）</h3><div class="wrap"><ChartBox type="line" :labels="timelineChart.labels" :datasets="timelineChart.datasets" :options="lineOptions()" /></div></div>
      <div class="card"><h3>Web 访问趋势</h3><div class="wrap"><ChartBox type="line" :labels="accessChart.labels" :datasets="accessChart.datasets" :options="lineOptions()" /></div></div>
      <div class="card"><h3>服务分布</h3><div class="wrap"><ChartBox type="bar" :labels="serviceChart.labels" :datasets="serviceChart.datasets" :options="barOptions(true)" /></div></div>
    </div>
    <div class="card logs-card">
      <h3>最近日志 <span class="total">共 {{ logTotal }} 条</span></h3>
      <div class="log-table">
        <LogTable v-if="logs.length" :rows="logs" :column-defs="logColDefs" row-key="id" expand-raw />
        <EmptyState v-else message="暂无日志" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.kpis { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; margin-bottom: 14px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
.card h3 { margin: 0 0 8px; font-size: 12px; color: var(--muted); font-weight: 600; }
.card .wrap { height: 220px; }
.logs-card .total { color: var(--muted); font-weight: 400; margin-left: 8px; }
.log-table { height: 320px; display: flex; flex-direction: column; }
</style>
