<script setup>
defineProps({
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: [Number, String], default: 200 }, // 数字或 'all'
  pageCount: { type: Number, default: 1 },
})
const emit = defineEmits(['page-change', 'size-change'])
const SIZES = [16, 32, 64, 128, 256, 512, 1024, 2048, 'all']
</script>

<template>
  <div class="pager">
    <span class="total">共 {{ total }} 条</span>
    <span class="size">每页
      <select :value="String(pageSize)" @change="emit('size-change', $event.target.value)">
        <option v-for="s in SIZES" :key="s" :value="String(s)">{{ s === 'all' ? '全部' : s }}</option>
      </select>
    </span>
    <span v-if="pageSize === 'all'" class="warn">全部显示 · 数据量大可能卡顿</span>
    <div v-if="pageSize !== 'all' && pageCount > 1" class="btns">
      <button :disabled="page <= 1" @click="emit('page-change', page - 1)">‹</button>
      <span>{{ page }} / {{ pageCount }}</span>
      <button :disabled="page >= pageCount" @click="emit('page-change', page + 1)">›</button>
    </div>
  </div>
</template>

<style scoped>
.pager { display: flex; align-items: center; gap: 12px; color: var(--muted); font-size: 12px; }
.size select { padding: 4px 6px; font-size: 12px; }
.warn { color: var(--yellow); font-size: 11px; }
.btns { display: flex; align-items: center; gap: 8px; }
.btns button { padding: 4px 10px; }
</style>
