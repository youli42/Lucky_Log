import { onBeforeUnmount, watch } from 'vue'
import { store } from '../store'

/**
 * 通用数据刷新：实例切换 / 手动刷新 /（可选）时间范围变化时自动重载。
 * 所有功能视图统一接入，避免漏写 watcher。
 *
 * @param {Function} reload 触发时执行的加载函数
 * @param {{ timeRange?: boolean }} opts timeRange=true 时同时监听 store.from/to
 */
export function useDataRefresh(reload, { timeRange = false } = {}) {
  const sources = [() => store.instance, () => store.refreshTick]
  if (timeRange) sources.push(() => store.from, () => store.to)
  const stop = watch(sources, () => reload())
  onBeforeUnmount(stop)
  return stop
}
