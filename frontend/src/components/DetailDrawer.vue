<script setup>
import { computed } from 'vue'
import { esc, fmtEpoch } from '../api'

const props = defineProps({ item: Object })
const emit = defineEmits(['close'])

const TYPE_LABEL = { mobile: '移动端', desktop: '桌面端', tablet: '平板', bot: '爬虫/机器人' }

function fmtBytes(b) {
  if (b == null) return '—'
  if (b >= 1e9) return (b / 1e9).toFixed(2) + ' GB'
  if (b >= 1e6) return (b / 1e6).toFixed(2) + ' MB'
  if (b >= 1e3) return (b / 1e3).toFixed(1) + ' KB'
  return b + ' B'
}

const sections = computed(() => {
  const it = props.item
  if (!it) return []
  return [
    {
      title: '请求',
      items: [
        ['时间', it.ts_text || '—'],
        ['方法', it.method || '—'],
        ['路径', it.path || '—'],
        ['域名 Host', it.host || '—'],
        ['规则 / 子代理', [it.rule_name, it.sub_name].filter(Boolean).join(' / ') || '—'],
        ['设备类型', TYPE_LABEL[it.device_type] || it.device_type || '—'],
      ],
    },
    {
      title: '访问者',
      items: [
        ['IP', it.client_ip || '—'],
        ['国家', it.country || '—'],
        ['省份', it.province || '—'],
        ['城市', it.city || '—'],
        ['ISP 运营商', it.isp || '—'],
        ['连接数(快照)', it.connections ?? '—'],
        ['流量入', fmtBytes(it.traffic_in)],
        ['流量出', fmtBytes(it.traffic_out)],
        ['最后访问', it.last_access ? fmtEpoch(it.last_access) : '—'],
      ],
    },
    {
      title: '客户端',
      items: [
        ['浏览器', [it.browser, it.browser_version].filter(Boolean).join(' ') || '—'],
        ['操作系统', [it.os, it.os_version].filter(Boolean).join(' ') || '—'],
        ['设备', [it.device_brand, it.device_model || it.device].filter(Boolean).join(' ') || '—'],
      ],
    },
  ]
})

function copyUa() {
  if (props.item?.ua) navigator.clipboard?.writeText(props.item.ua)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="item" class="mask" @click.self="emit('close')">
      <aside class="drawer">
        <header>
          <span>访问详情</span>
          <button class="close" @click="emit('close')">✕</button>
        </header>
        <div class="body">
          <section v-for="s in sections" :key="s.title">
            <h4>{{ s.title }}</h4>
            <dl>
              <template v-for="[k, v] in s.items" :key="k">
                <dt>{{ k }}</dt>
                <dd :class="{ mono: k === 'IP' || k === '路径' || k === '域名 Host' }">{{ v }}</dd>
              </template>
            </dl>
          </section>
          <section>
            <h4>原始 UA <button class="copy" @click="copyUa">复制</button></h4>
            <div class="ua">{{ item.ua || '—' }}</div>
          </section>
        </div>
      </aside>
    </div>
  </Teleport>
</template>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000; }
.drawer {
  position: absolute; top: 0; right: 0; height: 100%; width: 380px; max-width: 92vw;
  background: var(--panel); border-left: 1px solid var(--border);
  display: flex; flex-direction: column; animation: slide .18s ease;
}
@keyframes slide { from { transform: translateX(30px); opacity: 0; } to { transform: none; opacity: 1; } }
header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--border); font-weight: 700;
}
.close { border: none; background: none; font-size: 14px; color: var(--muted); }
.close:hover { color: var(--text); }
.body { flex: 1; overflow-y: auto; padding: 6px 16px 24px; }
section { margin-top: 14px; }
h4 { margin: 0 0 8px; font-size: 12px; color: var(--muted); font-weight: 600; }
dl { margin: 0; display: grid; grid-template-columns: 86px 1fr; gap: 5px 8px; }
dt { color: var(--muted); }
dd { margin: 0; word-break: break-all; }
.mono { font-family: Consolas, monospace; }
.copy { padding: 1px 8px; font-size: 11px; margin-left: 8px; }
.ua {
  background: var(--panel2); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px; font-family: Consolas, monospace; font-size: 11px; word-break: break-all; color: var(--muted);
}
</style>
