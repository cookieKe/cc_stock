<template>
  <div>
    <h2>数据汇总</h2>
    <button class="btn btn-primary" style="margin:12px 0" :disabled="loading" @click="loadData">
      {{ loading ? '加载中...' : '刷新数据' }}
    </button>

    <div class="metric-grid" v-if="summary">
      <div class="metric-card">
        <div class="label">股票总数</div>
        <div class="value">{{ summary.stocks?.total || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">活跃股票</div>
        <div class="value">{{ summary.stocks?.active || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">K线总量</div>
        <div class="value">{{ summary.klines?.total_records || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">有K线的股票</div>
        <div class="value">{{ summary.klines?.stocks_with_data || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">K线日期范围</div>
        <div class="value" style="font-size:12px">{{ summary.klines?.date_start || '-' }} ~ {{ summary.klines?.date_end || '-' }}</div>
      </div>
      <div class="metric-card">
        <div class="label">财务数据条数</div>
        <div class="value">{{ summary.financials?.total_records || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">扫描次数</div>
        <div class="value">{{ summary.scans?.scan_count || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">最近扫描日</div>
        <div class="value" style="font-size:14px">{{ summary.scans?.latest || '暂无' }}</div>
      </div>
      <div class="metric-card">
        <div class="label">追踪股票(活跃)</div>
        <div class="value">{{ summary.watchlist?.active || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">启用策略数</div>
        <div class="value">{{ summary.backtests?.enabled_strategies || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">回测记录</div>
        <div class="value">{{ summary.backtests?.total || 0 }}</div>
      </div>
      <div class="metric-card">
        <div class="label">通知(未读/总数)</div>
        <div class="value" style="font-size:14px">{{ summary.notifications?.unread || 0 }} / {{ summary.notifications?.total || 0 }}</div>
      </div>
    </div>

    <!-- 交易所分布 -->
    <div class="card" v-if="summary?.stocks?.exchanges?.length">
      <h3>交易所分布</h3>
      <table>
        <thead><tr><th>交易所</th><th>股票数量</th></tr></thead>
        <tbody>
          <tr v-for="e in summary.stocks.exchanges" :key="e.exchange">
            <td>{{ e.exchange === 'SH' ? '上海' : e.exchange === 'SZ' ? '深圳' : e.exchange }}</td>
            <td>{{ e.count }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 扫描历史 -->
    <div class="card" v-if="summary?.scans?.recent?.length">
      <h3>扫描历史</h3>
      <table>
        <thead><tr><th>扫描日期</th><th>上榜股票数</th><th>记录条数</th></tr></thead>
        <tbody>
          <tr v-for="s in summary.scans.recent" :key="s.date">
            <td>{{ s.date }}</td>
            <td>{{ s.stocks }}</td>
            <td>{{ s.records }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- K线覆盖Top -->
    <div class="card" v-if="summary?.klines?.top_coverage?.length">
      <h3>K线覆盖 Top 30</h3>
      <table>
        <thead><tr><th>股票代码</th><th>K线条数</th><th>最早日期</th><th>最晚日期</th></tr></thead>
        <tbody>
          <tr v-for="k in summary.klines.top_coverage" :key="k.code">
            <td><router-link :to="`/stock/${k.code}`">{{ k.code }}</router-link></td>
            <td>{{ k.records }}</td>
            <td>{{ k.first }}</td>
            <td>{{ k.last }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const summary = ref(null)
const loading = ref(false)

async function loadData() {
  loading.value = true
  try {
    const res = await axios.get('/api/stats/summary')
    summary.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>
