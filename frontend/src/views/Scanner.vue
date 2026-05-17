<template>
  <div>
    <h2>市场扫描</h2>

    <div class="card market-overview" v-if="marketData">
      <div class="overview-charts">
        <div v-for="(idx, i) in marketData.indices" :key="idx.code" class="index-panel">
          <div :ref="el => sparkRefs[i] = el" class="sparkline"></div>
          <div class="index-info">
            <span class="index-label">{{ idx.name }}</span>
            <span class="index-value">{{ idx.latest ?? '-' }}</span>
            <span v-if="idx.change_pct != null" :class="idx.change_pct >= 0 ? 'positive' : 'negative'">
              {{ idx.change_pct >= 0 ? '+' : '' }}{{ idx.change_pct }}%
            </span>
          </div>
        </div>
        <div v-if="marketData.active_market_cap" class="index-panel">
          <div :ref="el => sparkRefs[2] = el" class="sparkline"></div>
          <div class="index-info">
            <span class="index-label">{{ marketData.active_market_cap.name }}</span>
            <span class="index-value">{{ marketData.active_market_cap.latest ?? '-' }}</span>
            <span v-if="marketData.active_market_cap.change_pct != null"
                  :class="marketData.active_market_cap.change_pct >= 0 ? 'positive' : 'negative'">
              {{ marketData.active_market_cap.change_pct >= 0 ? '+' : '' }}{{ marketData.active_market_cap.change_pct }}%
            </span>
          </div>
        </div>
      </div>
      <div class="overview-footer">
        <span class="cap-info" v-if="marketData.total_market_cap">
          总市值 {{ formatCap(marketData.total_market_cap) }}
        </span>
        <span class="cap-info" v-else style="color:#ccc">总市值数据获取中...</span>
        <span class="cache-hint" v-if="marketData.cached">已缓存 · {{ marketData.trade_date }}</span>
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
const sparkRefs = ref([])
const marketData = ref(null)
const sparkCharts = []

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
  const src = strategyFilter.value || '全市场扫描'
  await api.addToWatchlist(code, '', src)
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
    if (data.indices) {
      data.indices.forEach((idx, i) => {
        if (idx.dates && idx.dates.length) renderSparkline(i, idx)
      })
    }
    // 活跃市值作为第3个面板
    const amv = data.active_market_cap
    if (amv && amv.dates && amv.dates.length) renderSparkline(2, amv)
  } catch { /* ignore */ }
}

function renderSparkline(i, item) {
  const el = sparkRefs.value[i]
  if (!el) return
  if (sparkCharts[i]) sparkCharts[i].dispose()
  sparkCharts[i] = echarts.init(el)

  const dates = item.dates
  const values = item.closes || item.values
  const isUp = (item.change_pct ?? 0) >= 0
  const lineColor = isUp ? '#cf1322' : '#3f8600'
  const areaColor = isUp ? 'rgba(207,19,34,0.06)' : 'rgba(63,134,0,0.06)'

  sparkCharts[i].setOption({
    grid: { left: 0, right: 42, top: 6, bottom: 0 },
    xAxis: { type: 'category', data: dates, show: false },
    yAxis: {
      type: 'value', scale: true, splitNumber: 3,
      axisLabel: { fontSize: 9, color: '#999', formatter: v => v >= 1000 ? (v / 1000).toFixed(1) + 'k' : v },
      splitLine: { lineStyle: { type: 'dashed', color: '#f0f0f0' } },
    },
    series: [{
      type: 'line', data: values, symbol: 'none',
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
  sparkCharts.forEach(c => c.dispose())
})
</script>

<style scoped>
.market-overview {
  padding: 12px 16px;
  margin-bottom: 12px;
}

.overview-charts {
  display: flex;
  gap: 32px;
}

.index-panel {
  flex: 1;
  min-width: 0;
}

.sparkline {
  width: 100%;
  height: 80px;
}

.index-info {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 4px;
}

.index-label {
  font-size: 12px;
  color: #888;
}

.index-value {
  font-size: 20px;
  font-weight: 700;
}

.overview-footer {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
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
  font-size: 14px;
  font-weight: 600;
  color: #cf1322;
}

.negative {
  font-size: 14px;
  font-weight: 600;
  color: #3f8600;
}
</style>
