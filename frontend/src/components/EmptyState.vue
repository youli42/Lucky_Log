<script setup>
defineProps({
  message: { type: String, default: '暂无数据' },
  detail: { type: String, default: '' },
})
</script>

<template>
  <div class="empty">
    <div>{{ message }}</div>
    <div v-if="detail" class="detail">{{ detail }}</div>
  </div>
</template>

<style scoped>
.empty { padding: 48px; text-align: center; color: var(--muted); }
.detail { margin-top: 8px; color: var(--red); font-size: 12px; }
</style>
