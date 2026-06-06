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
        <button v-if="stock.name" class="btn btn-primary btn-sm" @click="openAiAnalysis">AI 分析</button>
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

function getLimitThreshold(code) {
  if (code.startsWith('30') || code.startsWith('688')) return 19.5
  return 9.5
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

  // Detect 一字涨停 in last ~1 month (22 trading days)
  const limitThreshold = getLimitThreshold(stock.value.code)
  const yiZiZhangTingPoints = []
  const lookback = Math.min(22, kline.ohlc.length - 1)
  const startIdx = kline.ohlc.length - lookback
  for (let i = startIdx; i < kline.ohlc.length; i++) {
    const [o, c, l, h] = kline.ohlc[i]
    if (o === h && h === l && l === c) {
      const prevClose = kline.ohlc[i - 1]?.[1]
      if (prevClose && (c - prevClose) / prevClose * 100 > limitThreshold) {
        yiZiZhangTingPoints.push({
          name: '一字涨停，不要碰',
          coord: [kline.dates[i], h],
          value: '一',
        })
      }
    }
  }

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
          // Extract OHLC: ECharts 5.5 prepends the x-axis index to the value array,
          // turning our [open,close,low,high] into [index,open,close,low,high] (5 elts).
          // Older ECharts versions keep the 4-element array. Handle both.
          const d = first.data
          let raw = null
          if (d && typeof d === 'object') {
            if (!Array.isArray(d) && Array.isArray(d.value)) {
              raw = d.value
            } else if (Array.isArray(d) && d.length >= 4) {
              raw = d
            }
          }
          if (!raw && first.value && Array.isArray(first.value) && first.value.length >= 4) {
            raw = first.value
          }
          if (!raw || raw.length < 4) return ''

          // raw = [open,close,low,high] (4) or [x,open,close,low,high] (5)
          const off = raw.length >= 5 ? 1 : 0
          const o = raw[off], c = raw[off + 1], l = raw[off + 2], h = raw[off + 3]

          const date = first.axisValue

          // changePct: from our original data object
          let changeHtml = ''
          const cp = (d && typeof d === 'object' && !Array.isArray(d) && d.changePct != null)
            ? d.changePct
            : (first.changePct != null ? first.changePct : null)
          if (cp != null) {
            const pct = parseFloat(cp)
            const color = pct >= 0 ? '#cf1322' : '#3f8600'
            const sign = pct >= 0 ? '+' : ''
            changeHtml = `<br/>涨跌: <span style="color:${color};font-weight:bold">${sign}${cp}%</span>`
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
            开: ${o.toFixed(2)} 收: ${c.toFixed(2)} 低: ${l.toFixed(2)} 高: ${h.toFixed(2)}
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
        markPoint: {
          data: yiZiZhangTingPoints,
          symbol: 'rect',
          symbolSize: [24, 22],
          symbolOffset: [0, '-60%'],
          itemStyle: { color: '#cf1322', borderColor: '#cf1322' },
          label: { show: true, color: '#fff', fontSize: 14, fontWeight: 'bold', formatter: '一' },
          tooltip: { trigger: 'item', formatter: '一字涨停，不要碰' },
        },
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

function buildAiPrompt() {
  const s = stock.value
  const finLines = []
  if (s.pe != null) finLines.push(`- 市盈率(PE): ${s.pe}`)
  if (s.pb != null) finLines.push(`- 市净率(PB): ${s.pb}`)
  if (s.roe != null) finLines.push(`- ROE: ${s.roe}%`)
  if (s.revenue_growth != null) finLines.push(`- 营收增长率: ${s.revenue_growth}%`)
  if (s.profit_growth != null) finLines.push(`- 净利润增长率: ${s.profit_growth}%`)
  if (s.market_cap != null) finLines.push(`- 总市值: ${s.market_cap}元`)
  if (s.report_date != null) finLines.push(`- 财务数据截止: ${s.report_date}`)
  const finSection = finLines.length > 0 ? `\n\n【财务数据】\n${finLines.join('\n')}` : ''

  return `你是一位专业的A股投资分析师，请对以下股票进行多维度分析。

【股票信息】
- 名称：${s.name}（${s.code}）
- 行业：${s.industry || '未知'}
- 交易所：${s.exchange}${finSection}

请从以下五个方面给出详细分析：

一、近期趋势分析
分析近期的价格走势特征、成交量变化规律，以及各项技术指标（均线、KDJ等）所反映的趋势信号。判断当前处于上升/下降/震荡区间，以及关键支撑位和压力位。

二、行业分析
分析该股票所属行业（${s.industry || '未知'}）当前的行业景气度、政策环境、产业链位置、竞争格局。该行业是否处于上行周期，政策面是利好还是利空。

三、财报解析
解读该公司的基本面状况，包括盈利能力（ROE）、成长性（营收/利润增长情况）、估值水平（PE、PB、市值）等核心财务指标所反映的公司质地。如有明显亮点或风险点请指出。

四、热点相关性
判断该股票及所属行业是否与当前市场的核心热点（如AI、新能源、半导体、低空经济、中特估、新质生产力等）有关联，契合程度如何，是否具备主题催化条件。

五、综合建议
综合以上分析，给出中短期（1-3个月）的投资建议（推荐买入/持有/观望/规避）以及对应的风险提示。请标注分析中不确定的部分。

注：请基于公开市场信息和客观逻辑进行分析，不做内幕消息的揣测。`
}

function openAiAnalysis() {
  const prompt = buildAiPrompt()
  navigator.clipboard.writeText(prompt).then(() => {
    store.message = { type: 'success', text: '分析提示已复制到剪贴板，正在打开 DeepSeek 对话页面...' }
    window.open('https://chat.deepseek.com', '_blank')
    setTimeout(() => store.clearMessage(), 8000)
  }).catch(() => {
    store.message = { type: 'error', text: '复制失败，正在打开 DeepSeek，请在页面中手动粘贴（Ctrl+V）。' }
    window.open('https://chat.deepseek.com', '_blank')
  })
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
