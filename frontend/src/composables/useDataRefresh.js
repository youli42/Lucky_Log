import { onBeforeUnmount, watch } from 'vue'
import { store } from '../store'
import { notify } from '../notify'

/**
 * 通用数据刷新：实例切换 / 手动刷新 /（可选）时间范围变化时自动重载。
 * 所有功能视图统一接入，避免漏写 watcher。
 *
 * @param {Function} reload 触发时执行的加载函数（可 async）
 * @param {Object} opts
 * @param {boolean} [opts.timeRange=false] true 时同时监听 store.from/to
 * @param {string} [opts.notifyMessage] 刷新完成后弹右上角通知（如手动刷新/切换实例的反馈）
 * @param {'info'|'success'|'warn'|'error'} [opts.notifyType='success']
 * @param {string} [opts.notifyKey] 通知限频键
 * @param {number} [opts.notifyMinInterval=0] 通知限频间隔（毫秒）
 */
export function useDataRefresh(reload, {
  timeRange = false,
  notifyMessage = '',
  notifyType = 'success',
  notifyKey = '',
  notifyMinInterval = 0,
} = {}) {
  const sources = [() => store.instance, () => store.refreshTick]
  if (timeRange) sources.push(() => store.from, () => store.to)
  const stop = watch(sources, async () => {
    await reload()
    if (notifyMessage) {
      notify({ type: notifyType, message: notifyMessage, key: notifyKey, minInterval: notifyMinInterval })
    }
  })
  onBeforeUnmount(stop)
  return stop
}
