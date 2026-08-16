<script setup>
import { notifications, dismiss } from '../notify'

async function copy(n) {
  const text = n.title ? `${n.title}：${n.message}` : n.message
  try {
    await navigator.clipboard.writeText(text)
    n.copied = true
    setTimeout(() => { n.copied = false }, 1500)
  } catch { /* 剪贴板不可用时静默 */ }
}
</script>

<template>
  <Teleport to="body">
    <div class="toast-host" aria-live="polite">
      <div
        v-for="n in notifications" :key="n.id"
        class="toast" :class="n.type" @click="dismiss(n.id)"
      >
        <div class="t-main">
          <span v-if="n.title" class="t-title">{{ n.title }}</span>
          <span class="t-msg">{{ n.message }}</span>
        </div>
        <div class="t-actions">
          <span class="t-btn" title="复制内容" @click.stop="copy(n)">{{ n.copied ? '已复制' : '复制' }}</span>
          <span class="t-btn" title="关闭" @click.stop="dismiss(n.id)">✕</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-host {
  position: fixed; top: 56px; right: 14px; z-index: 3000;
  display: flex; flex-direction: column; gap: 8px; max-width: 360px;
}
.toast {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
  background: var(--panel); border: 1px solid var(--border); border-left: 3px solid var(--accent);
  border-radius: 8px; padding: 9px 12px; font-size: 12px; color: var(--text);
  box-shadow: 0 4px 16px rgba(0,0,0,.45);
  animation: slide-in .18s ease;
}
.toast.success { border-left-color: var(--green); }
.toast.warn { border-left-color: var(--yellow); }
.toast.error { border-left-color: var(--red); background: #2a1a22; }
.t-main { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.t-title { font-weight: 700; white-space: nowrap; }
.t-msg { color: var(--muted); word-break: break-all; }
.t-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; flex-shrink: 0; }
.t-btn { color: var(--muted); font-size: 11px; padding: 2px 6px; border-radius: 4px; user-select: none; }
.t-btn:hover { color: var(--text); background: var(--panel2); }
@keyframes slide-in { from { transform: translateX(30px); opacity: 0; } to { transform: none; opacity: 1; } }
</style>
