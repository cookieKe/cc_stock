<template>
  <div class="stock-detail">
    <div class="detail-header">
      <h2>{{ stock.name }} ({{ stock.code }})</h2>
      <button class="btn btn-primary btn-sm" @click="addWatch">+ 加入追踪</button>
    </div>

    <div class="card chart-card">
      <div ref="chartRef" class="chart-full"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import api from '../api'

const route = useRoute()
const code = route.params.code
const stock = ref({ code, name: '' })
const chartRef = ref(null)
let chart = null

onMounted(async () => {
  try {
    const detail = await api.getStock(code)
    stock.value = detail.data
  } catch (e) { /* ignore */ }

  const DAYS = 300

  const [klineRes, kdjRes, volRes, deepVRes] = await Promise.allSettled([
    api.getKline(code, DAYS),
    api.getKDJ(code, DAYS),
    api.getVolume(code, DAYS),
    api.getDeepV(code, DAYS),
  ])

  const kline = klineRes.status === 'fulfilled' ? klineRes.value.data : null
  const kdj = kdjRes.status === 'fulfilled' ? kdjRes.value.data : null
  const vol = volRes.status === 'fulfilled' ? volRes.value.data : null
  const deepV = deepVRes.status === 'fulfilled' ? deepVRes.value.data : null

  if (kline && kline.dates) {
    renderChart(kline, kdj, vol, deepV)
  }
})

onBeforeUnmount(() => {
  if (chart) {
    chart.dispose()
    chart = null
  }
  window.removeEventListener('resize', onResize)
})

function onResize() {
  if (chart) chart.resize()
}

function renderChart(kline, kdj, vol, deepV) {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  window.addEventListener('resize', onResize)

  const dates = kline.dates
  const upColor = '#cf1322'
  const downColor = '#3f8600'

  // Volume data with colors
  const volData = (vol && vol.volumes)
    ? vol.volumes.map((v, i) => ({
        value: v,
        itemStyle: { color: (vol.up_flags && vol.up_flags[i]) ? upColor : downColor },
      }))
    : []

  // KDJ mark area / mark line (merged into K series below)

  const option = {
    dataZoom: [
      {
        type: 'slider',
        xAxisIndex: [0, 1, 2, 3],
        bottom: 8,
        height: 22,
        start: 50,
        end: 100,
        borderColor: '#ddd',
        fillerColor: 'rgba(84,112,198,0.12)',
        handleStyle: { color: '#5470c6' },
        textStyle: { fontSize: 10 },
      },
      {
        type: 'inside',
        xAxisIndex: [0, 1, 2, 3],
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
      },
    ],

    grid: [
      { left: '8%', right: '3%', top: 18, height: '38%' },
      { left: '8%', right: '3%', top: '58%', height: '8%' },
      { left: '8%', right: '3%', top: '68%', height: '12%' },
      { left: '8%', right: '3%', top: '82%', height: '14%' },
    ],

    xAxis: [
      { gridIndex: 0, data: dates, axisLabel: { show: false }, axisPointer: { label: { show: true, fontSize: 10 } } },
      { gridIndex: 1, data: vol ? vol.dates : dates, axisLabel: { show: false } },
      { gridIndex: 2, data: kdj ? kdj.dates : dates, axisLabel: { show: false }, axisPointer: { label: { show: true, fontSize: 10 } } },
      { gridIndex: 3, data: deepV ? deepV.dates : dates, axisLabel: { rotate: 0, fontSize: 10 }, axisPointer: { label: { show: true, fontSize: 10 } } },
    ],

    yAxis: [
      { gridIndex: 0, scale: true, splitLine: { lineStyle: { color: '#f0f0f0' } }, axisLabel: { fontSize: 10 } },
      { gridIndex: 1, axisLabel: { fontSize: 9, formatter: v => v >= 1e8 ? (v / 1e8).toFixed(1) + '亿' : (v / 1e4).toFixed(0) + '万' }, splitLine: { show: false } },
      { gridIndex: 2, scale: true, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } }, axisLabel: { fontSize: 10 } },
      { gridIndex: 3, scale: true, splitLine: { lineStyle: { type: 'dashed', color: '#eee' } }, axisLabel: { fontSize: 10 } },
    ],

    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },

    series: [
      // ---- Grid 0: K-line ----
      {
        name: 'K线', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
        data: kline.ohlc,
        itemStyle: { color: upColor, color0: downColor, borderColor: upColor, borderColor0: downColor },
      },

      // ---- Grid 1: Volume ----
      {
        name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volData,
      },
      {
        name: 'VOL MA5', type: 'line', xAxisIndex: 1, yAxisIndex: 1,
        data: vol ? vol.ma5 : [], smooth: true, symbol: 'none',
        lineStyle: { width: 1, color: '#fac858' },
        itemStyle: { color: '#fac858' },
      },
      {
        name: 'VOL MA20', type: 'line', xAxisIndex: 1, yAxisIndex: 1,
        data: vol ? vol.ma20 : [], smooth: true, symbol: 'none',
        lineStyle: { width: 1, color: '#ee6666' },
        itemStyle: { color: '#ee6666' },
      },

      // ---- Grid 2: KDJ ----
      {
        name: 'K', type: 'line', xAxisIndex: 2, yAxisIndex: 2,
        data: kdj ? kdj.k : [], symbol: 'none', connectNulls: true,
        lineStyle: { width: 1.5, color: '#5470c6' },
        itemStyle: { color: '#5470c6' },
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { type: 'dashed', color: '#999' },
          data: [{ yAxis: 20, label: { formatter: '20' } }, { yAxis: 80, label: { formatter: '80' } }],
        },
        markArea: {
          silent: true,
          data: [
            [{ yAxis: 0, itemStyle: { color: 'rgba(63,134,0,0.04)' } }, { yAxis: 20 }],
            [{ yAxis: 80, itemStyle: { color: 'rgba(207,19,34,0.04)' } }, { yAxis: 100 }],
          ],
        },
      },
      {
        name: 'D', type: 'line', xAxisIndex: 2, yAxisIndex: 2,
        data: kdj ? kdj.d : [], symbol: 'none', connectNulls: true,
        lineStyle: { width: 1.5, color: '#91cc75' },
        itemStyle: { color: '#91cc75' },
      },
      {
        name: 'J', type: 'line', xAxisIndex: 2, yAxisIndex: 2,
        data: kdj ? kdj.j : [], symbol: 'none', connectNulls: true,
        lineStyle: { width: 1, color: '#fac858' },
        itemStyle: { color: '#fac858' },
      },

      // ---- Grid 3: Deep V (short + long) ----
      {
        name: '短期(3)', type: 'line', xAxisIndex: 3, yAxisIndex: 3,
        data: deepV ? deepV.short_line : [], symbol: 'none', connectNulls: true,
        lineStyle: { width: 1, color: '#cccccc' },
        itemStyle: { color: '#cccccc' },
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { type: 'dashed', color: '#999' },
          data: [{ yAxis: 20, label: { formatter: '20' } }, { yAxis: 80, label: { formatter: '80' } }],
        },
      },
      {
        name: '长期(21)', type: 'line', xAxisIndex: 3, yAxisIndex: 3,
        data: deepV ? deepV.long_line : [], symbol: 'none', connectNulls: true,
        lineStyle: { width: 2, color: '#cf1322' },
        itemStyle: { color: '#cf1322' },
      },
    ],
  }

  chart.setOption(option)
}

async function addWatch() {
  await api.addToWatchlist(code)
}
</script>

<style scoped>
.stock-detail {
  height: calc(100vh - 120px);
  display: flex;
  flex-direction: column;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.detail-header h2 {
  margin: 0;
}

.chart-card {
  flex: 1;
  min-height: 0;
  padding: 8px;
}

.chart-full {
  width: 100%;
  height: 100%;
  min-height: 500px;
}
</style>
