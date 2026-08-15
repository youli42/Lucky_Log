<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Chart } from 'chart.js'

const props = defineProps({
  type: { type: String, default: 'bar' },
  labels: { type: Array, default: () => [] },
  datasets: { type: Array, default: () => [] },
  options: { type: Object, default: () => ({}) },
})
const canvas = ref(null)
let chart = null

onMounted(() => {
  chart = new Chart(canvas.value, {
    type: props.type,
    data: { labels: props.labels || [], datasets: props.datasets || [] },
    options: props.options || {},
  })
})
watch(
  () => [props.labels, props.datasets],
  () => {
    if (!chart) return
    chart.data.labels = props.labels || []
    chart.data.datasets = props.datasets || []
    chart.update()
  },
  { deep: true },
)
onBeforeUnmount(() => { if (chart) chart.destroy() })
</script>

<template>
  <canvas ref="canvas"></canvas>
</template>
