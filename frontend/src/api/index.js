import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export default {
  // Stocks
  listStocks: (params) => api.get('/stocks/', { params }),
  getStock: (code) => api.get(`/stocks/${code}`),
  syncStockList: () => api.post('/stocks/sync/list'),
  syncKline: (code, days) => api.post('/stocks/sync/kline', null, { params: { code, days_back: days || 30 } }),
  syncFinancials: (code) => api.post('/stocks/sync/financials', null, { params: { code } }),
  initData: () => api.post('/stocks/init'),
  syncRecent: (days) => api.post('/stocks/sync/recent', null, { params: { days: days || 2 } }),

  // Charts
  getKline: (code, days) => api.get(`/charts/kline/${code}`, { params: { days } }),
  getKDJ: (code, days) => api.get(`/charts/kdj/${code}`, { params: { days } }),
  getDeepV: (code, days) => api.get(`/charts/deep_v/${code}`, { params: { days } }),
  getVolume: (code, days) => api.get(`/charts/volume/${code}`, { params: { days } }),

  // Strategies
  listStrategies: () => api.get('/strategies/'),
  createStrategy: (data) => api.post('/strategies/', data),
  updateStrategy: (id, data) => api.put(`/strategies/${id}`, data),
  deleteStrategy: (id) => api.delete(`/strategies/${id}`),
  runBacktest: (name, data) => api.post(`/strategies/${name}/backtest`, data),
  getBacktestList: (name) => api.get(`/strategies/${name}/backtest/history`),
  getBacktestDetail: (name, id) => api.get(`/strategies/${name}/backtest/${id}`),

  // Slipped Fish
  getSlippedFish: () => api.get('/slipped-fish/'),
  clearSlippedFishCache: () => api.delete('/slipped-fish/cache'),

  // Scans
  runScan: (strategyName) => api.post('/scans/run', null, { params: { strategy_name: strategyName || '' } }),
  getLatestRanking: (name, limit, offset) => api.get('/scans/latest', { params: { strategy_name: name, limit: limit || 50, offset: offset || 0 } }),
  getDataStatus: () => api.get('/stats/data-status'),
  getMarketOverview: () => api.get('/stats/market-overview'),
  getScanHistory: (code, days) => api.get(`/scans/history/${code}`, { params: { days } }),

  // Watchlist
  getWatchlist: () => api.get('/watchlist/'),
  addToWatchlist: (code, notes) => api.post('/watchlist/', { code, notes }),
  removeFromWatchlist: (id) => api.delete(`/watchlist/${id}`),
  updatePrices: () => api.post('/watchlist/update-prices'),
  getBenchmark: () => api.get('/watchlist/benchmark'),

  // Notifications
  getNotifications: (page) => api.get('/notifications/', { params: { page } }),
  markRead: (id) => api.put(`/notifications/${id}/read`),
  markAllRead: () => api.put('/notifications/read-all'),
}
