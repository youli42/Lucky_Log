<script setup>
import { notifications, dismiss } from '../notify'
</script>

<template>
  <Teleport to="body">
    <div class="toast-host" aria-live="polite">
      <div
        v-for="n in notifications" :key="n.id"
        class="toast" :class="n.type" @click="dismiss(n.id)"
      >
        <span v-if="n.title" class="t-title">{{ n.title }}</span>
        <span class="t-msg">{{ n.message }}</span>
        <span class="t-close" title="关闭">✕</span>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-host {
  position: fixed; top: 56px; right: 14px; z-index: 3000;
  display: flex; flex-direction: column; gap: 8px; max-width: 340px;
}
.toast {
  display: flex; align-items: baseline; gap: 8px; cursor: pointer;
  background: var(--panel); border: 1px solid var(--border); border-left: 3px solid var(--accent);
  border-radius: 8px; padding: 9px 12px; font-size: 12px; color: var(--text);
  box-shadow: 0 4px 16px rgba(0,0,0,.45);
  animation: slide-in .18s ease;
}
.toast.success { border-left-color: var(--green); }
.toast.warn { border-left-color: var(--yellow); }
.toast.error { border-left-color: var(--red); }
.t-title { font-weight: 700; white-space: nowrap; }
.t-msg { color: var(--muted); word-break: break-all; }
.t-close { margin-left: auto; color: var(--muted); font-size: 10px; }
.toast:hover .t-close { color: var(--text); }
@keyframes slide-in { from { transform: translateX(30px); opacity: 0; } to { transform: none; opacity: 1; } }
</style>
