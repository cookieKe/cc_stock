<template>
  <div>
    <h2>{{ stock.name }} ({{ stock.code }})</h2>
    <div class="flex-row" style="margin:12px 0">
      <button class="btn btn-primary" @click="addWatch">+ 加入追踪</button>
    </div>

    <div class="card"><h3>K线图</h3><div ref="klineRef" class="chart-box"></div></div>
    <div class="card"><h3>KDJ 指标</h3><div ref="kdjRef" class="chart-box"></div></div>
    <div class="card"><h3>成交量</h3><div ref="volRef" class="chart-box"></div></div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import api from '../api'

const route = useRoute()
const code = route.params.code
const stock = ref({ code, name: '' })
const klineRef = ref(null)
const kdjRef = ref(null)
const volRef = ref(null)

onMounted(async () => {
  try {
    const detail = await api.getStock(code)
    stock.value = detail.data
  } catch (e) { /* ignore */ }

  try {
    const kline = await api.getKline(code, 300)
    renderKline(kline.data)
  } catch (e) { /* ignore */ }

  try {
    const kdj = await api.getKDJ(code, 120)
    renderKDJ(kdj.data)
  } catch (e) { /* ignore */ }

  try {
    const vol = await api.getVolume(code, 120)
    renderVolume(vol.data)
  } catch (e) { /* ignore */ }
})

function renderKline(data) {
  if (!klineRef.value || !data.dates) return
  const chart = echarts.init(klineRef.value)
  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: { left: '8%', right: '4%', top: 20, bottom: 40 },
    xAxis: { data: data.dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { scale: true },
    series: [
      { name: 'K线', type: 'candlestick', data: data.ohlc, itemStyle: { color: '#cf1322', color0: '#3f8600', borderColor: '#cf1322', borderColor0: '#3f8600' } },
      { name: 'MA5', type: 'line', data: data.ma5, smooth: true, lineStyle: { width: 1 }, symbol: 'none' },
      { name: 'MA10', type: 'line', data: data.ma10, smooth: true, lineStyle: { width: 1 }, symbol: 'none' },
      { name: 'MA20', type: 'line', data: data.ma20, smooth: true, lineStyle: { width: 1 }, symbol: 'none' },
      { name: 'MA60', type: 'line', data: data.ma60, smooth: true, lineStyle: { width: 1 }, symbol: 'none' },
    ],
  })
}

function renderKDJ(data) {
  if (!kdjRef.value || !data.dates) return
  const chart = echarts.init(kdjRef.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '4%', top: 30, bottom: 40 },
    xAxis: { data: data.dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { min: 0, max: 100, splitLine: { lineStyle: { type: 'dashed' } } },
    series: [
      { name: 'K', type: 'line', data: data.k, lineStyle: { width: 1.5, color: '#5470c6' }, symbol: 'none' },
      { name: 'D', type: 'line', data: data.d, lineStyle: { width: 1.5, color: '#91cc75' }, symbol: 'none' },
      { name: 'J', type: 'line', data: data.j, lineStyle: { width: 1, color: '#fac858' }, symbol: 'none' },
      {
        type: 'line', markLine: {
          silent: true, symbol: 'none',
          lineStyle: { type: 'dashed', color: '#999' },
          data: [
            { yAxis: 20, label: { formatter: '超卖 20' } },
            { yAxis: 80, label: { formatter: '超买 80' } },
          ],
        },
        markArea: {
          silent: true,
          data: [
            [{ yAxis: 0, itemStyle: { color: 'rgba(63,134,0,0.05)' } }, { yAxis: 20 }],
            [{ yAxis: 80, itemStyle: { color: 'rgba(207,19,34,0.05)' } }, { yAxis: 100 }],
          ],
        },
        data: [],
      },
    ],
  })
}

function renderVolume(data) {
  if (!volRef.value || !data.dates) return
  const chart = echarts.init(volRef.value)
  const upColor = '#cf1322'
  const downColor = '#3f8600'
  const volumeData = data.volumes.map((v, i) => ({
    value: v,
    itemStyle: { color: (data.up_flags && data.up_flags[i]) ? upColor : downColor },
  }))
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '4%', top: 20, bottom: 40 },
    xAxis: { data: data.dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: {},
    series: [
      { name: '成交量', type: 'bar', data: volumeData },
      { name: 'MA5', type: 'line', data: data.ma5, smooth: true, symbol: 'none', lineStyle: { color: '#fac858' } },
      { name: 'MA20', type: 'line', data: data.ma20, smooth: true, symbol: 'none', lineStyle: { color: '#ee6666' } },
    ],
  })
}

async function addWatch() {
  await api.addToWatchlist(code)
}
</script>
