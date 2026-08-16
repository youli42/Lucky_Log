<script setup>
defineProps({
  title: String,
  value: [Number, String],
  sub: String,
  accent: { type: String, default: 'var(--accent)' },
  clickable: { type: Boolean, default: false },
})
const emit = defineEmits(['click'])
</script>

<template>
  <div class="kpi" :class="{ clickable }" @click="clickable && emit('click')">
    <div class="title">{{ title }}</div>
    <div class="value" :style="{ color: accent }">{{ value }}</div>
    <div class="sub">{{ sub }}</div>
  </div>
</template>

<style scoped>
.kpi {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 14px 16px; min-width: 140px;
}
.kpi.clickable { cursor: pointer; transition: border-color .15s, transform .1s; }
.kpi.clickable:hover { border-color: var(--accent); transform: translateY(-1px); }
.title { color: var(--muted); font-size: 12px; }
.value { font-size: 26px; font-weight: 700; margin: 4px 0; }
.sub { color: var(--muted); font-size: 11px; }
</style>
