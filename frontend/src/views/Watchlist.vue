<template>
  <div>
    <h2>自选股追踪</h2>
    <div class="flex-row" style="margin:16px 0;flex-wrap:wrap;gap:8px">
      <input v-model="newCode" placeholder="股票代码，如600519" style="width:160px" @keyup.enter="addStock" />
      <input v-model="newTarget" type="number" step="0.01" placeholder="预期价(可选)" style="width:120px" />
      <input v-model="newStopLoss" type="number" step="0.01" placeholder="止损价(可选)" style="width:120px" />
      <input v-model="newNotes" placeholder="备注(可选)" style="width:160px" />
      <button class="btn btn-primary" @click="addStock">添加追踪</button>
      <button class="btn btn-default" @click="updatePrices">刷新价格</button>
    </div>

    <!-- 活跃持仓统计 -->
    <div class="metric-grid" v-if="store.watchlist && activeItems.length">
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

    <!-- Tab 切换 -->
    <div class="tabs">
      <button :class="['tab', { active: activeTab === 'active' }]" @click="activeTab = 'active'">
        活跃持仓 ({{ activeItems.length }})
      </button>
      <button :class="['tab', { active: activeTab === 'closed' }]" @click="activeTab = 'closed'">
        已结束持仓 ({{ closedItems.length }})
        <span v-if="closedStats.avg_sell_return" class="tab-sub">
          | 均收益率 {{ closedStats.avg_sell_return }}%
        </span>
      </button>
    </div>

    <!-- 活跃持仓表格 -->
    <div class="card" v-if="activeTab === 'active'">
      <table v-if="activeItems.length">
        <thead>
          <tr>
            <th>代码</th><th>名称</th><th>来源</th><th>加入日期</th>
            <th>加入价</th><th>最新价</th><th>神马</th>
            <th>预期价</th><th>止损价</th><th>盈亏比</th>
            <th>卖出价</th>
            <th>累计收益</th><th>持有天数</th>
            <th>最高价</th><th>最低价</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in activeItems" :key="item.id">
            <td>{{ item.code }}</td>
            <td><router-link :to="`/stock/${item.code}`">{{ item.name }}</router-link></td>
            <td><span :style="item.source === '手动' ? 'color:#888' : 'color:#1890ff;font-weight:500'">{{ item.source }}</span></td>
            <td>{{ item.added_date }}</td>
            <td>{{ item.added_price }}</td>
            <td>{{ item.latest_price }}</td>
            <td>
              <span v-if="item.divine_horse" :style="{ color: horseColor(item.divine_horse), fontWeight: 'bold' }">
                {{ item.divine_horse }}
              </span>
            </td>
            <td>
              <input type="number" step="0.01" class="price-input"
                :value="item.target_price"
                @blur="saveField(item, 'target_price', $event.target.value)" />
            </td>
            <td>
              <input type="number" step="0.01" class="price-input"
                :value="item.stop_loss_price"
                @blur="saveField(item, 'stop_loss_price', $event.target.value)" />
            </td>
            <td class="ratio-cell">{{ calcPLRatio(item) }}</td>
            <td>
              <input type="number" step="0.01" class="price-input sell-input"
                :value="item.sell_price"
                @blur="saveSellPrice(item, $event.target.value)" />
            </td>
            <td :class="(item.cumulative_return || 0) >= 0 ? 'positive' : 'negative'"><b>{{ item.cumulative_return != null ? item.cumulative_return : '-' }}%</b></td>
            <td>{{ item.holding_days }}天</td>
            <td>{{ item.highest_price }}</td>
            <td>{{ item.lowest_price }}</td>
            <td><button class="btn btn-danger btn-sm" @click="removeStock(item)">移除</button></td>
          </tr>
        </tbody>
      </table>
      <p v-else style="color:#999;text-align:center;padding:40px">暂无活跃持仓</p>
    </div>

    <!-- 已结束持仓表格 -->
    <div class="card" v-if="activeTab === 'closed'">
      <table v-if="closedItems.length">
        <thead>
          <tr>
            <th>代码</th><th>名称</th><th>来源</th><th>加入日期</th>
            <th>加入价</th><th>卖出价</th><th>卖出收益率</th>
            <th>持有天数</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in closedItems" :key="item.id">
            <td>{{ item.code }}</td>
            <td><router-link :to="`/stock/${item.code}`">{{ item.name }}</router-link></td>
            <td><span :style="item.source === '手动' ? 'color:#888' : 'color:#1890ff;font-weight:500'">{{ item.source }}</span></td>
            <td>{{ item.added_date }}</td>
            <td>{{ item.added_price }}</td>
            <td>{{ item.sell_price }}</td>
            <td :class="(item.sell_return || 0) >= 0 ? 'positive' : 'negative'"><b>{{ item.sell_return != null ? item.sell_return : '-' }}%</b></td>
            <td>{{ item.holding_days }}天</td>
            <td><button class="btn btn-danger btn-sm" @click="removeStock(item)">移除</button></td>
          </tr>
        </tbody>
      </table>
      <p v-else style="color:#999;text-align:center;padding:40px">暂无已结束持仓</p>
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
const newTarget = ref('')
const newStopLoss = ref('')
const loading = ref(false)
const activeTab = ref('active')

const activeItems = computed(() => store.watchlist?.active_items || [])
const closedItems = computed(() => store.watchlist?.closed_items || [])
const closedStats = computed(() => store.watchlist?.closed_stats || {})

function calcPLRatio(item) {
  const { target_price: tp, added_price: ap, stop_loss_price: sl } = item
  if (!tp || !sl || !ap || ap === sl) return '-'
  const ratio = (tp - ap) / (ap - sl)
  return ratio > 0 ? ratio.toFixed(2) : '-'
}

function horseColor(label) {
  const colors = { '特等马': '#cf1322', '一等马': '#faad14', '低等马': '#3f8600' }
  return colors[label] || 'inherit'
}

async function saveField(item, field, rawValue) {
  const val = rawValue === '' ? null : parseFloat(rawValue)
  if (val !== null && isNaN(val)) return
  // 值未变化则跳过
  if (item[field] === val) return
  try {
    await api.updateWatchlistItem(item.id, { [field]: val })
  } catch (e) {
    console.error('保存失败:', e)
  }
  await loadWatchlist()
}

async function saveSellPrice(item, rawValue) {
  const val = rawValue === '' ? null : parseFloat(rawValue)
  if (val !== null && isNaN(val)) return
  if (item.sell_price === val) return
  try {
    await api.updateWatchlistItem(item.id, { sell_price: val })
    // 若设置了卖出价，自动切到已结束Tab
    if (val !== null) activeTab.value = 'closed'
  } catch (e) {
    console.error('保存失败:', e)
  }
  await loadWatchlist()
}

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
  // 如果填写了预期价/止损价，在添加后立即更新
  const wl = store.watchlist?.active_items?.find(i => i.code === newCode.value)
  if (wl && (newTarget.value || newStopLoss.value)) {
    const data = {}
    if (newTarget.value) data.target_price = parseFloat(newTarget.value)
    if (newStopLoss.value) data.stop_loss_price = parseFloat(newStopLoss.value)
    try { await api.updateWatchlistItem(wl.id, data) } catch {}
  }
  newCode.value = ''
  newNotes.value = ''
  newTarget.value = ''
  newStopLoss.value = ''
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

<style scoped>
.tabs {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border-bottom: 2px solid #e8e8e8;
}
.tab {
  padding: 8px 20px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 14px;
  color: #666;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all .2s;
}
.tab:hover { color: #1890ff; }
.tab.active { color: #1890ff; border-bottom-color: #1890ff; font-weight: 600; }
.tab-sub { font-weight: 400; font-size: 12px; color: #999; }

.price-input {
  width: 80px;
  padding: 2px 6px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  text-align: center;
  font-size: 13px;
  background: #fafafa;
  transition: border-color .2s;
}
.price-input:focus {
  outline: none;
  border-color: #1890ff;
  background: #fff;
  box-shadow: 0 0 0 2px rgba(24,144,255,.1);
}
.sell-input {
  border-color: #ffa940;
}
.sell-input:focus {
  border-color: #fa541c;
  box-shadow: 0 0 0 2px rgba(250,84,28,.1);
}
.ratio-cell {
  font-weight: 600;
  color: #722ed1;
  text-align: center;
}
</style>
