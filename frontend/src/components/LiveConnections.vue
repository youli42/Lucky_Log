<script setup>
import { onMounted, ref } from 'vue'
import { api, esc, fmtEpoch, qp } from '../api'
import { fmtBytes } from '../utils'
import { notifyError } from '../notify'

const props = defineProps({ instance: { type: String, required: true } })
const emit = defineEmits(['close'])

const data = ref(null)
const loading = ref(false)
const error = ref('')
const expanded = ref('')   // 展开的服务 sub_key
const cooldown = ref(0)    // 冷却倒计时（秒）

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api(`/api/access/connections?${qp({ instance: props.instance })}`)
    cooldown.value = 0
  } catch (e) {
    error.value = e.message
    // 429 = 冷却中，局部提示等待（非错误通知）
    const m = String(e.message)
    if (m.includes('429')) cooldown.value = 10
    else notifyError('连接详情加载失败', e, 'live-conn')
  } finally {
    loading.value = false
  }
}

function toggle(key) {
  expanded.value = expanded.value === key ? '' : key
}

function fmtEpochSafe(ts) { return ts ? fmtEpoch(ts) : '—' }

onMounted(load)
</script>

<template>
  <Teleport to="body">
    <div class="mask" @click.self="emit('close')">
      <aside class="drawer">
        <header>
          <span>实时连接详情 — {{ props.instance }}</span>
          <button class="close" @click="emit('close')">✕</button>
        </header>
        <div class="body">
          <div class="toolbar">
            <span class="hint">查看面板时的实时快照 · 每次点击实时拉取</span>
            <button :disabled="loading || cooldown > 0" @click="load">
              {{ loading ? '拉取中…' : (cooldown > 0 ? `冷却中 ${cooldown}s` : '刷新') }}
            </button>
          </div>
          <div v-if="error" class="err">{{ error }}<template v-if="cooldown">（10s 冷却，防频繁请求）</template></div>

          <template v-if="data">
            <div class="kpis">
              <div class="kpi"><div class="title">实时连接</div><div class="value" style="color:var(--accent)">{{ data.total_connections }}</div><div class="sub">当前连接总数</div></div>
              <div class="kpi"><div class="title">在线 IP</div><div class="value" style="color:var(--green)">{{ data.total_ips }}</div><div class="sub">有连接的访问者</div></div>
              <div class="kpi"><div class="title">流量入/出</div><div class="value mono" style="color:var(--yellow)">{{ fmtBytes(data.traffic_in) }}/{{ fmtBytes(data.traffic_out) }}</div><div class="sub">累计 · 快照</div></div>
              <div class="kpi"><div class="title">更新时间</div><div class="value" style="font-size:14px">{{ fmtEpochSafe(data.fetched_at) }}</div><div class="sub">实时拉取时刻</div></div>
            </div>

            <div class="svc" v-for="s in data.services" :key="s.sub_key">
              <div class="svc-head" @click="toggle(s.sub_key)">
                <span class="svc-name">{{ s.rule_name || s.rule_key }}{{ s.sub_name ? ' / ' + s.sub_name : '' }}</span>
                <span class="svc-stat">连接 {{ s.connections }} · IP {{ s.ip_count }} · {{ fmtBytes(s.traffic_in) }}/{{ fmtBytes(s.traffic_out) }}</span>
                <span class="arrow">{{ expanded === s.sub_key ? '▾' : '▸' }}</span>
              </div>
              <table v-if="expanded === s.sub_key" class="t">
                <thead>
                  <tr>
                    <th>访问者 IP</th><th>归属地</th><th>连接</th><th>流量入/出</th><th>最后访问</th><th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="ip in s.ips" :key="ip.client_ip">
                    <td class="mono">{{ esc(ip.client_ip) }}</td>
                    <td>{{ esc(ip.geo_short) }}</td>
                    <td>{{ ip.connections }}</td>
                    <td class="mono">{{ fmtBytes(ip.traffic_in) }}/{{ fmtBytes(ip.traffic_out) }}</td>
                    <td class="mono">{{ fmtEpochSafe(ip.last_access) }}</td>
                    <td>
                      <button class="block" disabled title="一键拉黑功能即将推出">拉黑</button>
                    </td>
                  </tr>
                  <tr v-if="!s.ips.length"><td colspan="6" class="muted">无连接</td></tr>
                </tbody>
              </table>
            </div>

            <div v-if="!data.services.length" class="empty">当前实例无实时连接</div>
          </template>
        </div>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1200; }
.drawer {
  position: absolute; top: 0; right: 0; height: 100%; width: 640px; max-width: 96vw;
  background: var(--panel); border-left: 1px solid var(--border);
  display: flex; flex-direction: column; animation: slide .18s ease;
}
@keyframes slide { from { transform: translateX(40px); opacity: 0; } to { transform: none; opacity: 1; } }
header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--border); font-weight: 700;
}
.close { border: none; background: none; font-size: 14px; color: var(--muted); }
.close:hover { color: var(--text); }
.body { flex: 1; overflow-y: auto; padding: 10px 16px 24px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.hint { color: var(--muted); font-size: 11px; }
.err { color: var(--red); font-size: 12px; margin-bottom: 10px; }
.kpis { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.kpi { background: var(--panel2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; min-width: 120px; flex: 1; }
.kpi .title { color: var(--muted); font-size: 11px; }
.kpi .value { font-size: 18px; font-weight: 700; margin: 3px 0; }
.kpi .value.mono { font-size: 13px; }
.kpi .sub { color: var(--muted); font-size: 10px; }
.svc { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
.svc-head { display: flex; align-items: center; gap: 10px; padding: 9px 12px; cursor: pointer; background: var(--panel2); }
.svc-head:hover { background: #1a2336; }
.svc-name { font-weight: 600; font-size: 12px; }
.svc-stat { color: var(--muted); font-size: 11px; margin-left: auto; }
.arrow { color: var(--muted); }
.t { width: 100%; border-collapse: collapse; font-size: 12px; }
.t th { text-align: left; color: var(--muted); padding: 6px 10px; border-bottom: 1px solid var(--border); font-weight: 600; }
.t td { padding: 6px 10px; border-bottom: 1px solid #1c2540; }
.mono { font-family: Consolas, monospace; }
.muted { color: var(--muted); }
.empty { padding: 32px; text-align: center; color: var(--muted); }
.block { padding: 2px 10px; font-size: 11px; opacity: .55; cursor: not-allowed; }
</style>
