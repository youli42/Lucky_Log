// 全局右上角通知（通用机制，所有模块共用；渲染由 components/ToastHost.vue 负责）。
// 约定（见 AGENTS.md「自动刷新与通知约定」）：
//  - 自动刷新一律静默（不弹窗、不闪烁），仅在数据变化/出错时通知；
//  - 手动刷新 / 事件型反馈用 notify()；禁止自造弹窗/alert。
import { reactive } from 'vue'

export const notifications = reactive([])

let seq = 0
const _lastByKey = {}

/**
 * 弹一条右上角通知。
 * @param {Object} opts
 * @param {'info'|'success'|'warn'|'error'} [opts.type='info']
 * @param {string} [opts.title]
 * @param {string} opts.message
 * @param {number|null} [opts.duration] 自动消失毫秒；默认 error 常驻(0)，其余 3000；0 = 常驻（需手动关闭）
 * @param {string} [opts.key] 限频键：同 key 在 minInterval 内不重复弹
 * @param {number} [opts.minInterval=0] 限频间隔毫秒（需配合 key）
 * @returns {number|null} 通知 id；被限频时返回 null
 */
export function notify({ type = 'info', title = '', message = '', duration = null, key = null, minInterval = 0 } = {}) {
  if (duration == null) duration = type === 'error' ? 0 : 3000
  if (key) {
    const now = Date.now()
    if (now - (_lastByKey[key] || 0) < minInterval) return null
    _lastByKey[key] = now
  }
  const id = ++seq
  notifications.push({ id, type, title, message })
  // 防御：常驻通知堆积时丢弃最旧的
  while (notifications.length > 20) notifications.shift()
  if (duration > 0) {
    setTimeout(() => dismiss(id), duration)
  }
  return id
}

/** 便捷函数：统一报错通知（error 常驻可复制，10s 限频防连发）。 */
export function notifyError(label, err, key = 'err') {
  return notify({
    type: 'error',
    title: label,
    message: (err && err.message) ? err.message : String(err),
    key,
    minInterval: 10000,
  })
}

export function dismiss(id) {
  const i = notifications.findIndex((n) => n.id === id)
  if (i >= 0) notifications.splice(i, 1)
}
