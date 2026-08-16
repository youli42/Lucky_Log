<script setup>
import { onMounted, ref } from 'vue'
import { api, fmtEpoch } from '../api'
import { nowEpoch, setTimeRange, store, toggleRealtime, triggerRefresh } from '../store'

const instInfo = ref('')
const ranges = [
  { key: '1h', label: '近1h' },
  { key: '6h', label: '近6h' },
  { key: '24h', label: '近24h' },
  { key: '7d', label: '近7d' },
  { key: 'custom', label: '自定义' },
]

async function loadInstances() {
  const data = await api('/api/instances')
  store.instances = (data.instances || []).filter((i) => i.enabled)
  if (!store.instance && store.instances.length) store.instance = store.instances[0].name
}

function renderInstInfo() {
  const inst = store.instances.find((i) => i.name === store.instance)
  if (!inst) { instInfo.value = ''; return }
  const parts = []
  if (inst.last_collect) parts.push(`最近采集 ${fmtEpoch(inst.last_collect)}`)
  parts.push(`库内 ${inst.total} 条`)
  instInfo.value = inst.last_error
    ? parts.join(' · ') + ` · <span style="color:var(--red)">错误: ${inst.last_error}</span>`
    : parts.join(' · ')
}

function pickRange(r) {
  store.timeRange = r.key
  if (r.key === 'custom') return
  setTimeRange(r.key)
  emit('range-change')
}

function applyCustom() {
  const from = toEpoch(document.getElementById('fromInput').value)
  const to = toEpoch(document.getElementById('toInput').value)
  setTimeRange('custom', from, to)
  emit('range-change')
}

function toEpoch(v) {
  if (!v) return null
  return Math.floor(new Date(v).getTime() / 1000)
}

const emit = defineEmits(['range-change'])
onMounted(async () => {
  await loadInstances()
  if (store.from == null) setTimeRange(store.timeRange)
  renderInstInfo()
})
</script>

<template>
  <header class="topbar">
    <span class="brand">Lucky Log</span>
    <select v-model="store.instance" title="实例">
      <option v-for="i in store.instances" :key="i.name" :value="i.name">{{ i.name }} ({{ i.host }})</option>
    </select>
    <span class="sep"></span>
    <button
      v-for="r in ranges" :key="r.key" class="time-btn"
      :class="{ active: store.timeRange === r.key }"
      @click="pickRange(r)"
    >{{ r.label }}</button>
    <input type="datetime-local" id="fromInput">
    <input type="datetime-local" id="toInput">
    <button id="applyTime" @click="applyCustom">应用</button>
    <span class="sep"></span>
    <button :class="{ on: store.realtime }" class="rt" @click="toggleRealtime()">
      实时: {{ store.realtime ? '开' : '关' }}
    </button>
    <button v-if="!store.realtime" class="refresh" @click="triggerRefresh()">手动刷新</button>
    <span class="info" v-html="instInfo"></span>
  </header>
</template>

<style scoped>
.topbar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 10px 14px; background: var(--panel); border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 10;
}
.brand { font-weight: 700; font-size: 15px; margin-right: 10px; color: var(--accent); }
.sep { width: 1px; height: 22px; background: var(--border); }
.time-btn { padding: 4px 10px; }
.time-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
input[type=datetime-local] { width: 165px; }
.rt.on { border-color: var(--green); }
.info { color: var(--muted); font-size: 12px; margin-left: auto; }
</style>
