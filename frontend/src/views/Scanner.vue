<template>
  <div>
    <h2>市场扫描</h2>

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
          <thead><tr><th>排名</th><th>代码</th><th>名称</th><th>评分</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="r in store.rankings" :key="r.code">
              <td><b>#{{ r.rank }}</b></td>
              <td>{{ r.code }}</td>
              <td><router-link :to="`/stock/${r.code}`">{{ r.name }}</router-link></td>
              <td><b>{{ r.score }}</b></td>
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
import { ref, onMounted, nextTick } from 'vue'
import { useStockStore } from '../stores/stock'
import api from '../api'

const store = useStockStore()
const strategyFilter = ref('')
const loadingMore = ref(false)
const scrollContainer = ref(null)

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
  await store.runScan()
  await loadRankings()
}
async function addWatch(code) {
  await api.addToWatchlist(code)
}
onMounted(() => {
  loadRankings()
  store.fetchStrategies()
})
</script>
