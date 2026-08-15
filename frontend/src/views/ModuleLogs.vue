<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, qp } from '../api'
import { store, onRealtime } from '../store'
import { lineOptions, paletteOf } from '../charts'
import ChartBox from '../components/ChartBox.vue'
import LogTable from '../components/LogTable.vue'
import EmptyState from '../components/EmptyState.vue'

const route = useRoute()
const module = computed(() => route.params.module)
const service = ref('')
const search = ref('')
const dedup = ref('time_content')
const page = ref(1)
const pageSize = 200
const data = ref({ total: 0, items: [] })
const services = ref([])
const loading = ref(false)

const baseParams = () => ({
  instance: store.instance,
  module: module.value,
  service: service.value,
  from_epoch: store.from,
  to_epoch: store.to,
  search: search.value,
})

async function loadServices() {
  if (module.value !== 'webservice') return
  const s = await api(`/api/services?instance=${encodeURIComponent(store.instance)}`)
  services.value = s.counts || []
}

async function loadLogs() {
  loading.value = true
  try {
    const p = new URLSearchParams(baseParams())
    p.set('dedup', dedup.value); p.set('page', page.value); p.set('page_size', pageSize)
    const d = await api(`/api/logs?${p}`)
    data.value = d
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  const p = new URLSearchParams(baseParams())
  p.set('granularity', 'hour')
  const s = await api(`/api/stats?${p}`)
  timeline.value = s.timeline || []
}

const timeline = ref([])
const timelineChart = computed(() => ({
  labels: timeline.value.map((b) => `${new Date(b.bucket * 1000).getHours()}:00`),
  datasets: [{ label: '日志数', data: timeline.value.map((b) => b.count), borderColor: '#4f8cff', backgroundColor: 'rgba(79,140,255,.15)', fill: true, tension: .3, pointRadius: 1 }],
}))

const totalPages = computed(() => Math.max(1, Math.ceil(data.value.total / pageSize)))
const modLabel = computed(() => String(module.value))

function exportLogs(fmt) {
  const p = new URLSearchParams(baseParams())
  p.set('dedup', dedup.value); p.set('format', fmt)
  window.location.href = `/api/export?${p}`
}

let off = null
onMounted(async () => {
  await loadServices()
  await Promise.all([loadLogs(), loadStats()])
  off = onRealtime((msg) => {
    if (msg.type !== 'logs' || !Array.isArray(msg.items)) return
    const incoming = msg.items.filter((r) => r.instance === store.instance && r.module === module.value)
    if (incoming.length) {
      data.value.items = [...incoming, ...data.value.items].slice(0, 500)
      loadStats()
    }
  })
})
watch(() => [store.instance, store.from, store.to], () => { page.value = 1; loadLogs(); loadStats(); loadServices() })
watch(service, () => { page.value = 1; loadLogs(); loadStats() })
onBeforeUnmount(() => off && off())
</script>

<template>
  <div :class="{ loading }">
    <div class="head">
      <h2>模块日志 — {{ modLabel }}</h2>
      <div class="filters">
        <select v-if="module === 'webservice'" v-model="service" title="服务">
          <option value="">全部服务</option>
          <option v-for="s in services" :key="s.key" :value="s.key">
            {{ s.parent_name ? s.parent_name + ' / ' : '' }}{{ s.name || s.key }}
            (日志{{ s.logs_count }} · 访问{{ s.access_count }})
          </option>
        </select>
        <select v-model="dedup" title="去重">
          <option value="time_content">去重: 时间+内容</option>
          <option value="content">去重: 内容</option>
          <option value="off">去重: 关闭</option>
        </select>
        <input v-model="search" placeholder="关键词搜索…" @keydown.enter="page = 1; loadLogs()">
        <button @click="page = 1; loadLogs()">查询</button>
        <button @click="exportLogs('csv')">CSV</button>
        <button @click="exportLogs('json')">JSON</button>
      </div>
    </div>
    <div class="card" v-if="timeline.length"><h3>趋势</h3><div class="wrap"><ChartBox type="line" :labels="timelineChart.labels" :datasets="timelineChart.datasets" :options="lineOptions()" /></div></div>
    <div class="card">
      <div class="log-table">
        <LogTable v-if="data.items.length" :items="data.items" />
        <EmptyState v-else message="该模块在此筛选下暂无日志" detail="可能是服务本身为空，或时间范围/服务筛选过于严格" />
      </div>
    </div>
    <div class="foot">
      <span>共 {{ data.total }} 条</span>
      <div class="pager">
        <button :disabled="page <= 1" @click="page--; loadLogs()">‹</button>
        <span>{{ page }} / {{ totalPages }}</span>
        <button :disabled="page >= totalPages" @click="page++; loadLogs()">›</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.head h2 { margin: 0; font-size: 16px; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px; margin-bottom: 12px; }
.card h3 { margin: 0 0 8px; font-size: 12px; color: var(--muted); font-weight: 600; }
.wrap { height: 150px; }
.log-table { height: 420px; display: flex; flex-direction: column; }
.foot { display: flex; justify-content: space-between; align-items: center; color: var(--muted); }
.pager { display: flex; gap: 8px; align-items: center; }
</style>
