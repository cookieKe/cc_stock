import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useStockStore } from '../stock'

// Mock the API module
vi.mock('../../api', () => ({
  default: {
    getLatestRanking: vi.fn(),
    getWatchlist: vi.fn(),
    getNotifications: vi.fn(),
    listStrategies: vi.fn(),
    listStocks: vi.fn(),
    initData: vi.fn(),
    syncRecent: vi.fn(),
    runScan: vi.fn(),
    getDataStatus: vi.fn(),
    addToWatchlist: vi.fn(),
  },
}))

import api from '../../api'

describe('useStockStore', () => {
  let store

  beforeEach(() => {
    setActivePinia(createPinia())
    store = useStockStore()
    vi.clearAllMocks()
  })

  describe('fetchRankings', () => {
    it('should set rankings from paginated API response', async () => {
      api.getLatestRanking.mockResolvedValue({
        data: {
          items: [
            { rank: 1, code: '000001', name: '平安银行', score: 85.5 },
            { rank: 2, code: '000002', name: '万科A', score: 78.3 },
          ],
          total: 2,
          limit: 50,
          offset: 0,
          scan_date: '2026-05-12',
        },
      })

      await store.fetchRankings('')

      expect(store.rankings).toHaveLength(2)
      expect(store.rankings[0].code).toBe('000001')
      expect(store.rankings[0].score).toBe(85.5)
      expect(store.rankingsTotal).toBe(2)
      expect(store.scanDate).toBe('2026-05-12')
    })

    it('should reset rankings on new fetch', async () => {
      api.getLatestRanking.mockResolvedValue({
        data: { items: [{ rank: 1, code: '000001', name: '平安银行', score: 85.5 }], total: 1, limit: 50, offset: 0 },
      })

      store.rankings = [{ rank: 99, code: 'old', name: 'Old', score: 10 }]
      store.rankingsOffset = 50

      await store.fetchRankings('')

      expect(store.rankings).toHaveLength(1)
      expect(store.rankingsOffset).toBe(50)
    })
  })

  describe('loadMoreRankings', () => {
    it('should append more items to existing rankings', async () => {
      store.rankings = [{ rank: 1, code: '000001', name: '平安银行', score: 85.5 }]
      store.rankingsTotal = 3
      store.rankingsOffset = 50

      api.getLatestRanking.mockResolvedValue({
        data: {
          items: [
            { rank: 51, code: '000002', name: '万科A', score: 78.3 },
            { rank: 101, code: '600000', name: '浦发银行', score: 72.1 },
          ],
          total: 3,
          limit: 50,
          offset: 50,
        },
      })

      await store.loadMoreRankings('')

      expect(store.rankings).toHaveLength(3)
      expect(store.rankingsOffset).toBe(100)
    })

    it('should not load more when all items are loaded', async () => {
      store.rankings = [{ rank: 1, code: '000001', name: '平安银行', score: 85.5 }]
      store.rankingsTotal = 1

      await store.loadMoreRankings('')

      expect(api.getLatestRanking).not.toHaveBeenCalled()
    })
  })

  describe('fetchDataStatus', () => {
    it('should set dataStatus from API', async () => {
      api.getDataStatus.mockResolvedValue({
        data: {
          stock_total: 5515,
          stock_active: 5515,
          kline_total: 4831,
          kline_stocks: 20,
          last_trade_date: '2026-05-11',
          latest_scan_date: '2026-05-12',
          scan_today: true,
        },
      })

      await store.fetchDataStatus()

      expect(store.dataStatus.stock_total).toBe(5515)
      expect(store.dataStatus.scan_today).toBe(true)
    })

    it('should handle API error gracefully', async () => {
      api.getDataStatus.mockRejectedValue(new Error('Network error'))

      await store.fetchDataStatus()

      expect(store.dataStatus).toBeNull()
    })
  })

  describe('syncRecent', () => {
    it('should set syncLoading and update dataStatus on success', async () => {
      api.syncRecent.mockResolvedValue({
        data: { status: 'ok', synced_records: 120, skipped: 5000, failed: 0, elapsed_seconds: 12.5, last_trade_date: '2026-05-12' },
      })
      api.getDataStatus.mockResolvedValue({
        data: { stock_total: 5515, last_trade_date: '2026-05-12' },
      })

      await store.syncRecent(2)

      expect(store.syncLoading).toBe(false)
      expect(store.message.type).toBe('success')
      expect(store.message.text).toContain('120')
      expect(store.message.text).toContain('5000')
      expect(api.syncRecent).toHaveBeenCalledWith(2)
    })

    it('should handle sync failure', async () => {
      api.syncRecent.mockRejectedValue({
        response: { data: { detail: 'Sync failed' } },
      })

      await store.syncRecent(2)

      expect(store.syncLoading).toBe(false)
      expect(store.message.type).toBe('error')
    })
  })

  describe('runScan', () => {
    it('should set scanLoading and show success message', async () => {
      api.runScan.mockResolvedValue({
        data: { total_ranked: 20 },
      })
      api.getDataStatus.mockResolvedValue({
        data: { scan_today: true },
      })

      await store.runScan()

      expect(store.scanLoading).toBe(false)
      expect(store.message.type).toBe('success')
      expect(store.message.text).toContain('20')
    })

    it('should handle scan API error', async () => {
      api.runScan.mockResolvedValue({
        data: { error: '没有启用的策略' },
      })

      await store.runScan()

      expect(store.message.type).toBe('error')
      expect(store.message.text).toContain('没有启用的策略')
    })
  })

  describe('clearMessage', () => {
    it('should clear the message', () => {
      store.message = { type: 'success', text: 'Done' }
      store.clearMessage()
      expect(store.message).toBeNull()
    })
  })
})
