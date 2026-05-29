<template>
  <div>
    <h2>仪表盘</h2>

    <!-- 数据为空提示 -->
    <div v-if="store.stockCount === 0" class="card" style="background:#fffbe6; border:1px solid #ffe58f; margin-bottom:16px">
      <div style="display:flex; align-items:center; justify-content:space-between">
        <div><b>数据为空</b> — 首次使用需要先同步股票数据</div>
        <button class="btn btn-primary" :disabled="store.initLoading" @click="initData">
          {{ store.initLoading ? '初始化中...' : '一键初始化' }}
        </button>
      </div>
    </div>

    <!-- 数据状态卡片 -->
    <div class="metric-grid" style="margin-bottom:16px" v-if="store.dataStatus">
      <div class="metric-card">
        <div class="label">活跃股票</div>
        <div class="value">{{ store.dataStatus.stock_active }}</div>
      </div>
      <div class="metric-card">
        <div class="label">K线数据量</div>
        <div class="value">{{ store.dataStatus.kline_total?.toLocaleString() }}</div>
      </div>
      <div class="metric-card">
        <div class="label">最新数据日期</div>
        <div class="value" style="font-size:18px">{{ store.dataStatus.last_trade_date || '-' }}</div>
      </div>
      <div class="metric-card">
        <div class="label">今日扫描</div>
        <div class="value" :class="store.dataStatus.scan_today ? 'positive' : ''">
          {{ store.dataStatus.scan_today ? '✅ 已完成' : '❌ 未扫描' }}
        </div>
      </div>
    </div>

    <!-- 快捷操作 -->
    <div class="flex-row" style="margin-bottom:16px">
      <button class="btn btn-primary" :disabled="store.syncLoading" @click="syncData">
        {{ store.syncLoading ? '同步中...' : '📡 同步最新数据' }}
      </button>
      <button class="btn btn-primary" :disabled="store.scanLoading" @click="runScan">
        {{ store.scanLoading ? '扫描中...' : '🔍 执行市场扫描' }}
      </button>
      <button class="btn btn-default" @click="loadAll">刷新</button>
    </div>

    <!-- 消息提示 -->
    <div v-if="store.message" class="card" :style="store.message.type === 'error' ? 'background:#fff1f0; border:1px solid #ffa39e' : 'background:#f6ffed; border:1px solid #b7eb8f'" style="margin-bottom:12px">
      {{ store.message.text }}
      <button class="btn btn-default btn-sm" style="float:right" @click="store.clearMessage">×</button>
    </div>

    <!-- 自选追踪概览 -->
    <div class="card" style="margin-bottom:16px" v-if="store.watchlist">
      <div class="flex-between" style="margin-bottom:12px">
        <h3>⭐ 自选追踪概览</h3>
        <router-link to="/watchlist">查看详情 →</router-link>
      </div>
      <div class="metric-grid">
        <div class="metric-card">
          <div class="label">追踪股票</div>
          <div class="value">{{ store.watchlist.count || 0 }}</div>
        </div>
        <div class="metric-card">
          <div class="label">平均累计收益</div>
          <div class="value" :class="(store.watchlist.avg_return||0) >= 0 ? 'positive' : 'negative'">{{ store.watchlist.avg_return || 0 }}%</div>
        </div>
        <div class="metric-card">
          <div class="label">盈利占比</div>
          <div class="value">{{ store.watchlist.positive_ratio || 0 }}%</div>
        </div>
        <div class="metric-card">
          <div class="label">今日平均涨跌</div>
          <div class="value" :class="(store.watchlist.today_avg_change||0) >= 0 ? 'positive' : 'negative'">{{ store.watchlist.today_avg_change || 0 }}%</div>
        </div>
      </div>
    </div>

    <!-- Top 5 排名速览 -->
    <div class="card">
      <div class="flex-between" style="margin-bottom:12px">
        <h3>🏆 最新排名 Top 5</h3>
        <router-link to="/scanner">查看全部排名 ({{ store.rankingsTotal }} 只) →</router-link>
      </div>
      <table v-if="store.rankings.length > 0">
        <thead>
          <tr><th>排名</th><th>代码</th><th>名称</th><th>综合评分</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in store.rankings.slice(0,5)" :key="r.code">
            <td><b>#{{ r.rank }}</b></td>
            <td>{{ r.code }}</td>
            <td><router-link :to="`/stock/${r.code}`">{{ r.name }}</router-link></td>
            <td><b>{{ r.score }}</b></td>
            <td><button class="btn btn-primary btn-sm" @click="addWatch(r)">+追踪</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else style="color:#999; text-align:center; padding:20px">暂无排名数据，请先执行市场扫描</div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useStockStore } from '../stores/stock'
import api from '../api'

const store = useStockStore()

async function loadAll() {
  await Promise.all([
    store.fetchDataStatus(),
    store.fetchRankings(''),
    store.fetchWatchlist(),
    store.fetchStrategies(),
    store.fetchStockCount(),
  ])
}
async function initData() {
  await store.initData()
  await store.fetchRankings('')
  await store.fetchWatchlist()
  await store.fetchStrategies()
}
async function syncData() {
  await store.syncRecent()
  await store.fetchRankings('')
}
async function runScan() {
  await store.runScan()
  await store.fetchRankings('')
  await store.fetchWatchlist()
}
async function addWatch(item) {
  await api.addToWatchlist(item.code, '', item.strategy_name || '全市场扫描')
  await store.fetchWatchlist()
}
onMounted(loadAll)
</script>
