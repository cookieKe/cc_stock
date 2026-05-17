<template>
  <div>
    <h2>漏网之鱼</h2>
    <p style="color:#888; font-size:13px; margin:8px 0 16px">
      过去一周出现过KDJ超卖信号(J&lt;13)，涨幅 &gt; 5%，但系统评分 &lt; 80 —— 策略未能捕捉到的机会。
    </p>

    <div class="flex-row" style="margin-bottom:16px">
      <button class="btn btn-primary" @click="loadData" :disabled="loading">
        {{ loading ? '加载中...' : '刷新' }}
      </button>
      <span v-if="tradeDate" style="color:#888; font-size:13px">
        数据日期: {{ tradeDate }}
        <template v-if="scanDate"> | 扫描日期: {{ scanDate }}</template>
        <template v-if="cached">
          | <span style="color:#52c41a; font-weight:600">已缓存</span>
          (至 {{ cacheUntil }})
        </template>
      </span>
      <span v-if="sortedItems.length" style="color:#888; font-size:13px">共 {{ sortedItems.length }} 只</span>
      <button v-if="cached" class="btn btn-default btn-sm" @click="clearCache" style="margin-left:auto">清除缓存</button>
    </div>

    <div v-if="error" class="card" style="background:#fff1f0; border:1px solid #ffa39e; margin-bottom:12px">
      {{ error }}
    </div>

    <div class="card">
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th style="cursor:pointer" @click="toggleSort('code')">代码{{ sortIndicator('code') }}</th>
              <th style="cursor:pointer" @click="toggleSort('name')">名称{{ sortIndicator('name') }}</th>
              <th style="cursor:pointer" @click="toggleSort('score')">系统评分{{ sortIndicator('score') }}</th>
              <th style="cursor:pointer" @click="toggleSort('min_j')">J最低值{{ sortIndicator('min_j') }}</th>
              <th style="cursor:pointer" @click="toggleSort('price_change_pct')">周涨幅{{ sortIndicator('price_change_pct') }}</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sortedItems" :key="item.code">
              <td>{{ item.code }}</td>
              <td><router-link :to="`/stock/${item.code}`">{{ item.name }}</router-link></td>
              <td><b :style="scoreStyle(item.score)">{{ item.score }}</b></td>
              <td>{{ item.min_j }}</td>
              <td class="positive"><b>{{ item.price_change_pct }}%</b></td>
              <td><button class="btn btn-primary btn-sm" @click="addWatch(item.code)">+追踪</button></td>
            </tr>
          </tbody>
        </table>
        <div v-if="sortedItems.length === 0 && !loading" style="text-align:center; padding:20px; color:#999">
          暂无漏网之鱼。请确认已同步K线数据并执行过市场扫描。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const items = ref([])
const loading = ref(false)
const error = ref('')
const scanDate = ref('')
const tradeDate = ref('')
const cached = ref(false)
const cacheUntil = ref('')
const sortKey = ref('')
const sortDir = ref('asc')

const sortedItems = computed(() => {
  if (!sortKey.value) return items.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...items.value].sort((a, b) => {
    const va = a[sortKey.value]
    const vb = b[sortKey.value]
    if (typeof va === 'string') return va.localeCompare(vb) * dir
    return (va - vb) * dir
  })
})

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

function sortIndicator(key) {
  if (sortKey.value !== key) return ' ↕'
  return sortDir.value === 'asc' ? ' ↑' : ' ↓'
}

function scoreStyle(score) {
  if (score < 30) return 'color:#cf1322'
  if (score < 60) return 'color:#fa8c16'
  return 'color:#999'
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.getSlippedFish()
    items.value = data.items || []
    scanDate.value = data.scan_date || ''
    tradeDate.value = data.trade_date || ''
    cached.value = !!data.cached
    cacheUntil.value = data.cache_until ? data.cache_until.replace('T', ' ') : ''
  } catch (e) {
    error.value = '加载失败: ' + (e.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function addWatch(code) {
  try {
    await api.addToWatchlist(code, '', '漏网之鱼')
    alert('已添加到追踪列表')
  } catch (e) {
    alert('添加失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function clearCache() {
  try {
    await api.clearSlippedFishCache()
    cached.value = false
    cacheUntil.value = ''
    await loadData()
  } catch (e) {
    alert('清除缓存失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(loadData)
</script>
