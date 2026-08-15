<script setup>
import { ref } from 'vue'
import { esc } from '../api'

const props = defineProps({
  items: { type: Array, default: () => [] },
  columns: { type: Array, default: () => ['time', 'module', 'service', 'content'] },
  keyField: { type: String, default: 'id' },
})
const openId = ref(null)

function toggle(row) {
  if (openId.value === row[props.keyField]) openId.value = null
  else openId.value = row[props.keyField]
}
</script>

<template>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th v-if="columns.includes('time')">时间</th>
          <th v-if="columns.includes('module')">模块</th>
          <th v-if="columns.includes('service')">服务</th>
          <th v-if="columns.includes('ip')">IP</th>
          <th v-if="columns.includes('method')">方法</th>
          <th v-if="columns.includes('path')">路径</th>
          <th v-if="columns.includes('ua')">UA</th>
          <th v-if="columns.includes('region')">归属地</th>
          <th v-if="columns.includes('content')">内容</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in items" :key="row[keyField]">
          <tr :class="{ open: openId === row[keyField] }">
            <td v-if="columns.includes('time')" class="ts">{{ row.ts_text || row.time }}</td>
            <td v-if="columns.includes('module')"><span class="tag">{{ row.module }}</span></td>
            <td v-if="columns.includes('service')" class="svc">{{ row.rule_name || row.sub_name || '—' }}</td>
            <td v-if="columns.includes('ip')" class="mono">{{ row.client_ip }}</td>
            <td v-if="columns.includes('method')"><span class="tag">{{ row.method }}</span></td>
            <td v-if="columns.includes('path')" class="mono path">{{ row.path }}</td>
            <td v-if="columns.includes('ua')" class="mono" :title="row.ua">{{ row.browser }} {{ row.os }} {{ row.device }}</td>
            <td v-if="columns.includes('region')" class="mono">{{ row.region }}</td>
            <td v-if="columns.includes('content')" class="content" @click="toggle(row)">{{ row.content }}</td>
          </tr>
          <tr v-if="openId === row[keyField] && row.raw" class="detail-row">
            <td :colspan="columns.length + 1"><pre>{{ esc(JSON.stringify(row.raw, null, 2)) }}</pre></td>
          </tr>
        </template>
      </tbody>
    </table>
    <div v-if="!items.length" class="empty">暂无数据</div>
  </div>
</template>

<style scoped>
.table-wrap { flex: 1; overflow: auto; min-height: 0; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
thead th {
  position: sticky; top: 0; background: var(--panel2); color: var(--muted);
  text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--border); font-weight: 600; white-space: nowrap;
}
tbody td { padding: 6px 10px; border-bottom: 1px solid #1c2540; vertical-align: top; }
tr:hover { background: #1a2336; }
tr.open td { background: #1c2742; }
.ts { white-space: nowrap; color: var(--muted); }
.svc { white-space: nowrap; color: var(--yellow); max-width: 150px; overflow: hidden; text-overflow: ellipsis; }
.mono { font-family: Consolas, monospace; white-space: nowrap; max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
.path { max-width: 260px; }
.content { cursor: pointer; word-break: break-all; }
.detail-row td { background: #121a2b; color: var(--muted); }
.detail-row pre { margin: 0; white-space: pre-wrap; word-break: break-all; font-family: Consolas, monospace; font-size: 11px; }
</style>
