<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { esc } from '../api'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  columnDefs: { type: Array, default: () => [] },
  rowKey: { type: String, default: 'id' },
  expandRaw: { type: Boolean, default: false },
  rowTooltip: { type: Function, default: null },
})
const emit = defineEmits(['row-click'])
const openId = ref(null)
const tip = ref(null)
let timer = null

function onRowEnter(e, row) {
  clearTimeout(timer)
  let html = ''
  if (props.rowTooltip) html += props.rowTooltip(row) || ''
  for (const d of props.columnDefs) {
    if (d.tip) html += d.tip(row) || ''
  }
  if (!html) return
  const rect = e.currentTarget.getBoundingClientRect()
  tip.value = { x: rect.left, y: rect.bottom + 6, html }
}
function onRowLeave() {
  timer = setTimeout(() => { tip.value = null }, 120)
}
function onCellClick(row) {
  if (props.expandRaw) {
    if (openId.value === row[props.rowKey]) openId.value = null
    else openId.value = row[props.rowKey]
  } else {
    emit('row-click', row)
  }
}
onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th v-for="d in columnDefs" :key="d.key">{{ d.label }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in rows" :key="row[rowKey]">
          <tr
            :class="{ expandable: expandRaw, open: expandRaw && openId === row[rowKey] }"
            @mouseenter="onRowEnter($event, row)"
            @mouseleave="onRowLeave"
            @click="onCellClick(row)"
          >
            <td
              v-for="d in columnDefs" :key="d.key" :class="d.cls"
              :title="d.title ? d.title(row) : undefined"
              v-html="d.render ? d.render(row) : ''"
            ></td>
          </tr>
          <tr v-if="expandRaw && openId === row[rowKey] && row.raw" class="detail-row">
            <td :colspan="columnDefs.length"><pre>{{ esc(JSON.stringify(row.raw, null, 2)) }}</pre></td>
          </tr>
        </template>
      </tbody>
    </table>
    <div v-if="!rows.length" class="empty">暂无数据</div>
  </div>
  <Teleport to="body">
    <div v-if="tip" class="rowtip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }" v-html="tip.html"></div>
  </Teleport>
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
tr.expandable { cursor: pointer; }
.ts { white-space: nowrap; color: var(--muted); }
.mono { font-family: Consolas, monospace; white-space: nowrap; max-width: 240px; overflow: hidden; text-overflow: ellipsis; }
.path { max-width: 280px; }
.svc { white-space: nowrap; color: var(--yellow); max-width: 150px; overflow: hidden; text-overflow: ellipsis; }
.detail-row td { background: #121a2b; color: var(--muted); }
.detail-row pre { margin: 0; white-space: pre-wrap; word-break: break-all; font-family: Consolas, monospace; font-size: 11px; }
.empty { padding: 48px; text-align: center; color: var(--muted); }
.rowtip {
  position: fixed; z-index: 9999; max-width: 320px; padding: 8px 10px; border-radius: 8px;
  background: #0d1424; border: 1px solid var(--border); color: var(--text);
  font-size: 12px; line-height: 1.6; pointer-events: none; box-shadow: 0 4px 16px rgba(0,0,0,.4);
}
:global(.rowtip .tip-title) { font-weight: 700; color: var(--accent); margin-bottom: 2px; }
</style>
