import { defineStore } from 'pinia'
import api from '../api'

export const useStockStore = defineStore('stock', {
  state: () => ({
    rankings: [],
    rankingsTotal: 0,
    rankingsOffset: 0,
    rankingsLimit: 50,
    scanDate: '',
    dataStatus: null,
    watchlist: null,
    notifications: [],
    strategies: [],
    stockCount: null,
    initLoading: false,
    scanLoading: false,
    syncLoading: false,
    message: null,
  }),
  actions: {
    async fetchRankings(strategyName, reset = true) {
      if (reset) {
        this.rankingsOffset = 0
        this.rankings = []
        this.rankingsTotal = 0
      }
      const res = await api.getLatestRanking(
        strategyName || '',
        this.rankingsLimit,
        this.rankingsOffset
      )
      const data = res.data
      if (data && data.items) {
        this.rankings = reset ? data.items : [...this.rankings, ...data.items]
        this.rankingsTotal = data.total
        this.scanDate = data.scan_date
        this.rankingsOffset += this.rankingsLimit
      }
    },
    async loadMoreRankings(strategyName) {
      if (this.rankings.length >= this.rankingsTotal) return
      const res = await api.getLatestRanking(
        strategyName || '',
        this.rankingsLimit,
        this.rankingsOffset
      )
      const data = res.data
      if (data && data.items) {
        this.rankings = [...this.rankings, ...data.items]
        this.rankingsTotal = data.total
        this.rankingsOffset += this.rankingsLimit
      }
    },
    async fetchDataStatus() {
      try {
        const res = await api.getDataStatus()
        this.dataStatus = res.data
      } catch {
        this.dataStatus = null
      }
    },
    async fetchWatchlist() {
      const res = await api.getWatchlist()
      this.watchlist = res.data
    },
    async fetchNotifications(page) {
      const res = await api.getNotifications(page || 1)
      this.notifications = res.data?.items || []
    },
    async fetchStrategies() {
      const res = await api.listStrategies()
      this.strategies = Array.isArray(res.data) ? res.data : []
    },
    async fetchStockCount() {
      try {
        const res = await api.listStocks({ page_size: 1 })
        this.stockCount = res.data?.total ?? 0
      } catch {
        this.stockCount = null
      }
    },
    async initData() {
      this.initLoading = true
      this.message = null
      try {
        const res = await api.initData()
        if (res.data?.error) {
          this.message = { type: 'error', text: '初始化失败: ' + res.data.error }
        } else {
          await this.fetchStockCount()
          await this.fetchDataStatus()
          this.message = { type: 'success', text: res.data?.message || '初始化完成' }
        }
      } catch (e) {
        this.message = { type: 'error', text: '初始化失败: ' + (e.response?.data?.detail || e.message) }
      } finally {
        this.initLoading = false
      }
    },
    async syncRecent(days) {
      this.syncLoading = true
      this.message = null
      try {
        const res = await api.syncRecent(days || 2)
        if (res.data?.error) {
          this.message = { type: 'error', text: res.data.error }
        } else {
          await this.fetchDataStatus()
          const d = res.data
          this.message = { type: 'success', text: `同步完成：${d.synced_records} 条新记录，跳过 ${d.skipped} 只已最新，失败 ${d.failed} 只，耗时 ${d.elapsed_seconds}s` }
        }
      } catch (e) {
        this.message = { type: 'error', text: '同步失败: ' + (e.response?.data?.detail || e.message) }
      } finally {
        this.syncLoading = false
      }
    },
    async runScan(strategyName) {
      this.scanLoading = true
      this.message = null
      try {
        const res = await api.runScan(strategyName)
        if (res.data?.error) {
          this.message = { type: 'error', text: res.data.error }
        } else {
          await this.fetchDataStatus()
          this.message = { type: 'success', text: `扫描完成，共 ${res.data.total_ranked} 只股票` }
        }
      } catch (e) {
        this.message = { type: 'error', text: '扫描失败: ' + (e.response?.data?.detail || e.message) }
      } finally {
        this.scanLoading = false
      }
    },
    clearMessage() {
      this.message = null
    },
  },
})
