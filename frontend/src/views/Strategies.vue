<template>
  <div>
    <h2>策略管理</h2>

    <div class="card">
      <h3>策略列表</h3>
      <table>
        <thead><tr><th>名称</th><th>描述</th><th>权重</th><th>状态</th><th>内置</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="s in store.strategies" :key="s.name">
            <td><b>{{ s.display_name }}</b></td>
            <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">{{ s.description }}</td>
            <td>{{ s.weight }}</td>
            <td><span :style="{color: s.is_enabled ? '#3f8600' : '#999'}">{{ s.is_enabled ? '启用' : '禁用' }}</span></td>
            <td>{{ s.is_builtin ? '是' : '否' }}</td>
            <td>
              <button v-if="s.is_enabled" class="btn btn-default btn-sm" @click="openParamEditor(s)">编辑参数</button>
              <button v-if="s.is_enabled" class="btn btn-default btn-sm" @click="toggleStrategy(s, false)">禁用</button>
              <button v-else class="btn btn-primary btn-sm" @click="enableWithParams(s)">启用</button>
              <button v-if="!s.is_builtin" class="btn btn-danger btn-sm" @click="deleteStrategy(s)">删除</button>
              <button class="btn btn-primary btn-sm" @click="runBacktestFor(s)">回测</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card" v-if="backtestResult">
      <h3>回测结果：{{ backtestName }}</h3>
      <div class="metric-grid">
        <div class="metric-card"><div class="label">累计收益</div><div class="value" :class="(backtestResult.total_return || 0) >= 0 ? 'positive' : 'negative'">{{ backtestResult.total_return }}%</div></div>
        <div class="metric-card"><div class="label">年化收益</div><div class="value">{{ backtestResult.annual_return }}%</div></div>
        <div class="metric-card"><div class="label">夏普比率</div><div class="value">{{ backtestResult.sharpe_ratio }}</div></div>
        <div class="metric-card"><div class="label">最大回撤</div><div class="value negative">{{ backtestResult.max_drawdown }}%</div></div>
        <div class="metric-card"><div class="label">胜率</div><div class="value">{{ backtestResult.win_rate }}%</div></div>
        <div class="metric-card"><div class="label">盈亏比</div><div class="value">{{ backtestResult.profit_loss_ratio }}</div></div>
        <div class="metric-card"><div class="label">超额收益α</div><div class="value" :class="(backtestResult.alpha || 0) >= 0 ? 'positive' : 'negative'">{{ backtestResult.alpha }}%</div></div>
        <div class="metric-card"><div class="label">信息比率</div><div class="value">{{ backtestResult.information_ratio }}</div></div>
      </div>
      <div ref="navRef" style="width:100%;height:350px;margin-top:16px"></div>
    </div>

    <div v-if="showParamModal" class="modal-overlay" @click.self="showParamModal = false">
      <div class="modal-box">
        <h3>编辑参数 — {{ editingStrategy.display_name }}</h3>
        <div v-for="(val, key) in editParams" :key="key" class="param-row">
          <label>{{ key }}</label>
          <input v-if="typeof val === 'number'" v-model.number="editParams[key]" type="number" step="any" />
          <input v-else v-model="editParams[key]" type="text" />
        </div>
        <div class="flex-row" style="justify-content:flex-end; margin-top:16px">
          <button class="btn btn-default" @click="showParamModal = false">取消</button>
          <button class="btn btn-primary" @click="saveParams">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useStockStore } from '../stores/stock'
import api from '../api'

const store = useStockStore()
const backtestResult = ref(null)
const backtestName = ref('')
const navRef = ref(null)

const showParamModal = ref(false)
const editingStrategy = ref({})
const editParams = ref({})

onMounted(() => store.fetchStrategies())

function enableWithParams(s) {
  editingStrategy.value = s
  editParams.value = JSON.parse(JSON.stringify(s.parameters || {}))
  showParamModal.value = true
}

function openParamEditor(s) {
  editingStrategy.value = s
  editParams.value = JSON.parse(JSON.stringify(s.parameters || {}))
  showParamModal.value = true
}

async function saveParams() {
  const s = editingStrategy.value
  if (s.id > 0) {
    await api.updateStrategy(s.id, { parameters: editParams.value })
  } else {
    await api.createStrategy({
      name: s.name,
      display_name: s.display_name,
      description: s.description,
      class_path: s.class_path,
      parameters: editParams.value,
      weight: s.weight,
      is_enabled: true,
    })
  }
  showParamModal.value = false
  store.fetchStrategies()
}

async function toggleStrategy(s, enable) {
  if (s.id > 0) {
    await api.updateStrategy(s.id, { is_enabled: enable })
  }
  store.fetchStrategies()
}

async function deleteStrategy(s) {
  if (s.id > 0) {
    await api.deleteStrategy(s.id)
    store.fetchStrategies()
  }
}

async function runBacktestFor(s) {
  backtestName.value = s.display_name
  backtestResult.value = null
  const res = await api.runBacktest(s.name, {
    start_date: '2024-01-01',
    end_date: '2025-12-31',
    top_n: 10,
  })
  backtestResult.value = res.data
  await nextTick()
  if (res.data?.nav_curve && navRef.value) {
    renderNavChart(res.data)
  }
}

function renderNavChart(data) {
  const chart = echarts.init(navRef.value)
  const dates = data.nav_curve.map(p => p.date)
  const navs = data.nav_curve.map(p => p.nav)
  const series = [{ name: '策略净值', type: 'line', data: navs, smooth: true, lineStyle: { width: 2 } }]
  if (data.benchmark_nav) {
    series.push({ name: '沪深300', type: 'line', data: data.benchmark_nav.map(p => p.nav), smooth: true, lineStyle: { width: 1, type: 'dashed' } })
  }
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '8%', right: '4%', top: 20, bottom: 40 },
    xAxis: { data: dates, axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { scale: true },
    series,
  })
}
</script>
