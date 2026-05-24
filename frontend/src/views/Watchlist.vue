<template>
  <div>
    <h2>自选股追踪</h2>
    <div class="flex-row" style="margin:16px 0">
      <input v-model="newCode" placeholder="输入股票代码，如600519" style="width:200px" @keyup.enter="addStock" />
      <input v-model="newNotes" placeholder="备注（可选）" style="width:200px" />
      <button class="btn btn-primary" @click="addStock">添加追踪</button>
      <button class="btn btn-default" @click="updatePrices">刷新价格</button>
    </div>

    <div class="metric-grid" v-if="store.watchlist">
      <div class="metric-card">
        <div class="label">追踪数量</div>
        <div class="value">{{ store.watchlist.count }}</div>
      </div>
      <div class="metric-card">
        <div class="label">平均收益</div>
        <div class="value" :class="(store.watchlist.avg_return || 0) >= 0 ? 'positive' : 'negative'">{{ store.watchlist.avg_return }}%</div>
      </div>
      <div class="metric-card">
        <div class="label">中位数收益</div>
        <div class="value" :class="(store.watchlist.median_return || 0) >= 0 ? 'positive' : 'negative'">{{ store.watchlist.median_return }}%</div>
      </div>
      <div class="metric-card">
        <div class="label">最大收益</div>
        <div class="value" :class="(store.watchlist.max_return || 0) >= 0 ? 'positive' : 'negative'">{{ store.watchlist.max_return }}%</div>
      </div>
      <div class="metric-card">
        <div class="label">最大亏损</div>
        <div class="value negative">{{ store.watchlist.min_return }}%</div>
      </div>
      <div class="metric-card">
        <div class="label">盈利 / 亏损</div>
        <div class="value">{{ store.watchlist.positive_count }} / {{ store.watchlist.negative_count }}</div>
      </div>
    </div>

    <div class="card">
      <h3>追踪列表</h3>
      <table>
        <thead>
          <tr><th>代码</th><th>名称</th><th>来源</th><th>加入日期</th><th>加入价</th><th>最新价</th><th>累计收益</th><th>持有天数</th><th>最高价</th><th>最低价</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.code">
            <td>{{ item.code }}</td>
            <td><router-link :to="`/stock/${item.code}`">{{ item.name }}</router-link></td>
            <td><span :style="item.source === '手动' ? 'color:#888' : 'color:#1890ff;font-weight:500'">{{ item.source }}</span></td>
            <td>{{ item.added_date }}</td>
            <td>{{ item.added_price }}</td>
            <td>{{ item.latest_price }}</td>
            <td :class="(item.cumulative_return || 0) >= 0 ? 'positive' : 'negative'"><b>{{ item.cumulative_return != null ? item.cumulative_return : '-' }}%</b></td>
            <td>{{ item.holding_days }}天</td>
            <td>{{ item.highest_price }}</td>
            <td>{{ item.lowest_price }}</td>
            <td><button class="btn btn-danger btn-sm" @click="removeStock(item)">移除</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useStockStore } from '../stores/stock'
import api from '../api'

const store = useStockStore()
const route = useRoute()
const newCode = ref('')
const newNotes = ref('')
const loading = ref(false)

const items = computed(() => store.watchlist?.items || [])

async function loadWatchlist() {
  loading.value = true
  try {
    await store.fetchWatchlist()
  } finally {
    loading.value = false
  }
}

async function addStock() {
  if (!newCode.value) return
  await api.addToWatchlist(newCode.value, newNotes.value)
  newCode.value = ''
  newNotes.value = ''
  await loadWatchlist()
}
async function removeStock(item) {
  if (item.id) {
    await api.removeFromWatchlist(item.id)
    await loadWatchlist()
  }
}
async function updatePrices() {
  await api.updatePrices()
  await loadWatchlist()
}

onMounted(loadWatchlist)
watch(() => route.path, (to) => { if (to === '/watchlist') loadWatchlist() })
</script>
