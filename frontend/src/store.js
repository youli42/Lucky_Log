import { reactive } from 'vue'
import { api } from './api'

const ranges = { '1h': 3600, '6h': 6 * 3600, '24h': 24 * 3600, '7d': 7 * 86400 }

export const store = reactive({
  instances: [],
  instance: '',
  timeRange: '24h',
  from: null,
  to: null,
  rangeSpan: null,   // 当前时间范围跨度（秒）；custom 时由用户输入计算，用于趋势粒度选择
  realtime: false,
  ws: null,
  refreshTick: 0,
  refreshInterval: 10,   // 面板统一自动刷新间隔（秒，0=关闭），来自 config.refresh_interval
  _listeners: [],
})

export function triggerRefresh() {
  store.refreshTick += 1
}

export async function loadGlobalConfig() {
  try {
    const data = await api('/api/config')
    store.refreshInterval = data.config.refresh_interval ?? 10
  } catch { /* ignore */ }
}

export function nowEpoch() {
  return Math.floor(Date.now() / 1000)
}

export async function refreshInstances() {
  const data = await api('/api/instances')
  store.instances = (data.instances || []).filter((i) => i.enabled)
  if (!store.instances.some((i) => i.name === store.instance)) {
    store.instance = store.instances[0] ? store.instances[0].name : ''
  }
}

function applyRange() {
  const now = nowEpoch()
  store.from = now - ranges[store.timeRange]
  store.to = now
  store.rangeSpan = ranges[store.timeRange] || null
}

export function setTimeRange(range, from = null, to = null) {
  store.timeRange = range
  if (range === 'custom') {
    store.from = from
    store.to = to
    store.rangeSpan = to && from ? to - from : null
  } else {
    applyRange()
  }
}

export function onRealtime(cb) {
  store._listeners.push(cb)
  return () => {
    store._listeners = store._listeners.filter((f) => f !== cb)
  }
}

export function toggleRealtime() {
  store.realtime = !store.realtime
  if (store.realtime) connectWS()
  else if (store.ws) store.ws.close()
}

function connectWS() {
  if (store.ws && (store.ws.readyState === WebSocket.OPEN || store.ws.readyState === WebSocket.CONNECTING)) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/stream`)
  store.ws = ws
  ws.onmessage = (e) => {
    try {
      const m = JSON.parse(e.data)
      store._listeners.forEach((f) => f(m))
    } catch { /* ignore */ }
  }
  ws.onclose = () => {
    if (store.realtime) setTimeout(connectWS, 2000)
  }
}
