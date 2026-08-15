import { Chart, registerables } from 'chart.js'
Chart.register(...registerables)

export const PALETTE = [
  '#4f8cff', '#3ddc84', '#f5c542', '#ff7a7a', '#b06cff', '#42c6c6',
  '#ff9d3c', '#e061cb', '#7be382', '#5ab2ff', '#ffd166', '#c77bff',
]

export const TICK = { color: '#8494b5' }

export const donutOptions = {
  plugins: {
    legend: { position: 'right', labels: { color: '#8494b5', boxWidth: 10, font: { size: 10 } } },
  },
  maintainAspectRatio: false,
}

export function barOptions(horizontal = false) {
  return {
    indexAxis: horizontal ? 'y' : 'x',
    plugins: { legend: { display: false } },
    scales: {
      x: horizontal ? { ticks: { color: '#8494b5' } } : { ticks: { color: '#8494b5', maxRotation: 45 } },
      y: horizontal ? { ticks: { color: '#8494b5', maxRotation: 0 } } : { ticks: { color: '#8494b5' } },
    },
    maintainAspectRatio: false,
  }
}

export function lineOptions() {
  return {
    plugins: { legend: { display: false } },
    scales: { x: { ticks: { ...TICK, maxTicksLimit: 12, maxRotation: 0 } }, y: { ticks: TICK } },
    maintainAspectRatio: false,
  }
}

export const paletteOf = (n) => Array.from({ length: n }, (_, i) => PALETTE[i % PALETTE.length])
