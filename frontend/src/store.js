import { reactive } from 'vue'
import { api } from './api'

const ranges = { '1h': 3600, '6h': 6 * 3600, '24h': 24 * 3600, '7d': 7 * 86400 }

export const store = reactive({
  instances: [],
  instance: '',
  timeRange: '24h',
  from: null,
  to: null,
  realtime: false,
  ws: null,
  _listeners: [],
})

export function nowEpoch() {
  return Math.floor(Date.now() / 1000)
}

export async function refreshInstances() {
  const data = await api('/api/instances')
  store.instances = (data.instances || []).filter((i) => i.enabled)
  if (store.instance && !store.instances.some((i) => i.name === store.instance)) {
    store.instance = store.instances[0] ? store.instances[0].name : ''
  }
  if (!store.instances.length) store.instance = ''
}

function applyRange() {
  const now = nowEpoch()
  store.from = now - ranges[store.timeRange]
  store.to = now
}

export function setTimeRange(range, from = null, to = null) {
  store.timeRange = range
  if (range === 'custom') {
    store.from = from
    store.to = to
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
