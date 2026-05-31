<template>
  <div class="stock-detail">
    <div class="detail-header">
      <div class="header-left">
        <h2>{{ stock.name }} ({{ stock.code }})</h2>
        <div class="header-meta">
          <span v-if="navCodes.length" class="nav-info">{{ currentIndex + 1 }} / {{ navCodes.length }}</span>
          <span v-if="stock.watchlist_added_at" class="watch-added">自选加入: {{ stock.watchlist_added_at }}</span>
        </div>
      </div>
      <div class="header-right">
        <button class="btn btn-default btn-sm" :disabled="!prevCode" @click="goPrev" title="上一个 (←)">◀ 上一个</button>
        <button class="btn btn-default btn-sm" :disabled="!nextCode" @click="goNext" title="下一个 (→)">下一个 ▶</button>
        <button v-if="!showAddForm" class="btn btn-primary btn-sm" :disabled="watching" @click="showAddForm = true">+ 加入追踪</button>
        <div v-else class="add-form-inline">
          <input v-model="addTarget" type="number" step="0.01" placeholder="预期价" class="add-input" @keyup.enter="addWatch" />
          <input v-model="addStopLoss" type="number" step="0.01" placeholder="止损价" class="add-input" @keyup.enter="addWatch" />
          <button class="btn btn-primary btn-sm" :disabled="watching" @click="addWatch">{{ watching ? '加入中...' : '确认' }}</button>
          <button class="btn btn-default btn-sm" @click="showAddForm = false; addTarget = ''; addStopLoss = ''">取消</button>
        </div>
      </div>
    </div>

    <div v-if="store.message" class="card" :style="store.message.type === 'error' ? 'background:#fff1f0; border:1px solid #ffa39e' : 'background:#f6ffed; border:1px solid #b7eb8f'" style="margin-bottom:12px">
      {{ store.message.text }}
      <button class="btn btn-default btn-sm" style="float:right" @click="store.clearMessage">×</button>
    </div>

    <div class="card chart-card">
      <div ref="chartRef" class="chart-full"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onBeforeUnmount, onActivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import api from '../api'
import { useStockStore } from '../stores/stock'

const route = useRoute()
const router = useRouter()
const store = useStockStore()
const stock = ref({ code: '', name: '' })
const chartRef = ref(null)
let chart = null

const navCodes = computed(() => {
  return store.rankings.map(r => r.code)
})

const currentIndex = computed(() => {
  return navCodes.value.indexOf(route.params.code)
})

const prevCode = computed(() => {
  const idx = currentIndex.value
  return idx > 0 ? navCodes.value[idx - 1] : null
})

const nextCode = computed(() => {
  const idx = currentIndex.value
  return idx >= 0 && idx < navCodes.value.length - 1 ? navCodes.value[idx + 1] : null
})

const LOAD_AHEAD = 5  // 距离列表末尾少于这个数时自动加载更多

async function ensureMore() {
  const remaining = store.rankingsTotal - store.rankings.length
  if (remaining > 0 && navCodes.value.length - currentIndex.value <= LOAD_AHEAD) {
    await store.loadMoreRankings()  // 使用 store 记住的策略名
  }
}

function goPrev() {
  if (prevCode.value) router.push(`/stock/${prevCode.value}`)
}

async function goNext() {
  await ensureMore()
  // loadMore 后 nextCode 会更新
  const codes = store.rankings.map(r => r.code)
  const idx = codes.indexOf(route.params.code)
  if (idx >= 0 && idx < codes.length - 1) {
    router.push(`/stock/${codes[idx + 1]}`)
  }
}

function onKeyDown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
  if (e.key === 'ArrowLeft') { e.preventDefault(); goPrev() }
  if (e.key === 'ArrowRight') { e.preventDefault(); goNext() }
}

window.addEventListener('keydown', onKeyDown)

function disposeChart() {
  if (chart) {
    chart.dispose()
    chart = null
  }
  window.removeEventListener('resize', onResize)
}

async function loadStock(newCode) {
  disposeChart()
  stock.value = { code: newCode, name: '' }

  try {
    const detail = await api.getStock(newCode)
    stock.value = detail.data
  } catch (e) { /* ignore */ }

  const DAYS = 300

  const [klineRes, kdjRes, volRes, deepVRes] = await Promise.allSettled([
    api.getKline(newCode, DAYS),
    api.getKDJ(newCode, DAYS),
    api.getVolume(newCode, DAYS),
    api.getDeepV(newCode, DAYS),
  ])

  const kline = klineRes.status === 'fulfilled' ? klineRes.value.data : null
  const kdj = kdjRes.status === 'fulfilled' ? kdjRes.value.data : null
  const vol = volRes.status === 'fulfilled' ? volRes.value.data : null
  const deepV = deepVRes.status === 'fulfilled' ? deepVRes.value.data : null

  if (kline && kline.dates) {
    renderChart(kline, kdj, vol, deepV)
  }
}

watch(() => route.params.code, loadStock, { immediate: true })

onActivated(() => {
  if (chart) chart.resize()
})

onBeforeUnmount(() => {
  disposeChart()
  window.removeEventListener('keydown', onKeyDown)
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

  // OHLC with daily change % for tooltip
  const ohlcData = kline.ohlc.map((d, i) => ({
    value: d,
    changePct: i > 0 ? ((d[1] - kline.ohlc[i - 1][1]) / kline.ohlc[i - 1][1] * 100).toFixed(2) : null,
  }))

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

    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: function (params) {
        if (!params || !params.length) return ''
        const first = params[0]

        // K-line tooltip with OHLC + change % + trend indicators
        if (first.seriesName === 'K线') {
          const d = first.data
          if (!d || !d.value) return ''
          const v = d.value
          const date = first.axisValue
          let changeHtml = ''
          if (d.changePct != null) {
            const c = parseFloat(d.changePct)
            const color = c >= 0 ? '#cf1322' : '#3f8600'
            const sign = c >= 0 ? '+' : ''
            changeHtml = `<br/>涨跌: <span style="color:${color};font-weight:bold">${sign}${d.changePct}%</span>`
          }
          // Extract trend indicator values from params
          const zsShort = params.find(p => p.seriesName === '知行短期(双EMA10)')
          const zsBB = params.find(p => p.seriesName === '知行多空线(BBI)')
          let trendHtml = ''
          if (zsShort && zsShort.data != null) {
            trendHtml += `<br/>知行短期(双EMA10): ${typeof zsShort.data === 'number' ? zsShort.data.toFixed(2) : zsShort.data}`
          }
          if (zsBB && zsBB.data != null) {
            trendHtml += `<br/>知行多空线(BBI): ${typeof zsBB.data === 'number' ? zsBB.data.toFixed(2) : zsBB.data}`
          }
          return `<div style="font-size:12px">
            <b>${date}</b><br/>
            开: ${v[0].toFixed(2)} 收: ${v[1].toFixed(2)} 低: ${v[2].toFixed(2)} 高: ${v[3].toFixed(2)}
            ${changeHtml}${trendHtml}
          </div>`
        }

        // Default tooltip for other series
        let html = `<div style="font-size:12px"><b>${first.axisValue}</b></div>`
        params.forEach(function (p) {
          let val = '-'
          if (p.data != null) {
            if (typeof p.data === 'object' && !Array.isArray(p.data)) {
              val = p.data.value != null ? p.data.value : '-'
            } else {
              val = p.data
            }
            if (typeof val === 'number') val = val.toFixed ? val.toFixed(2) : val
          }
          html += `<div>${p.marker} ${p.seriesName}: ${val}</div>`
        })
        return html
      },
    },

    series: [
      // ---- Grid 0: K-line ----
      {
        name: 'K线', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
        data: ohlcData,
        itemStyle: { color: upColor, color0: downColor, borderColor: upColor, borderColor0: downColor },
      },

      // ---- Grid 0 overlay: Trend indicators ----
      {
        name: '知行短期(双EMA10)', type: 'line', xAxisIndex: 0, yAxisIndex: 0,
        data: kline.zhixng_short || [], symbol: 'none', connectNulls: true,
        lineStyle: { width: 1, color: '#fa8c16' },
        itemStyle: { color: '#fa8c16' },
      },
      {
        name: '知行多空线(BBI)', type: 'line', xAxisIndex: 0, yAxisIndex: 0,
        data: kline.zhixng_bb || [], symbol: 'none', connectNulls: true,
        lineStyle: { width: 1.5, color: '#1890ff' },
        itemStyle: { color: '#1890ff' },
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

const watching = ref(false)
const showAddForm = ref(false)
const addTarget = ref('')
const addStopLoss = ref('')

async function addWatch() {
  watching.value = true
  try {
    const rankEntry = store.rankings.find(r => r.code === route.params.code)
    const source = rankEntry?.strategy_name || '手动'
    const res = await api.addToWatchlist(route.params.code, '', source)
    if (res.data?.error) {
      store.message = { type: 'error', text: res.data.error }
      return
    }
    // 如果填写了预期价/止损价，在添加后立即更新
    if (res.data.id && (addTarget.value || addStopLoss.value)) {
      const data = {}
      if (addTarget.value) data.target_price = parseFloat(addTarget.value)
      if (addStopLoss.value) data.stop_loss_price = parseFloat(addStopLoss.value)
      try { await api.updateWatchlistItem(res.data.id, data) } catch {}
    }
    store.message = { type: 'success', text: `${res.data.name || res.data.code} 已加入追踪` }
    showAddForm.value = false
    addTarget.value = ''
    addStopLoss.value = ''
  } catch (e) {
    store.message = { type: 'error', text: '加入追踪失败: ' + (e.response?.data?.detail || e.message) }
  } finally {
    watching.value = false
  }
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
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.nav-info {
  font-size: 13px;
  color: #999;
  background: #f5f5f5;
  padding: 2px 8px;
  border-radius: 4px;
}

.watch-added {
  font-size: 12px;
  color: #fa8c16;
  background: #fff7e6;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid #ffd591;
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

.add-form-inline {
  display: flex;
  align-items: center;
  gap: 6px;
}

.add-input {
  width: 90px;
  padding: 3px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  font-size: 12px;
}
.add-input:focus {
  outline: none;
  border-color: #1890ff;
  box-shadow: 0 0 0 2px rgba(24,144,255,.1);
}
</style>
