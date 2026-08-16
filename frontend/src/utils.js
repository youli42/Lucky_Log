// 前端公共工具（各视图共用，避免重复实现）

/** 字节数格式化。兼容纯数字与带 "B" 后缀的字符串（如 Docker API 返回的 "12.3 MB"）。 */
export function fmtBytes(b) {
  if (b == null) return '—'
  if (typeof b === 'string') {
    const s = b.replace(/\s?B$/, '').trim()
    const n = parseFloat(s)
    if (!isNaN(n)) b = n
    else return b
  }
  if (b >= 1e9) return (b / 1e9).toFixed(2) + ' GB'
  if (b >= 1e6) return (b / 1e6).toFixed(2) + ' MB'
  if (b >= 1e3) return (b / 1e3).toFixed(1) + ' KB'
  return b + ' B'
}

/** 时间桶标签：hour → "HH:00"，day → "M/D"。 */
export function bucketLabel(bucket, granularity = 'hour') {
  const d = new Date(bucket * 1000)
  if (granularity === 'day') return `${d.getMonth() + 1}/${d.getDate()}`
  return `${String(d.getHours()).padStart(2, '0')}:00`
}

/** 按时间范围自动选择趋势粒度：≥3 天用天粒度（避免 7d 下 168 个点挤成一团且无日期）。 */
export function granularityFor(range) {
  return range === '7d' || range === '30d' ? 'day' : 'hour'
}
