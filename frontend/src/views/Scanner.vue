<template>
  <div>
    <h2>市场扫描</h2>

    <div class="card market-overview" v-if="marketData">
      <div class="overview-left">
        <div ref="sparkRef" class="sparkline"></div>
      </div>
      <div class="overview-right">
        <div class="index-info">
          <span class="index-label">{{ marketData.index.name }}</span>
          <span class="index-value">{{ marketData.index.latest }}</span>
          <span :class="marketData.index.change_pct >= 0 ? 'positive' : 'negative'">
            {{ marketData.index.change_pct >= 0 ? '+' : '' }}{{ marketData.index.change_pct }}%
          </span>
        </div>
        <div class="cap-info" v-if="marketData.total_market_cap">
          总市值 {{ formatCap(marketData.total_market_cap) }}
        </div>
        <div class="cache-hint" v-if="marketData.cached">
          已缓存 · {{ marketData.trade_date }}
        </div>
      </div>
    </div>

    <div class="flex-row" style="margin:16px 0">
      <select v-model="strategyFilter" @change="onFilterChange">
        <option value="">全部策略</option>
        <option v-for="s in store.strategies" :key="s.name" :value="s.name">{{ s.display_name }}</option>
      </select>
      <button class="btn btn-primary" :disabled="store.scanLoading" @click="runScan">
        {{ store.scanLoading ? '扫描中...' : '执行全市场扫描' }}
      </button>
      <span v-if="store.scanDate" style="color:#888; font-size:13px">扫描日期: {{ store.scanDate }}</span>
    </div>

    <div v-if="store.message" class="card" :style="store.message.type === 'error' ? 'background:#fff1f0; border:1px solid #ffa39e' : 'background:#f6ffed; border:1px solid #b7eb8f'" style="margin-bottom:12px">
      {{ store.message.text }}
      <button class="btn btn-default btn-sm" style="float:right" @click="store.clearMessage">×</button>
    </div>

    <div class="card">
      <h3>排名结果 ({{ store.rankings.length }} / {{ store.rankingsTotal }} 只)</h3>
      <div class="table-scroll" @scroll="onScroll" ref="scrollContainer">
        <table>
          <thead><tr><th>排名</th><th>代码</th><th>名称</th><th>评分</th><th>匹配形态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="r in store.rankings" :key="r.code">
              <td><b>#{{ r.rank }}</b></td>
              <td>{{ r.code }}</td>
              <td><router-link :to="`/stock/${r.code}`">{{ r.name }}</router-link></td>
              <td><b>{{ r.score }}</b></td>
              <td><span :style="r.matched_pattern ? 'color:#1890ff;font-weight:bold' : 'color:#ccc'">{{ r.matched_pattern || '-' }}</span></td>
              <td><button class="btn btn-primary btn-sm" @click="addWatch(r.code)">+追踪</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="loadingMore" style="text-align:center; padding:16px; color:#999">加载中...</div>
        <div v-else-if="store.rankings.length >= store.rankingsTotal && store.rankingsTotal > 0" style="text-align:center; padding:16px; color:#999">已显示全部 {{ store.rankingsTotal }} 条</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, onBeforeUnmount } from 'vue'
import { useStockStore } from '../stores/stock'
import * as echarts from 'echarts'
import api from '../api'

const store = useStockStore()
const strategyFilter = ref('')
const loadingMore = ref(false)
const scrollContainer = ref(null)
const sparkRef = ref(null)
const marketData = ref(null)
let sparkChart = null

async function loadRankings() {
  await store.fetchRankings(strategyFilter.value, true)
}
async function onFilterChange() {
  await loadRankings()
  await nextTick()
  if (scrollContainer.value) scrollContainer.value.scrollTop = 0
}
async function onScroll(e) {
  const el = e.target
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 80 && !loadingMore.value) {
    if (store.rankings.length < store.rankingsTotal) {
      loadingMore.value = true
      await store.loadMoreRankings(strategyFilter.value)
      loadingMore.value = false
    }
  }
}
async function runScan() {
  await store.runScan(strategyFilter.value)
  await loadRankings()
}
async function addWatch(code) {
  await api.addToWatchlist(code)
}
function formatCap(n) {
  if (!n) return '-'
  if (n >= 1e12) return (n / 1e12).toFixed(1) + '万亿'
  return (n / 1e8).toFixed(0) + '亿'
}

async function loadMarketOverview() {
  try {
    const { data } = await api.getMarketOverview()
    marketData.value = data
    await nextTick()
    if (data.index && data.index.dates && data.index.dates.length) {
      renderSparkline(data.index)
    }
  } catch { /* ignore */ }
}

function renderSparkline(index) {
  if (!sparkRef.value) return
  if (sparkChart) sparkChart.dispose()
  sparkChart = echarts.init(sparkRef.value)

  const dates = index.dates
  const closes = index.closes
  const isUp = index.change_pct >= 0
  const lineColor = isUp ? '#cf1322' : '#3f8600'
  const areaColor = isUp ? 'rgba(207,19,34,0.08)' : 'rgba(63,134,0,0.08)'

  sparkChart.setOption({
    grid: { left: 0, right: 0, top: 4, bottom: 0 },
    xAxis: { type: 'category', data: dates, show: false },
    yAxis: { type: 'value', show: false, scale: true },
    series: [{
      type: 'line', data: closes, symbol: 'none',
      lineStyle: { width: 1.5, color: lineColor },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: areaColor },
        { offset: 1, color: 'rgba(255,255,255,0)' },
      ]) },
    }],
  })
}

onMounted(() => {
  loadRankings()
  store.fetchStrategies()
  loadMarketOverview()
})

onBeforeUnmount(() => {
  if (sparkChart) sparkChart.dispose()
})
</script>

<style scoped>
.market-overview {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 12px 16px;
  margin-bottom: 12px;
}

.overview-left {
  flex-shrink: 0;
}

.sparkline {
  width: 320px;
  height: 80px;
}

.overview-right {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.index-info {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.index-label {
  font-size: 13px;
  color: #888;
}

.index-value {
  font-size: 24px;
  font-weight: 700;
}

.cap-info {
  font-size: 13px;
  color: #555;
}

.cache-hint {
  font-size: 11px;
  color: #aaa;
}

.positive {
  font-size: 15px;
  font-weight: 600;
  color: #cf1322;
}

.negative {
  font-size: 15px;
  font-weight: 600;
  color: #3f8600;
}
</style>
